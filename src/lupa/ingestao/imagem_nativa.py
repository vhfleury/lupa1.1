"""OCR de detecção em imagens de páginas nativas (decisão da 4F sobre `imagem_com_texto`).

Página nativa não passa pelo OCR, então uma instrução escrita dentro de uma imagem não vira
texto nem alerta (revisão 4D, seção 6, item 2). Aqui cada imagem da página nativa com área acima
de ``LIMIAR_AREA`` da página é rasterizada e lida pelo Tesseract só para detecção: o texto lido
NÃO entra no texto da página, no normalizado nem no que vai ao modelo. Se ele casar com os
padrões de instrução (4D.5), a página recebe a flag ``padrao_instrucao`` e um registro em
``extracao.imagens_nativas`` com a caixa, as categorias e o hash do texto lido (sem o texto).

Custo medido nos processos de referência: 21 a 27 s por mil páginas nativas (12% das páginas
nativas têm imagem acima do limiar, quase sempre carimbo), contra cerca de 880 s por mil páginas
digitalizadas. Falha do OCR numa imagem não derruba a página: o registro sai com ``erro``.
"""

from typing import Any

import fitz

from lupa.dominio.esquemas import calcular_hash
from lupa.ingestao.ocr import OcrIndisponivelError, executar_tesseract, rasterizar
from lupa.ingestao.saneamento_pagina import categorias_de

LIMIAR_AREA = 0.02
DPI_DETECCAO = 300
ARGUMENTOS_TESSERACT = ["-l", "por", "--psm", "6"]


def regioes_de_imagem(pagina: fitz.Page, limiar: float = LIMIAR_AREA) -> list[fitz.Rect]:
    """Caixas das imagens da página com área acima do limiar (fração da página).

    Args:
        pagina: Página aberta.
        limiar: Fração mínima da área da página.

    Returns:
        Caixas em pontos PDF, recortadas à página.
    """
    area = abs(pagina.rect)
    if area <= 0:
        return []
    regioes = []
    for info in pagina.get_image_info():
        caixa = fitz.Rect(info["bbox"]) & pagina.rect
        if abs(caixa) / area > limiar:
            regioes.append(caixa)
    return regioes


def _ler(pagina: fitz.Page, caixa: fitz.Rect) -> dict[str, Any]:
    registro: dict[str, Any] = {"bbox": [round(v, 2) for v in caixa]}
    try:
        texto = executar_tesseract(
            rasterizar(pagina, DPI_DETECCAO, clip=caixa).png, ARGUMENTOS_TESSERACT
        )
    except OcrIndisponivelError:
        return registro | {"erro": "ocr", "categorias": []}
    return registro | {"categorias": categorias_de(texto), "hash": calcular_hash(texto)}


def imagens_suspeitas(pagina: fitz.Page) -> list[dict[str, Any]]:
    """Lê as imagens relevantes da página nativa e devolve só as com padrão de instrução.

    Args:
        pagina: Página nativa aberta.

    Returns:
        Registros `{bbox, categorias, hash}` (ou com `erro`), sem o texto lido.
    """
    registros = [_ler(pagina, caixa) for caixa in regioes_de_imagem(pagina)]
    return [r for r in registros if r["categorias"] or "erro" in r]
