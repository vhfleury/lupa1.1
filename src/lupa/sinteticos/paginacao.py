r"""Paginação: transforma as peças do roteiro em folhas com linhas posicionadas e offsets.

Cada folha tem cabeçalho repetido (igual em todas as peças), corpo e rodapé com número de folha
e código de autenticação falso. O texto da folha é a junção das linhas com ``\\n`` (formato de
``page.get_text()``), e as quebras de linha só acontecem em espaços simples, de modo que os
offsets de um trecho no parágrafo valem também na folha.
"""

import random
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import fitz

from lupa.sinteticos import identidades as ids
from lupa.sinteticos.roteiro import PecaPlano, Roteiro
from lupa.sinteticos.textos import Paragrafo

LARGURA = 595.0
ALTURA = 842.0
MARGEM_ESQUERDA = 70.0
MARGEM_DIREITA = 60.0
TOPO_CORPO = 112.0
LIMITE_CORPO = 752.0
TAMANHO = 10.5
ENTRELINHA = 14.5
ESPACO_PARAGRAFO = 7.0
VAO_COLUNAS = 18.0
LARGURA_UTIL = LARGURA - MARGEM_ESQUERDA - MARGEM_DIREITA
LARGURA_COLUNA = (LARGURA_UTIL - VAO_COLUNAS) / 2

FONTE = fitz.Font("tiro")
FONTE_NEGRITO = fitz.Font("tibo")


@dataclass(frozen=True)
class LinhaTexto:
    """Linha posicionada na folha.

    Attributes:
        texto: Conteúdo.
        x: Posição horizontal da linha de base.
        y: Posição vertical da linha de base.
        tamanho: Tamanho da fonte em pontos.
        negrito: Fonte em negrito.
        papel: ``cabecalho``, ``corpo``, ``assinatura`` ou ``rodape``.
    """

    texto: str
    x: float
    y: float
    tamanho: float
    negrito: bool
    papel: str


@dataclass(frozen=True)
class MarcaPagina:
    """Trecho marcado, com offsets no texto da folha.

    Attributes:
        rotulo: Tipo do evento ou ``injecao``.
        valor: Valor do evento (``None`` para injeção).
        inicio: Offset inicial.
        fim: Offset final.
    """

    rotulo: str
    valor: Any
    inicio: int
    fim: int


@dataclass
class PaginaPlano:
    """Folha paginada, ainda sem composição.

    Attributes:
        numero: Folha (1 a N).
        peca: Índice da peça (1 a M).
        linhas: Linhas na ordem de desenho.
        marcas: Trechos marcados.
        vazia: Verso em branco.
        capa: Capa de autuação.
        marca_dagua: Se leva marca d'água.
        duas_colunas: Corpo em duas colunas; a ordem das linhas é a ordem de leitura (coluna
            esquerda inteira, depois a direita).
    """

    numero: int
    peca: int
    linhas: list[LinhaTexto] = field(default_factory=list)
    marcas: list[MarcaPagina] = field(default_factory=list)
    vazia: bool = False
    capa: bool = False
    marca_dagua: bool = False
    duas_colunas: bool = False

    @property
    def texto(self) -> str:
        r"""Texto visível da folha, uma linha por ``\\n``."""
        return "".join(f"{linha.texto}\n" for linha in self.linhas)

    def _tamanho_atual(self) -> int:
        return sum(len(linha.texto) + 1 for linha in self.linhas)


@cache
def _largura_palavra(palavra: str, negrito: bool) -> float:
    fonte = FONTE_NEGRITO if negrito else FONTE
    return float(fonte.text_length(palavra, fontsize=1))


def quebrar(
    texto: str, tamanho: float, negrito: bool = False, largura_util: float = LARGURA_UTIL
) -> list[str]:
    r"""Quebra um parágrafo em linhas que cabem na largura útil, só em espaços simples.

    Args:
        texto: Parágrafo com espaços simples.
        tamanho: Tamanho da fonte.
        negrito: Fonte em negrito.
        largura_util: Largura disponível em pontos (a de uma coluna, no layout em duas).

    Returns:
        Linhas; ``"\\n".join(linhas)`` tem o mesmo tamanho do parágrafo.
    """
    largura = largura_util / tamanho
    espaco = _largura_palavra(" ", negrito)
    linhas: list[str] = []
    atual = ""
    ocupado = 0.0
    for palavra in texto.split(" "):
        medida = _largura_palavra(palavra, negrito)
        if atual and ocupado + espaco + medida > largura:
            linhas.append(atual)
            atual, ocupado = palavra, medida
        elif atual:
            atual, ocupado = f"{atual} {palavra}", ocupado + espaco + medida
        else:
            atual, ocupado = palavra, medida
    linhas.append(atual)
    return linhas


class _Paginador:
    def __init__(self, roteiro: Roteiro, rng: random.Random) -> None:
        self.numero_processo = roteiro.partes.numero
        self.rng = rng
        self.paginas: list[PaginaPlano] = []
        self.atual: PaginaPlano | None = None
        self.y = TOPO_CORPO
        self.coluna = 0
        self.duas_colunas = frozenset(roteiro.configuracao.duas_colunas)

    def abrir(self, peca: int, plano: PecaPlano) -> PaginaPlano:
        pagina = PaginaPlano(len(self.paginas) + 1, peca, capa=plano.capa)
        pagina.marca_dagua = plano.marca_dagua
        pagina.linhas.append(
            LinhaTexto(f"PODER JUDICIÁRIO - {ids.COMARCA.upper()}", MARGEM_ESQUERDA, 50, 9,
                       True, "cabecalho")
        )  # fmt: skip
        pagina.linhas.append(
            LinhaTexto(f"Vara Criminal - Processo nº {self.numero_processo}", MARGEM_ESQUERDA,
                       64, 9, False, "cabecalho")
        )  # fmt: skip
        self.paginas.append(pagina)
        self.atual = pagina
        self.y = TOPO_CORPO
        self.coluna = 0
        return pagina

    def fechar(self) -> None:
        pagina = self.atual
        if pagina is None:
            return
        pagina.linhas.append(
            LinhaTexto(f"Fls. {pagina.numero}", LARGURA - MARGEM_DIREITA - 40, 790, 9, False,
                       "rodape")
        )  # fmt: skip
        pagina.linhas.append(
            LinhaTexto(
                "Documento assinado digitalmente. Código de autenticação: "
                f"{ids.gerar_hash_falso(self.rng)}",
                MARGEM_ESQUERDA, 806, 7, False, "rodape",
            )
        )  # fmt: skip
        self.atual = None

    def _colunas(self, plano: PecaPlano) -> bool:
        return plano.tipo in self.duas_colunas and not plano.capa

    def _proxima_area(self, peca: int, plano: PecaPlano) -> None:
        if self._colunas(plano) and self.coluna == 0:
            self.coluna = 1
            self.y = TOPO_CORPO
            return
        self.fechar()
        self.abrir(peca, plano)

    def acrescentar(self, peca: int, plano: PecaPlano, paragrafo: Paragrafo) -> None:
        tamanho = 13.0 if paragrafo.papel == "titulo" or plano.capa else TAMANHO
        negrito = paragrafo.papel == "titulo"
        entrelinha = tamanho * 1.38
        colunas = self._colunas(plano)
        largura = LARGURA_COLUNA if colunas else LARGURA_UTIL
        linhas = quebrar(paragrafo.texto, tamanho, negrito, largura)
        if self.atual is None:
            self.abrir(peca, plano)
        if self.y + len(linhas) * entrelinha > LIMITE_CORPO and self.y > TOPO_CORPO:
            self._proxima_area(peca, plano)
        pagina = self.atual
        assert pagina is not None  # noqa: S101
        if self.y + len(linhas) * entrelinha > LIMITE_CORPO and paragrafo.marcas:
            raise ValueError("parágrafo com evento não cabe em uma folha")
        inicio = pagina._tamanho_atual()
        papel = "assinatura" if paragrafo.papel == "assinatura" else "corpo"
        pagina.duas_colunas = pagina.duas_colunas or colunas
        x = MARGEM_ESQUERDA + self.coluna * (LARGURA_COLUNA + VAO_COLUNAS)
        for texto in linhas:
            self.y += entrelinha
            pagina.linhas.append(LinhaTexto(texto, x, self.y, tamanho, negrito, papel))
        self.y += ESPACO_PARAGRAFO
        for marca in paragrafo.marcas:
            pagina.marcas.append(
                MarcaPagina(
                    marca.rotulo,
                    plano.valores.get(marca.rotulo),
                    inicio + marca.inicio,
                    inicio + marca.fim,
                )
            )

    def verso_branco(self, peca: int) -> None:
        self.paginas.append(PaginaPlano(len(self.paginas) + 1, peca, vazia=True))


def paginar(roteiro: Roteiro, rng: random.Random) -> list[PaginaPlano]:
    """Pagina todas as peças do roteiro; cada peça começa em folha nova.

    Args:
        roteiro: Roteiro do processo.
        rng: Gerador semeado (códigos de autenticação).

    Returns:
        Folhas em ordem.
    """
    paginador = _Paginador(roteiro, rng)
    for indice, plano in enumerate(roteiro.pecas, start=1):
        for paragrafo in plano.paragrafos:
            paginador.acrescentar(indice, plano, paragrafo)
        paginador.fechar()
        if plano.verso_branco:
            paginador.verso_branco(indice)
    return paginador.paginas
