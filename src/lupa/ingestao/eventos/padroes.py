"""Leitura dos padrões versionados: ``dados/eventos.yaml`` e ``dados/tipos_penais.yaml``."""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from lupa.dominio.enums import TipoFato, TipoPeca


@dataclass(frozen=True)
class RegraEvento:
    """Regra de evento datado guiada por gatilho.

    Attributes:
        tipo: Tipo de fato produzido.
        pecas: Tipos de peça em que a regra roda.
        gatilhos: Expressões (sobre o texto dobrado).
        janela: Distância máxima entre o fim do gatilho e o início da data.
        confianca: Confiança atribuída ao fato.
        ultima: Se vale a última ocorrência da peça (senão, todas).
        por_reu: Se o valor é de um réu.
    """

    tipo: TipoFato
    pecas: frozenset[TipoPeca]
    gatilhos: tuple[re.Pattern[str], ...]
    janela: int
    confianca: float
    ultima: bool
    por_reu: bool


@dataclass(frozen=True)
class TipoPenal:
    """Tipo penal da tabela mínima.

    Attributes:
        artigo: Número do artigo.
        lei: ``cp`` ou número da lei.
        pena_maxima_meses: Pena máxima em abstrato do caput, em meses.
    """

    artigo: str
    lei: str
    pena_maxima_meses: int


@dataclass(frozen=True)
class Padroes:
    """Padrões carregados.

    Attributes:
        versao: Versão de ``eventos.yaml``.
        versao_tipos: Versão de ``tipos_penais.yaml``.
        regras: Regras de eventos datados.
        tipos_penais: Tabela mínima de tipos penais.
    """

    versao: str
    versao_tipos: str
    regras: tuple[RegraEvento, ...]
    tipos_penais: tuple[TipoPenal, ...]

    @property
    def versao_extrator(self) -> str:
        """Versão gravada em ``fato.versao_extrator``: eventos e tabela de tipos penais."""
        return f"{self.versao}+tp{self.versao_tipos}"

    def regras_da_peca(self, tipo: TipoPeca) -> list[RegraEvento]:
        """Regras que rodam num tipo de peça.

        Args:
            tipo: Tipo da peça.

        Returns:
            Regras aplicáveis, na ordem do YAML.
        """
        return [r for r in self.regras if tipo in r.pecas]

    def pena_do_artigo(self, artigo: str, lei: str = "cp") -> int | None:
        """Pena máxima em meses de um artigo da tabela.

        Args:
            artigo: Número do artigo.
            lei: ``cp`` ou número da lei.

        Returns:
            Meses, ou None se o artigo não está na tabela.
        """
        for tipo in self.tipos_penais:
            if tipo.artigo == artigo and tipo.lei == lei:
                return tipo.pena_maxima_meses
        return None


def _ler(nome: str) -> dict[str, Any]:
    texto = files("lupa.ingestao").joinpath("dados").joinpath(nome).read_text("utf-8")
    dados: dict[str, Any] = yaml.safe_load(texto)
    return dados


def _regra(item: dict[str, Any]) -> RegraEvento:
    return RegraEvento(
        tipo=TipoFato(item["tipo"]),
        pecas=frozenset(TipoPeca(p) for p in item["pecas"]),
        gatilhos=tuple(re.compile(g) for g in item["gatilhos"]),
        janela=int(item["janela"]),
        confianca=float(item["confianca"]),
        ultima=bool(item.get("ultima", False)),
        por_reu=bool(item.get("por_reu", False)),
    )


def padroes_de(eventos: dict[str, Any], tipos: dict[str, Any]) -> Padroes:
    """Monta os padrões a partir dos dois YAML já lidos.

    Args:
        eventos: Conteúdo de ``eventos.yaml``.
        tipos: Conteúdo de ``tipos_penais.yaml``.

    Returns:
        Padrões.
    """
    return Padroes(
        versao=str(eventos["versao"]),
        versao_tipos=str(tipos["versao"]),
        regras=tuple(_regra(item) for item in eventos["regras"]),
        tipos_penais=tuple(
            TipoPenal(str(t["artigo"]), str(t["lei"]), int(t["pena_maxima_meses"]))
            for t in tipos["tipos"]
        ),
    )


@cache
def padroes_padrao() -> Padroes:
    """Padrões empacotados, lidos uma vez.

    Returns:
        Padrões dos YAML de ``lupa/ingestao/dados``.
    """
    return padroes_de(_ler("eventos.yaml"), _ler("tipos_penais.yaml"))
