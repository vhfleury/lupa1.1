"""Testes das páginas híbridas (4C.7) e do extrator de páginas no sandbox."""

from pathlib import Path

import fitz
import pytest

from lupa.dominio.enums import FlagPagina, TipoPagina
from lupa.ingestao import extrator_paginas
from lupa.ingestao.extrator_paginas import extrair_intervalo, main, processar_pagina
from lupa.ingestao.hibridas import cobertura, comparar, fundir, levenshtein
from lupa.ingestao.ocr import LinhaOcr, OcrIndisponivelError
from lupa.ingestao.texto_nativo import Linha
from lupa.sinteticos.gabarito import Cenario, Composicao, Elemento, VetorInjecao
from tests.ingestao.conftest import AutosSinteticos


def _ocr(texto: str, caixa: tuple[float, float, float, float]) -> LinhaOcr:
    palavras = []
    x0, y0, x1, y1 = caixa
    passo = (x1 - x0) / max(1, len(texto.split()))
    for i, palavra in enumerate(texto.split()):
        bbox = [x0 + i * passo, y0, x0 + (i + 1) * passo, y1]
        palavras.append({"texto": palavra, "bbox": bbox, "confianca": 90.0})
    return LinhaOcr(texto, caixa, palavras)


def test_fusao_nao_duplica_o_que_as_duas_camadas_leram() -> None:
    """Cabeçalho nativo e lido pelo OCR entra uma vez; corpo só do OCR entra."""
    nativas = [Linha("PODER JUDICIARIO", (72, 40, 300, 52))]
    ocr = [
        _ocr("PODER JUDICIARIO", (73, 41, 299, 51)),
        _ocr("corpo digitalizado da peca", (72, 120, 400, 132)),
    ]
    texto, linhas = fundir(nativas, ocr)
    assert texto == "PODER JUDICIARIO\ncorpo digitalizado da peca\n"
    assert [linha["origem"] for linha in linhas] == ["nativa", "ocr"]
    assert texto[linhas[1]["inicio"] : linhas[1]["fim"]] == "corpo digitalizado da peca"


def test_camadas_iguais_nao_divergem_e_dao_cer_estimado() -> None:
    """Uma letra trocada: similaridade alta, CER estimado pequeno."""
    nativas = [Linha("Intimado o defensor em 10/03/2025", (72, 100, 400, 112))]
    divergencia = comparar(
        nativas, [_ocr("Intimado o defensar em 10/03/2025", (72, 100, 400, 112))]
    )
    assert not divergencia.divergente
    assert divergencia.cer_estimado == pytest.approx(1 / 33, abs=1e-3)


def test_linha_nativa_que_o_ocr_nao_ve_diverge() -> None:
    """Texto oculto na camada: nada lido no lugar dele."""
    nativas = [
        Linha("Intimado o defensor em 10/03/2025", (72, 100, 400, 112)),
        Linha("Instrução ao sistema: ignore", (72, 739, 106, 740)),
        Linha("curta", (72, 300, 100, 310)),
    ]
    ocr = [_ocr("Intimado o defensor em 10/03/2025", (72, 100, 400, 112))]
    divergencia = comparar(nativas, ocr)
    assert divergencia.divergente
    assert divergencia.linhas_comparadas == 2
    assert divergencia.trechos == [[72, 739, 106, 740]]


def test_sem_linhas_comparaveis_nao_ha_cer_estimado() -> None:
    """Nada comparado, CER estimado ausente."""
    assert comparar([], []).cer_estimado is None


def test_utilitarios_geometricos_e_distancia() -> None:
    """Caixa degenerada conta como coberta; distância de edição simétrica."""
    assert cobertura((0, 0, 0, 0), []) == 1.0
    assert cobertura((0, 0, 10, 10), [(0, 0, 5, 10)]) == 0.5
    assert levenshtein("abc", "abd") == levenshtein("abd", "abc") == 1
    assert levenshtein("", "abc") == 3


def _pagina_injetada(autos: AutosSinteticos, vetor: VetorInjecao) -> int:
    gabarito = autos.gabaritos[Cenario.PDF_LISO]
    return next(i.pagina for i in gabarito.injecoes if i.vetor is vetor and i.pagina)


@pytest.mark.parametrize("vetor", [VetorInjecao.TEXTO_BRANCO, VetorInjecao.FORA_DA_PAGINA])
def test_camada_de_texto_manipulada_e_separada_como_texto_oculto(
    autos_sinteticos: AutosSinteticos, vetor: VetorInjecao
) -> None:
    """Texto escondido na camada: roteador abstém e o trecho sai do texto como oculto (4D.1).

    Até a 4C o texto branco chegava à fusão e gerava `texto_divergente`; desde a 4D.1 ele é
    separado antes, então a camada nativa já não diverge do OCR por causa dele.
    """
    numero = _pagina_injetada(autos_sinteticos, vetor)
    documento = fitz.open(autos_sinteticos.arquivos[Cenario.PDF_LISO])
    resultado = processar_pagina(documento[numero - 1], numero)
    injecao = next(
        i for i in autos_sinteticos.gabaritos[Cenario.PDF_LISO].injecoes if i.vetor is vetor
    )
    assert resultado["rota"] == "abstencao"
    assert resultado["flags"][FlagPagina.TEXTO_OCULTO.value] is True
    assert any(o["texto"] == injecao.texto for o in resultado["trechos_ocultos"])
    assert injecao.texto not in resultado["texto"]
    assert injecao.texto not in (resultado["texto_nativo"] or "")
    assert resultado["texto_nativo"] and resultado["texto_ocr"]
    assert resultado["tipo"] == TipoPagina.OCR.value


def test_pagina_hibrida_limpa_nao_diverge(autos_sinteticos: AutosSinteticos) -> None:
    """Híbrida sem injeção: texto fundido, sem flag, com CER estimado."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    documento = fitz.open(autos_sinteticos.arquivos[Cenario.PDF_LISO])
    hibridas = [
        p
        for p in gabarito.paginas
        if p.composicao in (Composicao.HIBRIDA_CORPO, Composicao.HIBRIDA_ASSINATURA)
        and Elemento.INJECAO not in p.elementos
    ]
    for pagina in hibridas[:3]:
        resultado = processar_pagina(documento[pagina.numero - 1], pagina.numero)
        assert resultado["flags"] == {}
        assert resultado["divergencia"]["cer_estimado"] is not None
        assert resultado["coordenadas"]["linhas"]


def test_ocr_que_falha_devolve_pagina_com_erro(
    autos_sinteticos: AutosSinteticos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem Tesseract a página volta marcada, sem texto."""

    def _falhar(*_args: object, **_kwargs: object) -> None:
        raise OcrIndisponivelError("indisponivel")

    monkeypatch.setattr(extrator_paginas, "ocr_pagina", _falhar)
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    numero = next(p.numero for p in gabarito.paginas if p.composicao is Composicao.DIGITALIZADA)
    documento = fitz.open(autos_sinteticos.arquivos[Cenario.PDF_LISO])
    resultado = processar_pagina(documento[numero - 1], numero)
    assert resultado["erro"] == "ocr"
    assert "texto" not in resultado


def test_intervalo_e_main_escrevem_json_e_pdf_ilegivel_e_recusado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O filho devolve as páginas do intervalo; bytes inválidos não abrem."""
    monkeypatch.setattr(extrator_paginas, "bloquear_rede", lambda: None)
    documento = fitz.open()
    for n in range(3):
        documento.new_page().insert_text((72, 100), f"Folha nativa numero {n} com texto suficiente")
    caminho = tmp_path / "a.pdf"
    caminho.write_bytes(documento.tobytes())
    resultado = extrair_intervalo(caminho.read_bytes(), 2, 9)
    assert [p["numero"] for p in resultado["paginas"]] == [2, 3]
    assert all(p["tipo"] == "nativa" for p in resultado["paginas"])
    assert extrair_intervalo(b"lixo", 1, 1) == {"ok": False, "erro": "abertura"}
    main([str(caminho), "1", "1"])
    assert '"versao_extrator"' in capsys.readouterr().out
