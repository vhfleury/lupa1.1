"""Testes da sessão de banco por requisição (confirmação em recusas, desfazer em erros)."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from lupa.acesso.erros import NaoEncontradoError
from lupa.api.banco import sessao_aplicacao
from lupa.dominio.tabelas import GabineteTabela

pytestmark = pytest.mark.integracao


def _existe(engine: Engine, gabinete_id: object) -> bool:
    with Session(engine) as session:
        return session.get(GabineteTabela, gabinete_id) is not None


def _inserir(session: Session) -> object:
    gabinete_id = uuid4()
    session.execute(
        text("INSERT INTO gabinete (id, nome) VALUES (:g, 'teste')"), {"g": gabinete_id}
    )
    return gabinete_id


@pytest.mark.parametrize(
    ("erro", "confirma"),
    [
        (NaoEncontradoError("x"), True),
        (HTTPException(status_code=404), True),
        (RuntimeError("falha inesperada"), False),
    ],
)
def test_recusa_prevista_confirma_e_erro_inesperado_desfaz(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine, erro: Exception, confirma: bool
) -> None:
    """`RecusaAcessoError`/`HTTPException` confirmam; outra exceção desfaz."""
    gravado: list[object] = []
    with pytest.raises(type(erro)), sessao_aplicacao(fabrica_sessao) as session:
        assert session.execute(text("SELECT current_user")).scalar() == "lupa_app"
        gravado.append(_inserir(session))
        raise erro
    assert _existe(engine_teste, gravado[0]) is confirma
