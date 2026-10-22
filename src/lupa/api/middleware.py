"""Middlewares HTTP da API: request_id e auditoria automática de acesso a conteúdo."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from lupa.acesso.servico import Ator, definir_contexto
from lupa.api.banco import sessao_aplicacao
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento
from lupa.auditoria.registrador import registrar
from lupa.dominio.enums import PapelUsuario

CABECALHO_REQUEST_ID = "X-Request-ID"
MENSAGEM_FALHA_AUDITORIA = "falha ao registrar a auditoria; conteúdo não entregue"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Gera um `request_id` por requisição e o expõe no log e no cabeçalho de resposta.

    Args:
        request: Requisição recebida.
        call_next: Próximo manipulador da cadeia.

    Returns:
        A resposta com o cabeçalho `X-Request-ID`.
    """
    request_id = uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers[CABECALHO_REQUEST_ID] = request_id
    return response


@dataclass(frozen=True)
class MarcaAuditoria:
    """Marca posta numa rota para a auditoria automática.

    Attributes:
        acao: Ação registrada quando a rota responde com sucesso.
        conteudo: Se a rota devolve conteúdo de autos (gera `admin_acesso_conteudo` para admin).
    """

    acao: AcaoAuditoria
    conteudo: bool


ATRIBUTO_MARCA = "__lupa_auditoria__"
ACOES_AUTOMATICAS = frozenset(
    {AcaoAuditoria.PROCESSO_ABERTO, AcaoAuditoria.PAGINA_VISTA, AcaoAuditoria.BUSCA}
)

Funcao = TypeVar("Funcao", bound=Callable[..., Any])


def auditar_rota(acao: AcaoAuditoria, *, conteudo: bool) -> Callable[[Funcao], Funcao]:
    """Decora uma rota para que o middleware registre o acesso automaticamente.

    Args:
        acao: `processo_aberto`, `pagina_vista` ou `busca`.
        conteudo: Se a rota devolve conteúdo de autos.

    Returns:
        Decorador que apenas anota a função.

    Raises:
        ValueError: Se a ação não for uma das automáticas.
    """
    if acao not in ACOES_AUTOMATICAS:
        raise ValueError(f"ação {acao} não é registrada automaticamente")

    def _decorar(funcao: Funcao) -> Funcao:
        setattr(funcao, ATRIBUTO_MARCA, MarcaAuditoria(acao, conteudo))
        return funcao

    return _decorar


def _eventos_automaticos(marca: MarcaAuditoria, ator: Ator, request: Request) -> list[NovoEvento]:
    processo_id, gabinete_id = getattr(request.state, "processo", (None, ator.gabinete_id))
    ip = request.client.host if request.client else None
    base = {
        "usuario_id": ator.usuario_id,
        "gabinete_id": gabinete_id,
        "processo_id": processo_id,
        "objeto_tipo": "rota",
        "objeto_id": request.url.path,
        "ip": ip,
        "localizacao": request.app.state.resolvedor.resolver(ip),
    }
    eventos = [NovoEvento(acao=marca.acao, **base)]
    if marca.conteudo and ator.papel is PapelUsuario.ADMINISTRADOR:
        eventos.append(NovoEvento(acao=AcaoAuditoria.ADMIN_ACESSO_CONTEUDO, **base))
    return eventos


def _gravar(fabrica: sessionmaker[Session], ator: Ator, eventos: list[NovoEvento]) -> None:
    with sessao_aplicacao(fabrica) as session:
        definir_contexto(session, ator.papel.value, ator.gabinete_id)
        for evento in eventos:
            registrar(session, evento)


async def auditoria_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Registra `processo_aberto`, `pagina_vista` e `busca` das rotas marcadas.

    Só registra respostas de sucesso de usuário autenticado; tentativas negadas são gravadas
    por `exige_processo`. Quando o usuário é administrador e a rota devolve conteúdo de autos,
    grava também `admin_acesso_conteudo` na cadeia do gabinete do processo.

    O evento é gravado (e confirmado) ANTES de a resposta sair deste middleware: `call_next`
    devolve uma resposta em streaming cujo corpo ainda não foi enviado ao cliente. Se a gravação
    falhar, o corpo é descartado e o cliente recebe 500 sem o conteúdo (Revisão da Etapa 3,
    correção 1: nenhum conteúdo de autos é entregue sem o evento correspondente).

    Args:
        request: Requisição recebida.
        call_next: Próximo manipulador da cadeia.

    Returns:
        A resposta inalterada, ou 500 se a auditoria não pôde ser gravada.
    """
    response = await call_next(request)
    marca = getattr(request.scope.get("endpoint"), ATRIBUTO_MARCA, None)
    ator = getattr(request.state, "ator", None)
    if marca is None or ator is None or response.status_code >= 400:
        return response
    try:
        eventos = _eventos_automaticos(marca, ator, request)
        await run_in_threadpool(_gravar, request.app.state.fabrica_sessao, ator, eventos)
    except Exception:
        structlog.get_logger(__name__).exception("auditoria_automatica_falhou", acao=marca.acao)
        await _descartar_corpo(response)
        return JSONResponse(status_code=500, content={"detail": MENSAGEM_FALHA_AUDITORIA})
    return response


async def _descartar_corpo(response: Response) -> None:
    """Fecha o iterador do corpo da resposta interna sem enviá-lo."""
    iterador = getattr(response, "body_iterator", None)
    fechar = getattr(iterador, "aclose", None)
    if fechar is not None:
        await fechar()
