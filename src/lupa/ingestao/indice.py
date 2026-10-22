"""Índice do processo: peças em ordem com tipo, origem, páginas, data e flags (Etapa 4E.7).

`montar_indice` é função pura sobre as páginas já extraídas de um arquivo e o diagnóstico:
calcula os sinais de fronteira (4E.1), separa as peças pelas regras (4E.2) ou pelas fronteiras
da origem conferidas pelo classificador (4E.3), classifica tipo e origem (4E.4, 4E.5), acha a
data com evidência (4E.6) e agrega as flags de saneamento das páginas de cada peça (4D.10).
As páginas do índice de movimentações (PDF com índice) não pertencem a peça nenhuma.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from lupa.dominio.enums import MetodoClassificacao, OrigemPeca, TipoPeca
from lupa.ingestao.classificacao import (
    classificar_origem,
    classificar_tipo,
    regras_classificacao_padrao,
)
from lupa.ingestao.data_peca import data_da_peca
from lupa.ingestao.fronteiras import (
    FORTE,
    FRACA,
    Fronteira,
    conferir_origem,
    regras_padrao,
    segmentar,
)
from lupa.ingestao.sinais_fronteira import (
    corpo,
    linhas_repetidas,
    sinais_do_arquivo,
    titulos_padrao,
)
from lupa.sinteticos.saida_pipeline import PecaSaida, RefPagina

FONTES_ORIGEM = ("manifesto", "bookmark", "indice")
CONFIANCA_ORIGEM = 0.95
CONFIANCA_ORIGEM_DIVERGENTE = 0.5
FATOR_FRACA = 0.5


@dataclass(frozen=True)
class PecaIndice:
    """Peça do índice, pronta para gravar em `peca`.

    Attributes:
        ordem: Posição no índice (1 a N).
        tipo: Tipo da peça.
        origem: Quem produziu.
        pagina_inicial: Primeira página (numeração contínua do arquivo).
        pagina_final: Última página.
        confianca: Menor confiança entre fronteira e tipo.
        data: Data da peça (None se não encontrada).
        tipo_data: O que a data representa.
        evidencia_data: `{pagina, inicio, fim, trecho, hash_trecho}` da data.
        flags: `peca` (fronteira_fraca, divergencia_fronteira, tipo_ambiguo,
            origem_desconhecida, data_ausente) e `paginas` (flags de saneamento somadas).
        classificacao: Detalhes (fronteira, tipo, origem, versões das regras).
        metodo: Sempre `regra` na classificação automática.
    """

    ordem: int
    tipo: TipoPeca
    origem: OrigemPeca
    pagina_inicial: int
    pagina_final: int
    confianca: float
    data: date | None
    tipo_data: str | None
    evidencia_data: dict[str, Any] | None
    flags: dict[str, Any]
    classificacao: dict[str, Any]
    metodo: MetodoClassificacao = MetodoClassificacao.REGRA


@dataclass
class ResultadoIndice:
    """Índice montado e o que foi medido no caminho.

    Attributes:
        pecas: Peças em ordem.
        sinais: Sinais de fronteira por página (mesma ordem das páginas recebidas).
        divergencias: Divergências entre origem e classificador (página em numeração do
            arquivo).
        fonte: `regras`, `manifesto`, `bookmark` ou `indice`.
    """

    pecas: list[PecaIndice] = field(default_factory=list)
    sinais: list[dict[str, Any]] = field(default_factory=list)
    divergencias: list[dict[str, Any]] = field(default_factory=list)
    fonte: str = "regras"


def _posicoes_origem(
    paginas: Sequence[dict[str, Any]], fronteiras_origem: Sequence[dict[str, Any]]
) -> tuple[str, list[tuple[int, dict[str, Any]]]]:
    por_numero = {int(p["numero"]): posicao for posicao, p in enumerate(paginas)}
    for fonte in FONTES_ORIGEM:
        entradas = [f for f in fronteiras_origem if f.get("fonte") == fonte]
        if not entradas:
            continue
        chave = "pagina_continua" if fonte == "manifesto" else "pagina"
        posicoes = [(por_numero[int(f[chave])], f) for f in entradas if int(f[chave]) in por_numero]
        return fonte, posicoes
    return "regras", []


def _discordancia_entre_origens(
    fronteiras_origem: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    conjuntos = {
        fonte: {int(f["pagina"]) for f in fronteiras_origem if f.get("fonte") == fonte}
        for fonte in ("bookmark", "indice")
    }
    if not conjuntos["bookmark"] or not conjuntos["indice"]:
        return []
    return [
        {"pagina": numero, "motivo": "origens_discordam", "pontuacao": None, "sinais": []}
        for numero in sorted(conjuntos["bookmark"] ^ conjuntos["indice"])
    ]


def _fronteiras(
    paginas: Sequence[dict[str, Any]],
    sinais: list[dict[str, Any]],
    diagnostico: dict[str, Any] | None,
    inicio: int,
) -> tuple[str, list[Fronteira], list[dict[str, Any]]]:
    origem = list((diagnostico or {}).get("fronteiras_origem") or [])
    fonte, posicoes = _posicoes_origem(paginas, origem)
    if not posicoes:
        return "regras", segmentar(sinais, inicio), []
    fronteiras, divergencias = conferir_origem(sinais, posicoes, inicio)
    numeradas = [d | {"pagina": int(paginas[d["pagina"]]["numero"])} for d in divergencias]
    return fonte, fronteiras, numeradas + _discordancia_entre_origens(origem)


def _confianca_fronteira(fronteira: Fronteira) -> float:
    if fronteira.nivel == FORTE:
        return fronteira.pontuacao
    if fronteira.nivel == FRACA:
        return round(fronteira.pontuacao * FATOR_FRACA, 4)
    return CONFIANCA_ORIGEM_DIVERGENTE if fronteira.divergente else CONFIANCA_ORIGEM


def _flags_paginas(paginas: Sequence[dict[str, Any]]) -> dict[str, int]:
    contagem: Counter[str] = Counter()
    for pagina in paginas:
        contagem.update(k for k, v in dict(pagina.get("flags") or {}).items() if v)
    return dict(sorted(contagem.items()))


def _evidencia(
    paginas: Sequence[dict[str, Any]],
) -> tuple[date | None, str | None, dict[str, Any] | None]:
    achada = data_da_peca([str(p.get("texto") or "") for p in paginas])
    if achada is None:
        return None, None, None
    evidencia = {
        "pagina": int(paginas[achada.pagina]["numero"]),
        "inicio": achada.inicio,
        "fim": achada.fim,
        "trecho": achada.trecho,
        "hash_trecho": achada.hash_trecho,
    }
    return achada.data, achada.tipo_data, evidencia


def _peca(
    ordem: int,
    fronteira: Fronteira,
    paginas: Sequence[dict[str, Any]],
    repetidas: frozenset[str],
    divergencias_internas: list[dict[str, Any]],
) -> PecaIndice:
    linhas = [linha for p in paginas for linha in corpo(str(p.get("texto") or ""), repetidas)]
    tipo = classificar_tipo(linhas)
    origem = classificar_origem(linhas)
    data, tipo_data, evidencia = _evidencia(paginas)
    marcas = {
        "fronteira_fraca": fronteira.nivel == FRACA,
        "divergencia_fronteira": fronteira.divergente or bool(divergencias_internas),
        "tipo_ambiguo": tipo.motivo in ("ambiguo", "sem_indicio"),
        "origem_desconhecida": origem.valor == OrigemPeca.DESCONHECIDA.value,
        "data_ausente": data is None,
    }
    confianca = round(min(_confianca_fronteira(fronteira), tipo.confianca), 4)
    return PecaIndice(
        ordem=ordem,
        tipo=TipoPeca(tipo.valor),
        origem=OrigemPeca(origem.valor),
        pagina_inicial=int(paginas[0]["numero"]),
        pagina_final=int(paginas[-1]["numero"]),
        confianca=confianca,
        data=data,
        tipo_data=tipo_data,
        evidencia_data=evidencia,
        flags={
            "peca": {k: v for k, v in marcas.items() if v},
            "paginas": _flags_paginas(paginas),
        },
        classificacao={
            "fronteira": {
                "nivel": fronteira.nivel,
                "pontuacao": fronteira.pontuacao,
                "sinais": list(fronteira.sinais),
                "divergente": fronteira.divergente,
                "origem": fronteira.origem,
                "divergencias_internas": divergencias_internas,
            },
            "tipo": {"confianca": tipo.confianca, "motivo": tipo.motivo, "pontos": tipo.pontos},
            "origem": {"confianca": origem.confianca, "motivo": origem.motivo},
            "versoes": versoes(),
        },
    )


def versoes() -> dict[str, str]:
    """Versões das regras usadas (fronteira, títulos, classificação)."""
    return {
        "fronteiras": regras_padrao().versao,
        "titulos": titulos_padrao().versao,
        "classificacao": regras_classificacao_padrao().versao,
    }


def montar_indice(
    paginas: Sequence[dict[str, Any]], diagnostico: dict[str, Any] | None = None
) -> ResultadoIndice:
    """Monta o índice do arquivo.

    Args:
        paginas: Páginas do arquivo em ordem: `{numero, tipo, texto, coordenadas, flags}`.
        diagnostico: Diagnóstico do arquivo (`fronteiras_origem`, `sinais.paginas_indice`).

    Returns:
        Peças, sinais por página, divergências e a fonte das fronteiras.
    """
    paginas = sorted(paginas, key=lambda p: int(p["numero"]))
    inicio = int(((diagnostico or {}).get("sinais") or {}).get("paginas_indice", 0))
    inicio = min(inicio, len(paginas))
    conteudo = paginas[inicio:]
    sinais = [{"indice": True, "vazia": True} for _ in paginas[:inicio]]
    sinais += sinais_do_arquivo(conteudo)
    repetidas = linhas_repetidas(str(p.get("texto") or "") for p in conteudo)
    fonte, fronteiras, divergencias = _fronteiras(paginas, sinais, diagnostico, inicio)
    resultado = ResultadoIndice(sinais=sinais, divergencias=divergencias, fonte=fonte)
    for ordem, fronteira in enumerate(fronteiras, start=1):
        fim = fronteiras[ordem].posicao if ordem < len(fronteiras) else len(paginas)
        trecho = paginas[fronteira.posicao : fim]
        numeros = {int(p["numero"]) for p in trecho[1:]}
        internas = [d for d in divergencias if d["pagina"] in numeros]
        resultado.pecas.append(_peca(ordem, fronteira, trecho, repetidas, internas))
    return resultado


def pecas_saida(
    pecas: Sequence[PecaIndice], paginas: Sequence[dict[str, Any]], arquivo: str
) -> tuple[PecaSaida, ...]:
    """Converte o índice para o formato de `lupa.sinteticos.saida_pipeline`.

    Args:
        pecas: Peças do índice.
        paginas: Páginas do arquivo (`numero`, `origem_arquivo`, `pagina_origem`).
        arquivo: Nome do arquivo físico, para páginas sem origem registrada.

    Returns:
        Peças com início e fim como `(arquivo, página)` e a data.
    """
    por_numero = {int(p["numero"]): p for p in paginas}

    def ref(numero: int) -> RefPagina:
        pagina = por_numero.get(numero, {})
        return RefPagina(
            arquivo=str(pagina.get("origem_arquivo") or arquivo),
            pagina=int(pagina.get("pagina_origem") or numero),
        )

    return tuple(
        PecaSaida(
            tipo=p.tipo,
            origem=p.origem,
            inicio=ref(p.pagina_inicial),
            fim=ref(p.pagina_final),
            data=p.data,
        )  # fmt: skip
        for p in pecas
    )
