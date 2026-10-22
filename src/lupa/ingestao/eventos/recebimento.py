"""Extrator da decisão de recebimento: data do recebimento da denúncia."""

from lupa.ingestao.eventos.base import regras_da_peca
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes


def extrair(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Eventos da peça pelas regras de ``dados/eventos.yaml``.

    Args:
        peca: Peça.
        padroes: Padrões.

    Returns:
        Candidatos.
    """
    return regras_da_peca(peca, padroes)
