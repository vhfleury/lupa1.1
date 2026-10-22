"""Desenho das folhas em PDF: nativa, digitalizada, híbridas, vazia e capa, com ruídos.

Texto nativo usa fontes embutidas (Nimbus Roman, embutida pelo PyMuPDF como Type0). Folhas
digitalizadas são desenhadas numa página auxiliar, rasterizadas em tons de cinza, degradadas
(contraste, ruído gaussiano, rotação, resolução) e inseridas como JPEG numa folha sem camada de
texto. Carimbos e imagens com texto entram como imagem; a marca d'água entra como texto
diagonal cinza claro, desenhado depois do corpo (fica no fim de ``get_text()``).
"""

import io
import random
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

import fitz
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from lupa.sinteticos.gabarito import Composicao, Degradacao
from lupa.sinteticos.paginacao import (
    ALTURA,
    FONTE,
    FONTE_NEGRITO,
    LARGURA,
    LIMITE_CORPO,
    MARGEM_ESQUERDA,
    TOPO_CORPO,
    LinhaTexto,
    PaginaPlano,
)

TEXTO_MARCA_DAGUA = "CÓPIA - DOCUMENTO SINTÉTICO"


@dataclass(frozen=True)
class ParametrosDegradacao:
    """Parâmetros de um nível de degradação.

    Attributes:
        dpi: Resolução da digitalização.
        ruido: Desvio-padrão do ruído gaussiano (0 a 255).
        rotacao_max: Rotação máxima em graus (para mais ou para menos).
        contraste: Faixa do fator de contraste.
        qualidade_jpeg: Qualidade do JPEG.
    """

    dpi: int
    ruido: float
    rotacao_max: float
    contraste: tuple[float, float]
    qualidade_jpeg: int


DEGRADACOES = {
    Degradacao.LEVE: ParametrosDegradacao(300, 6.0, 1.0, (0.9, 1.0), 45),
    Degradacao.MEDIA: ParametrosDegradacao(200, 14.0, 2.0, (0.75, 0.9), 45),
    Degradacao.FORTE: ParametrosDegradacao(150, 24.0, 3.0, (0.55, 0.75), 40),
}


@dataclass(frozen=True)
class Digitalizacao:
    """Como a imagem da folha foi produzida.

    Attributes:
        degradacao: Nível.
        dpi: Resolução usada.
        rotacao: Rotação aplicada em graus.
    """

    degradacao: Degradacao
    dpi: int
    rotacao: float


def escrever(
    pagina: fitz.Page, linhas: Iterable[LinhaTexto], cor: tuple[float, ...] = (0, 0, 0)
) -> None:
    """Escreve linhas como texto nativo com fontes embutidas.

    Args:
        pagina: Página de destino.
        linhas: Linhas posicionadas.
        cor: Cor RGB de 0 a 1.
    """
    escritor = fitz.TextWriter(pagina.rect, color=cor)
    for linha in linhas:
        fonte = FONTE_NEGRITO if linha.negrito else FONTE
        escritor.append((linha.x, linha.y), linha.texto, font=fonte, fontsize=linha.tamanho)
    escritor.write_text(pagina)


def escrever_marca_dagua(pagina: fitz.Page) -> None:
    """Escreve a marca d'água diagonal (45 graus, cinza claro).

    Args:
        pagina: Página de destino.
    """
    escritor = fitz.TextWriter(pagina.rect, color=(0.82, 0.82, 0.82))
    escritor.append((95, ALTURA / 2), TEXTO_MARCA_DAGUA, font=FONTE_NEGRITO, fontsize=34)
    centro = fitz.Point(LARGURA / 2, ALTURA / 2)
    escritor.write_text(pagina, morph=(centro, fitz.Matrix(-45)))


def _rasterizar(plano: PaginaPlano, clip: fitz.Rect, dpi: int) -> NDArray[np.uint8]:
    auxiliar = fitz.open()
    pagina = auxiliar.new_page(width=LARGURA, height=ALTURA)
    escrever(pagina, plano.linhas)
    if plano.marca_dagua:
        escrever_marca_dagua(pagina)
    pix = pagina.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, clip=clip)
    matriz = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.stride)[:, : pix.w]
    auxiliar.close()
    return matriz.copy()


@cache
def _campo_ruido(nivel: Degradacao) -> NDArray[np.float32]:
    parametros = DEGRADACOES[nivel]
    lado = int(max(LARGURA, ALTURA) / 72 * parametros.dpi) + 128
    gerador = np.random.default_rng(list(Degradacao).index(nivel))
    return gerador.normal(0.0, parametros.ruido, size=(lado, lado)).astype(np.float32)


def degradar(
    matriz: NDArray[np.uint8], nivel: Degradacao, rng: random.Random, girar: bool
) -> tuple[bytes, float]:
    """Aplica contraste, ruído, rotação e leve desfoque (scanner) e codifica em JPEG.

    Args:
        matriz: Imagem em tons de cinza.
        nivel: Nível de degradação.
        rng: Gerador semeado.
        girar: Se aplica rotação.

    Returns:
        JPEG e rotação aplicada em graus.
    """
    parametros = DEGRADACOES[nivel]
    contraste = rng.uniform(*parametros.contraste)
    imagem = (matriz.astype(np.float32) - 255.0) * contraste + 255.0 - rng.uniform(0, 20)
    ruido = _campo_ruido(nivel)
    dy = rng.randint(0, ruido.shape[0] - imagem.shape[0])
    dx = rng.randint(0, ruido.shape[1] - imagem.shape[1])
    imagem += ruido[dy : dy + imagem.shape[0], dx : dx + imagem.shape[1]]
    pil = Image.fromarray(np.clip(imagem, 0, 255).astype(np.uint8), mode="L")
    rotacao = (
        round(rng.uniform(-parametros.rotacao_max, parametros.rotacao_max), 2) if girar else 0.0
    )
    if rotacao:
        pil = pil.rotate(rotacao, resample=Image.Resampling.BILINEAR, fillcolor=235)
    pil = pil.filter(ImageFilter.GaussianBlur(0.7))
    saida = io.BytesIO()
    pil.save(saida, format="JPEG", quality=parametros.qualidade_jpeg)
    return saida.getvalue(), rotacao


@cache
def imagem_texto(texto: str, cor: tuple[int, int, int], largura: int, girar: float) -> bytes:
    """Gera PNG com texto (carimbo ou imagem com instrução), com fundo transparente.

    Args:
        texto: Texto; ``|`` separa linhas.
        cor: Cor RGB.
        largura: Largura em pixels.
        girar: Rotação em graus.

    Returns:
        PNG.
    """
    linhas = texto.split("|")
    fonte = ImageFont.load_default(size=22)
    altura = 16 + 30 * len(linhas)
    imagem = Image.new("RGBA", (largura, altura), (255, 255, 255, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle((2, 2, largura - 3, altura - 3), outline=(*cor, 220), width=3)
    for i, linha in enumerate(linhas):
        desenho.text((12, 10 + 30 * i), linha, fill=(*cor, 230), font=fonte)
    if girar:
        imagem = imagem.rotate(girar, expand=True, resample=Image.Resampling.BICUBIC)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def carimbar(pagina: fitz.Page, texto: str, rng: random.Random) -> None:
    """Sobrepõe um carimbo vermelho, levemente girado, sobre o corpo do texto.

    Args:
        pagina: Página de destino.
        texto: Texto do carimbo (``|`` separa linhas).
        rng: Gerador semeado.
    """
    png = imagem_texto(texto, (190, 20, 20), 300, float(rng.choice((-12, -6, 8, 14))))
    x = rng.uniform(220, 360)
    y = rng.uniform(200, 560)
    pagina.insert_image(fitz.Rect(x, y, x + 170, y + 80), stream=png, keep_proportion=True)


def _inserir_imagem(pagina: fitz.Page, retangulo: fitz.Rect, jpeg: bytes) -> None:
    pagina.insert_image(retangulo, stream=jpeg, keep_proportion=False)


def desenhar(
    documento: fitz.Document,
    plano: PaginaPlano,
    composicao: Composicao,
    nivel: Degradacao | None,
    rng: random.Random,
) -> tuple[fitz.Page, Digitalizacao | None]:
    """Cria a folha no documento conforme a composição.

    Args:
        documento: Documento de conteúdo.
        plano: Folha paginada.
        composicao: Como fabricar a folha.
        nivel: Degradação, para composições com imagem.
        rng: Gerador semeado.

    Returns:
        A página criada e os dados da digitalização (se houver).
    """
    pagina = documento.new_page(width=LARGURA, height=ALTURA)
    if composicao == Composicao.VAZIA:
        return pagina, None
    if composicao in (Composicao.NATIVA, Composicao.CAPA):
        escrever(pagina, plano.linhas)
        if plano.marca_dagua:
            escrever_marca_dagua(pagina)
        return pagina, None
    if nivel is None:
        raise ValueError("composição com imagem exige nível de degradação")
    dpi = DEGRADACOES[nivel].dpi
    if composicao == Composicao.DIGITALIZADA:
        jpeg, rotacao = degradar(_rasterizar(plano, pagina.rect, dpi), nivel, rng, girar=True)
        _inserir_imagem(pagina, pagina.rect, jpeg)
        return pagina, Digitalizacao(nivel, dpi, rotacao)
    if composicao == Composicao.HIBRIDA_CORPO:
        nativas = [linha for linha in plano.linhas if linha.papel in ("cabecalho", "rodape")]
        regiao = fitz.Rect(0, TOPO_CORPO - 4, LARGURA, LIMITE_CORPO + 6)
    else:
        nativas = [linha for linha in plano.linhas if linha.papel != "assinatura"]
        ys = [linha.y for linha in plano.linhas if linha.papel == "assinatura"]
        regiao = fitz.Rect(MARGEM_ESQUERDA - 10, min(ys) - 14, LARGURA - 40, max(ys) + 6)
    jpeg, _ = degradar(_rasterizar(plano, regiao, dpi), nivel, rng, girar=False)
    _inserir_imagem(pagina, regiao, jpeg)
    escrever(pagina, nativas)
    return pagina, Digitalizacao(nivel, dpi, 0.0)
