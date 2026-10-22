"""Roteador de páginas (4C.4): função pura dos sinais para o caminho de extração.

`rotear` devolve `nativa` (camada de texto confiável), `ocr` (página digitalizada), `vazia`
ou None (abstenção: página híbrida ou ambígua, que vai para OCR integral com o texto nativo
guardado para fusão). Os limiares ficam em `dados/roteador.yaml`, versionado com `versao` e
`fonte`. A regra é conservadora: na dúvida, abstém; só é `nativa` a página sem imagem opaca
relevante, sem texto invisível e com texto legível; e só é `vazia` a página sem tinta e sem
imagem opaca (digitalização em branco vai ao OCR, que confirma a ausência de texto).
"""

from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from lupa.dominio.enums import TipoPagina


@dataclass(frozen=True)
class Limiares:
    """Limiares do roteador.

    Attributes:
        versao: Versão do arquivo de limiares.
        fonte: De onde vieram os números.
        vazia_max_caracteres: Máximo de caracteres numa página visualmente vazia.
        nativa_min_caracteres: Mínimo de caracteres para confiar na camada de texto.
        nativa_max_area_imagem_opaca: Máxima fração coberta por imagem opaca.
        nativa_max_fragmentacao: Máxima fração de palavras de um caractere.
        nativa_max_substituicao: Máxima fração de U+FFFD.
        nativa_max_caracteres_invisiveis: Máximo de caracteres invisíveis.
        digitalizada_min_area_imagem_opaca: Fração mínima de imagem opaca.
        digitalizada_max_caracteres: Máximo de caracteres na camada de texto.
    """

    versao: str
    fonte: str
    vazia_max_caracteres: int
    nativa_min_caracteres: int
    nativa_max_area_imagem_opaca: float
    nativa_max_fragmentacao: float
    nativa_max_substituicao: float
    nativa_max_caracteres_invisiveis: int
    digitalizada_min_area_imagem_opaca: float
    digitalizada_max_caracteres: int


def limiares_de(dados: dict[str, Any]) -> Limiares:
    """Monta os limiares a partir do YAML lido.

    Args:
        dados: Conteúdo do YAML.

    Returns:
        Limiares.
    """
    vazia, nativa, digitalizada = dados["vazia"], dados["nativa"], dados["digitalizada"]
    return Limiares(
        versao=str(dados["versao"]),
        fonte=str(dados["fonte"]),
        vazia_max_caracteres=int(vazia["max_caracteres"]),
        nativa_min_caracteres=int(nativa["min_caracteres"]),
        nativa_max_area_imagem_opaca=float(nativa["max_area_imagem_opaca"]),
        nativa_max_fragmentacao=float(nativa["max_fragmentacao"]),
        nativa_max_substituicao=float(nativa["max_substituicao"]),
        nativa_max_caracteres_invisiveis=int(nativa["max_caracteres_invisiveis"]),
        digitalizada_min_area_imagem_opaca=float(digitalizada["min_area_imagem_opaca"]),
        digitalizada_max_caracteres=int(digitalizada["max_caracteres"]),
    )


@cache
def limiares_padrao() -> Limiares:
    """Limiares de `dados/roteador.yaml`, lidos uma vez.

    Returns:
        Limiares versionados.
    """
    texto = files("lupa.ingestao").joinpath("dados").joinpath("roteador.yaml").read_text("utf-8")
    return limiares_de(yaml.safe_load(texto))


def _camada_confiavel(sinais: dict[str, Any], limiares: Limiares) -> bool:
    caracteres = int(sinais["caracteres_imprimiveis"])
    substituicao = int(sinais["caracteres_substituicao"]) / max(1, caracteres)
    return (
        caracteres >= limiares.nativa_min_caracteres
        and float(sinais["fragmentacao"]) <= limiares.nativa_max_fragmentacao
        and substituicao <= limiares.nativa_max_substituicao
        and int(sinais["caracteres_invisiveis"]) <= limiares.nativa_max_caracteres_invisiveis
    )


def rotear(sinais: dict[str, Any], limiares: Limiares | None = None) -> TipoPagina | None:
    """Escolhe o caminho de extração da página.

    Args:
        sinais: Sinais de `lupa.ingestao.sinais.medir_sinais`.
        limiares: Limiares (padrão: os do YAML versionado).

    Returns:
        `vazia`, `ocr`, `nativa`, ou None para abstenção (OCR integral e fusão).
    """
    lim = limiares or limiares_padrao()
    caracteres = int(sinais["caracteres_imprimiveis"])
    opaca = float(sinais["area_imagem_opaca"])
    sem_imagem = opaca <= lim.nativa_max_area_imagem_opaca
    if sem_imagem and bool(sinais["visualmente_vazia"]) and caracteres <= lim.vazia_max_caracteres:
        return TipoPagina.VAZIA
    if opaca >= lim.digitalizada_min_area_imagem_opaca and caracteres <= (
        lim.digitalizada_max_caracteres
    ):
        return TipoPagina.OCR
    if sem_imagem and _camada_confiavel(sinais, lim):
        return TipoPagina.NATIVA
    return None
