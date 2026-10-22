"""Processo em revisão após incidente do agente (Etapa 6.8; `prompt-injection.md`, seção 8).

Quando a conferência bloqueia a resposta do modelo (instrução refletida ou identificador de
outro processo), o processo passa a `em_revisao`: o chat e os resumos do dossiê ficam
bloqueados até um desembargador do gabinete ou o administrador liberar. A abertura e a
liberação vão para a trilha de auditoria (sem conteúdo).
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from lupa.acesso.erros import ConflitoError
from lupa.acesso.servico import Contexto, auditar
from lupa.auditoria.eventos import AcaoAuditoria, ResultadoEvento
from lupa.dominio.enums import StatusProcesso
from lupa.dominio.tabelas import ProcessoTabela, RevisaoProcessoTabela

MSG_EM_REVISAO = (
    "Este processo está em revisão: uma resposta do assistente foi bloqueada por conter "
    "instrução ou dado de outro processo. O chat e os resumos gerados ficam suspensos até um "
    "desembargador ou o administrador liberar."
)


def em_revisao(processo: ProcessoTabela) -> bool:
    """Se o processo está em revisão.

    Args:
        processo: Processo.

    Returns:
        Verdadeiro se `status == em_revisao`.
    """
    return processo.status == StatusProcesso.EM_REVISAO.value


def revisao_aberta(session: Session, processo_id: UUID) -> RevisaoProcessoTabela | None:
    """Incidente ainda não liberado do processo.

    Args:
        session: Sessão.
        processo_id: Processo.

    Returns:
        A revisão aberta mais recente, ou None.
    """
    consulta = (
        select(RevisaoProcessoTabela)
        .where(
            RevisaoProcessoTabela.processo_id == processo_id,
            RevisaoProcessoTabela.liberada_em.is_(None),
        )
        .order_by(RevisaoProcessoTabela.aberta_em.desc())
        .limit(1)
    )
    return session.scalar(consulta)


def abrir(
    session: Session, ctx: Contexto, processo: ProcessoTabela, motivo: str, usuario_id: UUID
) -> None:
    """Põe o processo em revisão (idempotente) e registra o incidente.

    Args:
        session: Sessão.
        ctx: Contexto da requisição.
        processo: Processo.
        motivo: `instrucao_refletida` ou `outro_processo`.
        usuario_id: Quem fez a pergunta que gerou o incidente.
    """
    if not em_revisao(processo):
        session.add(
            RevisaoProcessoTabela(
                id=uuid4(),
                gabinete_id=processo.gabinete_id,
                processo_id=processo.id,
                motivo=motivo,
                status_anterior=processo.status,
            )
        )
        processo.status = StatusProcesso.EM_REVISAO.value
        session.flush()
    auditar(
        session,
        ctx,
        AcaoAuditoria.PROCESSO_EM_REVISAO,
        ResultadoEvento.BLOQUEADO,
        usuario_id=usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo="incidente",
        objeto_id=motivo,
    )


def liberar(
    session: Session, ctx: Contexto, processo: ProcessoTabela, usuario_id: UUID
) -> dict[str, Any]:
    """Libera o processo, devolvendo o status anterior, e registra a liberação.

    Args:
        session: Sessão.
        ctx: Contexto da requisição.
        processo: Processo autorizado.
        usuario_id: Quem libera.

    Returns:
        Situação depois da liberação.

    Raises:
        ConflitoError: Processo não está em revisão.
    """
    if not em_revisao(processo):
        raise ConflitoError("o processo não está em revisão")
    revisao = revisao_aberta(session, processo.id)
    anterior = revisao.status_anterior if revisao else StatusProcesso.PRONTO.value
    if revisao is not None:
        revisao.liberada_em = ctx.agora
        revisao.liberada_por = usuario_id
    processo.status = anterior
    session.flush()
    auditar(
        session,
        ctx,
        AcaoAuditoria.REVISAO_LIBERADA,
        usuario_id=usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo="processo",
        objeto_id=str(processo.id),
    )
    return situacao(session, processo)


def situacao(session: Session, processo: ProcessoTabela) -> dict[str, Any]:
    """Situação de revisão do processo para a interface.

    Args:
        session: Sessão.
        processo: Processo.

    Returns:
        `{processo_id, status, em_revisao, motivo, aberta_em}`.
    """
    revisao = revisao_aberta(session, processo.id) if em_revisao(processo) else None
    return {
        "processo_id": str(processo.id),
        "status": processo.status,
        "em_revisao": em_revisao(processo),
        "motivo": revisao.motivo if revisao else None,
        "aberta_em": revisao.aberta_em.isoformat() if revisao and revisao.aberta_em else None,
    }
