"""Fixtures dos autos sintéticos: um processo pequeno gerado uma vez por sessão."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from lupa.sinteticos.empacotamento import ArquivoGerado, exportar
from lupa.sinteticos.gabarito import TODOS_VETORES, Cenario, Composicao, Gabarito
from lupa.sinteticos.gerador import Conteudo, gerar_conteudo
from lupa.sinteticos.roteiro import Configuracao

MISTURA_TESTE = {
    Composicao.NATIVA: 0.4,
    Composicao.DIGITALIZADA: 0.3,
    Composicao.HIBRIDA_CORPO: 0.15,
    Composicao.HIBRIDA_ASSINATURA: 0.15,
}


@dataclass
class ProcessoGerado:
    """Processo de teste gerado nos três cenários.

    Attributes:
        conteudo: Conteúdo em memória.
        arquivos: Arquivos por cenário.
        gabaritos: Gabaritos por cenário, relidos do disco.
    """

    conteudo: Conteudo
    arquivos: dict[Cenario, ArquivoGerado]
    gabaritos: dict[Cenario, Gabarito]


@pytest.fixture(scope="session")
def processo(tmp_path_factory: pytest.TempPathFactory) -> ProcessoGerado:
    """Processo de ~45 folhas com todas as composições e todas as injeções."""
    config = Configuracao(
        semente=7, paginas_alvo=45, mistura=MISTURA_TESTE, injecoes=TODOS_VETORES,
        proporcao_vazias=0.3,
    )  # fmt: skip
    conteudo = gerar_conteudo(config)
    destino: Path = tmp_path_factory.mktemp("sinteticos")
    arquivos = {a.cenario: a for a in exportar(conteudo, destino)}
    gabaritos = {
        c: Gabarito.model_validate_json(a.gabarito.read_text(encoding="utf-8"))
        for c, a in arquivos.items()
    }
    return ProcessoGerado(conteudo, arquivos, gabaritos)


@pytest.fixture
def gabarito(processo: ProcessoGerado) -> Gabarito:
    """Gabarito do cenário PDF liso."""
    return processo.gabaritos[Cenario.PDF_LISO]
