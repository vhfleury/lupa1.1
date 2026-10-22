"""Correção 1 da Revisão da Etapa 3: conteúdo só sai depois de o evento estar gravado."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lupa.api import middleware
from lupa.dominio.enums import Materia, PapelUsuario, StatusProcesso
from lupa.dominio.tabelas import ProcessoTabela
from tests.conftest import (
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    gerar_numero_cnj,
    logar,
)

pytestmark = pytest.mark.integracao

CLASSE_MARCADORA = "Classe marcadora que nao pode vazar"


def test_falha_ao_gravar_auditoria_vira_500_e_o_conteudo_nao_sai(
    app_teste: FastAPI, engine_teste: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se `processo_aberto` não grava, a resposta é 500 sem os dados do processo."""
    assessor = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    processo_id = uuid4()
    with Session(engine_teste) as session, session.begin():
        session.add(
            ProcessoTabela(
                id=processo_id,
                gabinete_id=assessor.gabinete_id,
                numero_cnj=gerar_numero_cnj(int(processo_id.int % 9_000_000) + 1),
                classe=CLASSE_MARCADORA,
                materia=Materia.CRIMINAL.value,
                sigiloso=False,
                status=StatusProcesso.CRIADO.value,
                criado_por=assessor.id,
            )
        )
    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, assessor)

    def _falhar(*_args: object) -> None:
        raise RuntimeError("banco de auditoria indisponível (simulado)")

    monkeypatch.setattr(middleware, "_gravar", _falhar)
    resposta = cliente.get(f"/processos/{processo_id}")
    assert resposta.status_code == 500
    assert resposta.json() == {"detail": middleware.MENSAGEM_FALHA_AUDITORIA}
    assert CLASSE_MARCADORA not in resposta.text
    assert str(processo_id) not in resposta.text
    assert eventos_do_banco(engine_teste, processo_id=processo_id) == []

    monkeypatch.undo()
    ok = cliente.get(f"/processos/{processo_id}")
    assert ok.status_code == 200
    assert ok.json()["classe"] == CLASSE_MARCADORA
    assert [e.acao for e in eventos_do_banco(engine_teste, processo_id=processo_id)] == [
        "processo_aberto"
    ]
