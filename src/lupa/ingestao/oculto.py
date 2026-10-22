"""Texto oculto na camada de texto do PDF (Etapa 4D.1); roda só dentro do sandbox.

Um trecho da camada de texto é oculto quando o leitor humano não o vê na página renderizada:
fonte menor que 4 pt, cor igual ao fundo (fundo branco, o padrão de peças processuais),
opacidade zero, caixa fora da área visível (`CropBox`, que é `page.rect`) ou conteúdo numa
camada opcional (OCG) desligada. O trecho oculto sai do texto da página e vai para
`pagina.trechos_ocultos` com texto, caixa, motivo, hash e categorias de instrução.

Limitação: o fundo é suposto branco; texto da mesma cor de um retângulo colorido desenhado
atrás dele não é detectado aqui (a divergência OCR × nativo da 4C cobre parte desse caso).
Texto girado é visível ao leitor e não é tratado como oculto: a 4C já o tira do fluxo de leitura.
"""

from collections.abc import Iterable
from typing import Any

import fitz

from lupa.dominio.esquemas import calcular_hash

MIN_FONTE_VISIVEL = 4.0
COR_FUNDO = 0xFFFFFF
MASCARA_RGB = 0xFFFFFF
CASAS = 2
FLAGS_SEM_RECORTE = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
FONTE_PEQUENA = "fonte_pequena"
COR_DO_FUNDO = "cor_do_fundo"
OPACIDADE_ZERO = "opacidade_zero"
FORA_DA_AREA = "fora_da_area_visivel"
CAMADA_DESLIGADA = "camada_desligada"


def _alfa(span: dict[str, Any]) -> int:
    if "alpha" in span:
        return int(span["alpha"])
    cor = int(span["color"])
    return (cor >> 24) & 0xFF if cor < 0 or cor > MASCARA_RGB else 0xFF


def motivo_oculto(span: dict[str, Any], area: fitz.Rect) -> str | None:
    """Por que um span não é visível, ou None se é visível.

    Args:
        span: Span de `page.get_text("dict")`.
        area: Área visível da página.

    Returns:
        Motivo, ou None.
    """
    if not fitz.Rect(span["bbox"]).intersects(area):
        return FORA_DA_AREA
    if float(span["size"]) < MIN_FONTE_VISIVEL:
        return FONTE_PEQUENA
    if _alfa(span) == 0:
        return OPACIDADE_ZERO
    if int(span["color"]) & MASCARA_RGB == COR_FUNDO:
        return COR_DO_FUNDO
    return None


def _linhas(pagina: fitz.Page) -> Iterable[list[dict[str, Any]]]:
    dados = pagina.get_text("dict", flags=FLAGS_SEM_RECORTE, clip=fitz.INFINITE_RECT())
    for bloco in dados["blocks"]:
        if bloco.get("type") == 0:
            for linha in bloco["lines"]:
                yield [s for s in linha["spans"] if s["text"].strip()]


def _caixa(spans: list[dict[str, Any]]) -> list[float]:
    caixa = fitz.Rect(spans[0]["bbox"])
    for span in spans[1:]:
        caixa |= fitz.Rect(span["bbox"])
    return [round(float(v), CASAS) for v in caixa]


def _item(spans: list[dict[str, Any]], motivo: str) -> dict[str, Any]:
    texto = "".join(s["text"] for s in spans)
    return {"texto": texto, "bbox": _caixa(spans), "motivo": motivo, "hash": calcular_hash(texto)}


def _agrupar(spans: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    grupo: list[dict[str, Any]] = []
    motivo_grupo = ""
    for span, motivo in spans:
        if grupo and motivo != motivo_grupo:
            itens.append(_item(grupo, motivo_grupo))
            grupo = []
        grupo.append(span)
        motivo_grupo = motivo
    if grupo:
        itens.append(_item(grupo, motivo_grupo))
    return itens


def trechos_ocultos_por_estilo(pagina: fitz.Page) -> list[dict[str, Any]]:
    """Trechos ocultos por tamanho, cor, opacidade ou posição.

    Args:
        pagina: Página aberta.

    Returns:
        Itens `{texto, bbox, motivo, hash}`, um por linha e motivo.
    """
    area = pagina.rect
    itens: list[dict[str, Any]] = []
    for spans in _linhas(pagina):
        marcados = [(s, m) for s in spans if (m := motivo_oculto(s, area)) is not None]
        itens += _agrupar(marcados)
    return itens


def _assinaturas(pagina: fitz.Page) -> set[tuple[str, tuple[float, ...]]]:
    return {
        (s["text"], tuple(round(float(v), CASAS) for v in s["bbox"]))
        for spans in _linhas(pagina)
        for s in spans
    }


_LIGADOS: dict[int, fitz.Document] = {}


def documento_com_camadas_ligadas(documento: fitz.Document) -> fitz.Document:
    """Cópia do documento com todas as camadas opcionais ligadas (uma por documento).

    A troca de estado das camadas só vale para a extração depois de regravar o documento, por
    isso a cópia é aberta de novo a partir dos bytes; guarda-se só a do último documento.

    Args:
        documento: Documento aberto.

    Returns:
        Cópia com as camadas ligadas.
    """
    chave = id(documento)
    if chave not in _LIGADOS:
        copia = fitz.open(stream=documento.tobytes(), filetype="pdf")
        copia.set_layer(-1, on=list(copia.get_ocgs()), off=[])
        _LIGADOS.clear()
        _LIGADOS[chave] = fitz.open(stream=copia.tobytes(), filetype="pdf")
    return _LIGADOS[chave]


def trechos_em_camadas_desligadas(pagina: fitz.Page) -> list[dict[str, Any]]:
    """Trechos que só aparecem com todas as camadas opcionais (OCG) ligadas.

    Args:
        pagina: Página aberta.

    Returns:
        Itens `{texto, bbox, motivo, hash}` com motivo `camada_desligada`.
    """
    documento = pagina.parent
    camadas = documento.get_ocgs()
    if not camadas or all(info.get("on", True) for info in camadas.values()):
        return []
    visiveis = _assinaturas(pagina)
    ligada = documento_com_camadas_ligadas(documento)[pagina.number]
    novos = [
        s for spans in _linhas(ligada) for s in spans
        if (s["text"], tuple(round(float(v), CASAS) for v in s["bbox"])) not in visiveis
    ]  # fmt: skip
    return _agrupar([(s, CAMADA_DESLIGADA) for s in novos])


def trechos_ocultos(pagina: fitz.Page) -> list[dict[str, Any]]:
    """Todos os trechos ocultos da página.

    Args:
        pagina: Página aberta.

    Returns:
        Itens `{texto, bbox, motivo, hash}`.
    """
    return trechos_ocultos_por_estilo(pagina) + trechos_em_camadas_desligadas(pagina)
