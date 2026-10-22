"""Métricas da pipeline contra o gabarito: fronteiras, tipos, eventos, CER e tempo.

Definições:

- **Fronteira de peça**: folha em que uma peça começa. Precisão = inícios previstos corretos /
  inícios previstos; recall = inícios previstos corretos / inícios do gabarito. Início previsto
  numa página que não é conteúdo (índice) conta como erro.
- **Tipo e origem**: para cada peça do gabarito, a peça prevista que começa na mesma folha; sem
  ela, conta como erro. Acurácia = acertos / peças do gabarito.
- **Data da peça**: para cada peça do gabarito, a peça prevista que começa na mesma folha
  com a mesma data; peça sem data prevista conta como erro (nunca como acerto).
- **Eventos**: casamento por (tipo, valor, folha), um para um. Precisão e recall usuais.
- **Datas**: o mesmo casamento restrito aos eventos cujo tipo é data (``data_*``). A precisão
  é a meta da 4F.9 (sobre as datas extraídas).
- **CER**: distância de Levenshtein entre textos com espaços normalizados (sequências de espaço
  e quebra viram um espaço), somada por grupo e dividida pelo total de caracteres do gabarito.
  Agrupado por composição da folha e por nível de degradação. Páginas sem texto na saída
  contam com CER 1 (tudo faltando).
- **Tempo por mil páginas**: ``tempo_segundos`` da saída / folhas de conteúdo x 1000.
"""

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel

from lupa.sinteticos.gabarito import Gabarito
from lupa.sinteticos.saida_pipeline import (
    EventoSaida,
    PaginaSaida,
    PecaSaida,
    RefPagina,
    SaidaPipeline,
)


class Taxa(BaseModel):
    """Precisão, recall e F1 com as contagens."""

    precisao: float
    recall: float
    f1: float
    corretos: int
    previstos: int
    esperados: int


class Acuracia(BaseModel):
    """Acurácia com as contagens."""

    acuracia: float
    acertos: int
    total: int


class Cer(BaseModel):
    """CER de um grupo de páginas."""

    cer: float
    paginas: int
    caracteres: int
    distancia: int


class Relatorio(BaseModel):
    """Resultado da medição."""

    processo: str
    cenario: str
    folhas: int
    fronteira: Taxa
    tipo_peca: Acuracia
    origem_peca: Acuracia
    data_peca: Acuracia | None = None
    tipo_pagina: Acuracia
    eventos: Taxa
    datas: Taxa | None = None
    cer_por_composicao: dict[str, Cer]
    cer_por_degradacao: dict[str, Cer]
    tempo_por_mil_paginas: float | None


def levenshtein(a: str, b: str) -> int:
    """Distância de edição (inserção, remoção, substituição), em Python puro.

    Prefixo e sufixo comuns são descartados antes da programação dinâmica.

    Args:
        a: Primeiro texto.
        b: Segundo texto.

    Returns:
        Número mínimo de edições.
    """
    inicio = 0
    while inicio < min(len(a), len(b)) and a[inicio] == b[inicio]:
        inicio += 1
    a, b = a[inicio:], b[inicio:]
    while a and b and a[-1] == b[-1]:
        a, b = a[:-1], b[:-1]
    if len(a) < len(b):
        a, b = b, a
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def normalizar(texto: str) -> str:
    """Colapsa espaços e quebras de linha em um espaço.

    Args:
        texto: Texto.

    Returns:
        Texto normalizado.
    """
    return " ".join(texto.split())


def mapa_folhas(gabarito: Gabarito) -> dict[tuple[str, int], int | None]:
    """Mapeia (arquivo, página física) para a folha de conteúdo.

    Args:
        gabarito: Gabarito do cenário.

    Returns:
        Dicionário; ``None`` para páginas que não são conteúdo.
    """
    return {
        (arquivo.nome, posicao): folha
        for arquivo in gabarito.arquivos
        for posicao, folha in enumerate(arquivo.folhas, start=1)
    }


def _taxa(corretos: int, previstos: int, esperados: int) -> Taxa:
    precisao = corretos / previstos if previstos else 0.0
    recall = corretos / esperados if esperados else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return Taxa(
        precisao=precisao, recall=recall, f1=f1, corretos=corretos, previstos=previstos,
        esperados=esperados,
    )  # fmt: skip


def _acuracia(acertos: int, total: int) -> Acuracia:
    return Acuracia(acuracia=acertos / total if total else 0.0, acertos=acertos, total=total)


class _Medidor:
    def __init__(self, gabarito: Gabarito, saida: SaidaPipeline) -> None:
        self.gabarito = gabarito
        self.saida = saida
        self.mapa = mapa_folhas(gabarito)

    def folha(self, ref: RefPagina) -> int | None:
        return self.mapa.get((ref.arquivo, ref.pagina))

    def fronteira(self) -> Taxa:
        esperados = {p.pagina_inicial for p in self.gabarito.pecas}
        previstos = [self.folha(p.inicio) for p in self.saida.pecas]
        corretos = len(esperados & {f for f in previstos if f is not None})
        return _taxa(corretos, len(previstos), len(esperados))

    def tipo_e_origem(self) -> tuple[Acuracia, Acuracia]:
        por_inicio = {self.folha(p.inicio): p for p in self.saida.pecas}
        tipos = origens = 0
        for peca in self.gabarito.pecas:
            prevista = por_inicio.get(peca.pagina_inicial)
            tipos += prevista is not None and prevista.tipo == peca.tipo
            origens += prevista is not None and prevista.origem == peca.origem
        total = len(self.gabarito.pecas)
        return _acuracia(tipos, total), _acuracia(origens, total)

    def data_peca(self) -> Acuracia:
        por_inicio = {self.folha(p.inicio): p for p in self.saida.pecas}
        acertos = sum(
            (prevista := por_inicio.get(peca.pagina_inicial)) is not None
            and prevista.data == peca.data
            for peca in self.gabarito.pecas
        )
        return _acuracia(acertos, len(self.gabarito.pecas))

    def tipo_pagina(self) -> Acuracia:
        previstas = {self.folha(p.ref): p.tipo for p in self.saida.paginas}
        acertos = sum(previstas.get(p.numero) == p.tipo for p in self.gabarito.paginas)
        return _acuracia(acertos, len(self.gabarito.paginas))

    def eventos(self, so_datas: bool = False) -> Taxa:
        def chave(tipo: str, valor: Any, folha: int | None) -> str:
            return json.dumps([tipo, valor, folha], sort_keys=True, ensure_ascii=False)

        def incluir(tipo: str) -> bool:
            return not so_datas or str(tipo).startswith("data_")

        esperados = Counter(
            chave(e.tipo, e.valor, e.pagina) for e in self.gabarito.eventos if incluir(e.tipo)
        )
        previstos = Counter(
            chave(e.tipo, e.valor, self.folha(e.ref)) for e in self.saida.eventos if incluir(e.tipo)
        )
        corretos = sum((esperados & previstos).values())
        return _taxa(corretos, sum(previstos.values()), sum(esperados.values()))

    def cer(self) -> tuple[dict[str, Cer], dict[str, Cer]]:
        textos = {self.folha(p.ref): p.texto for p in self.saida.paginas}
        grupos: dict[str, list[int]] = {}
        niveis: dict[str, list[int]] = {}
        for pagina in self.gabarito.paginas:
            esperado = normalizar(pagina.texto)
            distancia = levenshtein(esperado, normalizar(textos.get(pagina.numero, "")))
            for destino, chave in ((grupos, pagina.composicao.value), (niveis, pagina.degradacao)):
                if chave is None:
                    continue
                acumulado = destino.setdefault(str(chave), [0, 0, 0])
                acumulado[0] += 1
                acumulado[1] += len(esperado)
                acumulado[2] += distancia
        return _consolidar(grupos), _consolidar(niveis)


def _consolidar(grupos: dict[str, list[int]]) -> dict[str, Cer]:
    return {
        chave: Cer(
            cer=(d / c) if c else 0.0 if d == 0 else 1.0, paginas=n, caracteres=c, distancia=d
        )
        for chave, (n, c, d) in sorted(grupos.items())
    }


def medir(gabarito: Gabarito, saida: SaidaPipeline) -> Relatorio:
    """Compara a saída da pipeline com o gabarito.

    Args:
        gabarito: Gabarito do cenário medido.
        saida: Saída da pipeline para o mesmo arquivo.

    Returns:
        Relatório de métricas.
    """
    medidor = _Medidor(gabarito, saida)
    tipo, origem = medidor.tipo_e_origem()
    cer_composicao, cer_degradacao = medidor.cer()
    folhas = len(gabarito.paginas)
    tempo = saida.tempo_segundos / folhas * 1000 if saida.tempo_segundos is not None else None
    return Relatorio(
        processo=gabarito.processo.numero_cnj, cenario=gabarito.processo.cenario.value,
        folhas=folhas, fronteira=medidor.fronteira(), tipo_peca=tipo, origem_peca=origem,
        data_peca=medidor.data_peca(),
        tipo_pagina=medidor.tipo_pagina(), eventos=medidor.eventos(),
        datas=medidor.eventos(so_datas=True),
        cer_por_composicao=cer_composicao, cer_por_degradacao=cer_degradacao,
        tempo_por_mil_paginas=tempo,
    )  # fmt: skip


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f}%"


def para_markdown(relatorio: Relatorio) -> str:
    """Formata o relatório em Markdown.

    Args:
        relatorio: Relatório de métricas.

    Returns:
        Texto Markdown.
    """
    r = relatorio
    linhas = [
        f"# Medição: processo {r.processo} ({r.cenario}, {r.folhas} folhas)",
        "",
        "| Métrica | Valor | Detalhe |",
        "| --- | --- | --- |",
        f"| Fronteira: precisão | {_pct(r.fronteira.precisao)} | {r.fronteira.corretos}/"
        f"{r.fronteira.previstos} |",
        f"| Fronteira: recall | {_pct(r.fronteira.recall)} | {r.fronteira.corretos}/"
        f"{r.fronteira.esperados} |",
        f"| Tipo de peça | {_pct(r.tipo_peca.acuracia)} | {r.tipo_peca.acertos}/"
        f"{r.tipo_peca.total} |",
        f"| Origem da peça | {_pct(r.origem_peca.acuracia)} | {r.origem_peca.acertos}/"
        f"{r.origem_peca.total} |",
        *(
            [
                f"| Data da peça | {_pct(r.data_peca.acuracia)} | {r.data_peca.acertos}/"
                f"{r.data_peca.total} |"
            ]
            if r.data_peca is not None
            else []
        ),
        f"| Tipo de página | {_pct(r.tipo_pagina.acuracia)} | {r.tipo_pagina.acertos}/"
        f"{r.tipo_pagina.total} |",
        f"| Eventos: precisão | {_pct(r.eventos.precisao)} | {r.eventos.corretos}/"
        f"{r.eventos.previstos} |",
        f"| Eventos: recall | {_pct(r.eventos.recall)} | {r.eventos.corretos}/"
        f"{r.eventos.esperados} |",
        *(
            [
                f"| Datas: precisão | {_pct(r.datas.precisao)} | {r.datas.corretos}/"
                f"{r.datas.previstos} |",
                f"| Datas: recall | {_pct(r.datas.recall)} | {r.datas.corretos}/"
                f"{r.datas.esperados} |",
            ]
            if r.datas is not None
            else []
        ),
        "| Tempo por mil páginas | "
        + (
            f"{r.tempo_por_mil_paginas:.1f} s"
            if r.tempo_por_mil_paginas is not None
            else "não informado"
        )
        + " | |",
        "",
    ]
    for titulo, grupos in (
        ("composição de página", r.cer_por_composicao),
        ("nível de degradação", r.cer_por_degradacao),
    ):
        linhas += [f"## CER por {titulo}", "", "| Grupo | CER | Páginas | Caracteres |"]
        linhas += ["| --- | --- | --- | --- |"]
        linhas += [
            f"| {k} | {_pct(c.cer)} | {c.paginas} | {c.caracteres} |" for k, c in grupos.items()
        ]
        linhas.append("")
    return "\n".join(linhas) + "\n"


def saida_perfeita(gabarito: Gabarito) -> SaidaPipeline:
    """Monta a saída que uma pipeline perfeita produziria (referência para 100%).

    Args:
        gabarito: Gabarito do cenário.

    Returns:
        Saída com peças, páginas (texto visível) e eventos do gabarito.
    """
    refs = {
        folha: RefPagina(arquivo=a, pagina=p)
        for (a, p), folha in mapa_folhas(gabarito).items()
        if folha
    }
    return SaidaPipeline(
        pecas=tuple(
            PecaSaida(
                tipo=p.tipo,
                origem=p.origem,
                inicio=refs[p.pagina_inicial],
                fim=refs[p.pagina_final],
                data=p.data,
            )
            for p in gabarito.pecas
        ),
        paginas=tuple(
            PaginaSaida(ref=refs[p.numero], tipo=p.tipo, texto=p.texto) for p in gabarito.paginas
        ),
        eventos=tuple(
            EventoSaida(tipo=e.tipo, valor=e.valor, ref=refs[e.pagina], trecho=e.trecho)
            for e in gabarito.eventos
        ),
    )
