"""Consulta da auditoria: filtros, paginação por cursor, exportação e relatório de uso.

A visibilidade por gabinete é garantida pela RLS; os filtros aqui só restringem.
A ordem é do mais recente para o mais antigo (`ocorrido_em DESC, id DESC`), e o cursor carrega
o par do último evento da página.
"""

import base64
import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, String, and_, cast, exists, func, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from lupa.agente.precos import TabelaPrecos, custo, tabela_padrao
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.esquemas import EventoAuditoria
from lupa.dominio.tabelas import ChamadaModeloTabela as Chamada
from lupa.dominio.tabelas import ConversaTabela
from lupa.dominio.tabelas import EventoAuditoriaTabela as Evento

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 500
LIMITE_EXPORTACAO = 100_000


class CursorInvalidoError(ValueError):
    """O cursor recebido não pôde ser decodificado."""


@dataclass(frozen=True)
class FiltroAuditoria:
    """Filtros da consulta; campos None não filtram.

    Attributes:
        gabinete_id: Gabinete.
        usuario_id: Usuário que agiu.
        processo_id: Processo envolvido.
        acao: Ação.
        inicio: Instante inicial (inclusive).
        fim: Instante final (exclusivo).
        ip: IP de origem.
    """

    gabinete_id: UUID | None = None
    usuario_id: UUID | None = None
    processo_id: UUID | None = None
    acao: AcaoAuditoria | None = None
    inicio: datetime | None = None
    fim: datetime | None = None
    ip: str | None = None


@dataclass(frozen=True)
class PaginaEventos:
    """Uma página de eventos.

    Attributes:
        eventos: Eventos da página, do mais recente ao mais antigo.
        proximo_cursor: Cursor da página seguinte, ou None se acabou.
    """

    eventos: list[EventoAuditoria]
    proximo_cursor: str | None


def codificar_cursor(evento: EventoAuditoria) -> str:
    """Codifica o cursor a partir do último evento da página.

    Args:
        evento: Último evento devolvido.

    Returns:
        Cursor opaco em base64 url-safe.
    """
    bruto = f"{evento.ocorrido_em.isoformat()}|{evento.id}"
    return base64.urlsafe_b64encode(bruto.encode()).decode()


def decodificar_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decodifica o cursor.

    Args:
        cursor: Cursor recebido.

    Returns:
        Par (ocorrido_em, id).

    Raises:
        CursorInvalidoError: Se o cursor estiver malformado.
    """
    try:
        instante, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(instante), UUID(ident)
    except ValueError as erro:
        raise CursorInvalidoError("cursor inválido") from erro


def _aplicar_filtros(consulta: Select[Any], filtro: FiltroAuditoria) -> Select[Any]:
    igualdades = {
        Evento.gabinete_id: filtro.gabinete_id,
        Evento.usuario_id: filtro.usuario_id,
        Evento.processo_id: filtro.processo_id,
        Evento.acao: filtro.acao.value if filtro.acao else None,
        Evento.ip: filtro.ip,
    }
    for coluna, valor in igualdades.items():
        if valor is not None:
            consulta = consulta.where(coluna == valor)
    if filtro.inicio is not None:
        consulta = consulta.where(Evento.ocorrido_em >= filtro.inicio)
    if filtro.fim is not None:
        consulta = consulta.where(Evento.ocorrido_em < filtro.fim)
    return consulta


def _para_esquema(linha: Evento) -> EventoAuditoria:
    return EventoAuditoria(
        **{coluna: getattr(linha, coluna) for coluna in EventoAuditoria.model_fields}
    )


def consultar(
    session: Session,
    filtro: FiltroAuditoria,
    cursor: str | None = None,
    limite: int = LIMITE_PADRAO,
) -> PaginaEventos:
    """Consulta uma página de eventos.

    Args:
        session: Sessão com contexto de RLS.
        filtro: Filtros.
        cursor: Cursor devolvido pela página anterior.
        limite: Tamanho da página (até `LIMITE_MAXIMO`).

    Returns:
        A página e o cursor da próxima.
    """
    limite = max(1, min(limite, LIMITE_MAXIMO))
    consulta = _aplicar_filtros(select(Evento), filtro)
    if cursor is not None:
        instante, ident = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(Evento.ocorrido_em, Evento.id) < tuple_(literal(instante), literal(ident))
        )
    consulta = consulta.order_by(Evento.ocorrido_em.desc(), Evento.id.desc()).limit(limite + 1)
    eventos = [_para_esquema(linha) for linha in session.scalars(consulta)]
    proximo = codificar_cursor(eventos[limite - 1]) if len(eventos) > limite else None
    return PaginaEventos(eventos[:limite], proximo)


def iterar_para_exportacao(session: Session, filtro: FiltroAuditoria) -> Iterator[EventoAuditoria]:
    """Percorre os eventos filtrados, até `LIMITE_EXPORTACAO`, do mais antigo ao mais recente.

    Args:
        session: Sessão com contexto de RLS.
        filtro: Filtros.

    Yields:
        Eventos em ordem cronológica.
    """
    consulta = (
        _aplicar_filtros(select(Evento), filtro)
        .order_by(Evento.ocorrido_em, Evento.id)
        .limit(LIMITE_EXPORTACAO)
        .execution_options(yield_per=1000)
    )
    for linha in session.scalars(consulta):
        yield _para_esquema(linha)


def exportar_csv(eventos: Iterator[EventoAuditoria]) -> str:
    """Serializa eventos em CSV com cabeçalho.

    Args:
        eventos: Eventos a exportar.

    Returns:
        Texto CSV.
    """
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=list(EventoAuditoria.model_fields))
    escritor.writeheader()
    for evento in eventos:
        escritor.writerow(evento.model_dump(mode="json"))
    return saida.getvalue()


def exportar_json(eventos: Iterator[EventoAuditoria]) -> str:
    """Serializa eventos em JSON (lista de objetos).

    Args:
        eventos: Eventos a exportar.

    Returns:
        Texto JSON.
    """
    return json.dumps([evento.model_dump(mode="json") for evento in eventos], ensure_ascii=False)


def relatorio_uso(session: Session, filtro: FiltroAuditoria) -> dict[str, Any]:
    """Resume o uso por processo ou por usuário, para o magistrado informar o tribunal.

    Args:
        session: Sessão com contexto de RLS.
        filtro: Filtro com `processo_id` ou `usuario_id`.

    Returns:
        Contagem por ação, primeiro e último acesso e versões de modelo/prompt usadas.
    """
    por_acao = session.execute(
        _aplicar_filtros(
            select(
                Evento.acao,
                func.count(),
                func.min(Evento.ocorrido_em),
                func.max(Evento.ocorrido_em),
            ),
            filtro,
        ).group_by(Evento.acao)
    ).all()
    versoes = session.execute(
        _aplicar_filtros(
            select(Evento.versao_modelo, Evento.versao_prompt, func.count()),
            FiltroAuditoria(**{**filtro.__dict__, "acao": AcaoAuditoria.CHAMADA_MODELO}),
        )
        .group_by(Evento.versao_modelo, Evento.versao_prompt)
        .order_by(Evento.versao_modelo, Evento.versao_prompt)
    ).all()
    return {
        "contagem_por_acao": {acao: total for acao, total, _, _ in por_acao},
        "primeiro_acesso": min((linha[2] for linha in por_acao), default=None),
        "ultimo_acesso": max((linha[3] for linha in por_acao), default=None),
        "chamadas_modelo": [
            {"versao_modelo": modelo, "versao_prompt": prompt, "total": total}
            for modelo, prompt, total in versoes
        ],
        "custo_estimado": custo_estimado(session, filtro),
    }


def _tokens_por_modelo(session: Session, filtro: FiltroAuditoria) -> list[tuple[str, int, int]]:
    consulta = select(
        Chamada.modelo,
        func.coalesce(func.sum(Chamada.tokens_entrada), 0),
        func.coalesce(func.sum(Chamada.tokens_saida), 0),
    )
    if filtro.usuario_id is not None:
        # Chat: chamadas das conversas do usuário. Resumos do dossiê (sem conversa, 6.10): o
        # evento `chamada_modelo` que aponta para a chamada diz quem pediu o resumo.
        do_resumo = exists().where(
            Evento.acao == AcaoAuditoria.CHAMADA_MODELO.value,
            Evento.objeto_id == cast(Chamada.id, String),
            Evento.usuario_id == filtro.usuario_id,
        )
        consulta = consulta.outerjoin(
            ConversaTabela, ConversaTabela.id == Chamada.conversa_id
        ).where(
            or_(
                ConversaTabela.usuario_id == filtro.usuario_id,
                and_(Chamada.conversa_id.is_(None), do_resumo),
            )
        )
    if filtro.processo_id is not None:
        consulta = consulta.where(Chamada.processo_id == filtro.processo_id)
    if filtro.gabinete_id is not None:
        consulta = consulta.where(Chamada.gabinete_id == filtro.gabinete_id)
    linhas = session.execute(consulta.group_by(Chamada.modelo).order_by(Chamada.modelo)).all()
    return [(str(m), int(e), int(s)) for m, e, s in linhas]


def custo_estimado(
    session: Session, filtro: FiltroAuditoria, tabela: TabelaPrecos | None = None
) -> dict[str, Any]:
    """Custo estimado em dinheiro das chamadas ao modelo (tokens de `chamada_modelo`).

    Por usuário, conta as chamadas das conversas dele e, desde a 6.10, os resumos do dossiê
    que ele pediu (sem conversa; o autor vem do evento `chamada_modelo` da chamada).

    Args:
        session: Sessão com contexto de RLS.
        filtro: Filtro com `processo_id` ou `usuario_id` (e o gabinete).
        tabela: Tabela de preços (padrão: `agente/dados/precos.yaml`).

    Returns:
        Total, moeda, versão e fonte da tabela, ressalva e detalhamento por modelo; modelo fora
        da tabela aparece com custo None e não entra no total.
    """
    tabela = tabela or tabela_padrao()
    por_modelo = []
    total = Decimal("0.0000")
    for modelo, entrada, saida in _tokens_por_modelo(session, filtro):
        preco = tabela.preco_de(modelo)
        valor = custo(preco, entrada, saida) if preco else None
        total += valor or 0
        por_modelo.append(
            {
                "modelo": modelo,
                "tokens_entrada": entrada,
                "tokens_saida": saida,
                "custo": str(valor) if valor is not None else None,
            }
        )
    return {
        "total": str(total),
        "moeda": tabela.moeda,
        "versao_tabela": tabela.versao,
        "fonte": tabela.fonte,
        "observacao": tabela.observacao,
        "por_modelo": por_modelo,
    }
