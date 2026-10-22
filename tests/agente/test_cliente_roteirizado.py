"""Modo de teste do agente: cliente falso com roteiro de arquivo (Etapa 6.8)."""

import asyncio
import json
from pathlib import Path

import pytest

from lupa.agente.cliente import ClienteFalso, ClienteSdk, FerramentaAgente, PedidoAgente
from lupa.agente.cliente_roteirizado import (
    ROTEIRO_PADRAO,
    ConfiguracaoAgenteError,
    carregar_roteiro,
    criar_cliente,
    segmentos_do_resultado,
)
from lupa.agente.contexto import Delimitador, formatar_segmentos, segmentos
from lupa.config import Settings

PAGINA = "11111111-2222-3333-4444-555555555555"
TEXTO = "CERTIDÃO\nCertifico que intimei o defensor em 10/03/2025."


def _settings(base: Settings, ambiente: str) -> Settings:
    return base.model_copy(update={"ambiente": ambiente})


def _resultado() -> str:
    corpo = formatar_segmentos(segmentos(TEXTO))
    return Delimitador().envelopar({"pagina_id": PAGINA, "numero": 3}, corpo)


def _pedido(pergunta: str) -> PedidoAgente:
    async def _buscar(_argumentos: dict[str, object]) -> str:
        return _resultado()

    ferramenta = FerramentaAgente("buscar_texto", "busca", {"type": "object"}, _buscar)
    mensagem = f'ficha\n\nPergunta do assessor:\n"""\n{pergunta}\n"""\n\nInstrução: incidente'
    return PedidoAgente("sistema", mensagem, "claude-opus-5-5", 3, (ferramenta,))


def test_sdk_e_o_padrao_e_valor_desconhecido_e_recusado(settings_ficticias: Settings) -> None:
    """Sem variável, o cliente é o SDK; valor fora de sdk/falso é recusado."""
    assert isinstance(criar_cliente(settings_ficticias, {}), ClienteSdk)
    with pytest.raises(ConfiguracaoAgenteError):
        criar_cliente(settings_ficticias, {"LUPA_AGENTE_CLIENTE": "outro"})


@pytest.mark.parametrize("ambiente", ["desenvolvimento", "teste"])
def test_cliente_falso_aceito_em_desenvolvimento_e_teste(
    settings_ficticias: Settings, ambiente: str
) -> None:
    """Desenvolvimento e teste aceitam o cliente falso com o roteiro padrão."""
    configuracao = _settings(settings_ficticias, ambiente)
    cliente = criar_cliente(configuracao, {"LUPA_AGENTE_CLIENTE": "falso"})
    assert isinstance(cliente, ClienteFalso)


def test_cliente_falso_recusado_em_producao(settings_ficticias: Settings) -> None:
    """Em produção a aplicação se recusa a usar o cliente falso."""
    configuracao = _settings(settings_ficticias, "producao")
    with pytest.raises(ConfiguracaoAgenteError, match="produção"):
        criar_cliente(configuracao, {"LUPA_AGENTE_CLIENTE": "falso"})


def test_segmentos_do_resultado_trazem_pagina_trecho_e_hash() -> None:
    """Os segmentos citáveis são lidos do resultado da ferramenta."""
    itens = segmentos_do_resultado(_resultado())
    assert itens[1]["pagina_id"] == PAGINA
    assert itens[1]["trecho"] == "Certifico que intimei o defensor em 10/03/2025."


def test_roteiro_escolhe_pela_pergunta_e_cita_o_resultado(tmp_path: Path) -> None:
    """A pergunta escolhe o roteiro; a citação vem do resultado; `adulterar` estraga o trecho."""
    arquivo = tmp_path / "roteiro.json"
    itens = [
        {
            "quando": "intim",
            "passos": [{"nome": "buscar_texto", "argumentos": {"termo": "x"}}],
            "texto": "ok",
            "citar": [
                {"segmento": 1},
                {"segmento": 1, "adulterar": True},
                {"segmento": 9},
                {"resultado": 5},
            ],
            "tokens": [7, 3],
        },
        {"texto": "padrão"},
    ]
    arquivo.write_text(json.dumps(itens), encoding="utf-8")
    cliente = ClienteFalso(carregar_roteiro(arquivo))
    resposta = asyncio.run(cliente.responder(_pedido("Quando houve intimação?")))
    corpo = json.loads(resposta.texto)
    assert corpo["texto"] == "ok" and len(corpo["citacoes"]) == 2
    assert corpo["citacoes"][1]["trecho"].startswith("trecho que não existe")
    assert (resposta.tokens_entrada, resposta.tokens_saida) == (7, 3)
    outra = asyncio.run(cliente.responder(_pedido("Outra coisa")))
    assert json.loads(outra.texto)["texto"] == "padrão"


def test_roteiro_padrao_do_pacote_e_valido() -> None:
    """O roteiro empacotado (usado no E2E) carrega e tem resposta padrão."""
    escolher = carregar_roteiro(ROTEIRO_PADRAO)
    roteiro = escolher(_pedido("pergunta sem palavra-chave"))
    assert callable(roteiro.resposta)
    assert "Não encontrei" in roteiro.resposta([])
