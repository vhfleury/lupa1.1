"""Lista, criação e arquivos do processo (Etapa 6.4): isolamento, validação CNJ e auditoria."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from lupa.api.rotas.processos import resumir_ingestao
from lupa.dominio.enums import PapelUsuario
from lupa.ingestao.fila import FilaMemoria
from lupa.ingestao.storage import ArmazenamentoMemoria
from tests.api.test_processos import _criar_processo
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    gerar_numero_cnj,
    logar,
)
from tests.ingestao.arquivos import pdf_com_senha, pdf_minimo

pytestmark = pytest.mark.integracao


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


def _corpo(sequencial: int) -> dict[str, object]:
    return {
        "numero_cnj": gerar_numero_cnj(sequencial),
        "classe": "Apelação Criminal",
        "materia": "criminal",
    }


def test_assessor_cria_processo_valida_cnj_e_recusa_duplicado(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """201 com auditoria; CNJ com dígito errado dá 422; repetido no gabinete dá 409."""
    gabinete = criar_gabinete_teste(engine_teste)
    assessor = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, gabinete)
    cliente = _cliente(app_teste, engine_teste, assessor)
    resposta = cliente.post("/processos", json=_corpo(4321))
    assert resposta.status_code == 201, resposta.text
    criado = resposta.json()
    assert criado["status"] == "criado" and criado["gabinete_id"] == str(gabinete)
    eventos = eventos_do_banco(engine_teste, acao="processo_criado", objeto_id=criado["id"])
    assert [e.resultado for e in eventos] == ["ok"]
    assert cliente.post("/processos", json=_corpo(4321)).status_code == 409
    valido = gerar_numero_cnj(4322)
    digito_errado = f"{(int(valido[8:10]) + 1) % 100:02d}"
    errado = _corpo(4322) | {"numero_cnj": valido[:8] + digito_errado + valido[10:]}
    assert cliente.post("/processos", json=errado).status_code == 422
    assert cliente.post("/processos", json=_corpo(1) | {"numero_cnj": "123"}).status_code == 422


def test_admin_precisa_informar_gabinete_e_desembargador_de_outro_gabinete_e_negado(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """Admin sem gabinete-alvo: 422; com gabinete: 201. Outro gabinete: 403 auditado."""
    gabinete = criar_gabinete_teste(engine_teste)
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    cliente = _cliente(app_teste, engine_teste, admin)
    assert cliente.post("/processos", json=_corpo(5101)).status_code == 422
    corpo = _corpo(5101) | {"gabinete_id": str(gabinete)}
    assert cliente.post("/processos", json=corpo).status_code == 201
    desembargador = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )
    outro = _cliente(app_teste, engine_teste, desembargador)
    assert (
        outro.post("/processos", json=_corpo(5102) | {"gabinete_id": str(gabinete)}).status_code
        == 403
    )
    negados = eventos_do_banco(
        engine_teste, acao="processo_criado", usuario_id=desembargador.id, resultado="negado"
    )
    assert len(negados) == 1


def test_lista_mostra_so_o_gabinete_com_situacao_da_ingestao_e_e_auditada(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """Lista isolada por gabinete, com a situação vinda de `job_ingestao`; evento `busca`."""
    assessor = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    vizinho = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    app_teste.state.storage = ArmazenamentoMemoria()
    app_teste.state.fila = FilaMemoria()
    meu = _criar_processo(engine_teste, assessor)
    alheio = _criar_processo(engine_teste, vizinho)
    cliente = _cliente(app_teste, engine_teste, assessor)
    assert (
        cliente.post(f"/processos/{meu}/arquivos?nome=a.pdf", content=pdf_minimo(2)).status_code
        == 201
    )
    assert (
        cliente.post(f"/processos/{meu}/arquivos?nome=b.pdf", content=pdf_com_senha()).status_code
        == 201
    )

    lista = cliente.get("/processos")
    assert lista.status_code == 200
    ids = [p["id"] for p in lista.json()]
    assert str(meu) in ids and str(alheio) not in ids
    item = next(p for p in lista.json() if p["id"] == str(meu))
    assert item["ingestao"]["situacao"] == "processando"
    assert item["ingestao"]["por_estado"] == {"recebido": 2}
    assert eventos_do_banco(engine_teste, acao="busca", usuario_id=assessor.id)

    arquivos = cliente.get(f"/processos/{meu}/arquivos")
    assert arquivos.status_code == 200
    corpo = arquivos.json()
    assert {a["nome"] for a in corpo["arquivos"]} == {"a.pdf", "b.pdf"}
    assert all(a["estado"] == "recebido" for a in corpo["arquivos"])
    assert cliente.get(f"/processos/{alheio}/arquivos").status_code == 404
    aberto = cliente.get(f"/processos/{meu}").json()
    assert aberto["sigiloso"] is False and "criado_em" in aberto


@pytest.mark.parametrize(
    ("estados", "esperado"),
    [
        ([], "sem_arquivos"),
        (["recebido", "concluido"], "processando"),
        (["quarentena"], "quarentena"),
        (["quarentena", "falho"], "falho"),
        (["concluido", "em_revisao"], "pendencias"),
        (["concluido", "quarentena"], "concluido"),
    ],
)
def test_resumo_da_ingestao(estados: list[str], esperado: str) -> None:
    """Situação agregada a partir dos estados dos jobs."""
    assert resumir_ingestao(estados) == esperado
