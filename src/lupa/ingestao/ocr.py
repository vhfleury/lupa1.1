"""OCR com Tesseract (4C.6); roda só dentro do sandbox, que chama o binário em subprocesso.

A página é rasterizada em tons de cinza (300 DPI por padrão) e entregue ao `tesseract` por
stdin, sem arquivo temporário; a saída TSV volta por stdout. Antes, a detecção de orientação
(`--psm 0`, modelo `osd`, sobre o mesmo raster) diz se a página está deitada ou de cabeça para
baixo; com confiança suficiente, a página é rasterizada de novo já girada. As caixas de palavra
saem em pixels do raster e são convertidas para pontos PDF pela inversa da matriz de
rasterização (que inclui a rotação de correção e a origem do recorte). Essa matriz
`pixel -> ponto` é devolvida com o resultado para registro.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

import fitz

DPI_OCR = 300
IDIOMA = "por"
PSM_PAGINA = "3"
CONFIANCA_MINIMA_OSD = 2.0
TEMPO_TESSERACT_SEGUNDOS = 90.0
CASAS = 2
ROTACOES_VALIDAS = frozenset({0, 90, 180, 270})
PADRAO_ROTACAO = re.compile(r"Rotate:\s*(\d+)")
PADRAO_CONFIANCA = re.compile(r"Orientation confidence:\s*([\d.]+)")


class OcrIndisponivelError(RuntimeError):
    """O binário do Tesseract não está instalado ou falhou."""


@dataclass(frozen=True)
class Raster:
    """Página rasterizada para o OCR.

    Attributes:
        png: Imagem PNG em tons de cinza.
        matriz: Transformação `pixel -> ponto PDF` (a, b, c, d, e, f).
        dpi: Resolução.
        rotacao: Rotação aplicada na rasterização (graus).
    """

    png: bytes
    matriz: tuple[float, float, float, float, float, float]
    dpi: int
    rotacao: int


@dataclass
class LinhaOcr:
    """Linha reconhecida, com caixa em pontos PDF.

    Attributes:
        texto: Palavras unidas por espaço.
        bbox: Caixa `[x0, y0, x1, y1]` em pontos.
        palavras: Palavras `{texto, bbox, confianca}`.
    """

    texto: str
    bbox: tuple[float, float, float, float]
    palavras: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ResultadoOcr:
    """Resultado do OCR de uma página.

    Attributes:
        texto: Linhas do OCR, cada uma terminada por quebra de linha.
        linhas: Linhas com caixas em pontos.
        dpi: Resolução usada.
        rotacao: Rotação de correção aplicada (graus, da detecção de orientação).
        confianca_osd: Confiança da detecção de orientação (0 se não houve).
        matriz: Transformação `pixel -> ponto` registrada.
        confianca_media: Média da confiança das palavras (0 a 100).
    """

    texto: str
    linhas: list[LinhaOcr]
    dpi: int
    rotacao: int
    confianca_osd: float
    matriz: tuple[float, float, float, float, float, float]
    confianca_media: float


def binario_tesseract() -> str:
    """Caminho do binário do Tesseract.

    Returns:
        Caminho absoluto.

    Raises:
        OcrIndisponivelError: Se o binário não estiver no PATH.
    """
    caminho = shutil.which("tesseract", path=os.environ.get("PATH") or os.defpath)
    if caminho is None:
        raise OcrIndisponivelError("tesseract não encontrado")
    return caminho


def rasterizar(
    pagina: fitz.Page, dpi: int, rotacao: int = 0, clip: fitz.Rect | None = None
) -> Raster:
    """Rasteriza a página (ou um recorte) em cinza, opcionalmente girada.

    Args:
        pagina: Página aberta.
        dpi: Resolução.
        rotacao: Rotação adicional em graus (múltiplo de 90).
        clip: Recorte em pontos (None = página inteira).

    Returns:
        Raster com a matriz `pixel -> ponto`.
    """
    escala = dpi / 72
    matriz = fitz.Matrix(escala, escala).prerotate(rotacao)
    pix = pagina.get_pixmap(matrix=matriz, colorspace=fitz.csGRAY, alpha=False, clip=clip)
    volta = fitz.Matrix(1, 0, 0, 1, pix.x, pix.y) * ~matriz
    coeficientes = (volta.a, volta.b, volta.c, volta.d, volta.e, volta.f)
    return Raster(pix.tobytes("png"), coeficientes, dpi, rotacao)


def executar_tesseract(png: bytes, argumentos: list[str]) -> str:
    """Roda o Tesseract com a imagem em stdin e devolve o stdout.

    Args:
        png: Imagem.
        argumentos: Argumentos depois de `stdin stdout`.

    Returns:
        Saída do Tesseract (texto UTF-8).

    Raises:
        OcrIndisponivelError: Se o processo falhar ou exceder o tempo.
    """
    ambiente = {"PATH": os.environ.get("PATH") or os.defpath, "OMP_THREAD_LIMIT": "1"}
    try:
        processo = subprocess.run(  # noqa: S603
            [binario_tesseract(), "stdin", "stdout", *argumentos],
            input=png,
            capture_output=True,
            timeout=TEMPO_TESSERACT_SEGUNDOS,
            env=ambiente,
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        raise OcrIndisponivelError("tesseract excedeu o tempo") from erro
    if processo.returncode != 0:
        raise OcrIndisponivelError(f"tesseract terminou com código {processo.returncode}")
    return processo.stdout.decode("utf-8", errors="replace")


def ler_orientacao(saida_osd: str) -> tuple[int, float]:
    """Interpreta a saída do `--psm 0`.

    Args:
        saida_osd: Texto devolvido pelo Tesseract.

    Returns:
        Rotação sugerida (0, 90, 180 ou 270) e a confiança; (0, 0.0) se ilegível.
    """
    rotacao = PADRAO_ROTACAO.search(saida_osd)
    confianca = PADRAO_CONFIANCA.search(saida_osd)
    if rotacao is None or confianca is None or int(rotacao[1]) not in ROTACOES_VALIDAS:
        return 0, 0.0
    return int(rotacao[1]), float(confianca[1])


def orientacao_do_raster(png: bytes) -> tuple[int, float]:
    """Detecta a orientação de uma imagem com o modelo `osd`.

    Imagem com pouco texto faz o Tesseract recusar a detecção; isso vale como 0 grau.

    Args:
        png: Imagem rasterizada.

    Returns:
        Rotação de correção em graus (sentido da rasterização do PyMuPDF) e a confiança.
    """
    try:
        saida = executar_tesseract(png, ["--psm", "0", "-l", "osd"])
    except OcrIndisponivelError:
        return 0, 0.0
    rotacao, confianca = ler_orientacao(saida)
    if confianca < CONFIANCA_MINIMA_OSD:
        return 0, confianca
    return rotacao, confianca


def detectar_orientacao(pagina: fitz.Page, dpi: int = DPI_OCR) -> tuple[int, float]:
    """Detecta a orientação da página.

    Args:
        pagina: Página aberta.
        dpi: Resolução do raster usado na detecção.

    Returns:
        Rotação de correção em graus e a confiança.
    """
    return orientacao_do_raster(rasterizar(pagina, dpi).png)


def _aplicar(matriz: fitz.Matrix, caixa: tuple[float, float, float, float]) -> tuple[float, ...]:
    retangulo = fitz.Rect(caixa) * matriz
    retangulo.normalize()
    return tuple(round(v, CASAS) for v in retangulo)


def _uniao(caixas: list[tuple[float, ...]]) -> tuple[float, float, float, float]:
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


def ler_tsv(tsv: str, matriz: tuple[float, ...]) -> list[LinhaOcr]:
    """Converte o TSV do Tesseract em linhas com caixas em pontos PDF.

    Args:
        tsv: Saída `tsv` do Tesseract.
        matriz: Transformação `pixel -> ponto`.

    Returns:
        Linhas na ordem do Tesseract, sem palavras vazias.
    """
    transformacao = fitz.Matrix(*matriz)
    linhas: dict[tuple[str, ...], LinhaOcr] = {}
    for registro in tsv.splitlines()[1:]:
        campos = registro.split("\t")
        if len(campos) < 12 or campos[0] != "5" or not campos[11].strip():
            continue
        x, y, largura, altura = (int(v) for v in campos[6:10])
        caixa = _aplicar(transformacao, (x, y, x + largura, y + altura))
        palavra = {"texto": campos[11].strip(), "bbox": list(caixa), "confianca": float(campos[10])}
        chave = tuple(campos[1:5])
        linha = linhas.setdefault(chave, LinhaOcr("", (0.0, 0.0, 0.0, 0.0)))
        linha.palavras.append(palavra)
    for linha in linhas.values():
        linha.texto = " ".join(p["texto"] for p in linha.palavras)
        linha.bbox = _uniao([tuple(p["bbox"]) for p in linha.palavras])
    return list(linhas.values())


def ocr_pagina(pagina: fitz.Page, dpi: int = DPI_OCR) -> ResultadoOcr:
    """Reconhece o texto da página inteira, com correção de orientação.

    Args:
        pagina: Página aberta.
        dpi: Resolução do raster.

    Returns:
        Texto, linhas com caixas em pontos e o registro da transformação.

    Raises:
        OcrIndisponivelError: Se o Tesseract falhar.
    """
    raster = rasterizar(pagina, dpi)
    rotacao, confianca_osd = orientacao_do_raster(raster.png)
    if rotacao:
        raster = rasterizar(pagina, dpi, rotacao)
    tsv = executar_tesseract(
        raster.png, ["-l", IDIOMA, "--psm", PSM_PAGINA, "--dpi", str(dpi), "tsv"]
    )
    linhas = ler_tsv(tsv, raster.matriz)
    confiancas = [p["confianca"] for linha in linhas for p in linha.palavras]
    return ResultadoOcr(
        texto="".join(linha.texto + "\n" for linha in linhas),
        linhas=linhas,
        dpi=dpi,
        rotacao=rotacao,
        confianca_osd=round(confianca_osd, CASAS),
        matriz=tuple(round(v, 6) for v in raster.matriz),  # type: ignore[arg-type]
        confianca_media=round(sum(confiancas) / len(confiancas), CASAS) if confiancas else 0.0,
    )
