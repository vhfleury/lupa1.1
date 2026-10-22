"""Páginas híbridas (4C.7): fusão do texto nativo com o OCR e detecção de divergência.

Funções puras sobre linhas com caixas em pontos PDF. Fusão: toda linha nativa horizontal
entra; uma linha do OCR só entra se menos da metade da sua área estiver coberta por linhas
nativas (deduplicação geométrica); o resultado segue a ordem de topo e esquerda. Linhas não
horizontais do nativo (marca d'água) ficam fora do texto fundido e continuam em
`texto_nativo`.

Divergência: para cada linha nativa horizontal com conteúdo suficiente, junta as palavras do
OCR cujo centro cai na caixa da linha (com folga) e mede a similaridade de caracteres. Linha
nativa que o OCR não enxerga no mesmo lugar (texto branco, fonte minúscula, camada trocada)
tem similaridade baixa. A distância somada sobre os caracteres comparados é também a
estimativa de CER do OCR da página.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from lupa.ingestao.ocr import LinhaOcr
from lupa.ingestao.texto_nativo import Linha

COBERTURA_DUPLICADA = 0.5
FOLGA_PONTOS = 2.0
MIN_CARACTERES_LINHA = 8
SIMILARIDADE_MINIMA = 0.5
CASAS = 4

Caixa = tuple[float, float, float, float]


@dataclass(frozen=True)
class Divergencia:
    """Comparação entre a camada de texto e o OCR.

    Attributes:
        linhas_comparadas: Linhas nativas com conteúdo suficiente.
        linhas_divergentes: Linhas com similaridade abaixo do mínimo.
        caracteres: Caracteres nativos comparados.
        distancia: Distância de edição somada.
        trechos: Caixas das linhas divergentes (para a tela de revisão).
    """

    linhas_comparadas: int
    linhas_divergentes: int
    caracteres: int
    distancia: int
    trechos: list[list[float]]

    @property
    def cer_estimado(self) -> float | None:
        """Distância sobre caracteres comparados; None se nada foi comparado."""
        if not self.caracteres:
            return None
        return round(min(1.0, self.distancia / self.caracteres), CASAS)

    @property
    def divergente(self) -> bool:
        """Verdadeiro se alguma linha nativa diverge do OCR."""
        return self.linhas_divergentes > 0


def levenshtein(a: str, b: str) -> int:
    """Distância de edição entre dois textos.

    Args:
        a: Primeiro texto.
        b: Segundo texto.

    Returns:
        Número mínimo de inserções, remoções e substituições.
    """
    if len(a) < len(b):
        a, b = b, a
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _normalizar(texto: str) -> str:
    return " ".join(unicodedata.normalize("NFC", texto).split())


def _area(caixa: Sequence[float]) -> float:
    return max(0.0, caixa[2] - caixa[0]) * max(0.0, caixa[3] - caixa[1])


def _intersecao(a: Sequence[float], b: Sequence[float]) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def cobertura(caixa: Sequence[float], outras: Sequence[Sequence[float]]) -> float:
    """Fração da área de `caixa` coberta pelas `outras` (sobreposições somadas, até 1).

    Args:
        caixa: Caixa avaliada.
        outras: Caixas que cobrem.

    Returns:
        Fração entre 0 e 1.
    """
    area = _area(caixa)
    if area <= 0:
        return 1.0
    return min(1.0, sum(_intersecao(caixa, outra) for outra in outras) / area)


def fundir(nativas: Sequence[Linha], ocr: Sequence[LinhaOcr]) -> tuple[str, list[dict[str, Any]]]:
    """Funde linhas nativas e do OCR sem duplicar o que as duas leram.

    Args:
        nativas: Linhas nativas horizontais.
        ocr: Linhas do OCR com caixas em pontos.

    Returns:
        Texto fundido e as linhas `{texto, bbox, origem, inicio, fim}` em ordem.
    """
    caixas_nativas = [linha.bbox for linha in nativas if linha.texto.strip()]
    candidatas = [(linha.bbox, linha.texto, "nativa") for linha in nativas if linha.texto.strip()]
    candidatas += [
        (linha.bbox, linha.texto, "ocr")
        for linha in ocr
        if cobertura(linha.bbox, caixas_nativas) < COBERTURA_DUPLICADA
    ]
    candidatas.sort(key=lambda c: (round(c[0][1]), c[0][0]))
    partes: list[str] = []
    saida: list[dict[str, Any]] = []
    cursor = 0
    for bbox, texto, origem in candidatas:
        partes.append(texto + "\n")
        saida.append(
            {
                "origem": origem,
                "bbox": list(bbox),
                "inicio": cursor,
                "fim": cursor + len(texto),
            }
        )
        cursor += len(texto) + 1
    return "".join(partes), saida


def _centro_dentro(caixa: Sequence[float], regiao: Caixa) -> bool:
    x = (caixa[0] + caixa[2]) / 2
    y = (caixa[1] + caixa[3]) / 2
    return regiao[0] <= x <= regiao[2] and regiao[1] <= y <= regiao[3]


def _palavras_na_regiao(ocr: Sequence[LinhaOcr], regiao: Caixa) -> str:
    return " ".join(
        p["texto"] for linha in ocr for p in linha.palavras if _centro_dentro(p["bbox"], regiao)
    )


def comparar(
    nativas: Sequence[Linha],
    ocr: Sequence[LinhaOcr],
    min_caracteres: int = MIN_CARACTERES_LINHA,
    similaridade_minima: float = SIMILARIDADE_MINIMA,
) -> Divergencia:
    """Compara cada linha nativa com o que o OCR leu no mesmo lugar.

    Args:
        nativas: Linhas nativas horizontais.
        ocr: Linhas do OCR.
        min_caracteres: Linhas nativas mais curtas são ignoradas.
        similaridade_minima: Abaixo disso a linha diverge.

    Returns:
        Contagens, distância e caixas das linhas divergentes.
    """
    comparadas = divergentes = caracteres = distancia = 0
    trechos: list[list[float]] = []
    for linha in nativas:
        nativo = _normalizar(linha.texto)
        if len(nativo) < min_caracteres:
            continue
        x0, y0, x1, y1 = linha.bbox
        regiao = (x0 - FOLGA_PONTOS, y0 - FOLGA_PONTOS, x1 + FOLGA_PONTOS, y1 + FOLGA_PONTOS)
        lido = _normalizar(_palavras_na_regiao(ocr, regiao))
        d = levenshtein(nativo, lido)
        comparadas += 1
        caracteres += len(nativo)
        distancia += min(d, len(nativo))
        if 1 - d / max(len(nativo), len(lido)) < similaridade_minima:
            divergentes += 1
            trechos.append(list(linha.bbox))
    return Divergencia(comparadas, divergentes, caracteres, distancia, trechos)
