"""Estruturas da extração de eventos: páginas e peças de entrada, candidatos de saída."""

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any
from uuid import UUID

from lupa.dominio.enums import OrigemPeca, TipoFato, TipoPeca
from lupa.ingestao.datas import OcorrenciaData, TextoAnalise


@dataclass(frozen=True)
class PaginaTexto:
    """Página com o texto original (``pagina.texto``).

    Attributes:
        id: Id da página.
        numero: Número da página no arquivo.
        texto: Texto original; offsets de evidência referem-se a ele.
        origem_arquivo: Arquivo de origem (entrada do ZIP ou o PDF).
        pagina_origem: Página dentro do arquivo de origem.
    """

    id: UUID
    numero: int
    texto: str
    origem_arquivo: str | None = None
    pagina_origem: int | None = None

    @cached_property
    def analise(self) -> TextoAnalise:
        """Normalizado e dobrado do texto, calculados uma vez."""
        return TextoAnalise.de(self.texto)

    @cached_property
    def datas(self) -> list[OcorrenciaData]:
        """Datas do texto, com offsets no dobrado."""
        return self.analise.datas()


@dataclass(frozen=True)
class PecaTexto:
    """Peça com o tipo, a origem e as páginas.

    Attributes:
        tipo: Tipo da peça (4E.4 ou correção manual).
        origem: Origem da peça (4E.5).
        paginas: Páginas da peça, em ordem.
    """

    tipo: TipoPeca
    origem: OrigemPeca
    paginas: tuple[PaginaTexto, ...]


@dataclass(frozen=True)
class ReuQualificado:
    """Réu identificado pela qualificação na denúncia.

    Attributes:
        pseudonimo: ``REU-01``, ``REU-02``...
        nome: Nome como está na denúncia (só vai para ``reu_identidade``).
        documento: CPF como está na denúncia, se houver.
        pagina_id: Página da qualificação.
        inicio: Offset do nome no texto original da página.
    """

    pseudonimo: str
    nome: str
    documento: str | None
    pagina_id: UUID
    inicio: int


@dataclass(frozen=True)
class Candidato:
    """Valor encontrado por um extrator, antes de virar ``Fato``.

    Attributes:
        tipo: Tipo de fato.
        valor: Valor no formato das validações (data ISO, meses, objeto de recurso).
        pagina: Página da evidência.
        inicio: Início da evidência no texto original da página.
        fim: Fim da evidência no texto original.
        confianca: Confiança da regra.
        data: Data a reconferir no trecho (None para valores que não são data).
        por_reu: Se o valor é de um réu específico.
        reu: Pseudônimo do réu, quando conhecido.
        regra: Identificação da regra (para relatório; nunca texto).
    """

    tipo: TipoFato
    valor: Any
    pagina: PaginaTexto
    inicio: int
    fim: int
    confianca: float
    data: date | None = None
    por_reu: bool = False
    reu: str | None = None
    regra: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
