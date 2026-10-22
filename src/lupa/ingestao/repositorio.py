"""Persistência da ingestão: job, lease com fencing token, lotes idempotentes e diagnóstico.

Todo instante vem do chamador (`agora`), nunca do `now()` do banco, para que a expiração do
lease seja testável e não dependa do início da transação.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lupa.dominio.enums import (
    EstadoJob,
    EstadoLote,
    MotivoFalha,
    MotivoQuarentena,
    StatusProcesso,
)
from lupa.dominio.esquemas import DiagnosticoArquivo, calcular_hash
from lupa.dominio.tabelas import (
    DiagnosticoArquivoTabela,
    JobIngestaoTabela,
    LoteIngestaoTabela,
    PaginaTabela,
    ProcessoTabela,
)
from lupa.ingestao.estados import ESTADOS_FINAIS, exigir_transicao
from lupa.ingestao.qualidade import resumo_saneamento

Job = JobIngestaoTabela
ESTADOS_COM_FIM = ESTADOS_FINAIS | {EstadoJob.FALHO, EstadoJob.VALIDADO, EstadoJob.PARCIAL}
ESTADOS_EM_ANDAMENTO = (EstadoJob.RECEBIDO, EstadoJob.VALIDADO, EstadoJob.EM_EXTRACAO)
ESPERA_JOB_CEDIDO = timedelta(minutes=10)


class LeasePerdidoError(RuntimeError):
    """O worker não tem mais o lease corrente do job (outro worker assumiu)."""


@dataclass(frozen=True)
class Lease:
    """Posse temporária de um job por um worker.

    Attributes:
        job_id: Job.
        gabinete_id: Gabinete do job.
        dono: Identificador opaco do worker.
        token: Fencing token; cresce a cada aquisição.
        tentativa: Número da tentativa (1 na primeira).
    """

    job_id: UUID
    gabinete_id: UUID
    dono: str
    token: int
    tentativa: int


def criar_job(session: Session, gabinete_id: UUID, processo_id: UUID, arquivo_id: UUID) -> Job:
    """Cria o job do arquivo no estado `recebido`.

    Args:
        session: Sessão com transação aberta.
        gabinete_id: Gabinete do processo.
        processo_id: Processo.
        arquivo_id: Arquivo recebido.

    Returns:
        O job criado.
    """
    job = Job(
        id=uuid4(),
        gabinete_id=gabinete_id,
        processo_id=processo_id,
        arquivo_id=arquivo_id,
        estado=EstadoJob.RECEBIDO.value,
        tentativas=0,
        fencing_token=0,
    )
    session.add(job)
    session.flush()
    return job


def obter_job_por_arquivo(session: Session, arquivo_id: UUID) -> Job | None:
    """Busca o job de um arquivo.

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        O job, ou None.
    """
    return session.scalar(select(Job).where(Job.arquivo_id == arquivo_id))


def adquirir_lease(
    session: Session, job_id: UUID, dono: str, agora: datetime, duracao: timedelta
) -> Lease | None:
    """Toma o job se ele não estiver com lease válido nem em estado final.

    Args:
        session: Sessão com transação aberta.
        job_id: Job.
        dono: Identificador do worker.
        agora: Instante de referência.
        duracao: Validade do lease.

    Returns:
        O lease com o novo fencing token, ou None se o job estiver ocupado ou finalizado.
    """
    finais = [estado.value for estado in ESTADOS_FINAIS]
    linha = session.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.estado.not_in(finais),
            or_(Job.lease_expira_em.is_(None), Job.lease_expira_em <= agora),
        )
        .values(
            fencing_token=Job.fencing_token + 1,
            tentativas=Job.tentativas + 1,
            lease_dono=dono,
            lease_expira_em=agora + duracao,
            heartbeat_em=agora,
            iniciado_em=agora,
        )
        .returning(Job.fencing_token, Job.gabinete_id, Job.tentativas)
    ).first()
    if linha is None:
        return None
    return Lease(job_id, linha.gabinete_id, dono, linha.fencing_token, linha.tentativas)


def _travar_job(session: Session, lease: Lease) -> Job:
    job = session.scalar(
        select(Job)
        .where(Job.id == lease.job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None or job.fencing_token != lease.token:
        raise LeasePerdidoError(str(lease.job_id))
    return job


def renovar_lease(session: Session, lease: Lease, agora: datetime, duracao: timedelta) -> None:
    """Heartbeat: estende o lease se o token ainda for o corrente.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        agora: Instante de referência.
        duracao: Nova validade a partir de `agora`.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    job = _travar_job(session, lease)
    job.heartbeat_em = agora
    job.lease_expira_em = agora + duracao
    session.flush()


def liberar_lease(session: Session, lease: Lease) -> None:
    """Solta o lease (fim normal do processamento).

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    job = _travar_job(session, lease)
    job.lease_dono = None
    job.lease_expira_em = None
    session.flush()


def mudar_estado(
    session: Session,
    lease: Lease,
    novo: EstadoJob,
    agora: datetime,
    *,
    motivo_quarentena: MotivoQuarentena | None = None,
    motivo_falha: MotivoFalha | None = None,
) -> Job:
    """Muda o estado do job conferindo o fencing token e a máquina de estados.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        novo: Estado de destino.
        agora: Instante de referência (vira `finalizado_em` ao fim de uma fase).
        motivo_quarentena: Obrigatório quando `novo` é `quarentena`.
        motivo_falha: Motivo quando `novo` é `falho`.

    Returns:
        O job atualizado.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
        TransicaoInvalidaError: Se a transição não for permitida.
    """
    job = _travar_job(session, lease)
    exigir_transicao(EstadoJob(job.estado), novo)
    job.estado = novo.value
    job.motivo_quarentena = motivo_quarentena.value if motivo_quarentena else None
    job.motivo_falha = motivo_falha.value if motivo_falha else None
    if novo in ESTADOS_COM_FIM:
        job.finalizado_em = agora
    session.flush()
    return job


def registrar_resultado(
    session: Session,
    lease: Lease,
    *,
    total_paginas: int,
    manifesto: list[dict[str, Any]],
) -> None:
    """Grava total de páginas e manifesto no job.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        total_paginas: Soma das páginas das entradas.
        manifesto: Entradas ordenadas (ver `EntradaManifesto`).

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    job = _travar_job(session, lease)
    job.total_paginas = total_paginas
    job.manifesto = manifesto
    session.flush()


def gravar_lote(
    session: Session,
    lease: Lease,
    numero: int,
    estado: EstadoLote,
    resultado: dict[str, Any],
) -> bool:
    """Grava o resultado de um lote uma única vez, só com o fencing token corrente.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        numero: Número do lote (1, 2, ...).
        estado: Estado do lote.
        resultado: Resultado serializável em JSON (sem texto dos autos).

    Returns:
        Verdadeiro se gravou; falso se o lote já existia (reprocessamento).

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    _travar_job(session, lease)
    inserido = session.execute(
        insert(LoteIngestaoTabela)
        .values(
            id=uuid4(),
            gabinete_id=lease.gabinete_id,
            job_id=lease.job_id,
            numero=numero,
            estado=estado.value,
            fencing_token=lease.token,
            resultado=resultado,
        )
        .on_conflict_do_nothing(index_elements=["job_id", "numero"])
        .returning(LoteIngestaoTabela.id)
    ).first()
    return inserido is not None


def lotes_do_job(session: Session, job_id: UUID) -> dict[int, LoteIngestaoTabela]:
    """Lotes já gravados do job, por número.

    Args:
        session: Sessão com transação aberta.
        job_id: Job.

    Returns:
        Mapa número → lote.
    """
    linhas = session.scalars(select(LoteIngestaoTabela).where(LoteIngestaoTabela.job_id == job_id))
    return {linha.numero: linha for linha in linhas}


def jobs_recuperaveis(
    session: Session, agora: datetime, espera: timedelta
) -> list[tuple[UUID, UUID]]:
    """Jobs em andamento parados: lease vencido, ou sem lease há tempo demais.

    `recebido` sem lease conta depois de `espera` desde a criação; `validado` e `em_extracao`
    sem lease (job que cedeu a vez e cuja mensagem se perdeu) contam depois de 10 minutos sem
    heartbeat. Usado pelo varredor; exige contexto de administrador (lê todos os gabinetes).

    Args:
        session: Sessão com transação aberta.
        agora: Instante de referência.
        espera: Idade mínima de um job `recebido` nunca tomado.

    Returns:
        Pares `(job_id, gabinete_id)`.
    """
    sem_lease = Job.lease_expira_em.is_(None)
    consulta = select(Job.id, Job.gabinete_id).where(
        Job.estado.in_([e.value for e in ESTADOS_EM_ANDAMENTO]),
        or_(
            Job.lease_expira_em <= agora,
            and_(
                sem_lease,
                Job.estado == EstadoJob.RECEBIDO.value,
                Job.criado_em <= agora - espera,
            ),
            and_(
                sem_lease,
                Job.estado != EstadoJob.RECEBIDO.value,
                Job.heartbeat_em <= agora - ESPERA_JOB_CEDIDO,
            ),
        ),
    )
    return [(linha.id, linha.gabinete_id) for linha in session.execute(consulta)]


def salvar_diagnostico(
    session: Session, gabinete_id: UUID, diagnostico: DiagnosticoArquivo
) -> None:
    """Grava (ou substitui) o diagnóstico do arquivo.

    Args:
        session: Sessão com transação aberta.
        gabinete_id: Gabinete do arquivo.
        diagnostico: Diagnóstico calculado.
    """
    dados = diagnostico.model_dump(mode="json") | {"gabinete_id": str(gabinete_id)}
    atualizaveis = (
        "cenario", "total_paginas", "tem_indice", "sinais", "fronteiras_origem",
        "metadados_descartados",
    )  # fmt: skip
    session.execute(
        insert(DiagnosticoArquivoTabela)
        .values(dados)
        .on_conflict_do_update(
            index_elements=["arquivo_id"], set_={campo: dados[campo] for campo in atualizaveis}
        )
    )


def obter_diagnostico(session: Session, arquivo_id: UUID) -> DiagnosticoArquivo | None:
    """Lê o diagnóstico do arquivo.

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        O diagnóstico, ou None.
    """
    linha = session.scalar(
        select(DiagnosticoArquivoTabela).where(DiagnosticoArquivoTabela.arquivo_id == arquivo_id)
    )
    if linha is None:
        return None
    return DiagnosticoArquivo(
        id=linha.id,
        arquivo_id=linha.arquivo_id,
        cenario=linha.cenario,
        total_paginas=linha.total_paginas,
        tem_indice=linha.tem_indice,
        sinais=linha.sinais,
        fronteiras_origem=linha.fronteiras_origem,
        metadados_descartados=linha.metadados_descartados,
        criado_em=linha.criado_em,
    )


def ceder_vez(session: Session, lease: Lease) -> None:
    """Solta o lease sem contar tentativa: o job cedeu a vez a outros (fatia concluída).

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    job = _travar_job(session, lease)
    job.lease_dono = None
    job.lease_expira_em = None
    job.tentativas = max(0, job.tentativas - 1)
    session.flush()


def descartar_lotes_falhos(session: Session, lease: Lease) -> int:
    """Apaga os lotes de validação que falharam, para a nova tentativa refazê-los.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.

    Returns:
        Quantidade apagada.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    _travar_job(session, lease)
    resultado = session.execute(
        delete(LoteIngestaoTabela)
        .where(
            LoteIngestaoTabela.job_id == lease.job_id,
            LoteIngestaoTabela.estado == EstadoLote.FALHO.value,
        )
        .returning(LoteIngestaoTabela.id)
    )
    return len(resultado.all())


def paginas_prontas(session: Session, arquivo_id: UUID, versao_extrator: str) -> set[int]:
    """Números das páginas do arquivo já gravadas pela versão do extrator.

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.
        versao_extrator: Versão corrente.

    Returns:
        Números de página.
    """
    consulta = select(PaginaTabela.numero).where(
        PaginaTabela.arquivo_id == arquivo_id,
        PaginaTabela.versao_extrator == versao_extrator,
    )
    return set(session.scalars(consulta))


def gravar_paginas(
    session: Session, lease: Lease, arquivo_id: UUID, paginas: list[dict[str, Any]]
) -> int:
    """Grava (ou substitui) páginas do arquivo, só com o fencing token corrente.

    Idempotente por `(arquivo_id, numero)`: a mesma página gravada de novo é atualizada no
    lugar, nunca duplicada; a versão do extrator gravada diz se ela precisa ser refeita.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        arquivo_id: Arquivo.
        paginas: Linhas de `lupa.ingestao.extracao.linha_pagina`.

    Returns:
        Quantidade gravada.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    _travar_job(session, lease)
    if not paginas:
        return 0
    valores = [
        p
        | {
            "id": uuid4(),
            "gabinete_id": lease.gabinete_id,
            "arquivo_id": arquivo_id,
            "hash_texto": calcular_hash(p["texto"]),
        }
        for p in paginas
    ]
    instrucao = insert(PaginaTabela).values(valores)
    fixas = ("id", "gabinete_id", "arquivo_id", "numero")
    colunas = [c for c in valores[0] if c not in fixas]
    session.execute(
        instrucao.on_conflict_do_update(
            index_elements=["arquivo_id", "numero"],
            set_={coluna: instrucao.excluded[coluna] for coluna in colunas},
        )
    )
    return len(valores)


def resumo_paginas(session: Session, arquivo_id: UUID) -> list[dict[str, Any]]:
    """Dados das páginas usados no relatório de qualidade (sem texto).

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        `{numero, tipo, flags, extracao, ocultos, suspeitos}` por página, em ordem; `ocultos` é a
        quantidade de trechos ocultos e `suspeitos` os trechos suspeitos (sem texto).
    """
    consulta = (
        select(
            PaginaTabela.numero,
            PaginaTabela.tipo,
            PaginaTabela.flags,
            PaginaTabela.extracao,
            PaginaTabela.trechos_ocultos,
            PaginaTabela.trechos_suspeitos,
        )
        .where(PaginaTabela.arquivo_id == arquivo_id)
        .order_by(PaginaTabela.numero)
    )
    return [
        {
            "numero": n,
            "tipo": tipo,
            "flags": flags,
            "extracao": extracao,
            "ocultos": len(ocultos or []),
            "suspeitos": suspeitos,
        }
        for n, tipo, flags, extracao, ocultos, suspeitos in session.execute(consulta)
    ]


def alertas_arquivo(session: Session, arquivo_id: UUID) -> dict[str, Any]:
    """Painel de alertas de injeção do arquivo (4D.10), sem texto dos autos.

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        Resumo do arquivo, metadados suspeitos (só hash) e, por página sinalizada, as flags,
        os trechos ocultos (motivo, caixa, hash, categorias) e os trechos suspeitos.
    """
    diagnostico = obter_diagnostico(session, arquivo_id)
    metadados = diagnostico.metadados_descartados if diagnostico else []
    consulta = (
        select(
            PaginaTabela.numero,
            PaginaTabela.flags,
            PaginaTabela.trechos_ocultos,
            PaginaTabela.trechos_suspeitos,
        )
        .where(PaginaTabela.arquivo_id == arquivo_id)
        .order_by(PaginaTabela.numero)
    )
    linhas = list(session.execute(consulta))
    resumo = resumo_saneamento(
        [
            {"numero": n, "flags": f, "ocultos": len(o or []), "suspeitos": s}
            for n, f, o, s in linhas
        ],
        metadados,
    )
    paginas = [
        {
            "numero": n,
            "flags": sorted(k for k, ligada in (f or {}).items() if ligada),
            "trechos_ocultos": [{k: v for k, v in o.items() if k != "texto"} for o in ocultos],
            "trechos_suspeitos": suspeitos,
        }
        for n, f, ocultos, suspeitos in linhas
        if any((f or {}).values())
    ]
    return {
        "arquivo_id": str(arquivo_id),
        "resumo": resumo,
        "metadados_suspeitos": [m for m in metadados if m.get("categorias")],
        "paginas": paginas,
    }


def registrar_relatorio(
    session: Session, lease: Lease, relatorio: dict[str, Any], versao_extrator: str
) -> None:
    """Grava o relatório de qualidade e a versão do extrator no job.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do worker.
        relatorio: Relatório (ver `lupa.ingestao.qualidade`).
        versao_extrator: Versão do extrator.

    Raises:
        LeasePerdidoError: Se outro worker assumiu o job.
    """
    job = _travar_job(session, lease)
    job.relatorio = relatorio
    job.versao_extrator = versao_extrator
    session.flush()


def tempo_acumulado(session: Session, job_id: UUID) -> float:
    """Tempo de parede de extração já acumulado pelo job (fatias anteriores).

    Args:
        session: Sessão com transação aberta.
        job_id: Job.

    Returns:
        Segundos.
    """
    relatorio = session.scalar(select(Job.relatorio).where(Job.id == job_id)) or {}
    return float(relatorio.get("tempo", {}).get("parede_segundos", 0.0))


def obter_relatorio(session: Session, arquivo_id: UUID) -> dict[str, Any] | None:
    """Relatório de qualidade do job do arquivo.

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        Estado do job e relatório, ou None se não houver job.
    """
    job = obter_job_por_arquivo(session, arquivo_id)
    if job is None:
        return None
    return {
        "job_id": str(job.id),
        "estado": job.estado,
        "versao_extrator": job.versao_extrator,
        "relatorio": job.relatorio,
    }


def atualizar_status_processo(session: Session, processo_id: UUID) -> StatusProcesso | None:
    """Ajusta `processo.status` aos jobs do processo.

    Algum job em andamento: `em_ingestao`. Nenhum em andamento e algum `concluido` ou
    `parcial`: `pronto`. Processo bloqueado ou arquivado não muda.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.

    Returns:
        O novo status, ou None se nada mudou.
    """
    processo = session.get(ProcessoTabela, processo_id)
    if processo is None or processo.status in (
        StatusProcesso.BLOQUEADO.value,
        StatusProcesso.ARQUIVADO.value,
        StatusProcesso.DESCARTADO.value,
    ):
        return None
    estados = set(session.scalars(select(Job.estado).where(Job.processo_id == processo_id)))
    if estados & {e.value for e in ESTADOS_EM_ANDAMENTO}:
        novo = StatusProcesso.EM_INGESTAO
    elif estados & {EstadoJob.CONCLUIDO.value, EstadoJob.PARCIAL.value}:
        novo = StatusProcesso.PRONTO
    else:
        return None
    if processo.status == novo.value:
        return None
    processo.status = novo.value
    session.flush()
    return novo
