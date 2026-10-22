"""Rotas consumidas pela interface (Etapa 6): sessão corrente e lista de gabinetes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from lupa.dominio.enums import PapelUsuario
from tests.conftest import criar_gabinete_teste, criar_usuario_teste, logar

pytestmark = pytest.mark.integracao


def test_sessao_devolve_usuario_e_permissoes_do_papel(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """Desembargador vê as próprias permissões; sem cookie, 401."""
    cliente = TestClient(app_teste, base_url="https://testserver")
    assert cliente.get("/auth/sessao").status_code == 401
    gabinete = criar_gabinete_teste(engine_teste)
    usuario = criar_usuario_teste(engine_teste, PapelUsuario.DESEMBARGADOR, gabinete)
    logar(cliente, engine_teste, usuario)
    corpo = cliente.get("/auth/sessao").json()
    assert corpo["nome_usuario"] == usuario.nome
    assert corpo["papel"] == "desembargador"
    assert corpo["gabinete_id"] == str(gabinete)
    assert corpo["troca_senha_obrigatoria"] is False
    assert "gerir_assessor" in corpo["permissoes"]
    assert "gerir_gabinetes" not in corpo["permissoes"]


def test_sessao_responde_mesmo_com_troca_de_senha_pendente(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """A interface precisa saber que deve levar à troca de senha."""
    cliente = TestClient(app_teste, base_url="https://testserver")
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste), troca_senha=True
    )
    logar(cliente, engine_teste, usuario)
    assert cliente.get("/auth/sessao").json()["troca_senha_obrigatoria"] is True


def test_lista_de_gabinetes_so_para_administrador(app_teste: FastAPI, engine_teste: Engine) -> None:
    """Admin lista todos os gabinetes; desembargador recebe 403."""
    gabinete = criar_gabinete_teste(engine_teste)
    admin = TestClient(app_teste, base_url="https://testserver")
    logar(admin, engine_teste, criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None))
    ids = [g["id"] for g in admin.get("/gabinetes").json()]
    assert str(gabinete) in ids
    desembargador = TestClient(app_teste, base_url="https://testserver")
    logar(
        desembargador,
        engine_teste,
        criar_usuario_teste(engine_teste, PapelUsuario.DESEMBARGADOR, gabinete),
    )
    assert desembargador.get("/gabinetes").status_code == 403
