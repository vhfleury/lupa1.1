"""Sinais por página para o roteador (4C.3); roda só dentro do sandbox (abre o PDF).

Todos os sinais são números ou booleanos determinísticos para o mesmo arquivo e a mesma
versão do PyMuPDF; áreas são frações da área da página. Imagens com máscara de transparência
(carimbos, logotipos sobrepostos) contam em `area_imagem`, mas não em `area_imagem_opaca`:
conteúdo digitalizado chega como imagem opaca.
"""

from typing import Any

import fitz

DPI_AMOSTRA = 24
LIMIAR_TINTA = 160
MAX_TINTA_VAZIA = 0.0005
MIN_FONTE_VISIVEL = 4.0
BRANCO = 0xFFFFFF
SUBSTITUICAO = chr(0xFFFD)
CASAS = 4
FLAGS_SEM_RECORTE = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP


def _fracao(valor: float, total: float) -> float:
    return round(min(1.0, valor / total), CASAS) if total > 0 else 0.0


def _imprimiveis(texto: str) -> int:
    return sum(1 for c in texto if c.isprintable() and not c.isspace())


def _spans(pagina: fitz.Page) -> list[dict[str, Any]]:
    dados = pagina.get_text("dict", flags=FLAGS_SEM_RECORTE, clip=fitz.INFINITE_RECT())
    return [
        span
        for bloco in dados["blocks"]
        if bloco.get("type") == 0
        for linha in bloco["lines"]
        for span in linha["spans"]
        if span["text"].strip()
    ]


def _invisivel(span: dict[str, Any], area: fitz.Rect) -> bool:
    caixa = fitz.Rect(span["bbox"])
    fora = not caixa.intersects(area)
    return fora or float(span["size"]) < MIN_FONTE_VISIVEL or int(span["color"]) & BRANCO == BRANCO


def _mascaras(pagina: fitz.Page) -> dict[int, bool]:
    return {int(item[0]): int(item[1]) > 0 for item in pagina.get_images(full=True)}


def _areas_imagem(pagina: fitz.Page) -> tuple[float, float, int]:
    area = pagina.rect
    mascaras = _mascaras(pagina)
    total = opaca = 0.0
    imagens = pagina.get_image_info(xrefs=True)
    for info in imagens:
        recorte = abs(fitz.Rect(info["bbox"]) & area)
        total += recorte
        if not mascaras.get(int(info.get("xref", 0)), False):
            opaca += recorte
    return _fracao(total, abs(area)), _fracao(opaca, abs(area)), len(imagens)


def _tinta(pagina: fitz.Page) -> float:
    pix = pagina.get_pixmap(dpi=DPI_AMOSTRA, colorspace=fitz.csGRAY, alpha=False)
    amostras = pix.samples
    escuros = sum(1 for valor in amostras if valor < LIMIAR_TINTA)
    return round(escuros / max(1, len(amostras)), CASAS)


def medir_sinais(pagina: fitz.Page) -> dict[str, Any]:
    """Mede os sinais de uma página.

    Args:
        pagina: Página aberta pelo PyMuPDF.

    Returns:
        `caracteres_imprimiveis`, `caracteres_substituicao`, `caracteres_invisiveis` (fonte
        abaixo de 4 pt, cor branca ou fora da página), `cobertura_texto`, `area_imagem`,
        `area_imagem_opaca`, `imagens`, `palavras`, `fragmentacao` (palavras de um caractere
        sobre o total), `rotacao` declarada, `tinta` (fração de pixels escuros numa amostra
        de 24 DPI) e `visualmente_vazia` (tinta abaixo de 0,05%).
    """
    area = pagina.rect
    texto = pagina.get_text()
    spans = _spans(pagina)
    visiveis = [s for s in spans if fitz.Rect(s["bbox"]).intersects(area)]
    cobertura = sum(abs(fitz.Rect(s["bbox"]) & area) for s in visiveis)
    palavras = pagina.get_text("words")
    curtas = sum(1 for p in palavras if len(p[4]) == 1)
    area_imagem, area_opaca, imagens = _areas_imagem(pagina)
    tinta = _tinta(pagina)
    return {
        "caracteres_imprimiveis": _imprimiveis(texto),
        "caracteres_substituicao": texto.count(SUBSTITUICAO),
        "caracteres_invisiveis": sum(_imprimiveis(s["text"]) for s in spans if _invisivel(s, area)),
        "cobertura_texto": _fracao(cobertura, abs(area)),
        "area_imagem": area_imagem,
        "area_imagem_opaca": area_opaca,
        "imagens": imagens,
        "palavras": len(palavras),
        "fragmentacao": round(curtas / len(palavras), CASAS) if palavras else 0.0,
        "rotacao": int(pagina.rotation),
        "tinta": tinta,
        "visualmente_vazia": tinta < MAX_TINTA_VAZIA,
    }
