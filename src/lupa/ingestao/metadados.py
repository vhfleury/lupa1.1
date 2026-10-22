"""Metadados, anotações e campos do PDF (Etapa 4D.2); roda só dentro do sandbox.

Info dict, pacote XMP, bookmarks, nomes de arquivos embutidos, anotações e campos de
formulário nunca entram no texto da página. São lidos só para registro: cada valor vira um item
com origem, chave, página (quando houver), hash, tamanho e categorias de instrução (4D.5). O
valor em si não sai do filho do sandbox. O XMP é lido por expressão regular, sem parser XML
(nenhuma expansão de entidade sobre conteúdo não confiável).
"""

import re
from collections.abc import Iterable
from typing import Any

import fitz

from lupa.dominio.esquemas import calcular_hash
from lupa.ingestao.saneamento_pagina import categorias_de

MAX_ITENS = 500
CHAVES_INFO = ("title", "author", "subject", "keywords", "creator", "producer")
CHAVES_ANOTACAO = ("content", "title", "subject")
PADRAO_TEXTO_XML = re.compile(r">([^<>]+)<")


def item(origem: str, chave: str, valor: str, pagina: int | None = None) -> dict[str, Any]:
    """Registro de um valor descartado (sem o valor).

    Args:
        origem: `info`, `xmp`, `bookmark`, `arquivo_embutido`, `anotacao` ou `campo`.
        chave: Nome do campo.
        valor: Valor lido.
        pagina: Página (1-based) quando o valor pertence a uma.

    Returns:
        `{origem, chave, pagina, hash, caracteres, categorias}`.
    """
    return {
        "origem": origem,
        "chave": chave,
        "pagina": pagina,
        "hash": calcular_hash(valor),
        "caracteres": len(valor),
        "categorias": categorias_de(valor),
    }


def textos_xmp(xmp: str) -> list[str]:
    """Textos dos nós do pacote XMP.

    Args:
        xmp: Pacote XMP.

    Returns:
        Textos não vazios.
    """
    return [t.strip() for t in PADRAO_TEXTO_XML.findall(xmp) if t.strip()]


def _documento(documento: fitz.Document) -> Iterable[dict[str, Any]]:
    metadados = documento.metadata or {}
    for chave in CHAVES_INFO:
        valor = str(metadados.get(chave) or "").strip()
        if valor:
            yield item("info", chave, valor)
    for posicao, texto in enumerate(textos_xmp(documento.get_xml_metadata() or "")):
        yield item("xmp", f"no_{posicao}", texto)
    for posicao, entrada in enumerate(documento.get_toc(simple=True)):
        yield item("bookmark", f"entrada_{posicao}", str(entrada[1]))
    for nome in documento.embfile_names():
        yield item("arquivo_embutido", "nome", str(nome))


def da_pagina(pagina: fitz.Page, numero: int) -> list[dict[str, Any]]:
    """Anotações e campos de formulário de uma página.

    Args:
        pagina: Página aberta.
        numero: Número da página (1-based).

    Returns:
        Itens descartados.
    """
    itens = []
    for anotacao in pagina.annots():
        info = anotacao.info or {}
        for chave in CHAVES_ANOTACAO:
            valor = str(info.get(chave) or "").strip()
            if valor:
                itens.append(item("anotacao", chave, valor, numero))
    for campo in pagina.widgets():
        for chave, valor in (("nome", campo.field_name), ("valor", campo.field_value)):
            texto = str(valor or "").strip()
            if texto:
                itens.append(item("campo", chave, texto, numero))
    return itens


def do_documento(documento: fitz.Document) -> list[dict[str, Any]]:
    """Metadados do documento (sem anotações nem campos).

    Args:
        documento: Documento aberto.

    Returns:
        Itens descartados, no máximo `MAX_ITENS`.
    """
    itens = []
    for registro in _documento(documento):
        itens.append(registro)
        if len(itens) >= MAX_ITENS:
            break
    return itens


def coletar(documento: fitz.Document) -> list[dict[str, Any]]:
    """Metadados do documento e anotações e campos de todas as páginas.

    Args:
        documento: Documento aberto.

    Returns:
        Itens descartados, no máximo `MAX_ITENS`.
    """
    itens = do_documento(documento)
    for numero, pagina in enumerate(documento, start=1):
        if len(itens) >= MAX_ITENS:
            break
        itens += da_pagina(pagina, numero)
    return itens[:MAX_ITENS]


def suspeito(itens: Iterable[dict[str, Any]]) -> bool:
    """Se algum item tem padrão de instrução.

    Args:
        itens: Itens descartados.

    Returns:
        True se houver categoria em algum item.
    """
    return any(i["categorias"] for i in itens)
