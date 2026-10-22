"""Política de recusa (Etapa 5.7): classificador por regras antes de chamar o modelo.

As regras ficam em `dados/recusa.yaml` (versionado) e são aplicadas à pergunta em minúsculas e
sem acentos. Pergunta vedada não chega ao modelo: o assessor recebe a explicação do limite em
linguagem simples e uma sugestão do que pode perguntar. O prompt de sistema repete a política
para o caso que escapar das regras.
"""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from lupa.ingestao.deteccao import dobrar


@dataclass(frozen=True)
class Categoria:
    """Categoria vedada.

    Attributes:
        nome: Identificador (`valoracao_prova`...).
        limite: Explicação do limite.
        sugestao: O que o assessor pode perguntar.
        padroes: `(id, regex)`.
    """

    nome: str
    limite: str
    sugestao: str
    padroes: tuple[tuple[str, re.Pattern[str]], ...]


@dataclass(frozen=True)
class Politica:
    """Política versionada.

    Attributes:
        versao: Versão do YAML.
        categorias: Categorias em ordem.
    """

    versao: str
    categorias: tuple[Categoria, ...]


@dataclass(frozen=True)
class Recusa:
    """Pergunta recusada.

    Attributes:
        categoria: Categoria vedada.
        padrao: Regra que disparou.
        mensagem: Texto mostrado ao assessor.
    """

    categoria: str
    padrao: str
    mensagem: str


@cache
def politica_padrao() -> Politica:
    """Política de `dados/recusa.yaml`, lida uma vez.

    Returns:
        Política compilada.
    """
    texto = files("lupa.agente").joinpath("dados").joinpath("recusa.yaml").read_text("utf-8")
    dados = yaml.safe_load(texto)
    categorias = tuple(
        Categoria(
            str(nome),
            str(item["limite"]),
            str(item["sugestao"]),
            tuple((str(p["id"]), re.compile(str(p["regex"]))) for p in item["padroes"]),
        )
        for nome, item in dados["categorias"].items()
    )
    return Politica(str(dados["versao"]), categorias)


def classificar(pergunta: str, politica: Politica | None = None) -> Recusa | None:
    """Aplica as regras à pergunta.

    Args:
        pergunta: Pergunta do assessor.
        politica: Política (padrão: a do YAML).

    Returns:
        Recusa, ou None se a pergunta é permitida.
    """
    dobrada = " ".join(dobrar(pergunta).split())
    for categoria in (politica or politica_padrao()).categorias:
        for ident, regex in categoria.padroes:
            if regex.search(dobrada):
                return Recusa(categoria.nome, ident, f"{categoria.limite} {categoria.sugestao}")
    return None
