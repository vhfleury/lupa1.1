"""Extrator da denúncia: data do fato, nascimento do réu, data da denúncia e pena máxima.

A pena máxima em abstrato sai da pena transcrita ("cuja pena é de reclusão, de 1 (um) a 4
(quatro) anos"), conferida com a tabela mínima de tipos penais (``dados/tipos_penais.yaml``,
a confirmar pelo gabinete) pelo artigo citado. Sem pena transcrita, vale a tabela pelo artigo,
com confiança menor. Pena e artigo divergentes reduzem a confiança.
"""

import re

from lupa.dominio.enums import TipoFato
from lupa.ingestao.eventos.base import buscar, candidato_do_trecho, regras_da_peca
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes

MESES_NO_ANO = 12
PENA = re.compile(
    r"\bpena\s+(?:e|sera|prevista\s+e)\s+de\s+(?:reclusao|detencao)\s*,?\s+de\s+"
    r"\d{1,2}\s*(?:\([a-z\s]+\))?\s*(?:anos?|mes(?:es)?)?\s+a\s+"
    r"(?P<maximo>\d{1,2})\s*(?:\([a-z\s]+\))?\s*(?P<unidade>anos?|mes(?:es)?)"
)
ARTIGO = re.compile(
    r"\b(?:incurs[oa]s?|sancoes|sancao|previsto)\b[^\n]{0,30}?"
    r"\bart(?:igo)?\.?\s*(?P<art>\d{1,3})\b(?P<resto>[^\n;]{0,60})"
)
LEI = re.compile(r"\blei\s+(?:n[o.]?\s*)?(?P<lei>\d{1,2}\.?\d{3})")
CONFIANCA_TEXTO = 0.9
CONFIANCA_TABELA = 0.6
CONFIANCA_DIVERGENTE = 0.5
DIGITOS_MILHAR = 3


def meses(quantidade: str, unidade: str) -> int:
    """Converte quantidade e unidade da pena em meses.

    Args:
        quantidade: Número.
        unidade: ``ano(s)`` ou ``mes(es)``.

    Returns:
        Meses.
    """
    fator = MESES_NO_ANO if unidade.startswith("ano") else 1
    return int(quantidade) * fator


def _lei(resto: str) -> str:
    achado = LEI.search(resto)
    if achado is None:
        return "cp"
    digitos = achado.group("lei").replace(".", "")
    return f"{digitos[:-DIGITOS_MILHAR]}.{digitos[-DIGITOS_MILHAR:]}"


def pena_pelo_artigo(peca: PecaTexto, padroes: Padroes) -> Candidato | None:
    """Pena máxima pela tabela mínima, a partir do primeiro artigo citado que está nela.

    Args:
        peca: Peça.
        padroes: Padrões com a tabela de tipos penais.

    Returns:
        Candidato com a citação do artigo como evidência, ou None.
    """
    for pagina, casamento in buscar(ARTIGO, peca):
        pena = padroes.pena_do_artigo(casamento.group("art"), _lei(casamento.group("resto")))
        if pena is not None:
            inicio = casamento.group(0).find("art") + casamento.start()
            return candidato_do_trecho(
                pagina,
                TipoFato.PENA_MAXIMA_ABSTRATA,
                pena,
                (inicio, casamento.end("art")),
                CONFIANCA_TABELA,
                "pena#tabela",
            )
    return None


def pena_maxima(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Pena máxima em abstrato, em meses, com evidência.

    Args:
        peca: Denúncia (ou sentença, como reserva).
        padroes: Padrões com a tabela de tipos penais.

    Returns:
        Zero ou mais candidatos (valores distintos viram conflito adiante).
    """
    pelo_artigo = pena_pelo_artigo(peca, padroes)
    transcritas: list[Candidato] = []
    for pagina, casamento in buscar(PENA, peca):
        valor = meses(casamento.group("maximo"), casamento.group("unidade"))
        confianca = CONFIANCA_TEXTO
        if pelo_artigo is not None and pelo_artigo.valor != valor:
            confianca = CONFIANCA_DIVERGENTE
        transcritas.append(
            candidato_do_trecho(
                pagina,
                TipoFato.PENA_MAXIMA_ABSTRATA,
                valor,
                casamento.span(),
                confianca,
                "pena#texto",
            )
        )
    if transcritas:
        return transcritas
    return [pelo_artigo] if pelo_artigo else []


def extrair(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Eventos da denúncia.

    Args:
        peca: Denúncia.
        padroes: Padrões.

    Returns:
        Candidatos.
    """
    return [*regras_da_peca(peca, padroes), *pena_maxima(peca, padroes)]
