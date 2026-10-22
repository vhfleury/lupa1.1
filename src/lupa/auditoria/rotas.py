"""Endpoints de consulta, exportação, verificação e relatório de uso da auditoria."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from lupa.acesso.autorizacao import ContextoReq, SessaoBanco, exige_gabinete, exige_papel
from lupa.acesso.erros import DadosInvalidosError
from lupa.acesso.papeis import Permissao
from lupa.acesso.servico import Ator, Contexto, auditar
from lupa.auditoria import consulta
from lupa.auditoria.consulta import CursorInvalidoError, FiltroAuditoria
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.auditoria.registrador import verificar_cadeia
from lupa.dominio.esquemas import EventoAuditoria

router = APIRouter(prefix="/auditoria")

GabineteAlvo = Annotated[UUID | None, Depends(exige_gabinete(Permissao.VER_AUDITORIA))]
Auditor = Annotated[Ator, Depends(exige_papel(Permissao.VER_AUDITORIA))]


class PaginaSaida(BaseModel):
    """Página de eventos."""

    eventos: list[EventoAuditoria]
    proximo_cursor: str | None


class VerificacaoSaida(BaseModel):
    """Resultado da verificação da cadeia."""

    gabinete_id: UUID | None
    integra: bool
    total: int
    primeiro_evento_quebrado: UUID | None
    motivo: str | None


def filtros(
    gabinete_id: GabineteAlvo,
    usuario_id: UUID | None = None,
    processo_id: UUID | None = None,
    acao: AcaoAuditoria | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    ip: str | None = Query(default=None, max_length=64),
) -> FiltroAuditoria:
    """Monta o filtro a partir da query string; o gabinete já vem resolvido pela autorização.

    Args:
        gabinete_id: Gabinete-alvo (próprio, ou qualquer/None para o administrador).
        usuario_id: Usuário.
        processo_id: Processo.
        acao: Ação.
        inicio: Início do intervalo (inclusive).
        fim: Fim do intervalo (exclusivo).
        ip: IP.

    Returns:
        Filtro da consulta.
    """
    return FiltroAuditoria(gabinete_id, usuario_id, processo_id, acao, inicio, fim, ip)


Filtro = Annotated[FiltroAuditoria, Depends(filtros)]


def _auditar_ato(
    session: SessaoBanco, ctx: Contexto, ator: Ator, acao: AcaoAuditoria, filtro: FiltroAuditoria
) -> None:
    auditar(
        session,
        ctx,
        acao,
        usuario_id=ator.usuario_id,
        gabinete_id=ator.gabinete_id,
        processo_id=filtro.processo_id,
        objeto_tipo="auditoria",
        objeto_id=str(filtro.gabinete_id) if filtro.gabinete_id else None,
    )


@router.get("")
def listar(
    filtro: Filtro,
    ator: Auditor,
    session: SessaoBanco,
    ctx: ContextoReq,
    cursor: str | None = Query(default=None, max_length=200),
    limite: int = Query(default=consulta.LIMITE_PADRAO, ge=1, le=consulta.LIMITE_MAXIMO),
) -> PaginaSaida:
    """Consulta eventos com filtros e paginação por cursor (mais recentes primeiro).

    Args:
        filtro: Filtros.
        ator: Usuário com permissão de ver auditoria.
        session: Sessão do banco.
        ctx: Contexto da requisição.
        cursor: Cursor da página anterior.
        limite: Tamanho da página.

    Returns:
        Página de eventos.

    Raises:
        DadosInvalidosError: Cursor malformado.
    """
    try:
        pagina = consulta.consultar(session, filtro, cursor, limite)
    except CursorInvalidoError as erro:
        raise DadosInvalidosError(str(erro)) from erro
    _auditar_ato(session, ctx, ator, AcaoAuditoria.AUDITORIA_CONSULTADA, filtro)
    return PaginaSaida(eventos=pagina.eventos, proximo_cursor=pagina.proximo_cursor)


@router.get("/exportar")
def exportar(
    filtro: Filtro,
    ator: Auditor,
    session: SessaoBanco,
    ctx: ContextoReq,
    formato: Literal["csv", "json"] = "csv",
) -> Response:
    """Exporta os eventos filtrados em CSV ou JSON; o próprio ato é registrado.

    Args:
        filtro: Filtros.
        ator: Usuário com permissão de ver auditoria.
        session: Sessão do banco.
        ctx: Contexto da requisição.
        formato: `csv` ou `json`.

    Returns:
        Arquivo para download.
    """
    eventos = consulta.iterar_para_exportacao(session, filtro)
    if formato == "csv":
        corpo, tipo = consulta.exportar_csv(eventos), "text/csv; charset=utf-8"
    else:
        corpo, tipo = consulta.exportar_json(eventos), "application/json"
    _auditar_ato(session, ctx, ator, AcaoAuditoria.AUDITORIA_EXPORTADA, filtro)
    cabecalho = {"Content-Disposition": f'attachment; filename="auditoria.{formato}"'}
    return Response(content=corpo, media_type=tipo, headers=cabecalho)


@router.get("/verificar")
def verificar(gabinete_id: GabineteAlvo, _ator: Auditor, session: SessaoBanco) -> VerificacaoSaida:
    """Percorre a cadeia do gabinete (administrador sem gabinete: cadeia global).

    Args:
        gabinete_id: Gabinete-alvo.
        _ator: Usuário com permissão de ver auditoria.
        session: Sessão do banco.

    Returns:
        Se a cadeia está íntegra e, se não, o primeiro evento quebrado.
    """
    resultado = verificar_cadeia(session, gabinete_id)
    return VerificacaoSaida(
        gabinete_id=gabinete_id,
        integra=resultado.integra,
        total=resultado.total,
        primeiro_evento_quebrado=resultado.primeiro_evento_quebrado,
        motivo=resultado.motivo,
    )


@router.get("/relatorio-uso")
def relatorio_uso(
    gabinete_id: GabineteAlvo,
    _ator: Auditor,
    session: SessaoBanco,
    processo: UUID | None = None,
    usuario: UUID | None = None,
) -> dict[str, object]:
    """Relatório de uso por processo ou por usuário, para informar o tribunal.

    Args:
        gabinete_id: Gabinete-alvo.
        _ator: Usuário com permissão de ver auditoria.
        session: Sessão do banco.
        processo: Processo (informe este ou `usuario`).
        usuario: Usuário (informe este ou `processo`).

    Returns:
        Contagem por ação, primeiro e último acesso e versões do modelo.

    Raises:
        DadosInvalidosError: Se não vier exatamente um entre `processo` e `usuario`.
    """
    if (processo is None) == (usuario is None):
        raise DadosInvalidosError("informe exatamente um: processo ou usuario")
    filtro = FiltroAuditoria(gabinete_id=gabinete_id, processo_id=processo, usuario_id=usuario)
    return {
        "processo": processo,
        "usuario": usuario,
        **consulta.relatorio_uso(session, filtro),
    }
