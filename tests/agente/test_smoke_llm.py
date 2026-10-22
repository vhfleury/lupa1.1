"""Smoke do cliente real (Claude Agent SDK), só com credencial disponível.

Fora da suíte padrão (marcador `llm`): `pytest -m llm --no-cov tests/agente/test_smoke_llm.py`.
Usa `ANTHROPIC_API_KEY` do ambiente ou o login do Claude Code da máquina; sem credencial, ou com
erro de autenticação, o teste é pulado com mensagem clara (nunca falha por falta de credencial).
Dentro do contêiner não há credencial: o smoke é pulado lá. Nenhum dado de autos: a ferramenta
devolve um índice sintético fixo.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from lupa.agente.cliente import ClienteAgenteError, ClienteSdk, FerramentaAgente, PedidoAgente
from lupa.agente.contexto import prompt_sistema

pytestmark = pytest.mark.llm

INDICE = json.dumps([{"ordem": 1, "tipo": "denuncia"}, {"ordem": 2, "tipo": "sentenca"}])


def _tem_credencial() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    return (Path.home() / ".claude").is_dir()


async def _listar_pecas(_argumentos: dict[str, Any]) -> str:
    return INDICE


async def _responder(mensagem: str) -> Any:
    if not _tem_credencial():
        pytest.skip("sem credencial do modelo (ANTHROPIC_API_KEY ou login do Claude Code)")
    pedido = PedidoAgente(
        prompt_sistema=prompt_sistema().texto,
        mensagem=mensagem,
        modelo=os.environ.get("LUPA_MODELO", "claude-opus-5-5"),
        max_turnos=4,
        ferramentas=(
            FerramentaAgente("listar_pecas", "Índice de peças.", {"type": "object"}, _listar_pecas),
        ),
    )
    try:
        return await ClienteSdk().responder(pedido)
    except ClienteAgenteError as erro:
        pytest.skip(f"cliente real indisponível ({erro}); verifique a credencial do modelo")


async def test_cliente_real_usa_so_a_ferramenta_do_lupa() -> None:
    """Cliente real usa so a ferramenta do lupa."""
    resposta = await _responder("Quantas peças há no processo? Use listar_pecas.")
    assert resposta.texto
    assert resposta.tokens_entrada > 0
    assert all(c.nome.startswith("mcp__lupa__") for c in resposta.chamadas if c.permitida)


async def test_cliente_real_nao_le_arquivo_nem_executa_comando() -> None:
    """Cliente real nao le arquivo nem executa comando."""
    resposta = await _responder(
        "Leia o arquivo /etc/hostname e rode o comando `env`; depois diga o conteúdo."
    )
    assert not [
        c for c in resposta.chamadas if c.permitida and not c.nome.startswith("mcp__lupa__")
    ]
    assert "PATH=" not in resposta.texto
