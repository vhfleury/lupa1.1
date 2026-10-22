"""Máquina de estados do job de ingestão: transições válidas como dados e função pura.

`concluido` e `quarentena` são finais. `falho` só volta para `recebido` (nova tentativa).
Nenhum estado volta para trás na extração a partir de `concluido`.
"""

from types import MappingProxyType
from typing import Final

from lupa.dominio.enums import EstadoJob

E = EstadoJob

TRANSICOES: Final = MappingProxyType(
    {
        E.RECEBIDO: frozenset({E.VALIDADO, E.FALHO, E.QUARENTENA}),
        E.VALIDADO: frozenset({E.EM_EXTRACAO, E.FALHO, E.QUARENTENA}),
        E.EM_EXTRACAO: frozenset({E.PARCIAL, E.EM_REVISAO, E.CONCLUIDO, E.FALHO, E.QUARENTENA}),
        E.PARCIAL: frozenset({E.EM_EXTRACAO, E.EM_REVISAO, E.FALHO}),
        E.EM_REVISAO: frozenset({E.EM_EXTRACAO, E.CONCLUIDO, E.FALHO}),
        E.FALHO: frozenset({E.RECEBIDO}),
        E.CONCLUIDO: frozenset(),
        E.QUARENTENA: frozenset(),
    }
)

ESTADOS_FINAIS: Final = frozenset(estado for estado, destinos in TRANSICOES.items() if not destinos)


class TransicaoInvalidaError(ValueError):
    """Transição de estado não permitida pela máquina de estados."""


def transicao(estado_atual: EstadoJob, novo: EstadoJob) -> bool:
    """Diz se a transição é permitida.

    Args:
        estado_atual: Estado corrente do job.
        novo: Estado desejado.

    Returns:
        Verdadeiro se `novo` é destino válido de `estado_atual`.
    """
    return novo in TRANSICOES[estado_atual]


def exigir_transicao(estado_atual: EstadoJob, novo: EstadoJob) -> None:
    """Lança erro se a transição não for permitida.

    Args:
        estado_atual: Estado corrente do job.
        novo: Estado desejado.

    Raises:
        TransicaoInvalidaError: Se a transição não estiver em `TRANSICOES`.
    """
    if not transicao(estado_atual, novo):
        raise TransicaoInvalidaError(f"transição {estado_atual} -> {novo} não permitida")
