"""Comparação dos achados da pipeline com o ``resultado_esperado`` do gabarito (Etapa 4F.7).

Os ids de fato e de evidência mudam entre o gabarito e a pipeline, então a comparação ignora as
chaves de id (``IDS``) em qualquer nível de ``valores``. Um achado "bate" quando o resultado é o
mesmo e os valores sem ids são iguais (datas, prazos, intervalos, pena, faixa, cadeia); a
explicação é comparada à parte, porque o texto cita só esses mesmos valores.
"""

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from pydantic import BaseModel

from lupa.sinteticos.gabarito import ResultadoEsperado

IDS = frozenset({"fato_id", "evidencia_id", "evidencia_ids", "fato_ids"})


class AchadoComparavel(Protocol):
    """O que a comparação lê de um achado (do motor ou do domínio)."""

    @property
    def validacao(self) -> str:
        """Nome da validação."""

    @property
    def resultado(self) -> Any:
        """Resultado."""

    @property
    def valores(self) -> dict[str, Any]:
        """Valores."""

    @property
    def explicacao(self) -> str:
        """Explicação."""


class ComparacaoAchado(BaseModel):
    """Resultado da comparação de uma validação."""

    validacao: str
    esperado: str
    obtido: str | None
    resultado_igual: bool
    valores_iguais: bool
    explicacao_igual: bool
    diferencas: list[str]


def sem_ids(valor: Any) -> Any:
    """Remove as chaves de id em qualquer nível.

    Args:
        valor: Valores do achado.

    Returns:
        Cópia sem ids.
    """
    if isinstance(valor, dict):
        return {k: sem_ids(v) for k, v in valor.items() if k not in IDS}
    if isinstance(valor, list | tuple):
        return [sem_ids(v) for v in valor]
    return valor


def _diferencas(esperado: Any, obtido: Any, caminho: str = "") -> list[str]:
    if isinstance(esperado, dict) and isinstance(obtido, dict):
        chaves = sorted(set(esperado) | set(obtido))
        return [
            d for k in chaves for d in _diferencas(esperado.get(k), obtido.get(k), f"{caminho}.{k}")
        ]
    if esperado != obtido:
        return [caminho or "."]
    return []


def comparar(
    esperados: Sequence[ResultadoEsperado], obtidos: Iterable[AchadoComparavel]
) -> list[ComparacaoAchado]:
    """Compara validação a validação.

    Args:
        esperados: ``resultado_esperado`` do gabarito.
        obtidos: Achados da pipeline.

    Returns:
        Uma comparação por validação esperada.
    """
    por_nome = {a.validacao: a for a in obtidos}
    saida = []
    for esperado in esperados:
        obtido = por_nome.get(esperado.validacao)
        valores_esperados = sem_ids(esperado.valores)
        valores_obtidos = sem_ids(obtido.valores) if obtido else None
        diferencas = _diferencas(valores_esperados, valores_obtidos)
        saida.append(
            ComparacaoAchado(
                validacao=esperado.validacao,
                esperado=str(esperado.resultado),
                obtido=str(obtido.resultado) if obtido else None,
                resultado_igual=obtido is not None
                and str(obtido.resultado) == str(esperado.resultado),
                valores_iguais=not diferencas,
                explicacao_igual=obtido is not None and obtido.explicacao == esperado.explicacao,
                diferencas=diferencas[:10],
            )
        )
    return saida
