"""Testes do OCR (4C.6): Tesseract por-BR, orientação, caixas em pontos PDF."""

import fitz
import pytest

from lupa.ingestao import ocr
from lupa.ingestao.ocr import (
    OcrIndisponivelError,
    detectar_orientacao,
    executar_tesseract,
    ler_orientacao,
    ler_tsv,
    ocr_pagina,
    rasterizar,
)

FRASE = "Intimado o defensor em 10/03/2025 para apresentar razoes de apelacao no prazo legal."


def _pagina_com_texto(rotacao_texto: int = 0) -> fitz.Page:
    documento = fitz.open()
    pagina = documento.new_page()
    for n in range(12):
        ponto = fitz.Point(72, 90 + 22 * n) if rotacao_texto == 0 else fitz.Point(90 + 22 * n, 780)
        pagina.insert_text(ponto, FRASE, fontsize=12, rotate=rotacao_texto)
    return pagina


def test_ocr_le_texto_e_datas_com_caixas_sobre_as_palavras_nativas() -> None:
    """Data reconhecida; caixa da palavra no OCR cobre a caixa nativa (pontos PDF)."""
    pagina = _pagina_com_texto()
    resultado = ocr_pagina(pagina)
    assert "10/03/2025" in resultado.texto
    assert resultado.rotacao == 0
    assert resultado.confianca_media > 50
    nativa = fitz.Rect(pagina.search_for("10/03/2025")[0])
    palavra = next(
        p for linha in resultado.linhas for p in linha.palavras if p["texto"] == "10/03/2025"
    )
    lida = fitz.Rect(palavra["bbox"])
    assert abs(lida & nativa) / abs(lida) > 0.9
    assert resultado.matriz[0] == pytest.approx(72 / 300, abs=1e-4)


def test_pagina_deitada_tem_orientacao_detectada_e_corrigida() -> None:
    """Texto girado 90 graus: o OSD manda girar e o texto sai legível."""
    pagina = _pagina_com_texto(rotacao_texto=90)
    rotacao, confianca = detectar_orientacao(pagina)
    assert rotacao in (90, 270)
    assert confianca > 0
    resultado = ocr_pagina(pagina)
    assert resultado.rotacao == rotacao
    assert "10/03/2025" in resultado.texto
    nativa = fitz.Rect(pagina.search_for("10/03/2025")[0])
    palavra = next(
        p for linha in resultado.linhas for p in linha.palavras if p["texto"] == "10/03/2025"
    )
    lida = fitz.Rect(palavra["bbox"])
    assert abs(lida & nativa) / abs(lida) > 0.8


def test_pagina_sem_texto_nao_tem_orientacao() -> None:
    """O OSD recusa página em branco; vale 0 grau."""
    assert detectar_orientacao(fitz.open().new_page()) == (0, 0.0)


def test_leitura_da_saida_do_osd() -> None:
    """Rotação e confiança; saída ilegível ou rotação estranha vale zero."""
    assert ler_orientacao("Rotate: 90\nOrientation confidence: 7.5\n") == (90, 7.5)
    assert ler_orientacao("Rotate: 45\nOrientation confidence: 7.5\n") == (0, 0.0)
    assert ler_orientacao("lixo") == (0, 0.0)


def test_tsv_vira_linhas_com_caixas_convertidas() -> None:
    """Palavras agrupadas por linha; pixels a 144 DPI viram pontos (metade)."""
    colunas = "level page_num block_num par_num line_num word_num left top width height conf text"
    cabecalho = colunas.replace(" ", "	")
    registros = [
        "5\t1\t1\t1\t1\t1\t100\t200\t50\t20\t95.0\tOla",
        "5\t1\t1\t1\t1\t2\t160\t200\t40\t20\t90.0\tmundo",
        "5\t1\t1\t1\t2\t1\t100\t240\t30\t20\t80.0\t ",
        "4\t1\t1\t1\t2\t0\t100\t240\t30\t20\t-1\t",
    ]
    linhas = ler_tsv("\n".join([cabecalho, *registros]), (0.5, 0, 0, 0.5, 0, 0))
    assert [linha.texto for linha in linhas] == ["Ola mundo"]
    assert linhas[0].bbox == (50.0, 100.0, 100.0, 110.0)


def test_rasterizacao_registra_a_transformacao_de_volta() -> None:
    """Pixel (0,0) do recorte volta ao canto do recorte em pontos."""
    pagina = _pagina_com_texto()
    raster = rasterizar(pagina, 144, clip=fitz.Rect(100, 200, 300, 400))
    canto = fitz.Point(0, 0) * fitz.Matrix(*raster.matriz)
    assert (round(canto.x), round(canto.y)) == (100, 200)


def test_tesseract_ausente_ou_com_erro_vira_ocr_indisponivel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem binário no PATH, ou argumento inválido, a falha é tipada."""
    with pytest.raises(OcrIndisponivelError):
        executar_tesseract(b"nao e imagem", ["--psm", "3"])
    monkeypatch.setenv("PATH", "/nao-existe")
    with pytest.raises(OcrIndisponivelError):
        ocr.binario_tesseract()


def test_tempo_esgotado_do_tesseract_vira_ocr_indisponivel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tesseract travado é morto pelo tempo."""
    monkeypatch.setattr(ocr, "TEMPO_TESSERACT_SEGUNDOS", 0.001)
    pagina = _pagina_com_texto()
    with pytest.raises(OcrIndisponivelError):
        executar_tesseract(rasterizar(pagina, 300).png, ["-l", "por"])
