"""Extrator do recurso: espécie e recorrente (``tipo_recurso``) e data da interposição.

O recorrente sai do texto ("por seu defensor" é defesa; peça aberta pelo Ministério Público é
MP) e, sem pista no texto, da origem da peça (4E.5). Sem recorrente conhecido, o tipo de recurso
não é gerado: a tempestividade fica ``verificar`` em vez de contar o prazo de quem não recorreu.
"""

import re

from lupa.dominio.enums import OrigemPeca, TipoFato
from lupa.ingestao.eventos.base import buscar, candidato_do_trecho, regras_da_peca
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes

ESPECIE = re.compile(
    r"\b(?:interpor|interpoe|opor|opoe|apresentar)\s+(?:o\s+presente\s+|os\s+presentes\s+)?"
    r"(?P<especie>recurso\s+de\s+apelacao|apelacao|recurso\s+em\s+sentido\s+estrito|"
    r"embargos\s+de\s+declaracao)"
)
DEFESA = re.compile(
    r"\bpor\s+(?:seu|sua)\s+(?:defensor|defensora|advogad[oa]|procurador)|\bdefensoria\s+publica"
)
MP = re.compile(r"\bministerio\s+publico\b")
INICIO_PECA = 600
CONFIANCA_TIPO = 0.9
ORIGEM_RECORRENTE = {OrigemPeca.DEFESA: "defesa", OrigemPeca.MP: "mp"}


def especie(texto: str) -> str:
    """Espécie normalizada do recurso.

    Args:
        texto: Espécie como casada (dobrada).

    Returns:
        ``apelacao``, ``rese`` ou ``embargos_declaracao``.
    """
    if "apelacao" in texto:
        return "apelacao"
    if texto.startswith("embargos"):
        return "embargos_declaracao"
    return "rese"


def recorrente(peca: PecaTexto) -> str | None:
    """Quem recorre: ``defesa``, ``mp`` ou None se não há pista.

    Args:
        peca: Recurso.

    Returns:
        Recorrente.
    """
    inicio = peca.paginas[0].analise.dobrado[:INICIO_PECA] if peca.paginas else ""
    if DEFESA.search(inicio):
        return "defesa"
    if MP.search(inicio):
        return "mp"
    return ORIGEM_RECORRENTE.get(peca.origem)


def tipo_recurso(peca: PecaTexto) -> list[Candidato]:
    """Espécie do recurso com o recorrente.

    Args:
        peca: Recurso.

    Returns:
        No máximo um candidato (a primeira espécie citada como interposta).
    """
    quem = recorrente(peca)
    if quem is None:
        return []
    for pagina, casamento in buscar(ESPECIE, peca):
        valor = {"tipo": especie(casamento.group("especie")), "recorrente": quem}
        return [
            candidato_do_trecho(
                pagina,
                TipoFato.TIPO_RECURSO,
                valor,
                casamento.span(),
                CONFIANCA_TIPO,
                "tipo_recurso",
            )
        ]
    return []


def extrair(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Eventos do recurso.

    Args:
        peca: Recurso.
        padroes: Padrões.

    Returns:
        Candidatos.
    """
    return [*regras_da_peca(peca, padroes), *tipo_recurso(peca)]
