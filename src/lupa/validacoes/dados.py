"""Carregadores, com validação pydantic, das tabelas jurídicas versionadas em YAML."""

from datetime import date
from functools import lru_cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from lupa.validacoes.calendario import Calendario, Periodo


class ArquivoVersionado(BaseModel):
    """Base de todo arquivo de dados jurídicos: exige ``versao`` e ``fonte``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    versao: str = Field(min_length=1)
    fonte: str = Field(min_length=1)


class Feriado(BaseModel):
    """Um feriado ou dia sem expediente forense."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data: date
    descricao: str


class ArquivoFeriados(ArquivoVersionado):
    """Lista de feriados de uma abrangência (nacional, tribunal)."""

    abrangencia: str
    feriados: list[Feriado]


class Suspensao(BaseModel):
    """Período de suspensão de prazos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inicio: date
    fim: date
    descricao: str
    base_legal: str

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> Self:
        if self.fim < self.inicio:
            raise ValueError("fim da suspensão anterior ao início")
        return self


class ArquivoSuspensoes(ArquivoVersionado):
    """Lista de suspensões de prazo."""

    suspensoes: list[Suspensao]


class RegraRecurso(BaseModel):
    """Prazo de interposição de um tipo de recurso."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str
    dias: PositiveInt
    base_legal: str


class TabelaPrazosRecursos(ArquivoVersionado):
    """Prazos de interposição por tipo de recurso criminal."""

    contagem_base_legal: str
    recursos: dict[str, RegraRecurso]


class FaixaArt109(BaseModel):
    """Faixa de pena máxima do art. 109 CP e o prazo prescricional correspondente."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inciso: str
    prazo_anos: PositiveInt
    acima_de_meses: int | None = None
    a_partir_de_meses: int | None = None
    ate_meses: int | None = None
    abaixo_de_meses: int | None = None

    def contem(self, pena_meses: int) -> bool:
        """Diz se a pena máxima cai nesta faixa.

        Args:
            pena_meses: Pena máxima em abstrato, em meses.

        Returns:
            Verdadeiro se a pena está dentro dos limites da faixa.
        """
        limites = (
            self.acima_de_meses is None or pena_meses > self.acima_de_meses,
            self.a_partir_de_meses is None or pena_meses >= self.a_partir_de_meses,
            self.ate_meses is None or pena_meses <= self.ate_meses,
            self.abaixo_de_meses is None or pena_meses < self.abaixo_de_meses,
        )
        return all(limites)


class ReducaoArt115(BaseModel):
    """Parâmetros da redução do art. 115 CP."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    idade_no_fato_abaixo_de: PositiveInt
    idade_na_sentenca_a_partir_de: PositiveInt
    divisor: PositiveInt
    base_legal: str


class TabelaPrescricao(ArquivoVersionado):
    """Tabela do art. 109 CP com a redução do art. 115."""

    base_legal: str
    faixas: list[FaixaArt109] = Field(min_length=1)
    reducao: ReducaoArt115

    def faixa_para(self, pena_meses: int) -> FaixaArt109:
        """Escolhe a faixa aplicável.

        Args:
            pena_meses: Pena máxima em abstrato, em meses.

        Returns:
            A única faixa que contém a pena.

        Raises:
            ValueError: Se nenhuma ou mais de uma faixa contém a pena.
        """
        encontradas = [f for f in self.faixas if f.contem(pena_meses)]
        if len(encontradas) != 1:
            raise ValueError(f"tabela do art. 109 ambígua para pena de {pena_meses} meses")
        return encontradas[0]


class ParametrosPreventiva(ArquivoVersionado):
    """Prazo de revisão periódica da preventiva."""

    prazo_revisao_dias: PositiveInt
    base_legal: str


def caminho_padrao(relativo: str) -> Traversable:
    """Localiza um arquivo de dados empacotado em ``lupa/validacoes/dados``.

    Args:
        relativo: Caminho relativo com ``/`` (ex.: ``"feriados/tjgo.yaml"``).

    Returns:
        Recurso legível.
    """
    recurso = files("lupa.validacoes").joinpath("dados")
    for parte in relativo.split("/"):
        recurso = recurso.joinpath(parte)
    return recurso


def carregar[M: ArquivoVersionado](origem: Traversable | Path, modelo: type[M]) -> M:
    """Lê um YAML e o valida contra o modelo.

    Args:
        origem: Arquivo YAML.
        modelo: Classe pydantic esperada.

    Returns:
        Instância validada.
    """
    return modelo.model_validate(yaml.safe_load(origem.read_text(encoding="utf-8")))


def montar_calendario(feriados: list[ArquivoFeriados], suspensoes: ArquivoSuspensoes) -> Calendario:
    """Junta arquivos de feriados e suspensões num calendário.

    Args:
        feriados: Arquivos de feriados (nacional, tribunal...).
        suspensoes: Arquivo de suspensões.

    Returns:
        Calendário com todos os dias sem expediente.
    """
    dias = {f.data: f.descricao for arquivo in feriados for f in arquivo.feriados}
    periodos = tuple(Periodo(s.inicio, s.fim, s.descricao) for s in suspensoes.suspensoes)
    return Calendario(feriados=dias, suspensoes=periodos)


@lru_cache(maxsize=1)
def calendario_padrao() -> tuple[Calendario, dict[str, str]]:
    """Calendário dos arquivos empacotados e as versões usadas.

    Returns:
        Calendário e mapa ``arquivo -> versao``.
    """
    nacionais = carregar(caminho_padrao("feriados/nacionais.yaml"), ArquivoFeriados)
    tjgo = carregar(caminho_padrao("feriados/tjgo.yaml"), ArquivoFeriados)
    suspensoes = carregar(caminho_padrao("suspensoes_prazo.yaml"), ArquivoSuspensoes)
    versoes = {
        "feriados/nacionais.yaml": nacionais.versao,
        "feriados/tjgo.yaml": tjgo.versao,
        "suspensoes_prazo.yaml": suspensoes.versao,
    }
    return montar_calendario([nacionais, tjgo], suspensoes), versoes


@lru_cache(maxsize=1)
def prazos_recursos_padrao() -> TabelaPrazosRecursos:
    """Tabela de prazos de recursos empacotada.

    Returns:
        Tabela validada.
    """
    return carregar(caminho_padrao("prazos_recursos.yaml"), TabelaPrazosRecursos)


@lru_cache(maxsize=1)
def prescricao_padrao() -> TabelaPrescricao:
    """Tabela do art. 109 empacotada.

    Returns:
        Tabela validada.
    """
    return carregar(caminho_padrao("prescricao_art109.yaml"), TabelaPrescricao)


@lru_cache(maxsize=1)
def preventiva_padrao() -> ParametrosPreventiva:
    """Parâmetros da revisão da preventiva empacotados.

    Returns:
        Parâmetros validados.
    """
    return carregar(caminho_padrao("preventiva.yaml"), ParametrosPreventiva)
