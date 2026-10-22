"""Índice gravado pelo worker, rota do índice e reclassificação manual (4E.7, 4E.8, 4E.10)."""

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lupa.dominio.enums import OrigemPeca, PapelUsuario
from lupa.dominio.tabelas import JobIngestaoTabela, PaginaTabela, PecaTabela
from lupa.ingestao import repositorio_pecas
from lupa.ingestao.indice import montar_indice
from lupa.ingestao.origem import origem_da_pagina
from lupa.ingestao.worker import Dependencias, sessao_gabinete
from lupa.sinteticos.gabarito import Cenario
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
)
from tests.ingestao.conftest import AutosSinteticos, ExtracaoSessao, lacrar_e_processar

pytestmark = pytest.mark.integracao


def _assessor(engine: Engine) -> UsuarioTeste:
    return criar_usuario_teste(engine, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine))


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


@pytest.fixture
def deps_extracao(extracao_sessao: ExtracaoSessao) -> Dependencias:
    """Dependências do worker da sessão (substitui a fixture homônima do conftest)."""
    return extracao_sessao.deps


@pytest.fixture
def processado(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> dict[str, Any]:
    """PDF sintético com índice processado até `concluido` num processo novo do assessor."""
    return lacrar_e_processar(extracao_sessao, engine_teste, tmp_path)


def _indice(cliente: TestClient, processo: UUID) -> list[dict[str, Any]]:
    resposta = cliente.get(f"/processos/{processo}/indice")
    assert resposta.status_code == 200, resposta.text
    return list(resposta.json()["pecas"])


def test_worker_grava_indice_sinais_e_divergencias(
    engine_teste: Engine,
    deps_extracao: Dependencias,
    processado: dict[str, Any],
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Uma peça por entrada do índice, sinais em toda página, relatório com divergências."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_INDICE]
    lacre = processado["lacre"]
    with Session(engine_teste) as session:
        pecas = list(session.scalars(select(PecaTabela).where(
            PecaTabela.arquivo_id == lacre.arquivo_id)))  # fmt: skip
        sinais = list(session.scalars(select(PaginaTabela.sinais_fronteira).where(
            PaginaTabela.arquivo_id == lacre.arquivo_id)))  # fmt: skip
        job = session.get_one(JobIngestaoTabela, lacre.job_id)
    assert len(pecas) == len(gabarito.pecas)
    assert all(p.metodo == "regra" and p.vigente for p in pecas)
    assert all(s.get("versao_titulos") or s.get("indice") for s in sinais)
    assert job.relatorio is not None
    assert job.relatorio["indice"]["pecas"] == len(gabarito.pecas)
    assert job.relatorio["indice"]["fonte"] == "bookmark"
    assert isinstance(job.relatorio["divergencias_fronteira"], list)
    assert sum(1 for p in pecas if p.data_evidencia_id) >= len(pecas) - 2
    with sessao_gabinete(deps_extracao.fabrica, processado["assessor"].gabinete_id) as session:
        paginas = repositorio_pecas.paginas_para_indice(session, lacre.arquivo_id)
        resultado = montar_indice(paginas, None)
        gravadas = repositorio_pecas.gravar_indice(
            session, processado["assessor"].gabinete_id, lacre.arquivo_id, paginas, resultado
        )
    assert gravadas == 0


def test_rota_do_indice_auditada_com_resumo_de_flags_e_isolada_por_gabinete(
    app_teste: FastAPI, engine_teste: Engine, processado: dict[str, Any]
) -> None:
    """GET do índice: peças em ordem, resumo de flags, evento; outro gabinete recebe 404."""
    processo = processado["processo"]
    cliente = _cliente(app_teste, engine_teste, processado["assessor"])
    pecas = _indice(cliente, processo)
    assert [p["ordem"] for p in pecas] == list(range(1, len(pecas) + 1))
    assert all({"peca", "saneamento", "total_saneamento"} <= set(p["resumo_flags"]) for p in pecas)
    assert any(p["resumo_flags"]["total_saneamento"] > 0 for p in pecas)
    com_data = next(p for p in pecas if p["evidencia_data"])
    assert com_data["data"] and com_data["evidencia_data"]["hash_trecho"]
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="processo_aberto")
    assert any(e.objeto_id == f"/processos/{processo}/indice" for e in eventos)
    peca = cliente.get(f"/processos/{processo}/pecas/{pecas[0]['id']}")
    assert peca.status_code == 200 and peca.json()["historico"] == []
    assert cliente.get(f"/processos/{processo}/pecas/{processo}").status_code == 404
    outro = _cliente(app_teste, engine_teste, _assessor(engine_teste))
    assert outro.get(f"/processos/{processo}/indice").status_code == 404
    assert outro.get(f"/processos/{processo}/pecas/{pecas[0]['id']}").status_code == 404


def _reclassificar(cliente: TestClient, processo: UUID, peca_id: str, corpo: dict[str, Any]) -> Any:
    return cliente.post(f"/processos/{processo}/pecas/{peca_id}/reclassificar", json=corpo)


def test_reclassificar_tipo_origem_dividir_e_unir_preserva_historico_e_audita(
    app_teste: FastAPI,
    engine_teste: Engine,
    deps_extracao: Dependencias,
    processado: dict[str, Any],
) -> None:
    """Cada correção grava peça nova manual, encerra a anterior e registra auditoria."""
    processo = processado["processo"]
    cliente = _cliente(app_teste, engine_teste, processado["assessor"])
    antes = _indice(cliente, processo)
    alvo = antes[1]
    resposta = _reclassificar(cliente, processo, alvo["id"], {"tipo": "laudo", "origem": "defesa"})
    assert resposta.status_code == 201, resposta.text
    nova = resposta.json()["pecas"][0]
    assert (nova["tipo"], nova["origem"], nova["metodo"]) == ("laudo", "defesa", "manual")
    assert nova["substitui_peca_id"] == alvo["id"]
    assert [h["id"] for h in nova["historico"]] == [alvo["id"]]
    depois = _indice(cliente, processo)
    assert len(depois) == len(antes) and depois[1]["id"] == nova["id"]
    with sessao_gabinete(deps_extracao.fabrica, processado["assessor"].gabinete_id) as session:
        pagina_id = session.scalar(select(PaginaTabela.id).where(
            PaginaTabela.arquivo_id == processado["lacre"].arquivo_id,
            PaginaTabela.numero == alvo["pagina_inicial"]))  # fmt: skip
        assert pagina_id is not None
        assert origem_da_pagina(session, pagina_id) is OrigemPeca.DEFESA
    repetida = _reclassificar(cliente, processo, alvo["id"], {"tipo": "sentenca"})
    assert repetida.status_code == 422

    longa = next(p for p in depois if p["pagina_final"] > p["pagina_inicial"])
    corte = longa["pagina_inicial"] + 1
    dividida = _reclassificar(cliente, processo, longa["id"], {"dividir_em": corte,
                                                               "tipo": "certidao"})  # fmt: skip
    assert dividida.status_code == 201, dividida.text
    partes = dividida.json()["pecas"]
    assert [(p["pagina_inicial"], p["pagina_final"]) for p in partes] == [
        (longa["pagina_inicial"], corte - 1),
        (corte, longa["pagina_final"]),
    ]
    assert partes[1]["tipo"] == "certidao" and partes[0]["tipo"] == longa["tipo"]
    assert len(_indice(cliente, processo)) == len(antes) + 1

    unida = _reclassificar(cliente, processo, partes[0]["id"], {"unir_com": partes[1]["id"]})
    assert unida.status_code == 201, unida.text
    inteira = unida.json()["pecas"][0]
    assert (inteira["pagina_inicial"], inteira["pagina_final"]) == (
        longa["pagina_inicial"],
        longa["pagina_final"],
    )
    historico = {h["id"] for h in inteira["historico"]}
    assert {partes[0]["id"], partes[1]["id"], longa["id"]} <= historico
    assert len(_indice(cliente, processo)) == len(antes)

    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="peca_reclassificada")
    assert len(eventos) == 4
    assert all(e.objeto_tipo == "peca" for e in eventos)
    with Session(engine_teste) as session:
        total = session.scalars(select(PecaTabela.id).where(
            PecaTabela.arquivo_id == processado["lacre"].arquivo_id)).all()  # fmt: skip
    assert len(total) == len(antes) + 4


def test_reclassificacao_invalida_e_recusada(
    app_teste: FastAPI, engine_teste: Engine, processado: dict[str, Any]
) -> None:
    """Pedido vazio, divisão fora da peça, união com peça não vizinha: 422; outro gabinete: 404."""
    processo = processado["processo"]
    cliente = _cliente(app_teste, engine_teste, processado["assessor"])
    pecas = _indice(cliente, processo)
    primeira, terceira = pecas[0], pecas[2]
    assert _reclassificar(cliente, processo, primeira["id"], {}).status_code == 422
    fora = {"dividir_em": primeira["pagina_final"] + 5}
    assert _reclassificar(cliente, processo, primeira["id"], fora).status_code == 422
    longe = {"unir_com": terceira["id"]}
    assert _reclassificar(cliente, processo, primeira["id"], longe).status_code == 422
    inexistente = {"unir_com": str(processo)}
    assert _reclassificar(cliente, processo, primeira["id"], inexistente).status_code == 422
    os_dois = {"dividir_em": 2, "unir_com": terceira["id"]}
    assert _reclassificar(cliente, processo, primeira["id"], os_dois).status_code == 422
    assert _reclassificar(cliente, processo, str(processo), {"tipo": "laudo"}).status_code == 404
    outro = _cliente(app_teste, engine_teste, _assessor(engine_teste))
    assert _reclassificar(outro, processo, primeira["id"], {"tipo": "laudo"}).status_code == 404
