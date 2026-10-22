"""4B.10: harness de medição com saída perfeita e com erros injetados."""

import json
from pathlib import Path

import pytest

from lupa.dominio.enums import TipoPagina, TipoPeca
from lupa.sinteticos import cli
from lupa.sinteticos.gabarito import Cenario, Gabarito
from lupa.sinteticos.medicao import levenshtein, medir, normalizar, para_markdown, saida_perfeita
from lupa.sinteticos.roteiro import Configuracao
from lupa.sinteticos.saida_pipeline import RefPagina, SaidaPipeline
from tests.sinteticos.conftest import ProcessoGerado


@pytest.mark.parametrize(
    ("a", "b", "distancia"),
    [("", "", 0), ("abc", "", 3), ("", "ab", 2), ("kitten", "sitting", 3), ("data", "dada", 1)],
)
def test_levenshtein(a: str, b: str, distancia: int) -> None:
    """Levenshtein."""
    assert levenshtein(a, b) == distancia


def test_normalizar_colapsa_espacos() -> None:
    """Normalizar colapsa espacos."""
    assert normalizar(" a\n b  c\n") == "a b c"


@pytest.mark.parametrize("cenario", list(Cenario))
def test_saida_perfeita_da_cem_por_cento(processo: ProcessoGerado, cenario: Cenario) -> None:
    """Saida perfeita da cem por cento."""
    gabarito = processo.gabaritos[cenario]
    relatorio = medir(gabarito, saida_perfeita(gabarito).model_copy(update={"tempo_segundos": 9.0}))
    for taxa in (relatorio.fronteira, relatorio.eventos):
        assert taxa.precisao == taxa.recall == taxa.f1 == 1.0
    assert relatorio.data_peca is not None
    for acuracia in (
        relatorio.tipo_peca, relatorio.origem_peca, relatorio.tipo_pagina, relatorio.data_peca,
    ):  # fmt: skip
        assert acuracia.acuracia == 1.0
    assert "Data da peça | 100.0%" in para_markdown(relatorio)
    assert all(c.cer == 0.0 for c in relatorio.cer_por_composicao.values())
    assert relatorio.tempo_por_mil_paginas == pytest.approx(9.0 / len(gabarito.paginas) * 1000)


def _com_erros(gabarito: Gabarito) -> SaidaPipeline:
    perfeita = saida_perfeita(gabarito)
    pecas = list(perfeita.pecas)
    pecas[1] = pecas[1].model_copy(update={"tipo": TipoPeca.OUTROS})
    pecas.pop(2)
    eventos = list(perfeita.eventos)
    eventos[0] = eventos[0].model_copy(update={"valor": "1900-01-01"})
    eventos.append(eventos[1].model_copy(update={"ref": RefPagina(arquivo="nada.pdf", pagina=1)}))
    paginas = list(perfeita.paginas)
    alvo = next(i for i, p in enumerate(paginas) if i and len(normalizar(p.texto)) > 100)
    paginas[alvo] = paginas[alvo].model_copy(
        update={"texto": "X" * 10 + normalizar(paginas[alvo].texto)[10:], "tipo": TipoPagina.VAZIA}
    )
    paginas.pop(0)
    return SaidaPipeline(pecas=tuple(pecas), paginas=tuple(paginas), eventos=tuple(eventos))


def test_erros_injetados_baixam_as_metricas(gabarito: Gabarito) -> None:
    """Erros injetados baixam as metricas."""
    relatorio = medir(gabarito, _com_erros(gabarito))
    total_pecas = len(gabarito.pecas)
    assert relatorio.fronteira.precisao == 1.0
    assert relatorio.fronteira.recall == pytest.approx((total_pecas - 1) / total_pecas)
    assert relatorio.tipo_peca.acertos == total_pecas - 2
    assert relatorio.origem_peca.acertos == total_pecas - 1
    assert relatorio.data_peca is not None
    assert relatorio.data_peca.acertos == total_pecas - 1
    assert relatorio.tipo_pagina.acertos == len(gabarito.paginas) - 2
    total_eventos = len(gabarito.eventos)
    assert relatorio.eventos.corretos == total_eventos - 1
    assert relatorio.eventos.previstos == total_eventos + 1
    assert relatorio.cer_por_composicao["capa"].cer == 1.0
    assert sum(c.distancia for c in relatorio.cer_por_composicao.values()) > 0
    assert relatorio.tempo_por_mil_paginas is None
    markdown = para_markdown(relatorio)
    assert "## CER por composição de página" in markdown and "não informado" in markdown


def test_saida_vazia_nao_quebra(gabarito: Gabarito) -> None:
    """Saida vazia nao quebra."""
    relatorio = medir(gabarito, SaidaPipeline())
    assert relatorio.fronteira.precisao == 0.0 and relatorio.eventos.recall == 0.0


def test_cli_medir_grava_json_e_markdown(processo: ProcessoGerado, tmp_path: Path) -> None:
    """Cli medir grava json e markdown."""
    gabarito = processo.gabaritos[Cenario.ZIP_POR_PECA]
    saida = tmp_path / "saida.json"
    saida.write_text(saida_perfeita(gabarito).model_dump_json(), encoding="utf-8")
    argumentos = [
        "--gabarito", str(processo.arquivos[Cenario.ZIP_POR_PECA].gabarito), "--saida", str(saida),
        "--json", str(tmp_path / "m.json"), "--markdown", str(tmp_path / "m.md"),
    ]  # fmt: skip
    assert cli.main_medir(argumentos) == 0
    assert json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["fronteira"]["f1"] == 1.0
    assert "Medição" in (tmp_path / "m.md").read_text(encoding="utf-8")


def test_cli_gerar_processo_referencia_e_injecao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cli gerar processo referencia e injecao."""
    assert cli.main_gerar(["--destino", str(tmp_path), "processo", "--semente", "3",
                           "--paginas", "8", "--cenarios", "pdf_liso", "--injecoes",
                           "base64"]) == 0  # fmt: skip
    assert (tmp_path / "processo_3" / "pdf_liso" / "autos.pdf").exists()
    monkeypatch.setattr(cli, "REFERENCIAS", {"mini": Configuracao(semente=4, paginas_alvo=6)})
    assert cli.main_gerar(["--destino", str(tmp_path), "referencia"]) == 0
    resumo = json.loads((tmp_path / "referencia" / "resumo.json").read_text(encoding="utf-8"))
    assert resumo[0]["nome"] == "mini" and set(resumo[0]["bytes_por_cenario"]) == {
        c.value for c in Cenario
    }
    assert cli.main_gerar(["--destino", str(tmp_path), "injecao", "--paginas", "6"]) == 0
    assert (tmp_path / "injecao" / "injecao_todos" / "pdf_liso" / "gabarito.json").exists()


def test_destino_padrao(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Destino padrao."""
    monkeypatch.setenv("LUPA_SINTETICOS_DIR", str(tmp_path))
    assert cli.destino_padrao() == tmp_path
    monkeypatch.delenv("LUPA_SINTETICOS_DIR")
    assert cli.destino_padrao().name == ".sinteticos"
