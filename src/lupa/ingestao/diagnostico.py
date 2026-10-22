"""Diagnóstico do contêiner: ZIP por peça, PDF com bookmarks, PDF com índice ou PDF liso.

Funções puras sobre dados já lidos do arquivo: o sumário (bookmarks) e o texto das primeiras
páginas vêm do parser no sandbox (`parser_pdf`); o manifesto vem do inventário do ZIP. Além do
cenário, o diagnóstico guarda as fronteiras candidatas que a própria origem oferece (linha do
índice de movimentações, bookmark de primeiro nível ou entrada do ZIP), cada uma com a página
física inicial. A Etapa 4E confere essas fronteiras contra o conteúdo.
"""

import re
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from lupa.dominio.enums import CenarioArquivo
from lupa.dominio.esquemas import DiagnosticoArquivo

MAX_PAGINAS_INDICE = 60
MIN_LINHAS_PRIMEIRA_PAGINA = 2
PROPORCAO_LINHAS_INDICE = 0.5
LINHAS_DE_CABECALHO = 3

PADRAO_LINHA_INDICE = re.compile(
    r"^\s*(?:movimenta[cç][aã]o|mov\.?|evento|seq\.?)\s*(?:n[º°o.]?\s*)?(?P<numero>\d{1,5})"
    r"\s*[-–—:]\s*(?P<data>\d{2}/\d{2}/\d{4})\s*[-–—]\s*(?P<titulo>.+?)\s*[-–—]\s*"
    r"(?:fls?\.?|folhas?|p[áa]g(?:ina)?s?\.?)\s*(?P<pagina>\d{1,6})\s*$",
    re.IGNORECASE,
)
PADRAO_DATA_BR = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
PADRAO_DATA_NOME = re.compile(r"(?:(\d{4})-(\d{2})-(\d{2}))|(?:(\d{2})-(\d{2})-(\d{4}))")


def _data_iso(dia: str, mes: str, ano: str) -> str | None:
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def data_no_texto(texto: str) -> str | None:
    """Primeira data dd/mm/aaaa válida do texto, em ISO.

    Args:
        texto: Texto livre (título de bookmark ou de movimentação).

    Returns:
        Data `AAAA-MM-DD` ou None.
    """
    for dia, mes, ano in PADRAO_DATA_BR.findall(texto):
        iso = _data_iso(dia, mes, ano)
        if iso:
            return iso
    return None


def data_no_nome(nome: str) -> str | None:
    """Data contida no nome de arquivo (`AAAA-MM-DD` ou `DD-MM-AAAA`), em ISO.

    Args:
        nome: Nome da entrada do ZIP.

    Returns:
        Data `AAAA-MM-DD` ou None.
    """
    for grupos in PADRAO_DATA_NOME.findall(nome):
        ano, mes, dia = grupos[:3] if grupos[0] else (grupos[5], grupos[4], grupos[3])
        iso = _data_iso(dia, mes, ano)
        if iso:
            return iso
    return None


def linhas_de_indice(texto: str) -> list[dict[str, Any]]:
    """Linhas de índice de movimentações reconhecidas num texto de página.

    Args:
        texto: Texto da página.

    Returns:
        Entradas `{numero, data, titulo, pagina}` na ordem do texto.
    """
    entradas = []
    for linha in texto.splitlines():
        achado = PADRAO_LINHA_INDICE.match(linha)
        if achado is None:
            continue
        dia, mes, ano = achado["data"].split("/")
        entradas.append(
            {
                "numero": int(achado["numero"]),
                "data": _data_iso(dia, mes, ano),
                "titulo": achado["titulo"].strip(),
                "pagina": int(achado["pagina"]),
            }
        )
    return entradas


def _e_pagina_de_indice(texto: str, entradas: int, primeira: bool) -> bool:
    if entradas == 0:
        return False
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    corpo = max(1, len(linhas) - LINHAS_DE_CABECALHO)
    if primeira and entradas < MIN_LINHAS_PRIMEIRA_PAGINA:
        return False
    return entradas >= PROPORCAO_LINHAS_INDICE * corpo


def ler_indice(textos: Iterable[str]) -> tuple[int, list[dict[str, Any]]]:
    """Lê o índice de movimentações nas páginas iniciais.

    O índice ocupa as primeiras páginas consecutivas em que a maior parte das linhas segue o
    padrão `Movimentação N - dd/mm/aaaa - título - fls. P` (aceita também `evento`, `mov.`,
    `seq.`, `pág.`). A primeira página precisa de ao menos duas linhas reconhecidas.

    Args:
        textos: Texto das páginas, em ordem (consumido só até o fim do índice).

    Returns:
        Quantidade de páginas de índice e as entradas lidas.
    """
    entradas: list[dict[str, Any]] = []
    paginas = 0
    for posicao, texto in enumerate(textos):
        if posicao >= MAX_PAGINAS_INDICE:
            break
        da_pagina = linhas_de_indice(texto)
        if not _e_pagina_de_indice(texto, len(da_pagina), primeira=posicao == 0):
            break
        entradas.extend(da_pagina)
        paginas += 1
    return paginas, entradas


def fronteiras_do_indice(entradas: Sequence[dict[str, Any]], arquivo: str) -> list[dict[str, Any]]:
    """Fronteiras candidatas a partir das entradas do índice.

    Args:
        entradas: Entradas de `ler_indice`.
        arquivo: Nome do arquivo físico.

    Returns:
        Fronteiras `{peca, titulo, data, arquivo, pagina, fonte}`.
    """
    return [
        {
            "peca": entrada["numero"],
            "titulo": entrada["titulo"],
            "data": entrada["data"],
            "arquivo": arquivo,
            "pagina": entrada["pagina"],
            "fonte": "indice",
        }
        for entrada in entradas
    ]


def fronteiras_do_sumario(toc: Sequence[Sequence[Any]], arquivo: str) -> list[dict[str, Any]]:
    """Fronteiras candidatas a partir dos bookmarks de primeiro nível.

    Args:
        toc: Sumário `[nivel, titulo, pagina]` (página 1-based; < 1 = sem destino).
        arquivo: Nome do arquivo físico.

    Returns:
        Fronteiras `{peca, titulo, data, arquivo, pagina, fonte}`.
    """
    primeiros = [item for item in toc if int(item[0]) == 1 and int(item[2]) >= 1]
    return [
        {
            "peca": ordem,
            "titulo": str(item[1]),
            "data": data_no_texto(str(item[1])),
            "arquivo": arquivo,
            "pagina": int(item[2]),
            "fonte": "bookmark",
        }
        for ordem, item in enumerate(primeiros, start=1)
    ]


def fronteiras_do_manifesto(entradas: Sequence[tuple[str, int]]) -> list[dict[str, Any]]:
    """Fronteiras candidatas do ZIP: cada entrada começa uma peça.

    Args:
        entradas: Pares `(nome, páginas)` na ordem do manifesto.

    Returns:
        Fronteiras com a página inicial na numeração contínua do arquivo e dentro da entrada.
    """
    fronteiras = []
    inicio = 1
    for ordem, (nome, paginas) in enumerate(entradas, start=1):
        fronteiras.append(
            {
                "peca": ordem,
                "titulo": PurePosixPath(nome).stem,
                "data": data_no_nome(nome),
                "arquivo": nome,
                "pagina": 1,
                "pagina_continua": inicio,
                "fonte": "manifesto",
            }
        )
        inicio += paginas
    return fronteiras


def cenario_pdf(tem_bookmarks: bool, tem_indice: bool) -> CenarioArquivo:
    """Cenário de um PDF único.

    Args:
        tem_bookmarks: Se o sumário tem entradas.
        tem_indice: Se há índice de movimentações no início.

    Returns:
        Cenário diagnosticado.
    """
    if tem_bookmarks and tem_indice:
        return CenarioArquivo.PDF_COM_BOOKMARKS_E_INDICE
    if tem_bookmarks:
        return CenarioArquivo.PDF_COM_BOOKMARKS
    if tem_indice:
        return CenarioArquivo.PDF_COM_INDICE
    return CenarioArquivo.PDF_LISO


def _suspeito(descartados: Sequence[dict[str, Any]]) -> bool:
    return any(item.get("categorias") for item in descartados)


def diagnosticar_pdf(arquivo_id: UUID, nome: str, inspecao: dict[str, Any]) -> DiagnosticoArquivo:
    """Diagnóstico de um PDF único a partir da inspeção do sandbox.

    Args:
        arquivo_id: Arquivo.
        nome: Nome do arquivo físico (vai para as fronteiras).
        inspecao: Resultado do lote (`paginas`, `toc`, `indice`, `paginas_indice`).

    Returns:
        Diagnóstico com cenário, sinais e fronteiras de origem.
    """
    toc = list(inspecao.get("toc", []))
    descartados = [dict(i) | {"entrada": nome} for i in inspecao.get("metadados", [])]
    indice = list(inspecao.get("indice", []))
    cenario = cenario_pdf(bool(toc), bool(indice))
    fronteiras = fronteiras_do_indice(indice, nome) + fronteiras_do_sumario(toc, nome)
    sinais = {
        "entradas": 1,
        "bookmarks": len(toc),
        "linhas_indice": len(indice),
        "paginas_indice": int(inspecao.get("paginas_indice", 0)),
        "metadado_suspeito": _suspeito(descartados),
    }
    return DiagnosticoArquivo(
        arquivo_id=arquivo_id,
        cenario=cenario,
        total_paginas=int(inspecao.get("paginas", 0)),
        tem_indice=cenario is not CenarioArquivo.PDF_LISO,
        sinais=sinais,
        fronteiras_origem=fronteiras,
        metadados_descartados=descartados,
    )


def diagnosticar_zip(
    arquivo_id: UUID, entradas: Sequence[tuple[str, dict[str, Any]]]
) -> DiagnosticoArquivo:
    """Diagnóstico de um ZIP a partir das entradas inspecionadas.

    Um ZIP com uma única entrada é diagnosticado pelo PDF que contém; com duas ou mais, é
    `zip_por_peca` e cada entrada é uma fronteira candidata.

    Args:
        arquivo_id: Arquivo (o ZIP).
        entradas: Pares `(nome da entrada, resultado da inspeção)` na ordem do manifesto.

    Returns:
        Diagnóstico com cenário, sinais e fronteiras de origem.
    """
    if len(entradas) == 1:
        nome, inspecao = entradas[0]
        unico = diagnosticar_pdf(arquivo_id, nome, inspecao)
        return unico.model_copy(update={"sinais": unico.sinais | {"zip_com_um_pdf": True}})
    paginas = [(nome, int(inspecao.get("paginas", 0))) for nome, inspecao in entradas]
    datados = sum(data_no_nome(nome) is not None for nome, _ in entradas)
    descartados = [
        dict(i) | {"entrada": nome}
        for nome, inspecao in entradas
        for i in inspecao.get("metadados", [])
    ]
    return DiagnosticoArquivo(
        arquivo_id=arquivo_id,
        cenario=CenarioArquivo.ZIP_POR_PECA,
        total_paginas=sum(p for _, p in paginas),
        tem_indice=True,
        sinais={
            "entradas": len(entradas),
            "nomes_datados": datados,
            "metadado_suspeito": _suspeito(descartados),
        },
        fronteiras_origem=fronteiras_do_manifesto(paginas),
        metadados_descartados=descartados,
    )
