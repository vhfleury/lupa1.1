"""Texto nativo com coordenadas (4C.5); roda só dentro do sandbox.

Coordenadas em pontos PDF (1/72 pol.) no sistema do PyMuPDF: origem no canto superior
esquerdo da página, y para baixo. A ordem de leitura vem de um corte XY sobre os blocos de
texto horizontais: a página é cortada em faixas por vãos verticais; faixas seguidas com mais
de uma coluna são lidas coluna a coluna, da esquerda para a direita; sem vão, os blocos
seguem por (topo, esquerda). Linhas não horizontais (marca d'água diagonal, carimbo de texto
girado) não fazem parte do fluxo de leitura e vão para o fim, na ordem do arquivo. O texto é a
concatenação das linhas, cada uma terminada por quebra de linha, como `page.get_text()`;
cada bloco e cada linha guarda seus offsets nesse texto, então os offsets são reproduzíveis.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import fitz

from lupa.ingestao.oculto import motivo_oculto

CASAS = 2
TOLERANCIA_DIRECAO = 1e-3
SOBREPOSICAO_TOLERADA = 1.0


@dataclass
class Linha:
    """Linha de texto com caixa.

    Attributes:
        texto: Texto da linha.
        bbox: Caixa `[x0, y0, x1, y1]` em pontos.
        horizontal: Se a linha corre na horizontal.
    """

    texto: str
    bbox: tuple[float, float, float, float]
    horizontal: bool = True


@dataclass
class Bloco:
    """Bloco de texto com suas linhas.

    Attributes:
        bbox: Caixa do bloco.
        linhas: Linhas na ordem do arquivo.
    """

    bbox: tuple[float, float, float, float]
    linhas: list[Linha] = field(default_factory=list)


@dataclass(frozen=True)
class TextoPagina:
    """Texto da página e as coordenadas de blocos e linhas.

    Attributes:
        texto: Texto na ordem de leitura.
        blocos: Blocos `{bbox, inicio, fim, linhas: [{bbox, inicio, fim}]}`.
        linhas: Linhas horizontais em ordem de leitura (usadas na fusão com o OCR).
        linhas_fora_do_fluxo: Linhas não horizontais.
    """

    texto: str
    blocos: list[dict[str, Any]]
    linhas: list[Linha]
    linhas_fora_do_fluxo: list[Linha]


def _caixa(valores: Sequence[float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (round(float(v), CASAS) for v in valores)
    return x0, y0, x1, y1


def _horizontal(direcao: Sequence[float]) -> bool:
    return abs(float(direcao[0]) - 1.0) < TOLERANCIA_DIRECAO and abs(float(direcao[1])) < (
        TOLERANCIA_DIRECAO
    )


def ler_blocos(pagina: fitz.Page) -> list[Bloco]:
    """Blocos de texto da página, na ordem do arquivo.

    Spans ocultos (4D.1: fonte pequena, cor do fundo, opacidade zero, fora da área visível)
    ficam fora; linha que só tinha texto oculto desaparece.

    Args:
        pagina: Página aberta.

    Returns:
        Blocos com linhas visíveis.
    """
    blocos = []
    area = pagina.rect
    for dado in pagina.get_text("dict")["blocks"]:
        if dado.get("type") != 0:
            continue
        linhas = [
            linha for bruta in dado["lines"] if (linha := _linha_visivel(bruta, area)) is not None
        ]
        if linhas:
            blocos.append(Bloco(_caixa(dado["bbox"]), linhas))
    return blocos


def _linha_visivel(linha: dict[str, Any], area: fitz.Rect) -> Linha | None:
    spans = linha["spans"]
    visiveis = [s for s in spans if not s["text"].strip() or motivo_oculto(s, area) is None]
    if not any(s["text"].strip() for s in visiveis) and any(s["text"].strip() for s in spans):
        return None
    caixa = linha["bbox"]
    if len(visiveis) < len(spans):
        uniao = fitz.Rect(visiveis[0]["bbox"])
        for span in visiveis[1:]:
            uniao |= fitz.Rect(span["bbox"])
        caixa = tuple(uniao)
    texto = "".join(span["text"] for span in visiveis)
    return Linha(texto, _caixa(caixa), _horizontal(linha["dir"]))


def _cortes(blocos: list[Bloco], eixo: int) -> list[list[Bloco]]:
    inicio, fim = eixo, eixo + 2
    grupos: list[list[Bloco]] = []
    limite = float("-inf")
    for bloco in sorted(blocos, key=lambda b: (b.bbox[inicio], b.bbox[1 - eixo])):
        if not grupos or bloco.bbox[inicio] >= limite - SOBREPOSICAO_TOLERADA:
            grupos.append([bloco])
            limite = bloco.bbox[fim]
        else:
            grupos[-1].append(bloco)
            limite = max(limite, bloco.bbox[fim])
    return grupos


def _colunas(blocos: list[Bloco]) -> list[Bloco] | None:
    colunas = _cortes(blocos, eixo=0)
    if len(colunas) < 2:
        return None
    return [b for coluna in colunas for b in ordenar_blocos(coluna)]


def _ordenar_regiao(faixas: list[list[Bloco]]) -> list[Bloco]:
    blocos = [b for faixa in faixas for b in faixa]
    por_coluna = _colunas(blocos)
    if por_coluna is not None:
        return por_coluna
    return [b for faixa in faixas for b in ordenar_blocos(faixa)]


def ordenar_blocos(blocos: list[Bloco]) -> list[Bloco]:
    """Ordena blocos horizontais em ordem de leitura.

    A página é cortada em faixas horizontais (vãos verticais sem texto). Faixas consecutivas
    que têm mais de uma coluna formam uma região lida coluna a coluna (cada coluna de cima para
    baixo); as demais faixas são lidas em ordem. Sem corte possível, (topo, esquerda).

    Args:
        blocos: Blocos de uma região.

    Returns:
        Blocos em ordem de leitura.
    """
    if len(blocos) <= 1:
        return list(blocos)
    faixas = _cortes(blocos, eixo=1)
    if len(faixas) == 1:
        por_coluna = _colunas(blocos)
        return por_coluna or sorted(blocos, key=lambda b: (b.bbox[1], b.bbox[0]))
    ordenados: list[Bloco] = []
    regiao: list[list[Bloco]] = []
    for faixa in faixas:
        if len(faixa) > 1 and len(_cortes(faixa, eixo=0)) > 1:
            regiao.append(faixa)
            continue
        if regiao:
            ordenados += _ordenar_regiao(regiao)
            regiao = []
        ordenados += ordenar_blocos(faixa)
    return ordenados + (_ordenar_regiao(regiao) if regiao else [])


def _separar(blocos: list[Bloco]) -> tuple[list[Bloco], list[Linha]]:
    horizontais: list[Bloco] = []
    fora: list[Linha] = []
    for bloco in blocos:
        linhas = [linha for linha in bloco.linhas if linha.horizontal]
        fora.extend(linha for linha in bloco.linhas if not linha.horizontal)
        if linhas:
            horizontais.append(Bloco(bloco.bbox, linhas))
    return horizontais, fora


def montar_texto(blocos: list[Bloco], fora: list[Linha]) -> TextoPagina:
    """Concatena blocos ordenados e linhas fora do fluxo, registrando offsets.

    Args:
        blocos: Blocos horizontais em ordem de leitura.
        fora: Linhas não horizontais.

    Returns:
        Texto e coordenadas.
    """
    partes: list[str] = []
    cursor = 0
    saida: list[dict[str, Any]] = []
    grupos = [(b.bbox, b.linhas, True) for b in blocos]
    grupos += [(linha.bbox, [linha], False) for linha in fora]
    for bbox, linhas, fluxo in grupos:
        inicio_bloco = cursor
        descritas = []
        for linha in linhas:
            partes.append(linha.texto + "\n")
            descritas.append(
                {"bbox": list(linha.bbox), "inicio": cursor, "fim": cursor + len(linha.texto)}
            )
            cursor += len(linha.texto) + 1
        saida.append(
            {
                "bbox": list(bbox),
                "inicio": inicio_bloco,
                "fim": cursor,
                "fluxo": fluxo,
                "linhas": descritas,
            }
        )
    linhas_fluxo = [linha for bloco in blocos for linha in bloco.linhas]
    return TextoPagina("".join(partes), saida, linhas_fluxo, fora)


def extrair_texto_nativo(pagina: fitz.Page) -> TextoPagina:
    """Extrai o texto nativo da página em ordem de leitura, com coordenadas.

    Args:
        pagina: Página aberta.

    Returns:
        Texto, blocos com offsets e linhas.
    """
    horizontais, fora = _separar(ler_blocos(pagina))
    return montar_texto(ordenar_blocos(horizontais), fora)
