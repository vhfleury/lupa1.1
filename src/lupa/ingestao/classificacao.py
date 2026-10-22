"""Tipo e origem da peça por regras (Etapas 4E.4 e 4E.5).

Funções puras sobre o texto das páginas da peça. O tipo soma pontos do título (lista de
`dados/titulos_peca.yaml`) e de fórmulas estáveis do início da peça ("Vistos", "É o
relatório", "CERTIFICO"...), configuradas em `dados/classificacao.yaml`; sem vencedor claro, a
peça fica `outros` com confiança baixa. A origem vem do cargo de quem assina a peça (juiz,
promotor, advogado ou OAB, perito); sem assinatura reconhecível, do vocabulário do início; sem
nenhum dos dois, `desconhecida`.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from lupa.dominio.enums import OrigemPeca, TipoPeca
from lupa.ingestao.sinais_fronteira import (
    ListaTitulos,
    e_assinatura,
    normalizar,
    reconhecer_titulo,
    titulos_padrao,
)

LINHAS_ASSINATURA = 12


@dataclass(frozen=True)
class RegrasClassificacao:
    """Regras de tipo e de origem.

    Attributes:
        versao: Versão do arquivo.
        dados: Conteúdo do YAML.
        formulas: Expressões compiladas por tipo.
        cargos: Expressões de cargo por origem.
        vocabulario: Expressões de vocabulário por origem.
    """

    versao: str
    dados: dict[str, Any]
    formulas: dict[TipoPeca, tuple[re.Pattern[str], ...]]
    cargos: dict[OrigemPeca, tuple[re.Pattern[str], ...]]
    vocabulario: dict[OrigemPeca, tuple[re.Pattern[str], ...]]


@dataclass(frozen=True)
class Classificacao:
    """Resultado de uma classificação por regras.

    Attributes:
        valor: Tipo ou origem escolhido.
        confianca: Confiança de 0 a 1.
        motivo: Como foi decidido (`titulo`, `formulas`, `assinatura`, `vocabulario`,
            `ambiguo`, `sem_indicio`).
        pontos: Pontuação por candidato (só para o tipo).
    """

    valor: str
    confianca: float
    motivo: str
    pontos: dict[str, float]


def _compilar(padroes: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.MULTILINE) for p in padroes)


def regras_classificacao_de(dados: dict[str, Any]) -> RegrasClassificacao:
    """Monta as regras a partir do YAML lido.

    Args:
        dados: Conteúdo do YAML.

    Returns:
        Regras compiladas.
    """
    origem = dados["origem"]
    return RegrasClassificacao(
        versao=str(dados["versao"]),
        dados=dados,
        formulas={TipoPeca(t): _compilar(c["formulas"]) for t, c in dados["tipos"].items()},
        cargos={OrigemPeca(o): _compilar(p) for o, p in origem["cargos"].items()},
        vocabulario={OrigemPeca(o): _compilar(p) for o, p in origem["vocabulario"].items()},
    )


@cache
def regras_classificacao_padrao() -> RegrasClassificacao:
    """Regras versionadas em `dados/classificacao.yaml`."""
    texto = files("lupa.ingestao").joinpath("dados/classificacao.yaml").read_text("utf-8")
    return regras_classificacao_de(yaml.safe_load(texto))


def _normalizadas(linhas: Sequence[str]) -> str:
    return "\n".join(normalizar(linha).lower() for linha in linhas)


def _titulo_da_peca(linhas: Sequence[str], lista: ListaTitulos) -> tuple[str | None, str | None]:
    for linha in linhas[:4]:
        titulo = reconhecer_titulo(linha, lista)
        if titulo is not None:
            return titulo.titulo, titulo.tipo
    return None, None


def _pontos_tipo(
    linhas: Sequence[str], regras: RegrasClassificacao, lista: ListaTitulos
) -> tuple[dict[TipoPeca, float], str | None]:
    dados = regras.dados
    titulo, _ = _titulo_da_peca(linhas, lista)
    texto = _normalizadas(linhas[: int(dados["linhas_inicio"])])
    pontos: dict[TipoPeca, float] = {}
    for tipo, config in dados["tipos"].items():
        candidato = TipoPeca(tipo)
        soma = float(dados["peso_formula"]) * sum(
            1 for p in regras.formulas[candidato] if p.search(texto)
        )
        if titulo is not None and titulo in {normalizar(t) for t in config["titulos"]}:
            unico = sum(
                1 for c in dados["tipos"].values() if titulo in map(normalizar, c["titulos"])
            )
            soma += float(dados["peso_titulo"] if unico == 1 else dados["peso_titulo_indefinido"])
        if soma:
            pontos[candidato] = soma
    return pontos, titulo


def classificar_tipo(
    linhas_corpo: Sequence[str],
    regras: RegrasClassificacao | None = None,
    lista: ListaTitulos | None = None,
) -> Classificacao:
    """Tipo da peça pelo título e pelas fórmulas do início.

    Args:
        linhas_corpo: Linhas do corpo da peça (sem cabeçalho e rodapé repetidos), em ordem.
        regras: Regras (padrão: `regras_classificacao_padrao()`).
        lista: Títulos (padrão: `titulos_padrao()`).

    Returns:
        Tipo, confiança e pontos. Ambíguo ou sem indício vira `outros` com confiança baixa.
    """
    regras = regras or regras_classificacao_padrao()
    lista = lista or titulos_padrao()
    dados = regras.dados
    pontos, titulo = _pontos_tipo(linhas_corpo, regras, lista)
    ordenados = sorted(pontos.items(), key=lambda item: (-item[1], item[0].value))
    registro = {t.value: p for t, p in ordenados}
    baixa = float(dados["confianca_ambiguo"])
    if not ordenados or ordenados[0][1] < float(dados["pontuacao_minima"]):
        return Classificacao(TipoPeca.OUTROS.value, baixa, "sem_indicio", registro)
    melhor, nota = ordenados[0]
    segunda = ordenados[1][1] if len(ordenados) > 1 else 0.0
    if nota - segunda < float(dados["margem_minima"]):
        return Classificacao(TipoPeca.OUTROS.value, baixa, "ambiguo", registro)
    confianca = round(min(0.99, 0.6 + 0.1 * (nota - segunda) + (0.1 if titulo else 0.0)), 2)
    return Classificacao(melhor.value, confianca, "titulo" if titulo else "formulas", registro)


def assinatura_da_peca(
    linhas_corpo: Sequence[str], regras: RegrasClassificacao | None = None
) -> str | None:
    """Trecho normalizado da última assinatura da peça (nome, cargo, data).

    A linha de assinatura é reconhecida com tolerância a erro de OCR (`e_assinatura`); a
    linha seguinte entra junto, porque o cargo às vezes quebra de linha.

    Args:
        linhas_corpo: Linhas do corpo da peça.
        regras: Regras (padrão: `regras_classificacao_padrao()`); não usadas, mantidas para
            simetria com as demais funções.

    Returns:
        A linha da última assinatura (e a seguinte), normalizada, ou None.
    """
    finais = list(linhas_corpo[-LINHAS_ASSINATURA:])
    for posicao in range(len(finais) - 1, -1, -1):
        if e_assinatura(finais[posicao]):
            return " ".join(normalizar(linha).lower() for linha in finais[posicao : posicao + 2])
    return None


def cargo_aproximado(
    assinatura: str, regras: RegrasClassificacao | None = None
) -> OrigemPeca | None:
    """Origem pelo cargo escrito com erro de OCR ("perivo rirúinal" ~ "perito criminal").

    Cada trecho da assinatura entre vírgulas é comparado com os cargos canônicos; vale o mais
    parecido, se a semelhança passar do mínimo configurado.

    Args:
        assinatura: Assinatura normalizada (`assinatura_da_peca`).
        regras: Regras (padrão: `regras_classificacao_padrao()`).

    Returns:
        Origem do cargo mais parecido, ou None.
    """
    regras = regras or regras_classificacao_padrao()
    config = regras.dados["origem"]
    minimo = float(config["semelhanca_cargo"])
    melhor: tuple[float, OrigemPeca | None] = (0.0, None)
    trechos = [t.strip() for t in re.split(r"\s{2,}|,| em ", assinatura) if t.strip()]
    palavras = assinatura.split()
    trechos += [" ".join(palavras[i : i + 2]) for i in range(len(palavras) - 1)]
    for origem, cargos in config["cargos_canonicos"].items():
        for cargo in cargos:
            for trecho in trechos:
                nota = SequenceMatcher(None, trecho, cargo).ratio()
                if nota > melhor[0]:
                    melhor = (nota, OrigemPeca(origem))
    return melhor[1] if melhor[0] >= minimo else None


def classificar_origem(
    linhas_corpo: Sequence[str], regras: RegrasClassificacao | None = None
) -> Classificacao:
    """Origem da peça pela assinatura e, na falta dela, pelo vocabulário do início.

    Args:
        linhas_corpo: Linhas do corpo da peça, em ordem.
        regras: Regras (padrão: `regras_classificacao_padrao()`).

    Returns:
        Origem e confiança; `desconhecida` (confiança 0) quando nada decide.
    """
    regras = regras or regras_classificacao_padrao()
    config = regras.dados["origem"]
    assinatura = assinatura_da_peca(linhas_corpo, regras)
    if assinatura:
        for origem, padroes in regras.cargos.items():
            if any(p.search(assinatura) for p in padroes):
                confianca = float(config["confianca_assinatura"])
                return Classificacao(origem.value, confianca, "assinatura", {})
        aproximado = cargo_aproximado(assinatura, regras)
        if aproximado is not None:
            confianca = float(config["confianca_cargo_aproximado"])
            return Classificacao(aproximado.value, confianca, "assinatura_aproximada", {})
    inicio = _normalizadas(linhas_corpo[: int(regras.dados["linhas_inicio"])])
    votos = {o: sum(1 for p in ps if p.search(inicio)) for o, ps in regras.vocabulario.items()}
    ordenados = sorted(votos.items(), key=lambda item: -item[1])
    if ordenados and ordenados[0][1] > 0 and (len(ordenados) < 2 or ordenados[1][1] == 0):
        confianca = float(config["confianca_vocabulario"])
        return Classificacao(ordenados[0][0].value, confianca, "vocabulario", {})
    return Classificacao(OrigemPeca.DESCONHECIDA.value, 0.0, "sem_indicio", {})
