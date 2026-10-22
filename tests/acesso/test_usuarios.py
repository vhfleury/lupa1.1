"""Testes da gestão de usuários e gabinetes pela API, conferindo papéis e gabinetes."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from lupa.dominio.enums import PapelUsuario
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
)

pytestmark = pytest.mark.integracao


def _cliente_logado(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


def _nome() -> str:
    return f"novo_{uuid4().hex[:10]}"


@pytest.fixture
def desembargador(engine_teste: Engine) -> UsuarioTeste:
    """Desembargador de um gabinete novo."""
    return criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )


@pytest.fixture
def administrador(engine_teste: Engine) -> UsuarioTeste:
    """Administrador (sem gabinete)."""
    return criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)


def test_desembargador_nao_consegue_criar_assessor_em_outro_gabinete(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """403 ao criar em outro gabinete; a tentativa negada fica na auditoria."""
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    outro = criar_gabinete_teste(engine_teste)
    resposta = cliente.post(
        "/usuarios",
        json={"nome_usuario": _nome(), "papel": "assessor", "gabinete_id": str(outro)},
    )
    assert resposta.status_code == 403
    negados = eventos_do_banco(
        engine_teste, usuario_id=desembargador.id, acao="usuario_criado", resultado="negado"
    )
    assert len(negados) == 1
    assert negados[0].gabinete_id == desembargador.gabinete_id


def test_desembargador_cria_assessor_no_proprio_gabinete_com_troca_obrigatoria(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Sem gabinete informado, usa o do desembargador; senha temporária vem uma vez."""
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    nome = _nome()
    resposta = cliente.post("/usuarios", json={"nome_usuario": nome, "papel": "assessor"})
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["gabinete_id"] == str(desembargador.gabinete_id)
    assert corpo["troca_senha_obrigatoria"] is True
    assert len(corpo["senha_temporaria"]) >= 20
    assert nome in {u["nome_usuario"] for u in cliente.get("/usuarios").json()}
    repetido = cliente.post("/usuarios", json={"nome_usuario": nome, "papel": "assessor"})
    assert repetido.status_code == 409
    invalido = cliente.post("/usuarios", json={"nome_usuario": "A B", "papel": "assessor"})
    assert invalido.status_code == 422


def test_desembargador_nao_cria_desembargador_nem_administrador(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Criar desembargador é só do administrador; administrador não é criado pela API."""
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    for papel in ("desembargador", "administrador"):
        resposta = cliente.post("/usuarios", json={"nome_usuario": _nome(), "papel": papel})
        assert resposta.status_code == 403, papel


def test_assessor_nao_gere_usuarios(app_teste: FastAPI, engine_teste: Engine) -> None:
    """Assessor não lista nem cria usuários."""
    assessor = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    cliente = _cliente_logado(app_teste, engine_teste, assessor)
    assert cliente.get("/usuarios").status_code == 403
    criar = cliente.post("/usuarios", json={"nome_usuario": _nome(), "papel": "assessor"})
    assert criar.status_code == 403


def test_administrador_cria_gabinete_e_desembargador(
    app_teste: FastAPI, engine_teste: Engine, administrador: UsuarioTeste
) -> None:
    """Admin cria gabinete e desembargador nele; lista usuários de qualquer gabinete."""
    cliente = _cliente_logado(app_teste, engine_teste, administrador)
    gabinete = cliente.post("/gabinetes", json={"nome": "Gabinete Sintético"})
    assert gabinete.status_code == 201
    gabinete_id = gabinete.json()["id"]
    novo = cliente.post(
        "/usuarios",
        json={"nome_usuario": _nome(), "papel": "desembargador", "gabinete_id": gabinete_id},
    )
    assert novo.status_code == 201
    listados = cliente.get("/usuarios", params={"gabinete_id": gabinete_id}).json()
    assert [u["papel"] for u in listados] == ["desembargador"]
    assert len(cliente.get("/usuarios").json()) >= 2
    sem_gabinete = cliente.post("/usuarios", json={"nome_usuario": _nome(), "papel": "assessor"})
    assert sem_gabinete.status_code == 404
    assert eventos_do_banco(engine_teste, acao="gabinete_criado", gabinete_id=gabinete_id)


def test_desembargador_nao_cria_gabinete(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Gerir gabinetes é só do administrador."""
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    assert cliente.post("/gabinetes", json={"nome": "Outro"}).status_code == 403


def test_desembargador_reseta_senha_e_mfa_do_assessor(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Reset de senha força troca e derruba as sessões; reset de MFA exige novo cadastro."""
    assessor = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, desembargador.gabinete_id)
    sessao_assessor = _cliente_logado(app_teste, engine_teste, assessor)
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    reset = cliente.post(f"/usuarios/{assessor.id}/resetar-senha")
    assert reset.status_code == 200
    assert reset.json()["troca_senha_obrigatoria"] is True
    assert sessao_assessor.get("/processos/" + str(uuid4())).status_code == 401
    temporaria = reset.json()["senha_temporaria"]
    login = sessao_assessor.post(
        "/auth/login", json={"nome_usuario": assessor.nome, "senha": temporaria}
    )
    assert login.json()["etapa"] == "mfa"
    mfa = cliente.post(f"/usuarios/{assessor.id}/resetar-mfa")
    assert mfa.status_code == 200 and mfa.json()["mfa_confirmado"] is False
    login = sessao_assessor.post(
        "/auth/login", json={"nome_usuario": assessor.nome, "senha": temporaria}
    )
    assert login.json()["etapa"] == "configurar_mfa"
    acoes = {e.acao for e in eventos_do_banco(engine_teste, usuario_id=desembargador.id)}
    assert {"senha_resetada", "mfa_resetado"} <= acoes


def test_desativar_impede_login_e_reativar_devolve_acesso(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Desativado não entra; reativado entra; histórico de auditoria permanece."""
    assessor = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, desembargador.gabinete_id)
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    assert cliente.post(f"/usuarios/{assessor.id}/desativar").json()["ativo"] is False
    tentativa = TestClient(app_teste, base_url="https://testserver")
    with pytest.raises(AssertionError):
        logar(tentativa, engine_teste, assessor)
    assert cliente.post(f"/usuarios/{assessor.id}/reativar").json()["ativo"] is True
    logar(tentativa, engine_teste, assessor)
    assert eventos_do_banco(engine_teste, usuario_id=assessor.id, acao="login_falha")


def test_desembargador_nao_enxerga_usuario_de_outro_gabinete(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Usuário de outro gabinete é invisível (404) pela RLS; pedir lista de outro dá 403."""
    outro_gabinete = criar_gabinete_teste(engine_teste)
    alheio = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, outro_gabinete)
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    assert cliente.post(f"/usuarios/{alheio.id}/desativar").status_code == 404
    lista = cliente.get("/usuarios", params={"gabinete_id": str(outro_gabinete)})
    assert lista.status_code == 403


def test_ninguem_gere_a_si_mesmo_nem_o_administrador(
    app_teste: FastAPI,
    engine_teste: Engine,
    desembargador: UsuarioTeste,
    administrador: UsuarioTeste,
) -> None:
    """Desativar a si mesmo ou o administrador é recusado."""
    admin = _cliente_logado(app_teste, engine_teste, administrador)
    assert admin.post(f"/usuarios/{administrador.id}/desativar").status_code == 403
    cliente = _cliente_logado(app_teste, engine_teste, desembargador)
    assert cliente.post(f"/usuarios/{desembargador.id}/desativar").status_code == 403
    assert admin.post(f"/usuarios/{desembargador.id}/resetar-senha").status_code == 200
