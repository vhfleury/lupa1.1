"""Sessão de banco por requisição, sempre sob o papel `lupa_app` (sujeito à RLS).

Recusas previstas (`RecusaAcessoError`, `HTTPException`) confirmam a transação, para que o evento de
auditoria da recusa fique gravado; qualquer outra exceção desfaz tudo.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from lupa.acesso.erros import RecusaAcessoError
from lupa.config import Settings
from lupa.dominio.sessao import assumir_papel_aplicacao


def configurar_banco(app: FastAPI, settings: Settings) -> None:
    """Cria o engine (sem conectar) e a fábrica de sessões da aplicação.

    Args:
        app: Aplicação.
        settings: Configuração; usa `url_banco_aplicacao()`.
    """
    engine = create_engine(settings.url_banco_aplicacao(), pool_pre_ping=True)
    app.state.fabrica_sessao = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def sessao_aplicacao(fabrica: sessionmaker[Session]) -> Iterator[Session]:
    """Abre sessão com transação sob `lupa_app`, confirmando no fim e em recusas previstas.

    Args:
        fabrica: Fábrica de sessões.

    Yields:
        Sessão pronta para uso.
    """
    with fabrica() as session:
        session.begin()
        assumir_papel_aplicacao(session)
        try:
            yield session
        except (RecusaAcessoError, HTTPException):
            session.commit()
            raise
        except BaseException:
            session.rollback()
            raise
        session.commit()


def obter_sessao_banco(request: Request) -> Iterator[Session]:
    """Dependência FastAPI: sessão da requisição.

    Args:
        request: Requisição corrente.

    Yields:
        Sessão sob `lupa_app`.
    """
    with sessao_aplicacao(request.app.state.fabrica_sessao) as session:
        yield session
