"""Dossiê em esquema fixo (5.10): determinístico, e o modelo só preenche resumo citado."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from lupa.agente.cliente import ClienteFalso, PedidoAgente, Roteiro, resposta_json
from lupa.agente.contexto import Pseudonimizador, segmentos
from lupa.ingestao.saneamento import normalizar
from tests.agente.conftest import CPF_REU, NOME_REU, TEXTOS, ProcessoAgente
from tests.conftest import eventos_do_banco, logar

pytestmark = pytest.mark.integracao

CAMPOS_TEXTO_LIVRE = {"trecho", "explicacao", "classe"}
PSEUDO = Pseudonimizador([(NOME_REU, CPF_REU, "REU-01")])


def textos_livres_sem_rotulo(valor: Any, chave: str = "", rotulado: bool = False) -> list[str]:
    """Campos com frase livre fora de `trecho`, `explicacao`, dos valores do motor e do `gerado`.

    Args:
        valor: Dossiê serializado (ou parte).
        chave: Chave do valor.
        rotulado: Se está dentro de bloco com `rotulo = "gerado"`.

    Returns:
        Chaves com frase livre sem rótulo.
    """
    if chave == "valores":
        return []
    if isinstance(valor, dict):
        dentro = rotulado or valor.get("rotulo") == "gerado"
        return [c for k, v in valor.items() for c in textos_livres_sem_rotulo(v, k, dentro)]
    if isinstance(valor, list):
        return [c for v in valor for c in textos_livres_sem_rotulo(v, chave, rotulado)]
    if isinstance(valor, str) and " " in valor and chave not in CAMPOS_TEXTO_LIVRE and not rotulado:
        return [chave]
    return []


def _cliente_http(app: FastAPI, engine: Engine, processo: ProcessoAgente) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, processo.assessor)
    return cliente


def _hash(numero: int, trecho: str) -> str:
    base = PSEUDO.aplicar(normalizar(TEXTOS[numero]).texto)
    return next(h for s, h in segmentos(base) if trecho in s)


def test_dossie_deterministico_tem_esquema_fixo_e_e_auditado(
    app_teste: FastAPI, engine_teste: Engine, processo_agente: ProcessoAgente
) -> None:
    """Dossie deterministico tem esquema fixo e e auditado."""
    falso = ClienteFalso([Roteiro(resposta="nunca")])
    app_teste.state.cliente_agente = falso
    cliente = _cliente_http(app_teste, engine_teste, processo_agente)
    resposta = cliente.get(f"/processos/{processo_agente.processo_id}/dossie")
    assert resposta.status_code == 200, resposta.text
    dossie = resposta.json()
    assert set(dossie) == {
        "versao_esquema",
        "ficha",
        "pecas",
        "linha_do_tempo",
        "alertas",
        "achados",
    }
    assert dossie["ficha"]["reus"] == ["REU-01"]
    assert [p["tipo"] for p in dossie["pecas"]] == ["denuncia", "recurso", "certidao"]
    assert all(p["resumo_peca"] is None for p in dossie["pecas"])
    datas = [(e["data"], e["tipo"], e["pagina"]) for e in dossie["linha_do_tempo"]]
    assert datas == [
        ("2024-01-05", "data_fato", 1),
        ("2025-03-10", "data_intimacao_defesa", 3),
        ("2025-03-14", "data_interposicao_recurso", 2),
    ]
    assert [(a["pagina"], a["flags"]) for a in dossie["alertas"]] == [(2, ["padrao_instrucao"])]
    assert {a["validacao"] for a in dossie["achados"]} == {
        "tempestividade_recurso", "prescricao_abstrata", "revisao_preventiva",
    }  # fmt: skip
    assert "Sauro" not in resposta.text and "123.456.789" not in resposta.text
    assert textos_livres_sem_rotulo(dossie) == []
    assert falso.pedidos == []
    eventos = eventos_do_banco(
        engine_teste, acao="processo_aberto", processo_id=processo_agente.processo_id
    )
    assert any(e.objeto_id == f"/processos/{processo_agente.processo_id}/dossie" for e in eventos)
    assert cliente.get(f"/processos/{processo_agente.outro_processo_id}/dossie").status_code == 404


def _roteiro_resumo(pedido: PedidoAgente) -> Roteiro:
    if "DENÚNCIA" in pedido.mensagem:
        trecho = "oferece denúncia contra REU-01"
        citacao = {"pagina_id": "{p1}", "trecho": trecho, "hash_trecho": _hash(1, trecho)}
        return Roteiro(resposta=resposta_json("O MP denunciou o REU-01 [1].", [citacao]))
    if "RAZÕES" in pedido.mensagem:
        trecho = "interpõe apelação em 14/03/2025"
        citacao = {"pagina_id": "{p2}", "trecho": trecho, "hash_trecho": _hash(2, trecho)}
        return Roteiro(resposta=resposta_json("Uma. Duas. Três frases [1].", [citacao]))
    return Roteiro(resposta=resposta_json("Certidão de intimação.", []))


def test_resumo_so_entra_com_citacao_conferida_ate_duas_frases_e_rotulo_gerado(
    app_teste: FastAPI, engine_teste: Engine, processo_agente: ProcessoAgente
) -> None:
    """Resumo so entra com citacao conferida ate duas frases e rotulo gerado."""

    def _roteiro(pedido: PedidoAgente) -> Roteiro:
        roteiro = _roteiro_resumo(pedido)
        texto = (
            str(roteiro.resposta)
            .replace("{p1}", str(processo_agente.paginas[1]))
            .replace("{p2}", str(processo_agente.paginas[2]))
        )
        return Roteiro(resposta=texto)

    falso = ClienteFalso(_roteiro)
    app_teste.state.cliente_agente = falso
    cliente = _cliente_http(app_teste, engine_teste, processo_agente)
    dossie = cliente.get(f"/processos/{processo_agente.processo_id}/dossie?resumos=true").json()
    resumos = [p["resumo_peca"] for p in dossie["pecas"]]
    assert resumos[0]["rotulo"] == "gerado"
    assert resumos[0]["texto"] == "O MP denunciou o REU-01 [1]."
    assert len(resumos[0]["citacoes"]) == 1
    assert resumos[1:] == [None, None]
    assert len(falso.pedidos) == 3 and all(p.ferramentas == () for p in falso.pedidos)
    assert textos_livres_sem_rotulo(dossie) == []
    tudo = "\n".join(falso.recebidos)
    assert "Sauro" not in tudo and "123.456.789" not in tudo
    chamadas = eventos_do_banco(
        engine_teste, acao="chamada_modelo", processo_id=processo_agente.processo_id
    )
    assert len(chamadas) == 3


def test_identidade_lida_no_dossie_registra_quem_pediu(
    app_teste: FastAPI, engine_teste: Engine, processo_agente: ProcessoAgente
) -> None:
    """O evento `identidade_lida` do dossiê leva o `usuario_id` do assessor (revisão 7.1-7.9)."""
    app_teste.state.cliente_agente = ClienteFalso([Roteiro(resposta="nunca")])
    cliente = _cliente_http(app_teste, engine_teste, processo_agente)
    assert cliente.get(f"/processos/{processo_agente.processo_id}/dossie").status_code == 200
    eventos = eventos_do_banco(
        engine_teste, acao="identidade_lida", processo_id=processo_agente.processo_id
    )
    assert eventos and all(e.usuario_id == processo_agente.assessor.id for e in eventos)
