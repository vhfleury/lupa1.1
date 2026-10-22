"""Esquema da saída da pipeline de ingestão que ``scripts/medir.py`` compara com o gabarito.

A pipeline não conhece as folhas de conteúdo do gabarito: ela vê arquivos e páginas físicas.
Por isso toda referência a página é ``(arquivo, pagina)``, com ``pagina`` começando em 1 dentro
do arquivo (no ZIP, ``arquivo`` é o nome da entrada; nos PDFs únicos, ``autos.pdf``). A medição
converte para folhas usando ``Gabarito.arquivos``. Os demais campos seguem o gabarito: tipo de
peça em ``TipoPeca``, origem em ``OrigemPeca``, tipo de página em ``TipoPagina``, eventos em
``TipoFato`` com valor no mesmo formato (data ``AAAA-MM-DD``, pena em meses, tipo de recurso como
objeto).
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lupa.dominio.enums import OrigemPeca, TipoFato, TipoPagina, TipoPeca


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RefPagina(_Base):
    """Página física de um arquivo."""

    arquivo: str = Field(min_length=1)
    pagina: int = Field(ge=1)


class PecaSaida(_Base):
    """Peça identificada pela pipeline."""

    tipo: TipoPeca
    origem: OrigemPeca
    inicio: RefPagina
    fim: RefPagina
    data: date | None = None


class PaginaSaida(_Base):
    """Página lida pela pipeline, com o texto final (nativo, OCR ou fusão)."""

    ref: RefPagina
    tipo: TipoPagina
    texto: str = ""


class EventoSaida(_Base):
    """Fato extraído pela pipeline."""

    tipo: TipoFato
    valor: Any
    ref: RefPagina
    trecho: str | None = None


class SaidaPipeline(_Base):
    """Tudo o que a pipeline produziu para um arquivo de autos."""

    pecas: tuple[PecaSaida, ...] = ()
    paginas: tuple[PaginaSaida, ...] = ()
    eventos: tuple[EventoSaida, ...] = ()
    tempo_segundos: float | None = Field(default=None, ge=0)
