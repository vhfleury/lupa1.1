"""Repositórios mínimos de fatos e achados (o necessário para as Etapas 2 e 3)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lupa.dominio.esquemas import Achado, Evidencia, Fato
from lupa.dominio.tabelas import (
    AchadoTabela,
    EvidenciaTabela,
    FatoEvidenciaTabela,
    FatoTabela,
    ProcessoTabela,
)


class ProcessoNaoEncontradoError(LookupError):
    """O processo não existe ou não é visível no gabinete corrente."""


def _gabinete_do_processo(session: Session, processo_id: UUID) -> UUID:
    gabinete_id = session.scalar(
        select(ProcessoTabela.gabinete_id).where(ProcessoTabela.id == processo_id)
    )
    if gabinete_id is None:
        raise ProcessoNaoEncontradoError(str(processo_id))
    return gabinete_id


def _salvar_evidencia(session: Session, evidencia: Evidencia, gabinete_id: UUID) -> None:
    dados = evidencia.model_dump(mode="json") | {"gabinete_id": str(gabinete_id)}
    session.execute(insert(EvidenciaTabela).values(dados).on_conflict_do_nothing())


def salvar_fato(session: Session, fato: Fato) -> None:
    """Grava o fato, suas evidências e a associação entre eles.

    Args:
        session: Sessão com transação aberta.
        fato: Fato validado (com ao menos uma evidência).

    Raises:
        ProcessoNaoEncontradoError: Se o processo não for visível.
    """
    gabinete_id = _gabinete_do_processo(session, fato.processo_id)
    dados = fato.model_dump(mode="json", exclude={"evidencias"})
    session.execute(insert(FatoTabela).values(dados | {"gabinete_id": str(gabinete_id)}))
    for evidencia in fato.evidencias:
        _salvar_evidencia(session, evidencia, gabinete_id)
        session.execute(
            insert(FatoEvidenciaTabela).values(
                fato_id=fato.id, evidencia_id=evidencia.id, gabinete_id=gabinete_id
            )
        )


def _evidencias_por_fato(session: Session, fato_ids: list[UUID]) -> dict[UUID, list[Evidencia]]:
    linhas = session.execute(
        select(FatoEvidenciaTabela.fato_id, EvidenciaTabela)
        .join(EvidenciaTabela, EvidenciaTabela.id == FatoEvidenciaTabela.evidencia_id)
        .where(FatoEvidenciaTabela.fato_id.in_(fato_ids))
        .order_by(EvidenciaTabela.pagina_id, EvidenciaTabela.inicio)
    ).all()
    resultado: dict[UUID, list[Evidencia]] = {}
    for fato_id, linha in linhas:
        resultado.setdefault(fato_id, []).append(
            Evidencia(
                id=linha.id,
                pagina_id=linha.pagina_id,
                trecho=linha.trecho,
                hash_trecho=linha.hash_trecho,
                inicio=linha.inicio,
                fim=linha.fim,
                bbox=linha.bbox,
            )
        )
    return resultado


def listar_fatos_por_processo(session: Session, processo_id: UUID) -> list[Fato]:
    """Lista os fatos de um processo com suas evidências, em ordem de criação.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo consultado.

    Returns:
        Fatos visíveis no gabinete corrente.
    """
    linhas = session.scalars(
        select(FatoTabela)
        .where(FatoTabela.processo_id == processo_id)
        .order_by(FatoTabela.criado_em, FatoTabela.id)
    ).all()
    evidencias = _evidencias_por_fato(session, [linha.id for linha in linhas])
    return [
        Fato(
            id=linha.id,
            processo_id=linha.processo_id,
            tipo=linha.tipo,
            valor=linha.valor,
            evidencias=tuple(evidencias[linha.id]),
            extraido_por=linha.extraido_por,
            versao_extrator=linha.versao_extrator,
            confianca=linha.confianca,
            status=linha.status,
            substitui_fato_id=linha.substitui_fato_id,
            criado_em=linha.criado_em,
        )
        for linha in linhas
    ]


def salvar_achado(session: Session, achado: Achado) -> None:
    """Grava um achado (imutável depois de inserido).

    Args:
        session: Sessão com transação aberta.
        achado: Achado produzido pelo motor.

    Raises:
        ProcessoNaoEncontradoError: Se o processo não for visível.
    """
    gabinete_id = _gabinete_do_processo(session, achado.processo_id)
    dados = achado.model_dump(mode="json", exclude={"fatos_usados"})
    session.execute(
        insert(AchadoTabela).values(
            dados | {"gabinete_id": str(gabinete_id), "fatos_usados": list(achado.fatos_usados)}
        )
    )


def listar_achados(session: Session, processo_id: UUID) -> list[Achado]:
    """Lista os achados de um processo, em ordem de criação.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo consultado.

    Returns:
        Achados visíveis no gabinete corrente.
    """
    linhas = session.scalars(
        select(AchadoTabela)
        .where(AchadoTabela.processo_id == processo_id)
        .order_by(AchadoTabela.criado_em, AchadoTabela.id)
    ).all()
    return [
        Achado(
            id=linha.id,
            processo_id=linha.processo_id,
            validacao=linha.validacao,
            versao_catalogo=linha.versao_catalogo,
            resultado=linha.resultado,
            fatos_usados=tuple(linha.fatos_usados),
            valores=linha.valores,
            explicacao=linha.explicacao,
            criado_em=linha.criado_em,
        )
        for linha in linhas
    ]
