"""Cliente do modelo atrás de uma interface (Etapa 5).

O resto de `lupa.agente` depende só do `Protocol` `ClienteAgente`. `ClienteSdk` é a
implementação real sobre o Claude Agent SDK (`claude-agent-sdk`); `ClienteFalso` é roteirizado
para os testes e grava tudo o que o "modelo" recebe. Trocar o SDK pelo tool runner do SDK
`anthropic` é escrever outra implementação de `ClienteAgente` aqui.

As duas implementações aplicam a mesma política de ferramentas (`decidir_ferramenta`): só as
ferramentas do Lupa (`mcp__lupa__<nome>`) são permitidas; qualquer ferramenta embutida do
harness é negada.
"""

import json
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

SERVIDOR_MCP = "lupa"
PREFIXO_FERRAMENTA = f"mcp__{SERVIDOR_MCP}__"
FERRAMENTAS_EMBUTIDAS = (
    "Agent",
    "Bash",
    "BashOutput",
    "Edit",
    "ExitPlanMode",
    "Glob",
    "Grep",
    "KillShell",
    "ListMcpResources",
    "LSP",
    "Monitor",
    "MultiEdit",
    "NotebookEdit",
    "NotebookRead",
    "PowerShell",
    "Read",
    "ReadMcpResource",
    "Skill",
    "SlashCommand",
    "Task",
    "TaskCreate",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "TodoWrite",
    "ToolSearch",
    "WebFetch",
    "WebSearch",
    "Workflow",
    "Write",
)
"""Ferramentas embutidas conhecidas do Claude Code, negadas por nome (além de `tools=[]`)."""

AMBIENTE_CLI = {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1",
    "ENABLE_TOOL_SEARCH": "false",
}
"""Variáveis passadas ao binário do SDK: sem tráfego além da API do modelo."""

Manipulador = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class FerramentaAgente:
    """Ferramenta oferecida ao modelo.

    Attributes:
        nome: Nome curto (sem prefixo).
        descricao: O que a ferramenta faz (o modelo lê).
        esquema: Esquema JSON dos argumentos.
        executar: Função assíncrona que recebe os argumentos e devolve texto.
    """

    nome: str
    descricao: str
    esquema: dict[str, Any]
    executar: Manipulador


@dataclass(frozen=True)
class PedidoAgente:
    """Uma chamada ao agente.

    Attributes:
        prompt_sistema: Prompt de sistema versionado.
        mensagem: Mensagem do usuário já montada (dado delimitado e instrução depois).
        modelo: Identificador do modelo.
        max_turnos: Limite de turnos do laço do agente.
        ferramentas: Ferramentas permitidas.
    """

    prompt_sistema: str
    mensagem: str
    modelo: str
    max_turnos: int
    ferramentas: tuple[FerramentaAgente, ...] = ()


@dataclass(frozen=True)
class ChamadaFerramenta:
    """Uma tentativa de chamada de ferramenta feita pelo modelo.

    Attributes:
        nome: Nome qualificado pedido (`mcp__lupa__x` ou o de uma embutida).
        permitida: Se a política deixou executar.
    """

    nome: str
    permitida: bool


@dataclass(frozen=True)
class RespostaAgente:
    """Resultado de uma chamada ao agente.

    Attributes:
        texto: Texto final do modelo (deve ser o JSON da resposta).
        modelo: Modelo que respondeu.
        tokens_entrada: Tokens de entrada (todos os turnos).
        tokens_saida: Tokens de saída (todos os turnos).
        latencia_ms: Latência total.
        chamadas: Chamadas de ferramenta tentadas, em ordem.
    """

    texto: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int
    chamadas: tuple[ChamadaFerramenta, ...] = ()


class ClienteAgente(Protocol):
    """Interface do cliente do modelo usada por todo o agente."""

    async def responder(self, pedido: PedidoAgente) -> RespostaAgente:
        """Executa o laço do agente com as ferramentas do pedido.

        Args:
            pedido: Prompt, mensagem, modelo e ferramentas.

        Returns:
            Texto final, tokens, latência e chamadas de ferramenta.
        """
        ...


class ClienteAgenteError(RuntimeError):
    """Falha do cliente (credencial, rede, API); a mensagem não contém conteúdo dos autos."""


def nome_qualificado(nome: str) -> str:
    """Nome com que o modelo enxerga uma ferramenta do Lupa.

    Args:
        nome: Nome curto.

    Returns:
        `mcp__lupa__<nome>`.
    """
    return f"{PREFIXO_FERRAMENTA}{nome}"


def decidir_ferramenta(nome: str, permitidas: frozenset[str]) -> bool:
    """Política única de ferramentas: só as do Lupa listadas no pedido.

    Args:
        nome: Nome qualificado pedido pelo modelo.
        permitidas: Nomes qualificados permitidos.

    Returns:
        Verdadeiro se pode executar.
    """
    return nome.startswith(PREFIXO_FERRAMENTA) and nome in permitidas


def permitidas_do_pedido(pedido: PedidoAgente) -> frozenset[str]:
    """Nomes qualificados das ferramentas do pedido.

    Args:
        pedido: Pedido.

    Returns:
        Conjunto de nomes permitidos.
    """
    return frozenset(nome_qualificado(f.nome) for f in pedido.ferramentas)


# --- Implementação real (Claude Agent SDK) -------------------------------------------------


def _resultado_ferramenta(texto: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texto}]}


def _envolver(
    ferramenta: FerramentaAgente,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    async def _executar(argumentos: dict[str, Any]) -> dict[str, Any]:
        return _resultado_ferramenta(await ferramenta.executar(dict(argumentos)))

    return _executar


def criar_guarda(
    permitidas: frozenset[str], registro: list[ChamadaFerramenta]
) -> Callable[[Any, str | None, Any], Awaitable[dict[str, Any]]]:
    """Hook `PreToolUse` que nega toda ferramenta fora da lista e registra a tentativa.

    Args:
        permitidas: Nomes qualificados permitidos.
        registro: Lista onde cada tentativa é anotada.

    Returns:
        Callback no formato de hook do SDK.
    """

    async def _guarda(entrada: Any, _tool_use_id: str | None, _contexto: Any) -> dict[str, Any]:
        nome = str(entrada.get("tool_name", ""))
        permitida = decidir_ferramenta(nome, permitidas)
        registro.append(ChamadaFerramenta(nome, permitida))
        if permitida:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "ferramenta não permitida no Lupa",
            }
        }

    return _guarda


def montar_opcoes(pedido: PedidoAgente, registro: list[ChamadaFerramenta], cwd: str) -> Any:
    """Opções do SDK: só as ferramentas do Lupa, nada do harness, sem configuração do host.

    Args:
        pedido: Pedido.
        registro: Lista que o hook preenche com as tentativas de ferramenta.
        cwd: Diretório de trabalho vazio.

    Returns:
        `ClaudeAgentOptions`.
    """
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, SdkMcpTool, create_sdk_mcp_server

    ferramentas = [
        SdkMcpTool(f.nome, f.descricao, f.esquema, _envolver(f)) for f in pedido.ferramentas
    ]
    servidor = create_sdk_mcp_server(name=SERVIDOR_MCP, version="1.0.0", tools=ferramentas)
    permitidas = permitidas_do_pedido(pedido)
    return ClaudeAgentOptions(
        tools=[],
        allowed_tools=sorted(permitidas),
        disallowed_tools=list(FERRAMENTAS_EMBUTIDAS),
        permission_mode="dontAsk",
        system_prompt=pedido.prompt_sistema,
        model=pedido.modelo,
        mcp_servers={SERVIDOR_MCP: servidor},
        strict_mcp_config=True,
        max_turns=pedido.max_turnos,
        setting_sources=[],
        agents={},
        plugins=[],
        cwd=cwd,
        env=dict(AMBIENTE_CLI),
        hooks={
            "PreToolUse": [
                HookMatcher(matcher=None, hooks=[cast(Any, criar_guarda(permitidas, registro))])
            ]
        },
    )


@dataclass
class _Acumulado:
    texto: str = ""
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0
    erro: str | None = None
    textos: list[str] = field(default_factory=list)


def _somar_uso(acumulado: _Acumulado, uso: dict[str, Any] | None) -> None:
    if not uso:
        return
    acumulado.tokens_entrada = (
        int(uso.get("input_tokens") or 0)
        + int(uso.get("cache_read_input_tokens") or 0)
        + int(uso.get("cache_creation_input_tokens") or 0)
    )
    acumulado.tokens_saida = int(uso.get("output_tokens") or 0)


def consumir_mensagem(acumulado: _Acumulado, mensagem: Any) -> None:
    """Incorpora uma mensagem do SDK ao resultado (texto final, modelo, tokens, erro).

    Args:
        acumulado: Estado parcial.
        mensagem: `AssistantMessage`, `ResultMessage` ou outra (ignorada).
    """
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    if isinstance(mensagem, AssistantMessage):
        acumulado.modelo = mensagem.model or acumulado.modelo
        if mensagem.error:
            acumulado.erro = str(mensagem.error)
        acumulado.textos.extend(b.text for b in mensagem.content if isinstance(b, TextBlock))
    elif isinstance(mensagem, ResultMessage):
        _somar_uso(acumulado, mensagem.usage)
        if mensagem.is_error:
            acumulado.erro = acumulado.erro or mensagem.subtype
        acumulado.texto = mensagem.result or (acumulado.textos[-1] if acumulado.textos else "")


class ClienteSdk:
    """Cliente real sobre o Claude Agent SDK.

    A credencial vem do ambiente do processo (`ANTHROPIC_API_KEY`) ou do login do Claude Code da
    máquina; nunca de arquivo do repositório.
    """

    async def _mensagens(self, pedido: PedidoAgente, opcoes: Any) -> AsyncIterator[Any]:
        from claude_agent_sdk import query

        async for mensagem in query(prompt=pedido.mensagem, options=opcoes):
            yield mensagem

    async def responder(self, pedido: PedidoAgente) -> RespostaAgente:
        """Executa o laço do agente no SDK.

        Args:
            pedido: Pedido.

        Returns:
            Resposta com tokens, latência e chamadas de ferramenta.

        Raises:
            ClienteAgenteError: Falha do SDK, da credencial ou da API.
        """
        from claude_agent_sdk import ClaudeSDKError

        registro: list[ChamadaFerramenta] = []
        acumulado = _Acumulado(modelo=pedido.modelo)
        inicio = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="lupa-agente-") as cwd:
            opcoes = montar_opcoes(pedido, registro, cwd)
            try:
                async for mensagem in self._mensagens(pedido, opcoes):
                    consumir_mensagem(acumulado, mensagem)
            except ClaudeSDKError as erro:
                raise ClienteAgenteError(type(erro).__name__) from None
        if acumulado.erro:
            raise ClienteAgenteError(acumulado.erro)
        return RespostaAgente(
            texto=acumulado.texto,
            modelo=acumulado.modelo,
            tokens_entrada=acumulado.tokens_entrada,
            tokens_saida=acumulado.tokens_saida,
            latencia_ms=int((time.monotonic() - inicio) * 1000),
            chamadas=tuple(registro),
        )


# --- Implementação falsa (testes) ----------------------------------------------------------


@dataclass(frozen=True)
class PassoFerramenta:
    """Chamada de ferramenta roteirizada.

    Attributes:
        nome: Nome curto de ferramenta do Lupa, ou nome de uma embutida (`Read`...).
        argumentos: Argumentos enviados.
    """

    nome: str
    argumentos: dict[str, Any] = field(default_factory=dict)


Composicao = Callable[[list[str]], str]


@dataclass(frozen=True)
class Roteiro:
    """O que o modelo falso faz numa chamada.

    Attributes:
        passos: Ferramentas chamadas, em ordem.
        resposta: Texto final, ou função que o compõe a partir dos resultados das ferramentas.
        tokens: Tokens (entrada, saída) informados.
    """

    passos: tuple[PassoFerramenta, ...] = ()
    resposta: str | Composicao = ""
    tokens: tuple[int, int] = (100, 50)


def resposta_json(texto: str, citacoes: Sequence[dict[str, Any]] = ()) -> str:
    """JSON de resposta no formato do contrato.

    Args:
        texto: Texto.
        citacoes: Citações.

    Returns:
        JSON.
    """
    return json.dumps({"texto": texto, "citacoes": list(citacoes)}, ensure_ascii=False)


class ClienteFalso:
    """Modelo roteirizado: executa as ferramentas pedidas e grava tudo o que recebeu.

    Attributes:
        recebidos: Todo texto enviado ao "modelo": prompts de sistema, mensagens e resultados de
            ferramenta.
        chamadas: Todas as tentativas de ferramenta, com a decisão da política.
        pedidos: Pedidos recebidos.
    """

    def __init__(self, roteiros: Sequence[Roteiro] | Callable[[PedidoAgente], Roteiro]) -> None:
        """Cria o cliente.

        Args:
            roteiros: Lista consumida em ordem (a última se repete), ou função do pedido.
        """
        self._roteiros = roteiros
        self._indice = 0
        self.recebidos: list[str] = []
        self.chamadas: list[ChamadaFerramenta] = []
        self.pedidos: list[PedidoAgente] = []

    def _proximo(self, pedido: PedidoAgente) -> Roteiro:
        if callable(self._roteiros):
            return self._roteiros(pedido)
        roteiro = self._roteiros[min(self._indice, len(self._roteiros) - 1)]
        self._indice += 1
        return roteiro

    async def _executar(self, passo: PassoFerramenta, pedido: PedidoAgente) -> str:
        embutida = passo.nome in FERRAMENTAS_EMBUTIDAS
        nome = passo.nome if embutida else nome_qualificado(passo.nome)
        permitida = decidir_ferramenta(nome, permitidas_do_pedido(pedido))
        self.chamadas.append(ChamadaFerramenta(nome, permitida))
        if not permitida:
            return "ferramenta não permitida no Lupa"
        ferramenta = next(f for f in pedido.ferramentas if nome_qualificado(f.nome) == nome)
        return await ferramenta.executar(dict(passo.argumentos))

    async def responder(self, pedido: PedidoAgente) -> RespostaAgente:
        """Segue o roteiro.

        Args:
            pedido: Pedido.

        Returns:
            Resposta roteirizada.
        """
        self.pedidos.append(pedido)
        self.recebidos.extend([pedido.prompt_sistema, pedido.mensagem])
        roteiro = self._proximo(pedido)
        inicio = len(self.chamadas)
        resultados = [await self._executar(p, pedido) for p in roteiro.passos]
        self.recebidos.extend(resultados)
        texto = roteiro.resposta(resultados) if callable(roteiro.resposta) else roteiro.resposta
        return RespostaAgente(
            texto=texto,
            modelo=pedido.modelo,
            tokens_entrada=roteiro.tokens[0],
            tokens_saida=roteiro.tokens[1],
            latencia_ms=1,
            chamadas=tuple(self.chamadas[inicio:]),
        )
