"""Testes da rota de processo: isolamento por gabinete e auditoria automática."""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.enums import Materia, PapelUsuario, StatusProcesso
from lupa.dominio.tabelas import ProcessoTabela
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    gerar_numero_cnj,
    logar,
)

pytestmark = pytest.mark.integracao


def _criar_processo(engine: Engine, autor: UsuarioTeste) -> UUID:
    processo_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            ProcessoTabela(
                id=processo_id,
                gabinete_id=autor.gabinete_id,
                numero_cnj=gerar_numero_cnj(int(processo_id.int % 9_000_000) + 1),
                classe="Apelação Criminal",
                materia=Materia.CRIMINAL.value,
                sigiloso=False,
                status=StatusProcesso.CRIADO.value,
                criado_por=autor.id,
            )
        )
    return processo_id


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


def _assessor(engine: Engine) -> UsuarioTeste:
    return criar_usuario_teste(engine, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine))


def test_assessor_do_gabinete_a_recebe_404_no_processo_do_gabinete_b_e_tentativa_e_registrada(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """404 (não 403) e evento `processo_aberto` com resultado `negado`."""
    assessor_a, assessor_b = _assessor(engine_teste), _assessor(engine_teste)
    processo_b = _criar_processo(engine_teste, assessor_b)
    cliente = _cliente(app_teste, engine_teste, assessor_a)
    resposta = cliente.get(f"/processos/{processo_b}")
    assert resposta.status_code == 404
    inexistente = cliente.get(f"/processos/{uuid4()}")
    assert (inexistente.status_code, inexistente.json()) == (404, resposta.json())
    tentativas = eventos_do_banco(engine_teste, usuario_id=assessor_a.id, processo_id=processo_b)
    assert [(e.acao, e.resultado) for e in tentativas] == [("processo_aberto", "negado")]
    assert tentativas[0].gabinete_id == assessor_a.gabinete_id


def test_assessor_abre_processo_do_proprio_gabinete_e_acesso_e_registrado(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """200 e evento `processo_aberto` com IP e localização."""
    assessor = _assessor(engine_teste)
    processo = _criar_processo(engine_teste, assessor)
    resposta = _cliente(app_teste, engine_teste, assessor).get(f"/processos/{processo}")
    assert resposta.status_code == 200
    assert resposta.json()["id"] == str(processo)
    eventos = eventos_do_banco(engine_teste, processo_id=processo)
    assert [(e.acao, e.resultado) for e in eventos] == [("processo_aberto", "ok")]
    assert eventos[0].localizacao == "Cidade Fictícia, Estado Fictício, País Fictício"
    assert eventos[0].ip == "testclient"


def test_acesso_de_admin_a_rota_de_conteudo_gera_admin_acesso_conteudo(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """Admin vê processo de qualquer gabinete; gera o evento normal e o destacado."""
    assessor = _assessor(engine_teste)
    processo = _criar_processo(engine_teste, assessor)
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    resposta = _cliente(app_teste, engine_teste, admin).get(f"/processos/{processo}")
    assert resposta.status_code == 200
    eventos = eventos_do_banco(engine_teste, processo_id=processo, usuario_id=admin.id)
    assert sorted(e.acao for e in eventos) == ["admin_acesso_conteudo", "processo_aberto"]
    assert {e.gabinete_id for e in eventos} == {assessor.gabinete_id}


def test_middleware_registra_busca_sem_processo(app_teste: FastAPI, engine_teste: Engine) -> None:
    """Rota marcada sem processo grava o evento na cadeia do gabinete do usuário."""
    from lupa.acesso.autorizacao import AtorAutenticado

    @app_teste.get("/busca-teste")
    @auditar_rota(AcaoAuditoria.BUSCA, conteudo=False)
    def _busca(ator: AtorAutenticado) -> dict[str, str]:
        return {"ok": "sim"}

    assessor = _assessor(engine_teste)
    cliente = _cliente(app_teste, engine_teste, assessor)
    assert cliente.get("/busca-teste").status_code == 200
    eventos = eventos_do_banco(engine_teste, usuario_id=assessor.id, acao="busca")
    assert len(eventos) == 1 and eventos[0].gabinete_id == assessor.gabinete_id
    assert eventos[0].objeto_id == "/busca-teste"


def test_auditar_rota_recusa_acao_nao_automatica() -> None:
    """Só `processo_aberto`, `pagina_vista` e `busca` são automáticas."""
    with pytest.raises(ValueError, match="não é registrada automaticamente"):
        auditar_rota(AcaoAuditoria.LOGIN_OK, conteudo=False)
