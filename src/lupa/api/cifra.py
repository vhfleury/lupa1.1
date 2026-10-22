"""Contexto de cifra por requisição (Etapa 7) e configuração do cofre da aplicação.

Cada requisição ganha um `ContextoCifra` vazio. `exige_processo` abre a DEK do processo do
caminho (`ativar_processo`); campos de outros processos lidos sob a RLS são abertos pelo
carregador. No fim da requisição as DEKs abertas são descartadas.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from lupa.config import Settings
from lupa.seguranca.chaves import carregador_sql
from lupa.seguranca.cofre import criar_cofre
from lupa.seguranca.contexto import contexto_cifra, definir_cofre


def configurar_cifra(app: FastAPI, settings: Settings) -> None:
    """Cria o cofre da aplicação e o registra para o processo Python.

    Args:
        app: Aplicação.
        settings: Configuração (`cofre_backend`, `vault_*`).
    """
    app.state.cofre = criar_cofre(settings)
    definir_cofre(app.state.cofre)


async def cifra_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Abre o contexto de cifra da requisição.

    Args:
        request: Requisição recebida.
        call_next: Próximo manipulador da cadeia.

    Returns:
        A resposta.
    """
    with contexto_cifra(carregador_sql(lambda: request.app.state.fabrica_sessao())):
        return await call_next(request)
