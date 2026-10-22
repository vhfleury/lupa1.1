"""Sinais de fronteira de peça por página (Etapa 4E.1).

Funções puras sobre o texto e as coordenadas já gravados em `pagina` (nada abre o PDF). O
cabeçalho e o rodapé que se repetem em quase todas as folhas (nome do tribunal, número do
processo, "Fls. N", código de autenticação, marca d'água) são descobertos no próprio documento
por `linhas_repetidas` e ficam fora do "corpo" da página, onde se procuram título, protocolo
e assinatura. Os sinais gravados em `pagina.sinais_fronteira`:

- `vazia`: página sem texto.
- `cabecalho`: máscara das duas primeiras linhas (dígitos viram `#`), comparada com a anterior.
- `titulo`, `titulo_tipo`, `titulo_secao`, `titulo_linha`: título de peça reconhecido entre as
  primeiras linhas do corpo (lista versionada em `dados/titulos_peca.yaml`).
- `numero_folha` e `reinicio_numeracao`: "fl. 1", "folha 1", "página 1 de N".
- `assinatura_fim`: linha de assinatura ("assinado eletronicamente por ...", tolerante a erro
  de OCR) entre as últimas linhas do corpo; o rodapé "assinado digitalmente. Código de
  autenticação" que se repete em toda folha não conta.
- `protocolo_topo`: protocolo, juntada, recebimento ou data nas primeiras linhas do corpo.
- `altura_linha`, `margem_esquerda`, `colunas`: fonte dominante (altura mediana das linhas) e
  layout, a partir das caixas das linhas.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache
from importlib.resources import files
from statistics import median
from typing import Any

import yaml

LINHAS_TOPO = 4
LINHAS_FIM = 6
MAX_TITULO = 70
SEMELHANCA_TITULO = 0.86
SEMELHANCA_REPETIDA = 0.8
FRACAO_REPETIDA = 0.3
MIN_PAGINAS_REPETIDA = 3
FRACAO_COLUNA = 0.25
LINHAS_ZONA = 3

PADRAO_DATA = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
PADRAO_POR = re.compile(r"\b(?:por|or)\b")
PADRAO_FOLHA = re.compile(r"^(?:fls?|folhas?|f)\s*\.?\s*(\d{1,6})\s*$")
PADRAO_PAGINA_DE = re.compile(r"\bpagina\s+(\d{1,6})\s+de\s+\d{1,6}\b")
PADRAO_PROTOCOLO = re.compile(
    r"\b(?:protocol\w*|recebid[oa] em|juntad[oa] em|autuad[oa] em)\b|^\d{2}/\d{2}/\d{4}"
)
PADRAO_HEX = re.compile(r"\b(?=\w*\d)\w{12,}\b")
PADRAO_DIGITOS = re.compile(r"\d+")


@dataclass(frozen=True)
class Titulo:
    """Título de peça da lista versionada.

    Attributes:
        titulo: Forma canônica (normalizada).
        tipo: Tipo de peça sugerido (None quando o título não decide, como "DECISÃO").
        secao: Se também aparece como seção dentro de outra peça.
        variacoes: Formas normalizadas aceitas.
    """

    titulo: str
    tipo: str | None
    secao: bool
    variacoes: tuple[str, ...]


@dataclass(frozen=True)
class ListaTitulos:
    """Lista de títulos com a versão do arquivo."""

    versao: str
    titulos: tuple[Titulo, ...]


def normalizar(texto: str) -> str:
    """Maiúsculas, sem acento e sem pontuação, com espaços simples.

    Args:
        texto: Texto livre.

    Returns:
        Texto normalizado.
    """
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9/ ]+", " ", sem_acento)
    return " ".join(limpo.upper().split())


def mascara(linha: str) -> str:
    """Forma da linha para comparar cabeçalhos e rodapés: números e códigos viram `#`.

    Args:
        linha: Linha de texto.

    Returns:
        Máscara normalizada.
    """
    return PADRAO_DIGITOS.sub("#", normalizar(PADRAO_HEX.sub("#", linha)))


def titulos_de(dados: dict[str, Any]) -> ListaTitulos:
    """Monta a lista de títulos a partir do YAML lido.

    Args:
        dados: Conteúdo do YAML.

    Returns:
        Lista de títulos.
    """
    titulos = tuple(
        Titulo(
            normalizar(item["titulo"]),
            item.get("tipo"),
            bool(item.get("secao", False)),
            tuple(normalizar(v) for v in item["variacoes"]),
        )
        for item in dados["titulos"]
    )
    return ListaTitulos(str(dados["versao"]), titulos)


@cache
def titulos_padrao() -> ListaTitulos:
    """Lista de títulos versionada em `dados/titulos_peca.yaml`."""
    texto = files("lupa.ingestao").joinpath("dados/titulos_peca.yaml").read_text("utf-8")
    return titulos_de(yaml.safe_load(texto))


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def _zonas(linhas: Sequence[str]) -> list[str]:
    if len(linhas) <= 2 * LINHAS_ZONA:
        return list(linhas)
    return list(linhas[:LINHAS_ZONA]) + list(linhas[-LINHAS_ZONA:])


def e_assinatura(linha: str) -> bool:
    """Se a linha é a assinatura de uma peça, com tolerância a erro de OCR.

    Exige "assinad..." e um indício do resto da fórmula ("eletr...", "por" ou uma data) e
    recusa o rodapé de autenticação ("código", "autenticação").

    Args:
        linha: Linha de texto.

    Returns:
        Verdadeiro para linha de assinatura.
    """
    forma = normalizar(linha).lower()
    if "assinad" not in forma or "autentic" in forma or "codigo" in forma:
        return False
    return "eletr" in forma or bool(PADRAO_POR.search(forma) or PADRAO_DATA.search(forma))


def linhas_repetidas(textos: Iterable[str]) -> frozenset[str]:
    """Máscaras de linha que se repetem em boa parte das páginas (cabeçalho, rodapé).

    Só contam as três primeiras e as três últimas linhas de cada página: texto repetido no
    meio do corpo (fórmulas, parágrafos padronizados) não é cabeçalho nem rodapé.

    Args:
        textos: Texto de cada página do arquivo.

    Returns:
        Máscaras presentes em ao menos 30% das páginas com texto (mínimo de três páginas).
    """
    contagem: Counter[str] = Counter()
    paginas = 0
    for texto in textos:
        mascaras = {mascara(linha) for linha in _zonas(_linhas(texto))}
        mascaras.discard("")
        if mascaras:
            paginas += 1
            contagem.update(mascaras)
    minimo = max(MIN_PAGINAS_REPETIDA, FRACAO_REPETIDA * paginas)
    return frozenset(m for m, n in contagem.items() if n >= minimo)


def _repetida(linha: str, repetidas: frozenset[str]) -> bool:
    forma = mascara(linha)
    if not forma or forma in repetidas:
        return True
    for r in repetidas:
        if abs(len(forma) - len(r)) > 0.3 * len(r):
            continue
        comparador = SequenceMatcher(None, forma, r)
        if comparador.quick_ratio() >= SEMELHANCA_REPETIDA <= comparador.ratio():
            return True
    return False


def corpo(texto: str, repetidas: frozenset[str]) -> list[str]:
    """Linhas da página sem cabeçalho e rodapé repetidos.

    Só as três primeiras e as três últimas linhas são conferidas contra as repetidas.

    Args:
        texto: Texto da página.
        repetidas: Máscaras de `linhas_repetidas`.

    Returns:
        Linhas do corpo, em ordem.
    """
    linhas = _linhas(texto)
    total = len(linhas)
    return [
        linha
        for posicao, linha in enumerate(linhas)
        if LINHAS_ZONA <= posicao < total - LINHAS_ZONA or not _repetida(linha, repetidas)
    ]


def reconhecer_titulo(linha: str, lista: ListaTitulos) -> Titulo | None:
    """Título de peça que a linha representa, se houver.

    Args:
        linha: Linha candidata.
        lista: Títulos conhecidos.

    Returns:
        O título (igual ou parecido, por semelhança ≥ 0,86), ou None.
    """
    forma = normalizar(linha)
    if not forma or len(forma) > MAX_TITULO:
        return None
    melhor: tuple[float, Titulo | None] = (0.0, None)
    for titulo in lista.titulos:
        for variacao in titulo.variacoes:
            if forma == variacao:
                return titulo
            nota = SequenceMatcher(None, forma, variacao).ratio()
            if nota > melhor[0]:
                melhor = (nota, titulo)
    return melhor[1] if melhor[0] >= SEMELHANCA_TITULO else None


def _titulo(linhas: Sequence[str], lista: ListaTitulos) -> dict[str, Any]:
    for posicao, linha in enumerate(linhas[:LINHAS_TOPO]):
        titulo = reconhecer_titulo(linha, lista)
        if titulo is not None:
            return {
                "titulo": titulo.titulo,
                "titulo_tipo": titulo.tipo,
                "titulo_secao": titulo.secao,
                "titulo_linha": posicao,
            }
    return {"titulo": None, "titulo_tipo": None, "titulo_secao": False, "titulo_linha": None}


def _numero_folha(linhas: Sequence[str]) -> tuple[int | None, bool]:
    for linha in list(linhas[:3]) + list(linhas[-3:]):
        forma = normalizar(linha).lower()
        achado = PADRAO_FOLHA.match(forma) or PADRAO_PAGINA_DE.search(forma)
        if achado:
            numero = int(achado.group(1))
            return numero, numero == 1
    return None, False


def _caixas(coordenadas: dict[str, Any]) -> list[list[float]]:
    if "blocos" in coordenadas:
        return [list(linha["bbox"]) for bloco in coordenadas["blocos"] for linha in bloco["linhas"]]
    return [list(linha["bbox"]) for linha in coordenadas.get("linhas", [])]


def _layout(coordenadas: dict[str, Any]) -> dict[str, Any]:
    caixas = [c for c in _caixas(coordenadas) if c[2] > c[0] and c[3] > c[1]]
    if not caixas:
        return {"altura_linha": None, "margem_esquerda": None, "colunas": 0}
    direita = max(c[2] for c in caixas)
    meio = min(c[0] for c in caixas) + (direita - min(c[0] for c in caixas)) / 2
    na_direita = sum(1 for c in caixas if c[0] > meio - 5)
    estreitas = sum(1 for c in caixas if c[2] < meio + 5)
    duas = na_direita >= FRACAO_COLUNA * len(caixas) and estreitas >= FRACAO_COLUNA * len(caixas)
    return {
        "altura_linha": round(median(c[3] - c[1] for c in caixas) * 2) / 2,
        "margem_esquerda": round(median(c[0] for c in caixas) / 5) * 5,
        "colunas": 2 if duas else 1,
    }


def medir_sinais_fronteira(
    texto: str,
    coordenadas: dict[str, Any],
    repetidas: frozenset[str],
    lista: ListaTitulos | None = None,
) -> dict[str, Any]:
    """Sinais de fronteira de uma página.

    Args:
        texto: Texto final da página.
        coordenadas: Coordenadas gravadas (`blocos` do nativo ou `linhas` do OCR e da fusão).
        repetidas: Máscaras de cabeçalho e rodapé do arquivo (`linhas_repetidas`).
        lista: Títulos conhecidos (padrão: `titulos_padrao()`).

    Returns:
        Sinais da página (ver docstring do módulo), com `versao_titulos`.
    """
    lista = lista or titulos_padrao()
    todas = _linhas(texto)
    if not todas:
        return {"vazia": True, "versao_titulos": lista.versao}
    linhas = corpo(texto, repetidas)
    topo = [normalizar(linha).lower() for linha in linhas[:LINHAS_TOPO]]
    numero, reinicio = _numero_folha(todas)
    return {
        "vazia": False,
        "versao_titulos": lista.versao,
        "cabecalho": " | ".join(mascara(linha) for linha in todas[:2]),
        **_titulo(linhas, lista),
        "numero_folha": numero,
        "reinicio_numeracao": reinicio,
        "assinatura_fim": any(e_assinatura(linha) for linha in linhas[-LINHAS_FIM:]),
        "protocolo_topo": any(PADRAO_PROTOCOLO.search(linha) for linha in topo),
        **_layout(coordenadas),
    }


def sinais_do_arquivo(paginas: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sinais de fronteira de todas as páginas de um arquivo, em ordem.

    Args:
        paginas: Páginas `{numero, texto, coordenadas}` em ordem.

    Returns:
        Um dicionário de sinais por página (com `tipo_pagina`), na mesma ordem.
    """
    repetidas = linhas_repetidas(str(p.get("texto") or "") for p in paginas)
    return [
        medir_sinais_fronteira(
            str(p.get("texto") or ""), dict(p.get("coordenadas") or {}), repetidas
        )
        | {"tipo_pagina": p.get("tipo")}
        for p in paginas
    ]
