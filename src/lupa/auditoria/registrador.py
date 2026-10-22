"""Gravação de eventos com hash encadeado e verificação da cadeia.

Cada gabinete tem sua cadeia; eventos sem gabinete formam a cadeia global. A função de banco
`lupa_travar_cadeia` (migração 0002) toma um advisory lock da cadeia e faz `SELECT ... FOR
UPDATE` do último evento, na transação de quem registra; assim dois registros concorrentes na
mesma cadeia são serializados. A unicidade `(gabinete_id, sequencia)` é a última barreira.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from lupa.auditoria.eventos import NovoEvento, calcular_hash_evento, hash_confere
from lupa.dominio.esquemas import EventoAuditoria
from lupa.dominio.tabelas import EventoAuditoriaTabela

LOTE_VERIFICACAO = 2000


@dataclass(frozen=True)
class ResultadoVerificacao:
    """Resultado da verificação de uma cadeia.

    Attributes:
        integra: Verdadeiro se todos os elos conferem.
        total: Quantidade de eventos percorridos.
        primeiro_evento_quebrado: Id do primeiro evento com problema, se houver.
        motivo: Descrição do problema (`hash`, `encadeamento` ou `sequencia`).
    """

    integra: bool
    total: int
    primeiro_evento_quebrado: UUID | None = None
    motivo: str | None = None


def _travar_cadeia(session: Session, gabinete_id: UUID | None) -> tuple[str | None, int]:
    linha = session.execute(
        text("SELECT hash_evento, sequencia FROM lupa_travar_cadeia(:gabinete)"),
        {"gabinete": gabinete_id},
    ).first()
    if linha is None:
        return None, 1
    return str(linha.hash_evento), int(linha.sequencia) + 1


def registrar(session: Session, evento: NovoEvento) -> EventoAuditoria:
    """Grava o evento no fim da cadeia do seu gabinete, na transação da sessão.

    Args:
        session: Sessão com transação aberta e contexto de RLS que permita inserir o evento.
        evento: Evento a registrar.

    Returns:
        O evento gravado, com hash, sequência e instante.
    """
    hash_anterior, sequencia = _travar_cadeia(session, evento.gabinete_id)
    campos: dict[str, Any] = evento.model_dump(mode="python")
    campos["acao"] = evento.acao.value
    campos["resultado"] = evento.resultado.value
    campos.update(id=uuid4(), sequencia=sequencia, ocorrido_em=datetime.now(UTC))
    campos["hash_anterior"] = hash_anterior
    campos["hash_evento"] = calcular_hash_evento(hash_anterior, campos)
    session.execute(insert(EventoAuditoriaTabela).values(**campos))
    return EventoAuditoria(**campos)


def _para_esquema(linha: EventoAuditoriaTabela) -> EventoAuditoria:
    return EventoAuditoria(
        **{coluna: getattr(linha, coluna) for coluna in EventoAuditoria.model_fields}
    )


def _eventos_da_cadeia(session: Session, gabinete_id: UUID | None) -> Iterator[EventoAuditoria]:
    filtro = (
        EventoAuditoriaTabela.gabinete_id.is_(None)
        if gabinete_id is None
        else EventoAuditoriaTabela.gabinete_id == gabinete_id
    )
    consulta = (
        select(EventoAuditoriaTabela)
        .where(filtro)
        .order_by(EventoAuditoriaTabela.sequencia)
        .execution_options(yield_per=LOTE_VERIFICACAO)
    )
    for linha in session.scalars(consulta):
        yield _para_esquema(linha)


def _problema(evento: EventoAuditoria, anterior: str | None, esperada: int) -> str | None:
    if evento.sequencia != esperada:
        return "sequencia"
    if evento.hash_anterior != anterior:
        return "encadeamento"
    if not hash_confere(evento):
        return "hash"
    return None


def verificar_cadeia(session: Session, gabinete_id: UUID | None) -> ResultadoVerificacao:
    """Percorre a cadeia do gabinete e aponta o primeiro evento quebrado.

    Args:
        session: Sessão com contexto de RLS que enxergue a cadeia.
        gabinete_id: Gabinete da cadeia, ou None para a cadeia global.

    Returns:
        Resultado com integridade, total e, se houver, o primeiro evento quebrado.
    """
    anterior: str | None = None
    total = 0
    for evento in _eventos_da_cadeia(session, gabinete_id):
        total += 1
        motivo = _problema(evento, anterior, total)
        if motivo is not None:
            return ResultadoVerificacao(False, total, evento.id, motivo)
        anterior = evento.hash_evento
    return ResultadoVerificacao(True, total)
