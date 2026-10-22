"""Registro das validações disponíveis por matéria e versão do catálogo."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from lupa.validacoes.criminal import prescricao, preventiva, tempestividade
from lupa.validacoes.modelo import AchadoValidacao, ModeloProcesso
from lupa.validacoes.versao import VERSAO_CATALOGO

Materia = Literal["criminal", "civel"]

__all__ = ["CATALOGO", "VERSAO_CATALOGO", "Materia", "Validacao", "validacoes_de"]


@dataclass(frozen=True)
class Validacao:
    """Entrada do catálogo: nome, fatos usados, base legal e função pura."""

    nome: str
    fatos_necessarios: tuple[str, ...]
    base_legal: str
    executar: Callable[[ModeloProcesso, date], AchadoValidacao]


CATALOGO: Mapping[str, tuple[Validacao, ...]] = {
    "criminal": tuple(
        Validacao(m.NOME, m.FATOS_NECESSARIOS, m.BASE_LEGAL, m.executar)
        for m in (tempestividade, prescricao, preventiva)
    ),
    "civel": (),
}


def validacoes_de(materia: str) -> tuple[Validacao, ...]:
    """Lista as validações de uma matéria.

    Args:
        materia: ``criminal`` ou ``civel``.

    Returns:
        Validações registradas.

    Raises:
        ValueError: Se a matéria não existir no catálogo.
    """
    if materia not in CATALOGO:
        raise ValueError(f"matéria desconhecida: {materia}")
    return CATALOGO[materia]
