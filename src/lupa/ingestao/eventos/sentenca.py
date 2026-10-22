"""Extrator da sentença: data da sentença e reincidência.

A pena aplicada não é extraída: ``TipoFato`` não tem tipo para ela e nenhuma validação a usa
(registrado no relatório da 4F.2). A pena máxima pelo artigo citado na sentença serve só de
reserva quando a denúncia não a trouxe (decidido em ``lupa.ingestao.eventos.fatos``).
"""

import re
from dataclasses import replace

from lupa.dominio.enums import TipoFato
from lupa.ingestao.eventos import denuncia
from lupa.ingestao.eventos.base import buscar, candidato_do_trecho, regras_da_peca
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes

REINCIDENCIA = re.compile(r"\b(?:reu|acusado|sentenciado)\s+e\s+(?P<v>reincidente|primario)\b")
CONFIANCA_REINCIDENCIA = 0.85
REGRA_PENA_SENTENCA = "pena#sentenca"


def reincidencia(peca: PecaTexto) -> list[Candidato]:
    """Reincidência declarada na dosimetria.

    Args:
        peca: Sentença.

    Returns:
        Candidatos com valor booleano.
    """
    return [
        candidato_do_trecho(
            pagina,
            TipoFato.REINCIDENTE,
            casamento.group("v") == "reincidente",
            casamento.span(),
            CONFIANCA_REINCIDENCIA,
            "reincidente",
        )
        for pagina, casamento in buscar(REINCIDENCIA, peca)
    ]


def extrair(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Eventos da sentença.

    Args:
        peca: Sentença.
        padroes: Padrões.

    Returns:
        Candidatos (a pena máxima vem marcada como reserva).
    """
    reserva = [replace(c, regra=REGRA_PENA_SENTENCA) for c in denuncia.pena_maxima(peca, padroes)]
    return [*regras_da_peca(peca, padroes), *reincidencia(peca), *reserva]
