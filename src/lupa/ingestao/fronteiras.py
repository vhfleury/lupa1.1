"""Classificador de fronteira de peça por regras (Etapas 4E.2 e 4E.3).

`pontuar` é função pura dos sinais de duas páginas consecutivas com texto (a anterior e a
atual; versos em branco ficam com a peça anterior e são pulados). Os pesos e os limiares
`forte` e `fraca` ficam em `dados/fronteiras.yaml`, versionado. Página com pontuação forte
começa peça nova; fraca também começa, mas a peça nasce com confiança baixa e a flag
`fronteira_fraca`, para conferência do assessor.

Quando a origem oferece fronteiras (entradas do ZIP, bookmarks, índice de movimentações),
elas são a fonte principal; o classificador roda mesmo assim e `conferir_origem` aponta cada
divergência: fronteira da origem sem sinal forte, ou sinal forte sem fronteira na origem.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

FORTE = "forte"
FRACA = "fraca"
ORIGEM = "origem"


@dataclass(frozen=True)
class Regras:
    """Pesos e limiares do classificador.

    Attributes:
        versao: Versão do arquivo.
        pesos: Peso de cada sinal.
        forte: Limiar de fronteira forte.
        fraca: Limiar de fronteira fraca.
        mudanca_fonte_pt: Diferença mínima de altura de linha para mudança de fonte.
        cabecalho_semelhanca: Semelhança máxima entre cabeçalhos para "cabeçalho novo".
    """

    versao: str
    pesos: dict[str, float]
    forte: float
    fraca: float
    mudanca_fonte_pt: float
    cabecalho_semelhanca: float


def regras_de(dados: dict[str, Any]) -> Regras:
    """Monta as regras a partir do YAML lido.

    Args:
        dados: Conteúdo do YAML.

    Returns:
        Regras.
    """
    return Regras(
        versao=str(dados["versao"]),
        pesos={k: float(v) for k, v in dados["pesos"].items()},
        forte=float(dados["limiares"]["forte"]),
        fraca=float(dados["limiares"]["fraca"]),
        mudanca_fonte_pt=float(dados["mudanca_fonte_pt"]),
        cabecalho_semelhanca=float(dados["cabecalho_semelhanca"]),
    )


@cache
def regras_padrao() -> Regras:
    """Regras versionadas em `dados/fronteiras.yaml`."""
    texto = files("lupa.ingestao").joinpath("dados/fronteiras.yaml").read_text("utf-8")
    return regras_de(yaml.safe_load(texto))


def _cabecalho_novo(anterior: dict[str, Any], atual: dict[str, Any], regras: Regras) -> bool:
    a, b = str(anterior.get("cabecalho") or ""), str(atual.get("cabecalho") or "")
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() < regras.cabecalho_semelhanca


def _mudou_fonte(anterior: dict[str, Any], atual: dict[str, Any], regras: Regras) -> bool:
    a, b = anterior.get("altura_linha"), atual.get("altura_linha")
    mesmo_tipo = anterior.get("tipo_pagina") == atual.get("tipo_pagina")
    return bool(mesmo_tipo and a and b and abs(float(a) - float(b)) >= regras.mudanca_fonte_pt)


def _mudou_layout(anterior: dict[str, Any], atual: dict[str, Any]) -> bool:
    a, b = anterior.get("colunas"), atual.get("colunas")
    return bool(a and b and a != b)


def sinais_ativos(
    anterior: dict[str, Any] | None, atual: dict[str, Any], regras: Regras | None = None
) -> list[str]:
    """Sinais de fronteira presentes na passagem da página anterior para a atual.

    Args:
        anterior: Sinais da última página com texto antes desta (None na primeira).
        atual: Sinais da página.
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        Nomes dos sinais (chaves de `pesos`), em ordem fixa.
    """
    regras = regras or regras_padrao()
    if atual.get("vazia"):
        return []
    anterior = anterior or {}
    presentes = {
        "titulo": bool(atual.get("titulo")) and not atual.get("titulo_secao"),
        "titulo_secao": bool(atual.get("titulo")) and bool(atual.get("titulo_secao")),
        "assinatura_anterior": bool(anterior.get("assinatura_fim")),
        "reinicio_numeracao": bool(atual.get("reinicio_numeracao")) and bool(anterior),
        "cabecalho_novo": _cabecalho_novo(anterior, atual, regras),
        "protocolo_topo": bool(atual.get("protocolo_topo")),
        "mudanca_fonte": _mudou_fonte(anterior, atual, regras),
        "mudanca_layout": _mudou_layout(anterior, atual),
    }
    return [nome for nome in regras.pesos if presentes.get(nome)]


def pontuar(
    sinais_pagina_anterior: dict[str, Any] | None,
    sinais_pagina: dict[str, Any],
    regras: Regras | None = None,
) -> float:
    """Pontuação de fronteira da página (0 a 1).

    Args:
        sinais_pagina_anterior: Sinais da última página com texto antes desta; None quando a
            página é a primeira do arquivo (sempre começa peça: 1,0).
        sinais_pagina: Sinais da página.
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        Soma dos pesos dos sinais presentes, limitada a 1; 0 para página vazia.
    """
    if sinais_pagina.get("vazia"):
        return 0.0
    if sinais_pagina_anterior is None:
        return 1.0
    regras = regras or regras_padrao()
    ativos = sinais_ativos(sinais_pagina_anterior, sinais_pagina, regras)
    return round(min(1.0, sum(regras.pesos[nome] for nome in ativos)), 4)


def nivel(pontuacao: float, regras: Regras | None = None) -> str | None:
    """Nível da fronteira para a pontuação.

    Args:
        pontuacao: Resultado de `pontuar`.
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        `forte`, `fraca` ou None.
    """
    regras = regras or regras_padrao()
    if pontuacao >= regras.forte:
        return FORTE
    if pontuacao >= regras.fraca:
        return FRACA
    return None


@dataclass(frozen=True)
class Fronteira:
    """Página (posição na lista do arquivo, 0-based) em que uma peça começa.

    Attributes:
        posicao: Índice da página na lista.
        pontuacao: Pontuação do classificador.
        nivel: `forte`, `fraca` ou `origem` (fronteira vinda da origem).
        sinais: Sinais ativos.
        divergente: Se a origem e o classificador discordam nesta página.
        origem: Entrada da origem (título, data, fonte) quando houver.
    """

    posicao: int
    pontuacao: float
    nivel: str
    sinais: tuple[str, ...] = ()
    divergente: bool = False
    origem: dict[str, Any] = field(default_factory=dict)


def avaliar(
    sinais: Sequence[dict[str, Any]], inicio: int = 0, regras: Regras | None = None
) -> list[tuple[int, float, tuple[str, ...]]]:
    """Pontua cada página com texto a partir de `inicio`.

    Args:
        sinais: Sinais de fronteira por página, em ordem.
        inicio: Primeira posição de conteúdo (depois das páginas de índice).
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        `(posição, pontuação, sinais ativos)` por página com texto.
    """
    regras = regras or regras_padrao()
    anterior: dict[str, Any] | None = None
    avaliadas = []
    for posicao in range(inicio, len(sinais)):
        atual = sinais[posicao]
        if atual.get("vazia"):
            continue
        avaliadas.append(
            (
                posicao,
                pontuar(anterior, atual, regras),
                tuple(sinais_ativos(anterior, atual, regras)),
            )
        )
        anterior = atual
    return avaliadas


def segmentar(
    sinais: Sequence[dict[str, Any]], inicio: int = 0, regras: Regras | None = None
) -> list[Fronteira]:
    """Fronteiras por regras (sem fronteiras da origem).

    A primeira página com texto sempre começa peça.

    Args:
        sinais: Sinais de fronteira por página, em ordem.
        inicio: Primeira posição de conteúdo.
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        Fronteiras em ordem.
    """
    regras = regras or regras_padrao()
    fronteiras = []
    for posicao, pontuacao, ativos in avaliar(sinais, inicio, regras):
        grau = nivel(pontuacao, regras)
        if grau is not None:
            fronteiras.append(Fronteira(posicao, pontuacao, grau, ativos))
    return fronteiras


def conferir_origem(
    sinais: Sequence[dict[str, Any]],
    origem: Sequence[tuple[int, dict[str, Any]]],
    inicio: int = 0,
    regras: Regras | None = None,
) -> tuple[list[Fronteira], list[dict[str, Any]]]:
    """Usa as fronteiras da origem e marca onde o classificador discorda.

    Args:
        sinais: Sinais de fronteira por página, em ordem.
        origem: `(posição, entrada da origem)` das fronteiras da origem.
        inicio: Primeira posição de conteúdo.
        regras: Regras (padrão: `regras_padrao()`).

    Returns:
        Fronteiras (as da origem, com `divergente` quando não há sinal forte) e a lista de
        divergências `{pagina, motivo, pontuacao, sinais}` (posição 0-based em `pagina`):
        `origem_sem_sinal_forte` ou `sinal_forte_sem_origem`.
    """
    regras = regras or regras_padrao()
    avaliadas = {p: (nota, ativos) for p, nota, ativos in avaliar(sinais, inicio, regras)}
    marcadas = {posicao for posicao, _ in origem}
    primeira = min(avaliadas, default=None)
    fronteiras: list[Fronteira] = []
    divergencias: list[dict[str, Any]] = []
    for posicao, entrada in sorted(origem, key=lambda item: item[0]):
        nota, ativos = avaliadas.get(posicao, (0.0, ()))
        if posicao == primeira:
            nota = 1.0
        divergente = nota < regras.forte
        if divergente:
            divergencias.append(_divergencia(posicao, "origem_sem_sinal_forte", nota, ativos))
        fronteiras.append(Fronteira(posicao, nota, ORIGEM, ativos, divergente, dict(entrada)))
    for posicao, (nota, ativos) in sorted(avaliadas.items()):
        if posicao not in marcadas and nota >= regras.forte:
            divergencias.append(_divergencia(posicao, "sinal_forte_sem_origem", nota, ativos))
    return fronteiras, sorted(divergencias, key=lambda d: d["pagina"])


def _divergencia(posicao: int, motivo: str, nota: float, ativos: tuple[str, ...]) -> dict[str, Any]:
    return {"pagina": posicao, "motivo": motivo, "pontuacao": nota, "sinais": list(ativos)}
