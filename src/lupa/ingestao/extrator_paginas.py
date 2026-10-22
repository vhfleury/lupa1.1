"""Extração de um lote de páginas (4C.3 a 4C.7), executada só dentro do sandbox.

Para cada página do intervalo: mede os sinais, roteia, extrai o texto nativo com
coordenadas e, quando a rota pede (`ocr` ou abstenção), roda o OCR; na abstenção guarda os dois
textos, funde por geometria e compara as camadas (flag `texto_divergente`). Na página nativa,
as imagens grandes passam por OCR só de detecção (`lupa.ingestao.imagem_nativa`, versão 4f.0).
Escreve um único objeto JSON em stdout: `{"ok": true, "paginas": [...]}`. Página cujo OCR
falhou volta com `erro` e sem texto (o job fica `parcial`). Falta de memória termina com
`EXIT_MEMORIA`.

Argumentos: caminho do PDF, página inicial e página final (1-based, inclusivas).
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

import fitz

from lupa.dominio.enums import FlagPagina, TipoPagina
from lupa.ingestao import metadados
from lupa.ingestao.hibridas import comparar, fundir
from lupa.ingestao.imagem_nativa import imagens_suspeitas
from lupa.ingestao.ocr import OcrIndisponivelError, ResultadoOcr, ocr_pagina
from lupa.ingestao.oculto import trechos_ocultos
from lupa.ingestao.parser_pdf import EXIT_MEMORIA, bloquear_rede
from lupa.ingestao.roteador import limiares_padrao, rotear
from lupa.ingestao.saneamento_pagina import categorias_de, sanear
from lupa.ingestao.sinais import medir_sinais
from lupa.ingestao.texto_nativo import TextoPagina, extrair_texto_nativo

VERSAO_EXTRATOR = "4f.0"
SISTEMA_COORDENADAS = "pdf_pontos_origem_superior_esquerda"
ROTA_ABSTENCAO = "abstencao"


def _tem_texto(texto: str) -> bool:
    return any(c.isprintable() and not c.isspace() for c in texto)


def _registro_ocr(ocr: ResultadoOcr) -> dict[str, Any]:
    return {
        "dpi": ocr.dpi,
        "rotacao_correcao": ocr.rotacao,
        "confianca_osd": ocr.confianca_osd,
        "matriz_pixel_para_ponto": list(ocr.matriz),
        "confianca_media": ocr.confianca_media,
    }


def _linhas_ocr(ocr: ResultadoOcr) -> list[dict[str, Any]]:
    linhas = []
    cursor = 0
    for linha in ocr.linhas:
        linhas.append(
            {
                "origem": "ocr",
                "bbox": list(linha.bbox),
                "inicio": cursor,
                "fim": cursor + len(linha.texto),
                "palavras": linha.palavras,
            }
        )
        cursor += len(linha.texto) + 1
    return linhas


def _nativa(nativo: TextoPagina) -> dict[str, Any]:
    return {
        "tipo": TipoPagina.NATIVA.value,
        "texto": nativo.texto,
        "coordenadas": {"sistema": SISTEMA_COORDENADAS, "blocos": nativo.blocos},
    }


def _imagens(pagina: fitz.Page) -> dict[str, Any]:
    registros = imagens_suspeitas(pagina)
    if not registros:
        return {}
    flags = (
        {FlagPagina.PADRAO_INSTRUCAO.value: True} if any(r["categorias"] for r in registros) else {}
    )
    return {"imagens_nativas": registros, "flags": flags}


def _digitalizada(ocr: ResultadoOcr) -> dict[str, Any]:
    tipo = TipoPagina.OCR if _tem_texto(ocr.texto) else TipoPagina.VAZIA
    return {
        "tipo": tipo.value,
        "texto": ocr.texto,
        "texto_ocr": ocr.texto,
        "coordenadas": {"sistema": SISTEMA_COORDENADAS, "linhas": _linhas_ocr(ocr)},
        "ocr": _registro_ocr(ocr),
    }


def _hibrida(nativo: TextoPagina, ocr: ResultadoOcr) -> dict[str, Any]:
    texto, linhas = fundir(nativo.linhas, ocr.linhas)
    divergencia = comparar(nativo.linhas, ocr.linhas)
    tipo = TipoPagina.OCR if _tem_texto(texto) else TipoPagina.VAZIA
    flags = {FlagPagina.TEXTO_DIVERGENTE.value: True} if divergencia.divergente else {}
    return {
        "tipo": tipo.value,
        "texto": texto,
        "texto_ocr": ocr.texto,
        "flags": flags,
        "coordenadas": {
            "sistema": SISTEMA_COORDENADAS,
            "linhas": linhas,
            "blocos_nativos": nativo.blocos,
            "linhas_ocr": _linhas_ocr(ocr),
        },
        "ocr": _registro_ocr(ocr),
        "divergencia": {
            "linhas_comparadas": divergencia.linhas_comparadas,
            "linhas_divergentes": divergencia.linhas_divergentes,
            "caracteres": divergencia.caracteres,
            "distancia": divergencia.distancia,
            "cer_estimado": divergencia.cer_estimado,
            "trechos": divergencia.trechos,
        },
    }


def processar_pagina(pagina: fitz.Page, numero: int) -> dict[str, Any]:
    """Extrai uma página.

    Args:
        pagina: Página aberta.
        numero: Número da página no arquivo (1-based).

    Returns:
        `numero`, `sinais`, `rota`, `tipo`, `texto`, `texto_nativo`, `texto_ocr`, `flags`,
        `coordenadas`, `ocr`, `divergencia`, `segundos`; ou `numero`, `sinais`, `rota` e
        `erro` se o OCR falhou.
    """
    inicio = time.perf_counter()
    sinais = medir_sinais(pagina)
    rota = rotear(sinais)
    nativo = extrair_texto_nativo(pagina)
    base: dict[str, Any] = {
        "numero": numero,
        "sinais": sinais,
        "rota": rota.value if rota else ROTA_ABSTENCAO,
        "versao_roteador": limiares_padrao().versao,
        "texto_nativo": nativo.texto if _tem_texto(nativo.texto) else None,
        "texto_ocr": None,
        "flags": {},
        "ocr": None,
        "divergencia": None,
    }
    if rota is TipoPagina.NATIVA:
        resultado = _nativa(nativo) | _imagens(pagina)
    elif rota is TipoPagina.VAZIA:
        resultado = {"tipo": TipoPagina.VAZIA.value, "texto": "", "coordenadas": {}}
    else:
        try:
            ocr = ocr_pagina(pagina)
        except OcrIndisponivelError:
            return base | {"erro": "ocr", "segundos": round(time.perf_counter() - inicio, 3)}
        resultado = _digitalizada(ocr) if rota is TipoPagina.OCR else _hibrida(nativo, ocr)
    resultado = base | resultado
    resultado |= saneamento_da_pagina(pagina, numero, resultado)
    return resultado | {"segundos": round(time.perf_counter() - inicio, 3)}


def saneamento_da_pagina(
    pagina: fitz.Page, numero: int, resultado: dict[str, Any]
) -> dict[str, Any]:
    """Saneamento da página extraída (4D): ocultos, metadados, normalização e trechos.

    Args:
        pagina: Página aberta.
        numero: Número da página no PDF (1-based); a primeira carrega os metadados do documento.
        resultado: Página já extraída (`texto`, `tipo`, `flags`).

    Returns:
        `texto_normalizado`, `trechos_ocultos`, `trechos_suspeitos`, `flags` (somadas às da
        extração), `metadados_descartados` e `saneamento` (resumo).
    """
    ocultos = [o | {"categorias": categorias_de(o["texto"])} for o in trechos_ocultos(pagina)]
    descartados = metadados.da_pagina(pagina, numero)
    if numero == 1:
        descartados = metadados.do_documento(pagina.parent) + descartados
    saneado = sanear(str(resultado.get("texto") or ""), str(resultado["tipo"]))
    flags = dict(resultado.get("flags") or {}) | saneado.flags
    if ocultos:
        flags[FlagPagina.TEXTO_OCULTO.value] = True
    if metadados.suspeito(descartados):
        flags[FlagPagina.METADADO_SUSPEITO.value] = True
    return {
        "texto_normalizado": saneado.texto_normalizado,
        "trechos_ocultos": ocultos,
        "trechos_suspeitos": saneado.trechos_suspeitos,
        "flags": flags,
        "metadados_descartados": descartados,
        "saneamento": saneado.resumo,
    }


def extrair_intervalo(dados: bytes, inicio: int, fim: int) -> dict[str, Any]:
    """Extrai as páginas `inicio..fim` do PDF.

    Args:
        dados: Bytes do PDF.
        inicio: Primeira página (1-based).
        fim: Última página (inclusiva).

    Returns:
        `{"ok": true, "paginas": [...]}` ou `{"ok": false, "erro": "abertura"}`.
    """
    try:
        documento = fitz.open(stream=dados, filetype="pdf")
    except Exception:
        return {"ok": False, "erro": "abertura"}
    ultima = min(fim, documento.page_count)
    paginas = [processar_pagina(documento[n - 1], n) for n in range(inicio, ultima + 1)]
    return {"ok": True, "versao_extrator": VERSAO_EXTRATOR, "paginas": paginas}


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada do processo filho.

    Args:
        argv: `[caminho, inicio, fim]` (padrão: `sys.argv[1:]`).
    """
    bloquear_rede()
    caminho, inicio, fim = argv or sys.argv[1:]
    try:
        resultado = extrair_intervalo(Path(caminho).read_bytes(), int(inicio), int(fim))
    except MemoryError:
        sys.exit(EXIT_MEMORIA)
    sys.stdout.write(json.dumps(resultado, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    main()
