"""Worker da ingestão: valida e extrai o arquivo recebido, sob lease com fencing token.

Validação (Etapa 4A): adquire o lease (novo fencing token), baixa o objeto, monta as unidades
de trabalho (um PDF avulso é um lote; um ZIP vira um lote por entrada, depois do inventário
seguro), inspeciona cada PDF no sandbox e grava o resultado do lote uma única vez. Lotes já
gravados por uma tentativa anterior são reaproveitados, então um worker morto no meio é
retomado sem duplicar gravação; um worker que perdeu o lease não grava mais nada. O job vai
para `validado`, `quarentena` (com motivo) ou `falho` (com motivo).

Extração (Etapa 4C): do `validado`, grava o diagnóstico do arquivo, passa a `em_extracao` e
extrai as páginas em lotes paralelos (`lupa.ingestao.extracao`), gravando cada lote assim que
termina. Páginas já gravadas na versão corrente do extrator são puladas. A cada fatia de
páginas o job cede a vez (solta o lease sem contar tentativa e volta ao fim da fila), para que
um arquivo enorme não ocupe o worker enquanto jobs menores esperam. No fim: `concluido`,
`parcial` (algumas páginas sem resultado) ou `falho`; o relatório de qualidade vai para o job
e o status do processo é atualizado. Falha por `tempo_esgotado` ou `erro_parser` volta a
`recebido` até duas vezes; `limite_memoria` e `limite_cpu` nunca são retentados.

Eventos (Etapa 4F): antes de qualquer extração, páginas de outro arquivo do mesmo gabinete com o
mesmo SHA-256 e a mesma versão do extrator são copiadas (`lupa.ingestao.cache`). Depois do índice,
`lupa.ingestao.eventos.etapa` grava réus, fatos e achados num savepoint: falha ali fica no
relatório (`eventos.erro`) sem desfazer páginas nem peças.

Os logs carregam só ids opacos, estados, motivos e contagens; nunca nome de arquivo nem texto.
"""

import os
import socket
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from rq import Queue, SimpleWorker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from lupa.config import Settings, get_settings
from lupa.dominio.enums import EstadoJob, EstadoLote, MotivoFalha, MotivoQuarentena
from lupa.dominio.esquemas import DiagnosticoArquivo, EntradaManifesto
from lupa.dominio.sessao import assumir_papel_aplicacao, definir_gabinete, definir_papel
from lupa.dominio.tabelas import ArquivoTabela, JobIngestaoTabela
from lupa.ingestao import cache, repositorio, repositorio_pecas
from lupa.ingestao.diagnostico import diagnosticar_pdf, diagnosticar_zip
from lupa.ingestao.eventos.etapa import processar_eventos
from lupa.ingestao.extracao import (
    LIMITADOR_PADRAO,
    Executor,
    FontePaginas,
    LimitadorGabinete,
    Paralelismo,
    ResultadoTarefa,
    Tarefa,
    executar_em_paralelo,
    linha_pagina,
    pendentes,
    planejar,
)
from lupa.ingestao.extrator_paginas import VERSAO_EXTRATOR
from lupa.ingestao.fila import FilaIngestao, conectar_redis, criar_fila
from lupa.ingestao.indice import montar_indice
from lupa.ingestao.indice import versoes as versoes_indice
from lupa.ingestao.inventario import LimitesZip, ZipRecusadoError, inventariar
from lupa.ingestao.qualidade import relatorio_qualidade
from lupa.ingestao.quarentena import motivo_do_parser
from lupa.ingestao.recepcao import TipoArquivo
from lupa.ingestao.repositorio import Lease, LeasePerdidoError
from lupa.ingestao.sandbox import (
    LimitesSandbox,
    ResultadoSandbox,
    executar,
    inspecionar_pdf,
    inspecionar_pdfs,
)
from lupa.ingestao.storage import ObjectStorage, ObjetoAusenteError, chave_objeto, criar_storage
from lupa.logging import configurar_logging, get_logger
from lupa.seguranca.chaves import carregador_sql
from lupa.seguranca.contexto import ChaveIndisponivelError, contexto_atual, contexto_cifra, dek_de

PAPEL_SISTEMA = "administrador"
ESPERA_VARREDURA = timedelta(seconds=30)
INTERVALO_LOOP_SEGUNDOS = 2.0
MAGICO_PDF = b"%PDF-"
MOTIVOS_RETENTAVEIS = frozenset({MotivoFalha.TEMPO_ESGOTADO, MotivoFalha.ERRO_PARSER})
FALHA_OCR = "erro_ocr"
ENTRADAS_POR_FILHO = 32

log = get_logger(__name__)


@dataclass(frozen=True)
class Dependencias:
    """Tudo de que o worker precisa, injetável nos testes.

    Attributes:
        fabrica: Fábrica de sessões do banco.
        storage: Object storage.
        limites_sandbox: Limites do parser.
        limites_zip: Limites do inventário de ZIP.
        duracao_lease: Validade do lease (renovado a cada lote).
        max_tentativas: Tentativas antes de marcar `falho`.
        dir_temporario: Diretório de trabalho (None = padrão do sistema).
        relogio: Fonte do instante atual.
        dono: Identificador opaco deste worker.
        extrair: Se segue do `validado` para a extração de páginas.
        max_retentativas: Novas tentativas automáticas para falhas retentáveis.
        paralelismo: Tetos de lotes de páginas simultâneos.
        fatia_paginas: Páginas por aquisição antes de ceder a vez (0 = sem fatiar).
        fila: Fila usada para reenfileirar o job que cede a vez ou é retentado.
        limitador: Semáforos por gabinete.
        executor: Executor do sandbox (injetável nos testes).
        eventos: Se extrai eventos e executa o catálogo no fim da extração (4F).
    """

    fabrica: sessionmaker[Session]
    storage: ObjectStorage
    limites_sandbox: LimitesSandbox
    limites_zip: LimitesZip
    duracao_lease: timedelta
    max_tentativas: int
    dir_temporario: Path | None = None
    relogio: Callable[[], datetime] = lambda: datetime.now(UTC)
    dono: str = ""
    extrair: bool = True
    max_retentativas: int = 2
    paralelismo: Paralelismo = field(default_factory=Paralelismo)
    fatia_paginas: int = 0
    fila: FilaIngestao | None = None
    limitador: LimitadorGabinete = LIMITADOR_PADRAO
    executor: Executor = executar
    eventos: bool = True


@dataclass(frozen=True)
class DadosJob:
    """Dados do job e do arquivo lidos ao adquirir o lease.

    Attributes:
        estado: Estado do job.
        arquivo_id: Arquivo.
        processo_id: Processo.
        chave: Chave do objeto no storage.
        mime: Tipo do arquivo.
        nome: Nome original (vai só para o manifesto, nunca para log).
        sha256: Hash do arquivo.
    """

    estado: EstadoJob
    arquivo_id: UUID
    processo_id: UUID
    chave: str
    mime: str
    nome: str
    sha256: str


@dataclass(frozen=True)
class Unidade:
    """Unidade de trabalho de um lote: um PDF.

    Attributes:
        numero: Número do lote (ordem do manifesto).
        manifesto: Entrada do manifesto.
        caminho: Arquivo local do PDF.
    """

    numero: int
    manifesto: EntradaManifesto
    caminho: Path


@dataclass(frozen=True)
class Desfecho:
    """Estado final de uma execução e seu motivo.

    Attributes:
        estado: `validado`, `quarentena` ou `falho`.
        motivo_quarentena: Motivo quando em quarentena.
        motivo_falha: Motivo quando falho.
    """

    estado: EstadoJob
    motivo_quarentena: MotivoQuarentena | None = None
    motivo_falha: MotivoFalha | None = None


class DesfechoAntecipado(Exception):  # noqa: N818
    """Interrompe o processamento com um desfecho já conhecido (quarentena ou falha)."""

    def __init__(self, desfecho: Desfecho) -> None:
        """Cria a interrupção.

        Args:
            desfecho: Desfecho a aplicar.
        """
        super().__init__(desfecho.estado.value)
        self.desfecho = desfecho


def identificador_worker() -> str:
    """Identificador opaco do processo worker.

    Returns:
        `host:pid:aleatório`.
    """
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def dependencias_da_configuracao(settings: Settings) -> Dependencias:
    """Monta as dependências a partir da configuração.

    Args:
        settings: Configuração.

    Returns:
        Dependências do worker.
    """
    engine = create_engine(settings.url_banco_aplicacao(), pool_pre_ping=True)
    return Dependencias(
        fabrica=sessionmaker(engine, expire_on_commit=False),
        storage=criar_storage(settings),
        limites_sandbox=LimitesSandbox(
            settings.sandbox_memoria_mb,
            settings.sandbox_cpu_segundos,
            settings.sandbox_tempo_segundos,
        ),
        limites_zip=LimitesZip(
            settings.zip_max_entradas,
            settings.zip_max_razao,
            settings.zip_max_descomprimido_bytes,
        ),
        duracao_lease=timedelta(seconds=settings.lease_segundos),
        max_tentativas=settings.max_tentativas,
        dir_temporario=settings.ingestao_dir_temporario,
        dono=identificador_worker(),
        max_retentativas=settings.max_retentativas,
        paralelismo=Paralelismo(
            settings.extracao_paginas_por_lote,
            settings.extracao_lotes_por_job,
            settings.extracao_lotes_por_gabinete,
        ),
        fatia_paginas=settings.extracao_fatia_paginas,
        fila=criar_fila(settings),
    )


@lru_cache(maxsize=1)
def dependencias_padrao() -> Dependencias:
    """Dependências do processo worker, criadas uma vez.

    Returns:
        Dependências da configuração do ambiente.
    """
    return dependencias_da_configuracao(get_settings())


@contextmanager
def sessao_gabinete(fabrica: sessionmaker[Session], gabinete_id: UUID) -> Iterator[Session]:
    """Transação sob `lupa_app` restrita ao gabinete do job.

    Args:
        fabrica: Fábrica de sessões.
        gabinete_id: Gabinete do job.

    Yields:
        Sessão; confirma no fim, desfaz em erro.
    """
    with fabrica() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_gabinete(session, gabinete_id)
        yield session


@contextmanager
def sessao_sistema(fabrica: sessionmaker[Session]) -> Iterator[Session]:
    """Transação sob `lupa_app` com visão de todos os gabinetes (só para o varredor).

    Args:
        fabrica: Fábrica de sessões.

    Yields:
        Sessão; confirma no fim, desfaz em erro.
    """
    with fabrica() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_papel(session, PAPEL_SISTEMA)
        yield session


def _adquirir(deps: Dependencias, job_id: UUID, gabinete_id: UUID) -> tuple[Lease, DadosJob] | None:
    with sessao_gabinete(deps.fabrica, gabinete_id) as session:
        lease = repositorio.adquirir_lease(
            session, job_id, deps.dono, deps.relogio(), deps.duracao_lease
        )
        if lease is None:
            return None
        job = session.get_one(JobIngestaoTabela, job_id)
        arquivo = session.get_one(ArquivoTabela, job.arquivo_id)
        dados = DadosJob(
            estado=EstadoJob(job.estado),
            arquivo_id=job.arquivo_id,
            processo_id=job.processo_id,
            chave=arquivo.chave_storage,
            mime=arquivo.mime,
            nome=arquivo.nome_original,
            sha256=arquivo.sha256,
        )
        return lease, dados


def _baixar(deps: Dependencias, chave: str, destino: Path) -> None:
    try:
        claro = deps.storage.ler(chave)
        descritor = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descritor, "wb") as saida:
            saida.write(claro)
    except ObjetoAusenteError:
        raise DesfechoAntecipado(
            Desfecho(EstadoJob.FALHO, motivo_falha=MotivoFalha.ARQUIVO_AUSENTE)
        ) from None


def _guardar_entradas(
    deps: Dependencias, lease: Lease, processo_id: UUID, unidades: list[Unidade]
) -> None:
    for unidade in unidades:
        chave = chave_objeto(lease.gabinete_id, processo_id, unidade.manifesto.sha256)
        if not deps.storage.existe(chave):
            with unidade.caminho.open("rb") as origem:
                deps.storage.gravar(chave, origem)


def _unidades(deps: Dependencias, lease: Lease, dados: DadosJob, diretorio: Path) -> list[Unidade]:
    original = diretorio / "original"
    _baixar(deps, dados.chave, original)
    if dados.mime == TipoArquivo.PDF.value:
        entrada = EntradaManifesto(
            ordem=1, nome=dados.nome, tamanho_bytes=original.stat().st_size, sha256=dados.sha256
        )
        return [Unidade(1, entrada, original)]
    extraidas_dir = diretorio / "entradas"
    extraidas_dir.mkdir()
    try:
        extraidas = inventariar(original, extraidas_dir, deps.limites_zip)
    except ZipRecusadoError as erro:
        raise DesfechoAntecipado(
            Desfecho(EstadoJob.QUARENTENA, motivo_quarentena=erro.motivo)
        ) from None
    unidades = [Unidade(e.manifesto.ordem, e.manifesto, e.caminho) for e in extraidas]
    _guardar_entradas(deps, lease, dados.processo_id, unidades)
    return unidades


def _e_pdf(unidade: Unidade) -> bool:
    with unidade.caminho.open("rb") as entrada:
        return entrada.read(len(MAGICO_PDF)) == MAGICO_PDF


def _inspecoes(deps: Dependencias, unidades: list[Unidade]) -> dict[int, ResultadoSandbox]:
    pdfs = [u for u in unidades if _e_pdf(u)]
    if len(pdfs) <= 1:
        return {}
    resultados = inspecionar_pdfs([u.caminho for u in pdfs], deps.limites_sandbox)
    return dict(zip([u.numero for u in pdfs], resultados, strict=True))


def _resultado_unidade(
    deps: Dependencias, unidade: Unidade, inspecao: ResultadoSandbox | None = None
) -> dict[str, Any]:
    if not _e_pdf(unidade):
        return {"motivo_quarentena": MotivoQuarentena.TIPO_INVALIDO.value}
    resultado = inspecao or inspecionar_pdf(unidade.caminho, deps.limites_sandbox)
    if resultado.motivo_falha is not None:
        return {"motivo_falha": resultado.motivo_falha.value}
    motivo = motivo_do_parser(resultado.dados)
    if motivo is not None:
        return {"motivo_quarentena": motivo.value}
    dados = resultado.dados
    return {
        "paginas": int(dados.get("paginas", 0)),
        "bookmarks": int(dados.get("bookmarks", 0)),
        "toc": list(dados.get("toc", [])),
        "paginas_indice": int(dados.get("paginas_indice", 0)),
        "indice": list(dados.get("indice", [])),
        "metadados": list(dados.get("metadados", [])),
    }


def _processar_lotes(
    deps: Dependencias,
    lease: Lease,
    unidades: list[Unidade],
    ao_gravar_lote: Callable[[int], None] | None,
) -> dict[int, dict[str, Any]]:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        prontos = {
            n: dict(lote.resultado)
            for n, lote in repositorio.lotes_do_job(session, lease.job_id).items()
        }
    faltantes = [u for u in unidades if u.numero not in prontos]
    inspecoes: dict[int, ResultadoSandbox] = {}
    for posicao, unidade in enumerate(faltantes):
        if posicao % ENTRADAS_POR_FILHO == 0:
            inspecoes = _inspecoes(deps, faltantes[posicao : posicao + ENTRADAS_POR_FILHO])
        resultado = _resultado_unidade(deps, unidade, inspecoes.get(unidade.numero))
        estado = EstadoLote.CONCLUIDO if "paginas" in resultado else EstadoLote.FALHO
        with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
            repositorio.renovar_lease(session, lease, deps.relogio(), deps.duracao_lease)
            repositorio.gravar_lote(session, lease, unidade.numero, estado, resultado)
        prontos[unidade.numero] = resultado
        log.info("lote_gravado", job_id=str(lease.job_id), lote=unidade.numero, estado=estado.value)
        if ao_gravar_lote is not None:
            ao_gravar_lote(unidade.numero)
    return prontos


def desfecho_dos_lotes(resultados: list[dict[str, Any]]) -> Desfecho:
    """Combina os resultados dos lotes: falha vence quarentena, que vence validação.

    Args:
        resultados: Resultados na ordem dos lotes.

    Returns:
        Desfecho do job.
    """
    for resultado in resultados:
        if "motivo_falha" in resultado:
            return Desfecho(EstadoJob.FALHO, motivo_falha=MotivoFalha(resultado["motivo_falha"]))
    for resultado in resultados:
        if "motivo_quarentena" in resultado:
            motivo = MotivoQuarentena(resultado["motivo_quarentena"])
            return Desfecho(EstadoJob.QUARENTENA, motivo_quarentena=motivo)
    return Desfecho(EstadoJob.VALIDADO)


def _retentar(deps: Dependencias, session: Session, lease: Lease, desfecho: Desfecho) -> bool:
    retentavel = desfecho.motivo_falha in MOTIVOS_RETENTAVEIS
    if not retentavel or lease.tentativa > deps.max_retentativas:
        return False
    repositorio.descartar_lotes_falhos(session, lease)
    repositorio.mudar_estado(session, lease, EstadoJob.RECEBIDO, deps.relogio())
    return True


def _encerrar(deps: Dependencias, session: Session, lease: Lease, desfecho: Desfecho) -> bool:
    repositorio.mudar_estado(
        session,
        lease,
        desfecho.estado,
        deps.relogio(),
        motivo_quarentena=desfecho.motivo_quarentena,
        motivo_falha=desfecho.motivo_falha,
    )
    retentado = desfecho.estado is EstadoJob.FALHO and _retentar(deps, session, lease, desfecho)
    processo_id = session.get_one(JobIngestaoTabela, lease.job_id).processo_id
    repositorio.atualizar_status_processo(session, processo_id)
    repositorio.liberar_lease(session, lease)
    return retentado


def _registrar_validacao(
    session: Session,
    lease: Lease,
    unidades: list[Unidade],
    resultados: dict[int, dict[str, Any]],
) -> None:
    if unidades:
        paginas = sum(int(r.get("paginas", 0)) for r in resultados.values())
        manifesto = [u.manifesto.model_dump(mode="json") for u in unidades]
        repositorio.registrar_resultado(session, lease, total_paginas=paginas, manifesto=manifesto)


def _log_fim(lease: Lease, desfecho: Desfecho, retentado: bool) -> None:
    log.info(
        "job_finalizado",
        job_id=str(lease.job_id),
        estado=desfecho.estado.value,
        motivo=(desfecho.motivo_quarentena or desfecho.motivo_falha or None),
        tentativa=lease.tentativa,
        retentado=retentado,
    )


def _finalizar(
    deps: Dependencias,
    lease: Lease,
    desfecho: Desfecho,
    unidades: list[Unidade],
    resultados: dict[int, dict[str, Any]],
) -> None:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        _registrar_validacao(session, lease, unidades, resultados)
        retentado = _encerrar(deps, session, lease, desfecho)
    _log_fim(lease, desfecho, retentado)
    if retentado and deps.fila is not None:
        deps.fila.enfileirar(lease.job_id, lease.gabinete_id)


def _diagnostico(
    dados: DadosJob, unidades: list[Unidade], resultados: dict[int, dict[str, Any]]
) -> DiagnosticoArquivo:
    if dados.mime == TipoArquivo.PDF.value:
        return diagnosticar_pdf(dados.arquivo_id, dados.nome, resultados[unidades[0].numero])
    entradas = [(u.manifesto.nome, resultados[u.numero]) for u in unidades]
    return diagnosticar_zip(dados.arquivo_id, entradas)


def _iniciar_extracao(
    deps: Dependencias,
    lease: Lease,
    dados: DadosJob,
    unidades: list[Unidade],
    resultados: dict[int, dict[str, Any]],
) -> None:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        if dados.estado is EstadoJob.RECEBIDO:
            _registrar_validacao(session, lease, unidades, resultados)
            repositorio.mudar_estado(session, lease, EstadoJob.VALIDADO, deps.relogio())
        repositorio.salvar_diagnostico(
            session, lease.gabinete_id, _diagnostico(dados, unidades, resultados)
        )
        repositorio.mudar_estado(session, lease, EstadoJob.EM_EXTRACAO, deps.relogio())
        repositorio.registrar_relatorio(session, lease, {}, VERSAO_EXTRATOR)
        repositorio.atualizar_status_processo(session, dados.processo_id)
    log.info("extracao_iniciada", job_id=str(lease.job_id))


@dataclass
class Progresso:
    """Estado acumulado da extração entre fatias (guardado no relatório parcial do job).

    Attributes:
        parede_segundos: Tempo de parede somado das fatias.
        falhas: Páginas sem resultado por motivo, com os números.
    """

    parede_segundos: float = 0.0
    falhas: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def do_relatorio(cls, relatorio: dict[str, Any] | None) -> "Progresso":
        """Lê o progresso do relatório parcial.

        Args:
            relatorio: Relatório gravado no job (pode ser vazio).

        Returns:
            Progresso.
        """
        dados = relatorio or {}
        return cls(
            float(dados.get("tempo", {}).get("parede_segundos", 0.0)),
            {k: list(v) for k, v in dados.get("falhas_paginas", {}).items()},
        )

    def falhou(self) -> set[int]:
        """Páginas que já falharam nesta tentativa."""
        return {n for numeros in self.falhas.values() for n in numeros}

    def registrar(self, motivo: str, numeros: list[int]) -> None:
        """Acrescenta páginas sem resultado.

        Args:
            motivo: Motivo da falha.
            numeros: Páginas.
        """
        self.falhas.setdefault(motivo, []).extend(numeros)

    def parcial(self) -> dict[str, Any]:
        """Relatório parcial gravado quando o job cede a vez."""
        return {"tempo": {"parede_segundos": self.parede_segundos}, "falhas_paginas": self.falhas}


def _fontes(unidades: list[Unidade], resultados: dict[int, dict[str, Any]]) -> list[FontePaginas]:
    fontes = []
    deslocamento = 0
    for unidade in unidades:
        paginas = int(resultados[unidade.numero].get("paginas", 0))
        fontes.append(FontePaginas(unidade.caminho, unidade.manifesto.nome, paginas, deslocamento))
        deslocamento += paginas
    return fontes


def _fatiar(tarefas: list[Tarefa], limite: int) -> tuple[list[Tarefa], bool]:
    if limite <= 0:
        return tarefas, False
    fatia: list[Tarefa] = []
    paginas = 0
    for tarefa in tarefas:
        if fatia and paginas + len(tarefa.numeros) > limite:
            return fatia, True
        fatia.append(tarefa)
        paginas += len(tarefa.numeros)
    return fatia, False


def _gravar_resultado(
    deps: Dependencias,
    lease: Lease,
    arquivo_id: UUID,
    resultado: ResultadoTarefa,
    progresso: Progresso,
) -> None:
    if resultado.motivo_falha is not None:
        progresso.registrar(resultado.motivo_falha.value, list(resultado.tarefa.numeros))
    linhas = [linha_pagina(p, VERSAO_EXTRATOR) for p in resultado.paginas if "erro" not in p]
    sem_ocr = [int(p["numero"]) for p in resultado.paginas if "erro" in p]
    if sem_ocr:
        progresso.registrar(FALHA_OCR, sem_ocr)
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        repositorio.renovar_lease(session, lease, deps.relogio(), deps.duracao_lease)
        repositorio.gravar_paginas(session, lease, arquivo_id, linhas)


def _desfecho_extracao(relatorio: dict[str, Any], progresso: Progresso) -> Desfecho:
    if relatorio["paginas_faltando"] == 0:
        return Desfecho(EstadoJob.CONCLUIDO)
    if relatorio["paginas_extraidas"] > 0:
        return Desfecho(EstadoJob.PARCIAL)
    contagem = Counter({motivo: len(n) for motivo, n in progresso.falhas.items()})
    motivo = contagem.most_common(1)[0][0] if contagem else MotivoFalha.ERRO_PARSER.value
    falha = MotivoFalha(motivo) if motivo in MotivoFalha.__members__.values() else None
    return Desfecho(EstadoJob.FALHO, motivo_falha=falha or MotivoFalha.ERRO_PARSER)


def _gravar_indice(
    session: Session,
    gabinete_id: UUID,
    arquivo_id: UUID,
    diagnostico: DiagnosticoArquivo | None,
) -> dict[str, Any]:
    paginas = repositorio_pecas.paginas_para_indice(session, arquivo_id)
    resultado = montar_indice(paginas, diagnostico.model_dump(mode="json") if diagnostico else None)
    gravadas = repositorio_pecas.gravar_indice(session, gabinete_id, arquivo_id, paginas, resultado)
    log.info("indice_gravado", arquivo_id=str(arquivo_id), pecas=gravadas)
    return {
        "indice": {
            "fonte": resultado.fonte,
            "pecas": len(resultado.pecas),
            "gravadas": gravadas,
            "fronteiras_fracas": sum(
                1 for p in resultado.pecas if "fronteira_fraca" in p.flags["peca"]
            ),
            "versoes": versoes_indice(),
        },
        "divergencias_fronteira": resultado.divergencias,
    }


def _gravar_eventos(
    deps: Dependencias, session: Session, gabinete_id: UUID, processo_id: UUID
) -> dict[str, Any]:
    if not deps.eventos:
        return {}
    try:
        with session.begin_nested():
            resumo = processar_eventos(session, gabinete_id, processo_id, deps.relogio().date())
    except Exception as erro:  # noqa: BLE001 - falha nos eventos não desfaz páginas nem índice
        log.error("eventos_falharam", processo_id=str(processo_id), erro=type(erro).__name__)
        return {"eventos": {"erro": type(erro).__name__}}
    return {"eventos": resumo}


def _reaproveitar_cache(deps: Dependencias, lease: Lease, dados: DadosJob, total: int) -> int:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        origem = cache.fonte_em_cache(
            session, lease.gabinete_id, dados.arquivo_id, dados.sha256, VERSAO_EXTRATOR, total
        )
        if origem is None:
            return 0
        copiadas = cache.copiar_paginas(session, lease, origem, dados.arquivo_id)
    log.info("paginas_reaproveitadas", job_id=str(lease.job_id), paginas=copiadas)
    return copiadas


def _concluir_extracao(
    deps: Dependencias, lease: Lease, dados: DadosJob, total: int, progresso: Progresso
) -> Desfecho:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        resumo = repositorio.resumo_paginas(session, dados.arquivo_id)
        diagnostico = repositorio.obter_diagnostico(session, dados.arquivo_id)
        relatorio = relatorio_qualidade(
            resumo,
            total_paginas=total,
            tempo_parede_segundos=progresso.parede_segundos,
            falhas={motivo: len(n) for motivo, n in progresso.falhas.items()},
            versao_extrator=VERSAO_EXTRATOR,
            metadados=diagnostico.metadados_descartados if diagnostico else [],
        )
        desfecho = _desfecho_extracao(relatorio, progresso)
        if desfecho.estado in (EstadoJob.CONCLUIDO, EstadoJob.PARCIAL):
            relatorio |= _gravar_indice(session, lease.gabinete_id, dados.arquivo_id, diagnostico)
            relatorio |= _gravar_eventos(deps, session, lease.gabinete_id, dados.processo_id)
        repositorio.registrar_relatorio(session, lease, relatorio, VERSAO_EXTRATOR)
        retentado = _encerrar(deps, session, lease, desfecho)
    _log_fim(lease, desfecho, retentado)
    if retentado and deps.fila is not None:
        deps.fila.enfileirar(lease.job_id, lease.gabinete_id)
    return desfecho


def _ceder_vez(deps: Dependencias, lease: Lease, progresso: Progresso) -> None:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        repositorio.registrar_relatorio(session, lease, progresso.parcial(), VERSAO_EXTRATOR)
        repositorio.ceder_vez(session, lease)
    if deps.fila is not None:
        deps.fila.enfileirar(lease.job_id, lease.gabinete_id)
    log.info("job_cedeu_vez", job_id=str(lease.job_id))


def _extrair(
    deps: Dependencias,
    lease: Lease,
    dados: DadosJob,
    unidades: list[Unidade],
    resultados: dict[int, dict[str, Any]],
) -> Desfecho | None:
    fontes = _fontes(unidades, resultados)
    total = sum(f.paginas for f in fontes)
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        prontas = repositorio.paginas_prontas(session, dados.arquivo_id, VERSAO_EXTRATOR)
    if not prontas and _reaproveitar_cache(deps, lease, dados, total):
        with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
            prontas = repositorio.paginas_prontas(session, dados.arquivo_id, VERSAO_EXTRATOR)
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        job = session.get_one(JobIngestaoTabela, lease.job_id)
        progresso = Progresso.do_relatorio(job.relatorio)
    tarefas = pendentes(
        planejar(fontes, deps.paralelismo.paginas_por_lote), prontas | progresso.falhou()
    )
    fatia, resta = _fatiar(tarefas, deps.fatia_paginas if deps.fila is not None else 0)
    inicio = time.perf_counter()
    for resultado in executar_em_paralelo(
        fatia,
        deps.limites_sandbox,
        deps.paralelismo,
        str(lease.gabinete_id),
        limitador=deps.limitador,
        executor=deps.executor,
    ):
        _gravar_resultado(deps, lease, dados.arquivo_id, resultado, progresso)
    progresso.parede_segundos += time.perf_counter() - inicio
    if resta:
        _ceder_vez(deps, lease, progresso)
        return None
    return _concluir_extracao(deps, lease, dados, total, progresso)


def _soltar(deps: Dependencias, lease: Lease) -> None:
    with sessao_gabinete(deps.fabrica, lease.gabinete_id) as session:
        repositorio.liberar_lease(session, lease)


def _executar(
    deps: Dependencias,
    lease: Lease,
    dados: DadosJob,
    ao_gravar_lote: Callable[[int], None] | None,
) -> Desfecho | None:
    unidades: list[Unidade] = []
    resultados: dict[int, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="lupa-job-", dir=deps.dir_temporario) as pasta:
        try:
            unidades = _unidades(deps, lease, dados, Path(pasta))
            resultados = _processar_lotes(deps, lease, unidades, ao_gravar_lote)
            desfecho = desfecho_dos_lotes([resultados[u.numero] for u in unidades])
            if desfecho.estado is not EstadoJob.VALIDADO or not deps.extrair:
                _finalizar(deps, lease, desfecho, unidades, resultados)
                return desfecho
            if dados.estado is not EstadoJob.EM_EXTRACAO:
                _iniciar_extracao(deps, lease, dados, unidades, resultados)
            return _extrair(deps, lease, dados, unidades, resultados)
        except DesfechoAntecipado as antecipado:
            _finalizar(deps, lease, antecipado.desfecho, unidades, resultados)
            return antecipado.desfecho


def _abandonar(deps: Dependencias, lease: Lease, desfecho: Desfecho) -> None:
    _finalizar(deps, lease, desfecho, [], {})


def _estados_processaveis(deps: Dependencias) -> frozenset[EstadoJob]:
    if not deps.extrair:
        return frozenset({EstadoJob.RECEBIDO})
    return frozenset({EstadoJob.RECEBIDO, EstadoJob.VALIDADO, EstadoJob.EM_EXTRACAO})


def processar_job(
    deps: Dependencias,
    job_id: UUID,
    gabinete_id: UUID,
    *,
    ao_gravar_lote: Callable[[int], None] | None = None,
) -> EstadoJob | None:
    """Processa um job: valida (de `recebido`) e extrai as páginas (até `concluido`).

    Sem `deps.extrair`, para em `validado` (comportamento da Etapa 4A).

    Args:
        deps: Dependências.
        job_id: Job.
        gabinete_id: Gabinete do job.
        ao_gravar_lote: Gancho chamado depois de cada lote gravado (usado nos testes).

    Returns:
        O estado ao fim desta execução, ou None se o job estava ocupado ou finalizado, se o
        lease foi perdido ou se o job cedeu a vez no meio da extração.
    """
    with contexto_cifra(carregador_sql(deps.fabrica)):
        return _processar_job_cifrado(deps, job_id, gabinete_id, ao_gravar_lote)


def _processar_job_cifrado(
    deps: Dependencias,
    job_id: UUID,
    gabinete_id: UUID,
    ao_gravar_lote: Callable[[int], None] | None,
) -> EstadoJob | None:
    adquirido = _adquirir(deps, job_id, gabinete_id)
    if adquirido is None:
        log.info("job_ignorado", job_id=str(job_id))
        return None
    lease, dados = adquirido
    try:
        dek_de(dados.processo_id)
        contexto_atual().atual = dados.processo_id
        if dados.estado not in _estados_processaveis(deps):
            _soltar(deps, lease)
            return None
        if lease.tentativa > deps.max_tentativas:
            desfecho = Desfecho(EstadoJob.FALHO, motivo_falha=MotivoFalha.ERRO_INTERNO)
            _abandonar(deps, lease, desfecho)
            return desfecho.estado
        final = _executar(deps, lease, dados, ao_gravar_lote)
        return final.estado if final else None
    except LeasePerdidoError:
        log.warning("lease_perdido", job_id=str(job_id))
        return None
    except ChaveIndisponivelError:
        log.warning("processo_sem_chave", job_id=str(job_id))
        desfecho = Desfecho(EstadoJob.FALHO, motivo_falha=MotivoFalha.ERRO_INTERNO)
        _abandonar(deps, lease, desfecho)
        return desfecho.estado


def executar_job(job_id: str, gabinete_id: str) -> None:
    """Ponto de entrada chamado pelo RQ.

    Args:
        job_id: Job (texto do UUID).
        gabinete_id: Gabinete (texto do UUID).
    """
    processar_job(dependencias_padrao(), UUID(job_id), UUID(gabinete_id))


def varrer(deps: Dependencias, fila: FilaIngestao) -> int:
    """Reenfileira jobs em andamento parados (lease vencido ou mensagem perdida).

    Args:
        deps: Dependências.
        fila: Fila de ingestão.

    Returns:
        Quantidade reenfileirada.
    """
    with sessao_sistema(deps.fabrica) as session:
        parados = repositorio.jobs_recuperaveis(session, deps.relogio(), ESPERA_VARREDURA)
    for job_id, gabinete_id in parados:
        fila.enfileirar(job_id, gabinete_id)
        log.info("job_reenfileirado", job_id=str(job_id))
    return len(parados)


def main() -> None:  # pragma: no cover
    """Loop do contêiner `worker`: varre jobs parados e consome a fila em rajadas."""
    settings = get_settings()
    configurar_logging(nivel=settings.log_level)
    conexao = conectar_redis(settings)
    fila = criar_fila(settings)
    deps = dependencias_padrao()
    log.info("worker_iniciado", dono=deps.dono)
    while True:
        try:
            varrer(deps, fila)
            SimpleWorker(
                [Queue(settings.fila_ingestao, connection=conexao)], connection=conexao
            ).work(burst=True, logging_level="WARNING", with_scheduler=False)
        except Exception as erro:
            log.error("ciclo_worker_falhou", erro=type(erro).__name__)
        time.sleep(INTERVALO_LOOP_SEGUNDOS)


if __name__ == "__main__":  # pragma: no cover
    main()
