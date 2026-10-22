"""Modo de teste do agente: cliente falso com roteiro lido de arquivo (Etapa 6.8).

`LUPA_AGENTE_CLIENTE=falso` troca o `ClienteSdk` por um `ClienteFalso` cujo roteiro vem de
`LUPA_AGENTE_ROTEIRO` (JSON; padrão `dados/roteiro_falso.json`). Só em `desenvolvimento` ou
`teste`; em `producao` a aplicação se recusa a subir. Serve aos testes ponta a ponta do chat,
sem chave de API e sem rede.

Cada roteiro do arquivo tem `quando` (trecho, em minúsculas, que a pergunta deve conter; o
primeiro que casar vale, e o sem `quando` é o padrão), `passos` (ferramentas do Lupa chamadas),
`texto` (texto da resposta), `citar` (citações montadas dos resultados das ferramentas:
`resultado`, `segmento` e `adulterar`, que estraga o trecho para a conferência descartá-lo) e
`tokens` (entrada, saída). Assim o roteiro cita páginas reais do processo sem conhecer os ids.
"""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lupa.agente.cliente import (
    ClienteAgente,
    ClienteFalso,
    ClienteSdk,
    PassoFerramenta,
    PedidoAgente,
    Roteiro,
    resposta_json,
)
from lupa.config import Settings

AMBIENTES_FALSO = frozenset({"desenvolvimento", "teste"})
ROTEIRO_PADRAO = Path(__file__).parent / "dados" / "roteiro_falso.json"
ORIGEM = re.compile(r"^\[origem\] (\{.*\})$", re.MULTILINE)
SEGMENTO = re.compile(r"^\[hash=([0-9a-f]{64})\] (.+)$", re.MULTILINE)
PERGUNTA = re.compile(r'Pergunta do assessor:\n"""\n(.*?)\n"""', re.DOTALL)


class ConfiguracaoAgenteError(RuntimeError):
    """Configuração do cliente do agente recusada (por exemplo, cliente falso em produção)."""


def segmentos_do_resultado(resultado: str) -> list[dict[str, str]]:
    """Segmentos citáveis de um resultado de ferramenta, com a página de origem.

    Args:
        resultado: Texto devolvido pela ferramenta.

    Returns:
        `[{pagina_id, trecho, hash_trecho}]` na ordem em que aparecem.
    """
    saida = []
    blocos = ORIGEM.split(resultado)
    for indice in range(1, len(blocos) - 1, 2):
        pagina_id = str(json.loads(blocos[indice]).get("pagina_id", ""))
        for hash_trecho, trecho in SEGMENTO.findall(blocos[indice + 1]):
            saida.append({"pagina_id": pagina_id, "trecho": trecho, "hash_trecho": hash_trecho})
    return saida


def _citacao(pedido: dict[str, Any], resultados: list[str]) -> dict[str, str] | None:
    indice = int(pedido.get("resultado", 0))
    if indice >= len(resultados):
        return None
    itens = segmentos_do_resultado(resultados[indice])
    posicao = int(pedido.get("segmento", 0))
    if posicao >= len(itens):
        return None
    citacao = dict(itens[posicao])
    if pedido.get("adulterar"):
        citacao["trecho"] = "trecho que não existe na página " + citacao["trecho"][:20]
    return citacao


def _compor(item: dict[str, Any]) -> Callable[[list[str]], str]:
    def _resposta(resultados: list[str]) -> str:
        citacoes = [c for p in item.get("citar", []) if (c := _citacao(p, resultados))]
        return resposta_json(str(item.get("texto", "")), citacoes)

    return _resposta


def _roteiro(item: dict[str, Any]) -> Roteiro:
    passos = tuple(
        PassoFerramenta(str(p["nome"]), dict(p.get("argumentos", {})))
        for p in item.get("passos", [])
    )
    entrada, saida = item.get("tokens", [100, 50])
    return Roteiro(passos=passos, resposta=_compor(item), tokens=(int(entrada), int(saida)))


def carregar_roteiro(caminho: Path) -> Callable[[PedidoAgente], Roteiro]:
    """Lê o arquivo de roteiro e devolve a escolha do roteiro pela pergunta.

    Args:
        caminho: Arquivo JSON (lista de roteiros).

    Returns:
        Função do pedido para o roteiro.
    """
    itens: list[dict[str, Any]] = json.loads(caminho.read_text(encoding="utf-8"))
    roteiros = [(str(i.get("quando", "")).lower(), _roteiro(i)) for i in itens]
    padrao = next(
        (r for q, r in roteiros if not q), Roteiro(resposta=resposta_json("Sem roteiro."))
    )

    def _escolher(pedido: PedidoAgente) -> Roteiro:
        achada = PERGUNTA.search(pedido.mensagem)
        mensagem = (achada.group(1) if achada else pedido.mensagem).lower()
        return next((r for q, r in roteiros if q and q in mensagem), padrao)

    return _escolher


def criar_cliente(settings: Settings, ambiente: dict[str, str] | None = None) -> ClienteAgente:
    """Cliente do modelo conforme `LUPA_AGENTE_CLIENTE` (`sdk`, padrão, ou `falso`).

    Args:
        settings: Configuração (ambiente de execução).
        ambiente: Variáveis de ambiente (padrão: as do processo).

    Returns:
        Cliente real ou roteirizado.

    Raises:
        ConfiguracaoAgenteError: Valor desconhecido, ou cliente falso fora de
            desenvolvimento/teste.
    """
    variaveis = os.environ if ambiente is None else ambiente
    tipo = variaveis.get("LUPA_AGENTE_CLIENTE", "sdk").strip().lower() or "sdk"
    if tipo == "sdk":
        return ClienteSdk()
    if tipo != "falso":
        raise ConfiguracaoAgenteError("LUPA_AGENTE_CLIENTE deve ser sdk ou falso")
    if settings.ambiente not in AMBIENTES_FALSO:
        raise ConfiguracaoAgenteError("cliente falso do agente recusado em produção")
    caminho = Path(variaveis.get("LUPA_AGENTE_ROTEIRO") or ROTEIRO_PADRAO)
    return ClienteFalso(carregar_roteiro(caminho))
