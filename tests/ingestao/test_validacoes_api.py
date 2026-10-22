"""Tela de validações (Etapa 6.7): fatos, correção versionada, histórico de achados e anotações."""

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lupa.dominio import correcoes
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import AchadoTabela, FatoTabela
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
)
from tests.ingestao.conftest import ExtracaoSessao, lacrar_e_processar

pytestmark = pytest.mark.integracao


def _colega(engine: Engine, processado: dict[str, Any]) -> UsuarioTeste:
    """Assessor novo do mesmo gabinete (cada login gasta um passo TOTP do usuário)."""
    return criar_usuario_teste(engine, PapelUsuario.ASSESSOR, processado["assessor"].gabinete_id)


@pytest.fixture
def processado(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> dict[str, Any]:
    """Processo novo processado até achados."""
    return lacrar_e_processar(extracao_sessao, engine_teste, tmp_path)


@pytest.fixture
def colega(engine_teste: Engine, processado: dict[str, Any]) -> UsuarioTeste:
    """Assessor do gabinete do processo."""
    return _colega(engine_teste, processado)


@pytest.fixture
def cliente(app_teste: FastAPI, engine_teste: Engine, colega: UsuarioTeste) -> TestClient:
    """Cliente de um assessor do gabinete do processo."""
    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, colega)
    return cliente


def _valor(fato: dict[str, Any]) -> Any:
    valor = fato["valor"]
    return valor["valor"] if isinstance(valor, dict) and "reu_id" in valor else valor


def _fato_de_data(fatos: list[dict[str, Any]], usado: set[str]) -> dict[str, Any]:
    for fato in fatos:
        valor = _valor(fato)
        if fato["vigente"] and fato["id"] in usado and isinstance(valor, str):
            try:
                date.fromisoformat(valor)
            except ValueError:
                continue
            return fato
    raise AssertionError("nenhum fato de data usado por achado")


def test_correcao_grava_fato_novo_ligado_e_achado_antigo_vira_historico(
    cliente: TestClient, engine_teste: Engine, processado: dict[str, Any]
) -> None:
    """Fato novo `corrigido` com `substitui_fato_id`; original intacto; achados versionados."""
    processo = processado["processo"]
    achados = cliente.get(f"/processos/{processo}/achados").json()["achados"]
    usados = {f for a in achados for f in a["fatos_usados"]}
    fatos = cliente.get(f"/processos/{processo}/fatos").json()["fatos"]
    alvo = _fato_de_data(fatos, usados)
    assert all(e["arquivo_id"] and e["pagina"] for e in alvo["evidencias"])
    novo_valor = (date.fromisoformat(_valor(alvo)) - timedelta(days=4000)).isoformat()
    antes = {a["id"] for a in achados}

    resposta = cliente.post(
        f"/processos/{processo}/fatos/{alvo['id']}/corrigir",
        json={"status": "corrigido", "valor": novo_valor},
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    novo = corpo["fato"]
    assert novo["status"] == "corrigido" and novo["substitui_fato_id"] == alvo["id"]
    assert _valor(novo) == novo_valor
    if isinstance(alvo["valor"], dict):
        assert novo["valor"]["reu_id"] == alvo["valor"]["reu_id"]
    with Session(engine_teste) as session:
        original = session.get_one(FatoTabela, UUID(alvo["id"]))
        assert original.valor == alvo["valor"] and original.status == "automatico"
        todos = set(
            session.scalars(
                select(AchadoTabela.id).where(AchadoTabela.processo_id == processo)
            ).all()
        )
    assert {UUID(i) for i in antes} <= todos
    assert corpo["achados_gravados"] >= 1

    depois = cliente.get(f"/processos/{processo}/fatos").json()["fatos"]
    por_id = {f["id"]: f for f in depois}
    assert por_id[alvo["id"]]["vigente"] is False
    assert por_id[alvo["id"]]["substituido_por"] == novo["id"]
    assert por_id[novo["id"]]["vigente"] is True
    assert por_id[novo["id"]]["evidencias"] == alvo["evidencias"]

    historico = cliente.get(f"/processos/{processo}/achados/historico").json()["achados"]
    assert {a["id"] for a in historico} >= antes
    assert any(not a["vigente"] for a in historico)
    vigentes = {a["id"] for a in cliente.get(f"/processos/{processo}/achados").json()["achados"]}
    assert vigentes == {a["id"] for a in historico if a["vigente"]}

    eventos = {e.acao for e in eventos_do_banco(engine_teste, processo_id=processo)}
    assert {"fato_corrigido", "validacao_executada"} <= eventos
    repetida = cliente.post(
        f"/processos/{processo}/fatos/{alvo['id']}/corrigir", json={"status": "confirmado"}
    )
    assert repetida.status_code == 409


def test_confirmar_mantem_valor_e_validacoes_de_corpo(
    cliente: TestClient, processado: dict[str, Any]
) -> None:
    """Confirmação grava `confirmado` com o mesmo valor; tipo diferente ou igual é recusado."""
    processo = processado["processo"]
    fatos = cliente.get(f"/processos/{processo}/fatos").json()["fatos"]
    alvo = _fato_de_data(fatos, {f["id"] for f in fatos})
    base = f"/processos/{processo}/fatos/{alvo['id']}/corrigir"
    assert cliente.post(base, json={"status": "corrigido", "valor": 12}).status_code == 422
    assert (
        cliente.post(base, json={"status": "corrigido", "valor": _valor(alvo)}).status_code == 422
    )
    assert cliente.post(base, json={"status": "corrigido"}).status_code == 422
    assert cliente.post(base, json={"status": "automatico"}).status_code == 422
    inexistente = f"/processos/{processo}/fatos/{processo}/corrigir"
    assert cliente.post(inexistente, json={"status": "confirmado"}).status_code == 404
    confirmado = cliente.post(base, json={"status": "confirmado"})
    assert confirmado.status_code == 201
    assert confirmado.json()["fato"]["valor"] == alvo["valor"]
    assert confirmado.json()["fato"]["status"] == "confirmado"


def test_anotacao_em_achado_e_fato_com_auditoria_e_isolamento(
    app_teste: FastAPI,
    cliente: TestClient,
    engine_teste: Engine,
    processado: dict[str, Any],
    colega: UsuarioTeste,
) -> None:
    """Anota achado e fato; lista com autor; alvo de outro processo é 404; outro gabinete 404."""
    processo = processado["processo"]
    achado = cliente.get(f"/processos/{processo}/achados").json()["achados"][0]
    fato = cliente.get(f"/processos/{processo}/fatos").json()["fatos"][0]
    url = f"/processos/{processo}/anotacoes"
    primeira = cliente.post(url, json={"achado_id": achado["id"], "texto": "Conferir certidão."})
    assert primeira.status_code == 201, primeira.text
    assert cliente.post(url, json={"fato_id": fato["id"], "texto": "ok"}).status_code == 201
    assert cliente.post(url, json={"texto": "sem alvo"}).status_code == 422
    assert (
        cliente.post(
            url, json={"achado_id": achado["id"], "fato_id": fato["id"], "texto": "dois"}
        ).status_code
        == 422
    )
    assert cliente.post(url, json={"fato_id": str(processo), "texto": "x"}).status_code == 404
    assert cliente.post(url, json={"achado_id": str(processo), "texto": "x"}).status_code == 404
    lista = cliente.get(url).json()["anotacoes"]
    assert [a["texto"] for a in lista] == ["Conferir certidão.", "ok"]
    assert lista[0]["autor"] == colega.nome
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="anotacao")
    assert [e.objeto_id for e in eventos] == [primeira.json()["id"], lista[1]["id"]]

    outro = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    intruso = TestClient(app_teste, base_url="https://testserver")
    logar(intruso, engine_teste, outro)
    assert intruso.get(url).status_code == 404
    assert intruso.post(url, json={"fato_id": fato["id"], "texto": "x"}).status_code == 404


def test_admin_le_fatos_com_auditoria_de_acesso_a_conteudo(
    app_teste: FastAPI, cliente: TestClient, engine_teste: Engine, processado: dict[str, Any]
) -> None:
    """O administrador lê os fatos e gera `admin_acesso_conteudo`."""
    processo = processado["processo"]
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    cliente_admin = TestClient(app_teste, base_url="https://testserver")
    logar(cliente_admin, engine_teste, admin)
    assert cliente_admin.get(f"/processos/{processo}/fatos").status_code == 200
    conteudo = eventos_do_banco(engine_teste, usuario_id=admin.id, acao="admin_acesso_conteudo")
    assert conteudo


def test_fatos_vigentes_e_valor_corrigido_unitarios() -> None:
    """Regras puras: substituídos saem; envelope do réu é reaplicado; tipos conferidos."""
    assert correcoes.valor_corrigido({"valor": "2020-01-01", "reu_id": "r"}, "2020-02-01") == {
        "valor": "2020-02-01",
        "reu_id": "r",
    }
    assert correcoes.valor_corrigido(5, 6.5) == 6.5
    assert correcoes.valor_corrigido(True, False) is False
    assert correcoes.valor_corrigido("texto", "outro") == "outro"
    for original, novo in (("2020-01-01", "abc"), (5, "5"), ("x", "x")):
        with pytest.raises(correcoes.CorrecaoInvalidaError):
            correcoes.valor_corrigido(original, novo)
