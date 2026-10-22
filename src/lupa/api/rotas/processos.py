"""Rotas de processo: lista do gabinete, criação, leitura e arquivos com o estado da ingestão.

`GET /processos` lista os processos visíveis (RLS do gabinete; o administrador vê todos) com o
resumo da ingestão vindo de `job_ingestao`; é auditada como `busca` (só metadados). `POST
/processos` cria o processo no gabinete do ator (número CNJ validado no servidor, dígito
verificador incluído) e grava `processo_criado`. `GET /processos/{id}` e `GET
/processos/{id}/arquivos` usam `exige_processo` (404 para outro gabinete, tentativa auditada).
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from lupa.acesso.autorizacao import (
    AtorAutenticado,
    ContextoReq,
    SessaoBanco,
    exige_papel,
    exige_processo,
)
from lupa.acesso.erros import ConflitoError, DadosInvalidosError, PermissaoNegadaError
from lupa.acesso.papeis import Permissao, pode
from lupa.acesso.servico import Ator, auditar
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria, ResultadoEvento
from lupa.dominio.cnj import NumeroCnjInvalidoError, validar_numero_cnj
from lupa.dominio.enums import EstadoJob, Materia, StatusProcesso
from lupa.dominio.tabelas import ArquivoTabela, JobIngestaoTabela, ProcessoTabela

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
Leitor = Annotated[Ator, Depends(exige_papel(Permissao.VER_PROCESSO))]

ESTADOS_FINAIS = frozenset({EstadoJob.CONCLUIDO, EstadoJob.QUARENTENA, EstadoJob.FALHO})
ESTADOS_COM_PENDENCIA = frozenset({EstadoJob.PARCIAL, EstadoJob.EM_REVISAO})


class CorpoProcesso(BaseModel):
    """Dados do processo novo."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    numero_cnj: str = Field(min_length=25, max_length=25)
    classe: str = Field(min_length=2, max_length=120)
    materia: Materia
    sigiloso: bool = False
    gabinete_id: UUID | None = None

    @field_validator("numero_cnj")
    @classmethod
    def _cnj_valido(cls, valor: str) -> str:
        try:
            return validar_numero_cnj(valor)
        except NumeroCnjInvalidoError as erro:
            raise ValueError(str(erro)) from None


def _serializar(processo: ProcessoTabela) -> dict[str, Any]:
    return {
        "id": processo.id,
        "gabinete_id": processo.gabinete_id,
        "numero_cnj": processo.numero_cnj,
        "classe": processo.classe,
        "materia": processo.materia,
        "sigiloso": processo.sigiloso,
        "status": processo.status,
        "criado_em": processo.criado_em,
    }


def resumir_ingestao(estados: list[str]) -> str:
    """Situação agregada da ingestão a partir dos estados dos jobs do processo.

    Args:
        estados: Estado de cada job.

    Returns:
        `sem_arquivos`, `processando` (algum job não final), `quarentena` (todos os jobs em
        quarentena), `falho`, `pendencias` (parcial/em revisão) ou `concluido`.
    """
    if not estados:
        return "sem_arquivos"
    conjunto = {EstadoJob(e) for e in estados}
    if conjunto - ESTADOS_FINAIS - ESTADOS_COM_PENDENCIA:
        return "processando"
    if conjunto == {EstadoJob.QUARENTENA}:
        return "quarentena"
    if EstadoJob.FALHO in conjunto:
        return "falho"
    if conjunto & ESTADOS_COM_PENDENCIA:
        return "pendencias"
    return "concluido"


@router.get("/processos")
@auditar_rota(AcaoAuditoria.BUSCA, conteudo=False)
def listar_processos(ator: Leitor, sessao: SessaoBanco) -> list[dict[str, Any]]:
    """Processos visíveis ao ator, mais recentes primeiro, com o resumo da ingestão.

    Args:
        ator: Ator com permissão de ver processos.
        sessao: Sessão (RLS restringe ao gabinete; o administrador vê todos).

    Returns:
        Processos com `ingestao: {situacao, por_estado, ultimo_envio}`.
    """
    consulta = select(ProcessoTabela).order_by(ProcessoTabela.criado_em.desc())
    if ator.gabinete_id is not None:
        consulta = consulta.where(ProcessoTabela.gabinete_id == ator.gabinete_id)
    processos = list(sessao.scalars(consulta))
    jobs: dict[UUID, list[tuple[str, datetime]]] = {}
    if processos:
        linhas = sessao.execute(
            select(
                JobIngestaoTabela.processo_id, JobIngestaoTabela.estado, JobIngestaoTabela.criado_em
            ).where(JobIngestaoTabela.processo_id.in_([p.id for p in processos]))
        )
        for processo_id, estado, criado_em in linhas:
            jobs.setdefault(processo_id, []).append((estado, criado_em))
    resultado = []
    for processo in processos:
        do_processo = jobs.get(processo.id, [])
        estados = [estado for estado, _ in do_processo]
        por_estado: dict[str, int] = {}
        for estado in estados:
            por_estado[estado] = por_estado.get(estado, 0) + 1
        resultado.append(
            _serializar(processo)
            | {
                "ingestao": {
                    "situacao": resumir_ingestao(estados),
                    "por_estado": por_estado,
                    "ultimo_envio": max((c for _, c in do_processo), default=None),
                }
            }
        )
    return resultado


@router.post("/processos", status_code=201)
def criar_processo(
    corpo: CorpoProcesso, ator: AtorAutenticado, sessao: SessaoBanco, ctx: ContextoReq
) -> dict[str, Any]:
    """Cria o processo no gabinete do ator (o administrador informa `gabinete_id`).

    Args:
        corpo: Número CNJ, classe, matéria e sigilo.
        ator: Quem cria.
        sessao: Sessão da requisição.
        ctx: Contexto para a auditoria.

    Returns:
        Processo criado.

    Raises:
        PermissaoNegadaError: Papel sem `subir_processo` no gabinete-alvo.
        DadosInvalidosError: Administrador sem gabinete-alvo.
        ConflitoError: Número já cadastrado no gabinete.
    """
    alvo = corpo.gabinete_id or ator.gabinete_id
    if alvo is None:
        raise DadosInvalidosError("informe o gabinete do processo")
    if not pode(ator.papel, Permissao.SUBIR_PROCESSO, ator.gabinete_id, alvo):
        auditar(
            sessao,
            ctx,
            AcaoAuditoria.PROCESSO_CRIADO,
            ResultadoEvento.NEGADO,
            usuario_id=ator.usuario_id,
            gabinete_id=ator.gabinete_id,
            objeto_tipo="processo",
        )
        raise PermissaoNegadaError("ação não permitida para o seu papel")
    existente = sessao.scalar(
        select(ProcessoTabela.id).where(
            ProcessoTabela.gabinete_id == alvo, ProcessoTabela.numero_cnj == corpo.numero_cnj
        )
    )
    if existente is not None:
        raise ConflitoError("número CNJ já cadastrado no gabinete")
    processo = ProcessoTabela(
        id=uuid4(),
        gabinete_id=alvo,
        numero_cnj=corpo.numero_cnj,
        classe=corpo.classe,
        materia=corpo.materia.value,
        sigiloso=corpo.sigiloso,
        status=StatusProcesso.CRIADO.value,
        criado_por=ator.usuario_id,
    )
    sessao.add(processo)
    try:
        sessao.flush()
    except IntegrityError:  # pragma: no cover (corrida entre dois envios iguais)
        raise ConflitoError("número CNJ já cadastrado no gabinete") from None
    sessao.refresh(processo)
    auditar(
        sessao,
        ctx,
        AcaoAuditoria.PROCESSO_CRIADO,
        usuario_id=ator.usuario_id,
        gabinete_id=alvo,
        processo_id=processo.id,
        objeto_tipo="processo",
        objeto_id=str(processo.id),
    )
    return _serializar(processo)


@router.get("/processos/{processo_id}")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def abrir_processo(
    processo: Annotated[ProcessoTabela, Depends(exige_processo)],
) -> dict[str, object]:
    """Devolve os dados do processo; gera `processo_aberto` (e `admin_acesso_conteudo`).

    Args:
        processo: Processo já autorizado.

    Returns:
        Dados básicos do processo.
    """
    return _serializar(processo)


@router.get("/processos/{processo_id}/arquivos")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=False)
def listar_arquivos(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Arquivos do processo com o estado do job de ingestão (para o acompanhamento na tela).

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, status, situacao, arquivos: [...]}`, mais recentes primeiro.
    """
    linhas = sessao.execute(
        select(ArquivoTabela, JobIngestaoTabela)
        .outerjoin(JobIngestaoTabela, JobIngestaoTabela.arquivo_id == ArquivoTabela.id)
        .where(ArquivoTabela.processo_id == processo.id)
        .order_by(ArquivoTabela.enviado_em.desc())
    ).all()
    arquivos = [
        {
            "arquivo_id": arquivo.id,
            "nome": arquivo.nome_original,
            "mime": arquivo.mime,
            "tamanho_bytes": arquivo.tamanho_bytes,
            "enviado_em": arquivo.enviado_em,
            "job_id": job.id if job else None,
            "estado": job.estado if job else None,
            "motivo_quarentena": job.motivo_quarentena if job else None,
            "motivo_falha": job.motivo_falha if job else None,
            "total_paginas": job.total_paginas if job else None,
            "finalizado_em": job.finalizado_em if job else None,
        }
        for arquivo, job in linhas
    ]
    return {
        "processo_id": processo.id,
        "status": processo.status,
        "situacao": resumir_ingestao([a["estado"] for a in arquivos if a["estado"]]),
        "arquivos": arquivos,
    }
