"""Textos das peças a partir de templates ``.txt`` com ``string.Template``.

Sintaxe dos templates (em ``templates/``): a primeira linha é o título da peça; parágrafos são
separados por linha em branco; ``$nome`` é substituído pelas variáveis do processo;
``[[a||b]]`` sorteia uma das alternativas; ``{{tipo:trecho}}`` marca o trecho literal de um
evento do gabarito (o marcador some do texto e o trecho fica registrado com seus offsets).
"""

import random
import re
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from string import Template

_ESCOLHA = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)
_MARCA = re.compile(r"\{\{(\w+):(.+?)\}\}", re.DOTALL)


@dataclass(frozen=True)
class Marca:
    """Trecho marcado dentro de um parágrafo.

    Attributes:
        rotulo: Tipo do evento (valor de ``TipoFato``) ou ``injecao``.
        inicio: Offset inicial no parágrafo.
        fim: Offset final (exclusivo).
    """

    rotulo: str
    inicio: int
    fim: int


@dataclass
class Paragrafo:
    """Parágrafo pronto para paginar.

    Attributes:
        texto: Texto sem marcadores.
        marcas: Trechos de eventos.
        papel: ``corpo``, ``titulo`` ou ``assinatura``.
    """

    texto: str
    marcas: list[Marca] = field(default_factory=list)
    papel: str = "corpo"


@cache
def carregar_template(nome: str) -> str:
    """Lê um template empacotado.

    Args:
        nome: Nome do arquivo sem extensão.

    Returns:
        Conteúdo do template.
    """
    return (files("lupa.sinteticos") / "templates" / f"{nome}.txt").read_text(encoding="utf-8")


def _escolher(texto: str, rng: random.Random) -> str:
    return _ESCOLHA.sub(lambda m: rng.choice(m.group(1).split("||")), texto)


def extrair_marcas(texto: str) -> Paragrafo:
    """Remove os marcadores ``{{tipo:trecho}}`` e registra os offsets.

    Args:
        texto: Parágrafo com marcadores.

    Returns:
        Parágrafo limpo com as marcas.
    """
    partes: list[str] = []
    marcas: list[Marca] = []
    posicao = 0
    tamanho = 0
    for casamento in _MARCA.finditer(texto):
        anterior = texto[posicao : casamento.start()]
        partes.append(anterior)
        tamanho += len(anterior)
        trecho = casamento.group(2)
        marcas.append(Marca(casamento.group(1), tamanho, tamanho + len(trecho)))
        partes.append(trecho)
        tamanho += len(trecho)
        posicao = casamento.end()
    partes.append(texto[posicao:])
    return Paragrafo("".join(partes), marcas)


def renderizar_texto(fonte: str, variaveis: dict[str, str], rng: random.Random) -> list[Paragrafo]:
    """Renderiza um texto com a sintaxe dos templates (sem título).

    Args:
        fonte: Texto com ``$variaveis``, ``[[escolhas]]`` e ``{{marcas}}``.
        variaveis: Valores das variáveis.
        rng: Gerador semeado.

    Returns:
        Parágrafos com marcas.
    """
    texto = _escolher(Template(fonte).substitute(variaveis), rng)
    blocos = [" ".join(b.split()) for b in texto.split("\n\n")]
    return [extrair_marcas(b) for b in blocos if b]


def renderizar_peca(
    nome: str, variaveis: dict[str, str], rng: random.Random
) -> tuple[str, list[Paragrafo]]:
    """Renderiza o template de uma peça.

    Args:
        nome: Nome do template.
        variaveis: Valores das variáveis.
        rng: Gerador semeado.

    Returns:
        Título e parágrafos (o primeiro parágrafo é o título, com papel ``titulo``).
    """
    titulo, _, corpo = carregar_template(nome).partition("\n")
    paragrafos = renderizar_texto(corpo, variaveis, rng)
    return titulo.strip(), [Paragrafo(titulo.strip(), papel="titulo"), *paragrafos]


def enchimento(variaveis: dict[str, str], rng: random.Random, quantidade: int) -> list[Paragrafo]:
    """Sorteia parágrafos genéricos (com datas distratoras) para alongar a peça.

    Args:
        variaveis: Valores das variáveis (``data_distracao`` e ``numero_oficio`` são sorteados).
        rng: Gerador semeado.
        quantidade: Número de parágrafos.

    Returns:
        Parágrafos sem marcas de evento.
    """
    modelos = carregar_template("enchimento").split("\n\n")
    saida: list[Paragrafo] = []
    for _ in range(quantidade):
        locais = {
            **variaveis,
            "data_distracao": f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/"
            f"{rng.randint(2015, 2023)}",
            "numero_oficio": f"{rng.randint(100, 9999)}/{rng.randint(2015, 2023)}",
        }
        saida.extend(renderizar_texto(rng.choice(modelos), locais, rng))
    return saida
