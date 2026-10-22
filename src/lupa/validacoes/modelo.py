"""Esquema de saída do motor e índice de fatos de um processo.

A entrada das validações é o próprio ``lupa.dominio.esquemas.Fato`` (com ``Evidencia``): ids
``UUID``, ``tipo`` como ``TipoFato`` e ``evidencias`` em tupla. A saída é ``AchadoValidacao``, que
não é cópia do ``Achado`` do domínio: não tem ``id``, ``processo_id`` nem ``criado_em``, porque o
motor não conhece o processo nem persiste nada. ``lupa.validacoes.adaptador.para_dominio`` o
converte no ``Achado`` do domínio.
"""

import json
from collections.abc import Iterable
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from lupa.dominio.enums import ResultadoAchado as ResultadoAchadoDominio
from lupa.dominio.esquemas import Evidencia, Fato

__all__ = [
    "AchadoValidacao",
    "ConflitoDeFatosError",
    "Evidencia",
    "Fato",
    "ModeloProcesso",
    "ResultadoAchado",
    "reu_de",
    "valor_de",
]

ResultadoAchado = Literal["conforme", "atencao", "verificar"]
"""Valores literais usados pelas validações; viram ``lupa.dominio.enums.ResultadoAchado``."""


class AchadoValidacao(BaseModel):
    """Resultado de uma validação antes de ser vinculado a um processo.

    ``valores`` contém só tipos serializáveis em JSON (ids como string).
    """

    model_config = ConfigDict(frozen=True)

    validacao: str
    versao_catalogo: str
    resultado: ResultadoAchadoDominio
    fatos_usados: tuple[UUID, ...]
    valores: dict[str, Any]
    explicacao: str


class ConflitoDeFatosError(ValueError):
    """Há mais de um valor distinto para um tipo de fato que deveria ser único."""

    def __init__(self, tipo: str, fato_ids: list[str]) -> None:
        """Cria o erro.

        Args:
            tipo: Tipo de fato em conflito.
            fato_ids: Ids dos fatos com valores divergentes.
        """
        super().__init__(f"valores divergentes para o fato {tipo}: {fato_ids}")
        self.tipo = tipo
        self.fato_ids = fato_ids


def valor_de(fato: Fato) -> Any:
    """Retorna o valor útil do fato, desembrulhando ``{"valor": ...}`` quando houver.

    Args:
        fato: Fato de origem.

    Returns:
        O valor do fato.
    """
    if isinstance(fato.valor, dict) and "valor" in fato.valor:
        return fato.valor["valor"]
    return fato.valor


def reu_de(fato: Fato) -> str | None:
    """Retorna o réu a que o fato se refere, ou ``None`` se vale para o processo todo.

    Args:
        fato: Fato de origem.

    Returns:
        Id do réu ou ``None``.
    """
    if isinstance(fato.valor, dict):
        reu = fato.valor.get("reu_id")
        return str(reu) if reu is not None else None
    return None


class ModeloProcesso:
    """Índice imutável dos fatos de um processo por tipo e por réu."""

    def __init__(self, fatos: Iterable[Fato]) -> None:
        """Indexa os fatos.

        Args:
            fatos: Fatos do processo, em qualquer ordem.
        """
        self._fatos = tuple(sorted(fatos, key=lambda f: f.id))
        indice: dict[str, list[Fato]] = {}
        for fato in self._fatos:
            indice.setdefault(fato.tipo, []).append(fato)
        self._por_tipo = {tipo: tuple(lista) for tipo, lista in indice.items()}

    @property
    def todos(self) -> tuple[Fato, ...]:
        """Todos os fatos, ordenados por id."""
        return self._fatos

    def fatos(self, tipo: str) -> list[Fato]:
        """Lista os fatos de um tipo.

        Args:
            tipo: Tipo de fato.

        Returns:
            Fatos do tipo, ordenados por id (lista vazia se não houver).
        """
        return list(self._por_tipo.get(tipo, ()))

    def fato(self, tipo: str) -> Fato | None:
        """Retorna o fato único de um tipo.

        Fatos repetidos com o mesmo valor são aceitos e o primeiro (por id) é devolvido.

        Args:
            tipo: Tipo de fato.

        Returns:
            O fato, ou ``None`` se não houver.

        Raises:
            ConflitoDeFatosError: Se houver valores distintos para o tipo.
        """
        lista = self.fatos(tipo)
        if not lista:
            return None
        distintos = {json.dumps(valor_de(f), sort_keys=True, default=str) for f in lista}
        if len(distintos) > 1:
            raise ConflitoDeFatosError(tipo, [str(f.id) for f in lista])
        return lista[0]

    def reus(self) -> list[str]:
        """Lista os réus mencionados nos fatos, em ordem.

        Returns:
            Ids de réu distintos.
        """
        return sorted({r for f in self._fatos if (r := reu_de(f)) is not None})

    def por_reu(self, reu_id: str) -> "ModeloProcesso":
        """Recorta o modelo para um réu: fatos dele e fatos comuns a todos.

        Args:
            reu_id: Id do réu.

        Returns:
            Novo modelo só com os fatos aplicáveis ao réu.
        """
        return ModeloProcesso(f for f in self._fatos if reu_de(f) in (None, reu_id))
