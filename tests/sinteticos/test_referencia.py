"""4B.9: dez processos de referência e reprodutibilidade por semente."""

from pathlib import Path

from lupa.sinteticos.gabarito import TODOS_VETORES, Cenario, Composicao
from lupa.sinteticos.referencia import (
    REFERENCIAS,
    configuracoes_injecao,
    gerar_processo,
    mistura,
)
from lupa.sinteticos.roteiro import Configuracao


def test_dez_referencias_com_tamanhos_crescentes_e_misturas_extremas() -> None:
    """Dez referencias com tamanhos crescentes e misturas extremas."""
    assert list(REFERENCIAS) == [f"semente_{n:02d}" for n in range(1, 11)]
    tamanhos = [c.paginas_alvo for c in REFERENCIAS.values()]
    assert tamanhos == sorted(tamanhos) and tamanhos[0] == 200 and tamanhos[-1] == 5000
    digitalizadas = [c.mistura[Composicao.DIGITALIZADA] for c in REFERENCIAS.values()]
    nativas = [c.mistura[Composicao.NATIVA] for c in REFERENCIAS.values()]
    assert max(digitalizadas) >= 0.9 and max(nativas) >= 0.9
    assert len({c.semente for c in REFERENCIAS.values()}) == 10
    assert {c.preventiva for c in REFERENCIAS.values()} == {"conforme", "atencao", "ausente"}


def test_mistura_soma_um() -> None:
    """Mistura soma um."""
    assert abs(sum(mistura(0.5).values()) - 1.0) < 1e-9


def test_mesma_semente_gera_o_mesmo_gabarito(tmp_path: Path) -> None:
    """Mesma semente gera o mesmo gabarito."""
    config = Configuracao(semente=21, paginas_alvo=12)
    primeiro = gerar_processo("a", config, tmp_path, (Cenario.PDF_LISO,))
    segundo = gerar_processo("b", config, tmp_path, (Cenario.PDF_LISO,))
    assert primeiro.folhas == segundo.folhas
    gabaritos = [
        (tmp_path / n / "pdf_liso" / "gabarito.json").read_text(encoding="utf-8") for n in "ab"
    ]
    assert gabaritos[0] == gabaritos[1]
    assert primeiro.bytes_por_cenario.keys() == {"pdf_liso"}


def test_tamanho_gerado_fica_perto_do_alvo(tmp_path: Path) -> None:
    """Tamanho gerado fica perto do alvo."""
    resumo = gerar_processo("c", Configuracao(semente=22, paginas_alvo=80), tmp_path, ())
    assert abs(resumo.folhas - 80) <= 4


def test_corpus_de_injecao_tem_uma_variante_por_vetor_e_uma_com_todos() -> None:
    """Corpus de injecao tem uma variante por vetor e uma com todos."""
    variantes = configuracoes_injecao(10)
    assert len(variantes) == len(TODOS_VETORES) + 1
    assert variantes["injecao_todos"].injecoes == TODOS_VETORES
