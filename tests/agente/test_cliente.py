"""Cliente do modelo (5.1): política de ferramentas, opções do SDK e cliente falso."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from lupa.agente import cliente as modulo
from lupa.agente.cliente import (
    FERRAMENTAS_EMBUTIDAS,
    ClienteAgenteError,
    ClienteFalso,
    ClienteSdk,
    FerramentaAgente,
    PassoFerramenta,
    PedidoAgente,
    Roteiro,
    _Acumulado,
    consumir_mensagem,
    criar_guarda,
    decidir_ferramenta,
    montar_opcoes,
    nome_qualificado,
    resposta_json,
)


async def _eco(argumentos: dict[str, Any]) -> str:
    return f"eco:{sorted(argumentos)}"


def _pedido() -> PedidoAgente:
    return PedidoAgente(
        prompt_sistema="sistema",
        mensagem="mensagem",
        modelo="claude-opus-5-5",
        max_turnos=3,
        ferramentas=(FerramentaAgente("listar_pecas", "índice", {"type": "object"}, _eco),),
    )


def test_politica_so_permite_ferramentas_do_lupa_listadas() -> None:
    """Politica so permite ferramentas do lupa listadas."""
    permitidas = frozenset({nome_qualificado("listar_pecas")})
    assert decidir_ferramenta("mcp__lupa__listar_pecas", permitidas)
    assert not decidir_ferramenta("mcp__lupa__outra", permitidas)
    for embutida in FERRAMENTAS_EMBUTIDAS:
        assert not decidir_ferramenta(embutida, permitidas | {embutida})
    assert not decidir_ferramenta("mcp__outro__listar_pecas", permitidas)


def test_opcoes_do_sdk_removem_todas_as_embutidas_e_nao_carregam_configuracao_do_host() -> None:
    """Opcoes do sdk removem todas as embutidas e nao carregam configuracao do host."""
    opcoes = montar_opcoes(_pedido(), [], "vazio")
    assert opcoes.tools == []
    assert opcoes.allowed_tools == ["mcp__lupa__listar_pecas"]
    for nome in ("Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Task"):
        assert nome in opcoes.disallowed_tools
    assert opcoes.permission_mode == "dontAsk"
    assert opcoes.setting_sources == []
    assert opcoes.agents == {}
    assert opcoes.strict_mcp_config is True
    assert list(opcoes.mcp_servers) == ["lupa"]
    assert opcoes.system_prompt == "sistema"
    assert opcoes.model == "claude-opus-5-5"
    assert opcoes.max_turns == 3
    assert opcoes.env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert "PreToolUse" in opcoes.hooks


async def test_guarda_nega_embutida_e_registra_a_tentativa() -> None:
    """Guarda nega embutida e registra a tentativa."""
    registro: list[modulo.ChamadaFerramenta] = []
    guarda = criar_guarda(frozenset({"mcp__lupa__listar_pecas"}), registro)
    negado = await guarda(
        {"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}, None, None
    )
    assert negado["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert await guarda({"tool_name": "mcp__lupa__listar_pecas"}, None, None) == {}
    assert [(c.nome, c.permitida) for c in registro] == [
        ("Read", False),
        ("mcp__lupa__listar_pecas", True),
    ]


def test_consumir_mensagens_do_sdk_soma_tokens_e_pega_o_texto_final() -> None:
    """Consumir mensagens do sdk soma tokens e pega o texto final."""
    acumulado = _Acumulado()
    consumir_mensagem(
        acumulado,
        AssistantMessage(
            content=[TextBlock("parcial"), ToolUseBlock("1", "mcp__lupa__listar_pecas", {})],
            model="claude-opus-5-5",
        ),
    )
    consumir_mensagem(
        acumulado,
        ResultMessage(
            subtype="success", duration_ms=10, duration_api_ms=9, is_error=False, num_turns=2,
            session_id="s", result='{"texto": "ok", "citacoes": []}',
            usage={"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 7},
        ),
    )  # fmt: skip
    assert acumulado.texto == '{"texto": "ok", "citacoes": []}'
    assert (acumulado.tokens_entrada, acumulado.tokens_saida) == (15, 7)
    assert acumulado.modelo == "claude-opus-5-5"
    consumir_mensagem(acumulado, object())
    consumir_mensagem(acumulado, AssistantMessage(content=[], model="m", error="rate_limit"))
    assert acumulado.erro == "rate_limit"


class _SdkRoteirizado(ClienteSdk):
    def __init__(self, mensagens: list[Any], erro: Exception | None = None) -> None:
        self.mensagens = mensagens
        self.erro = erro
        self.opcoes: Any = None

    async def _mensagens(self, pedido: PedidoAgente, opcoes: Any) -> AsyncIterator[Any]:
        self.opcoes = opcoes
        for mensagem in self.mensagens:
            yield mensagem
        if self.erro:
            raise self.erro


async def test_cliente_sdk_devolve_texto_tokens_e_latencia_sem_rede() -> None:
    """Cliente sdk devolve texto tokens e latencia sem rede."""
    final = ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
        session_id="s", result="resposta", usage={"input_tokens": 3, "output_tokens": 2},
    )  # fmt: skip
    cliente = _SdkRoteirizado([AssistantMessage([TextBlock("resposta")], "claude-opus-5-5"), final])
    resposta = await cliente.responder(_pedido())
    assert resposta.texto == "resposta"
    assert (resposta.tokens_entrada, resposta.tokens_saida) == (3, 2)
    assert cliente.opcoes.tools == []


async def test_cliente_sdk_converte_erros_sem_vazar_conteudo() -> None:
    """Cliente sdk converte erros sem vazar conteudo."""
    with pytest.raises(ClienteAgenteError, match="ClaudeSDKError"):
        await _SdkRoteirizado([], ClaudeSDKError("detalhe interno")).responder(_pedido())
    erro = ResultMessage(
        subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=3,
        session_id="s",
    )  # fmt: skip
    with pytest.raises(ClienteAgenteError, match="error_max_turns"):
        await _SdkRoteirizado([erro]).responder(_pedido())


async def test_cliente_falso_nega_ferramenta_embutida_e_executa_as_do_lupa() -> None:
    """Cliente falso nega ferramenta embutida e executa as do lupa."""
    falso = ClienteFalso(
        [
            Roteiro(
                passos=(
                    PassoFerramenta("Read", {"file_path": "/app/.env"}),
                    PassoFerramenta("Bash", {"command": "cat /etc/passwd"}),
                    PassoFerramenta("listar_pecas", {"processo_id": "forjado"}),
                ),
                resposta=lambda resultados: resposta_json(resultados[-1]),
            )
        ]
    )
    resposta = await falso.responder(_pedido())
    assert [(c.nome, c.permitida) for c in resposta.chamadas] == [
        ("Read", False),
        ("Bash", False),
        ("mcp__lupa__listar_pecas", True),
    ]
    assert "eco:['processo_id']" in resposta.texto
    assert "ferramenta não permitida no Lupa" in falso.recebidos
    assert falso.recebidos[:2] == ["sistema", "mensagem"]


async def test_cliente_falso_aceita_roteiro_por_funcao_e_repete_o_ultimo() -> None:
    """Cliente falso aceita roteiro por funcao e repete o ultimo."""
    por_funcao = ClienteFalso(lambda pedido: Roteiro(resposta=pedido.modelo))
    assert (await por_funcao.responder(_pedido())).texto == "claude-opus-5-5"
    lista = ClienteFalso([Roteiro(resposta="a"), Roteiro(resposta="b")])
    textos = [(await lista.responder(_pedido())).texto for _ in range(3)]
    assert textos == ["a", "b", "b"]
