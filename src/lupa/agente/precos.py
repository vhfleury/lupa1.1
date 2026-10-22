"""Tabela de preços versionada do modelo (`dados/precos.yaml`) e cálculo do custo estimado.

Usada pelo relatório de uso da auditoria (Etapa 6.9). O custo é estimativa em dólar a partir
dos tokens gravados em `chamada_modelo`; o valor real vem da fatura.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CAMINHO_PRECOS = Path(__file__).parent / "dados" / "precos.yaml"
MILHAO = Decimal(1_000_000)
CENTAVO = Decimal("0.0001")


@dataclass(frozen=True)
class Preco:
    """Preço de um modelo por milhão de tokens.

    Attributes:
        entrada: Dólares por milhão de tokens de entrada.
        saida: Dólares por milhão de tokens de saída.
    """

    entrada: Decimal
    saida: Decimal


@dataclass(frozen=True)
class TabelaPrecos:
    """Tabela carregada do YAML.

    Attributes:
        versao: Versão da tabela.
        fonte: De onde vieram os valores.
        moeda: Moeda.
        observacao: Ressalva exibida junto do custo.
        modelos: Preço por identificador de modelo.
    """

    versao: str
    fonte: str
    moeda: str
    observacao: str
    modelos: dict[str, Preco]

    def preco_de(self, modelo: str) -> Preco | None:
        """Preço do modelo (aceita identificador com sufixo, pelo prefixo mais longo).

        Args:
            modelo: Identificador gravado na chamada.

        Returns:
            Preço, ou None se o modelo não está na tabela.
        """
        candidatos = [m for m in self.modelos if modelo == m or modelo.startswith(f"{m}-")]
        return self.modelos[max(candidatos, key=len)] if candidatos else None


def ler_tabela(caminho: Path) -> TabelaPrecos:
    """Lê e valida a tabela de preços.

    Args:
        caminho: Arquivo YAML.

    Returns:
        Tabela.
    """
    dados: dict[str, Any] = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    modelos = {
        str(nome): Preco(Decimal(str(v["entrada_por_milhao"])), Decimal(str(v["saida_por_milhao"])))
        for nome, v in dados["modelos"].items()
    }
    return TabelaPrecos(
        str(dados["versao"]), str(dados["fonte"]), str(dados["moeda"]),
        str(dados["observacao"]), modelos,
    )  # fmt: skip


@lru_cache(maxsize=1)
def tabela_padrao() -> TabelaPrecos:
    """Tabela empacotada com a aplicação.

    Returns:
        Tabela.
    """
    return ler_tabela(CAMINHO_PRECOS)


def custo(preco: Preco, tokens_entrada: int, tokens_saida: int) -> Decimal:
    """Custo estimado de um volume de tokens.

    Args:
        preco: Preço do modelo.
        tokens_entrada: Tokens de entrada.
        tokens_saida: Tokens de saída.

    Returns:
        Dólares, com quatro casas.
    """
    bruto = (preco.entrada * tokens_entrada + preco.saida * tokens_saida) / MILHAO
    return bruto.quantize(CENTAVO, rounding=ROUND_HALF_UP)
