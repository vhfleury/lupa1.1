"""Motor comum dos extratores: regra de gatilho e janela aplicada às páginas de uma peça.

Toda busca é feita no texto dobrado da página (normalizado, minúsculas, sem acento); os offsets
voltam ao texto original pelo mapa do normalizado, de modo que a evidência é sempre um trecho
literal de ``pagina.texto``.
"""

import re
from collections.abc import Iterator
from typing import Any

from lupa.dominio.enums import TipoFato
from lupa.ingestao.eventos.modelo import Candidato, PaginaTexto, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes, RegraEvento

REDUCAO_ANO_DOIS_DIGITOS = 0.8


def candidato_do_trecho(
    pagina: PaginaTexto,
    tipo: TipoFato,
    valor: Any,
    intervalo_dobrado: tuple[int, int],
    confianca: float,
    regra: str,
) -> Candidato:
    """Candidato com evidência dada por um intervalo do texto dobrado.

    Args:
        pagina: Página.
        tipo: Tipo de fato.
        valor: Valor.
        intervalo_dobrado: Início e fim no dobrado.
        confianca: Confiança.
        regra: Identificação da regra.

    Returns:
        Candidato com offsets no original.
    """
    inicio, fim = pagina.analise.para_original(*intervalo_dobrado)
    return Candidato(tipo, valor, pagina, inicio, fim, confianca, regra=regra)


def _na_pagina(regra: RegraEvento, pagina: PaginaTexto) -> list[Candidato]:
    achados: dict[tuple[int, int], Candidato] = {}
    for posicao, gatilho in enumerate(regra.gatilhos):
        for casamento in gatilho.finditer(pagina.analise.dobrado):
            limite = casamento.end() + regra.janela
            data = next((d for d in pagina.datas if casamento.end() <= d.inicio <= limite), None)
            if data is None or (data.inicio, data.fim) in achados:
                continue
            inicio, fim = pagina.analise.para_original(casamento.start(), data.fim)
            fator = REDUCAO_ANO_DOIS_DIGITOS if data.ano_dois_digitos else 1.0
            achados[(data.inicio, data.fim)] = Candidato(
                regra.tipo,
                data.iso,
                pagina,
                inicio,
                fim,
                round(regra.confianca * fator, 3),
                data=data.data,
                por_reu=regra.por_reu,
                regra=f"{regra.tipo.value}#{posicao}",
            )
    return sorted(achados.values(), key=lambda c: c.inicio)


def aplicar_regra(regra: RegraEvento, peca: PecaTexto) -> list[Candidato]:
    """Aplica uma regra de gatilho a todas as páginas da peça.

    Args:
        regra: Regra do YAML.
        peca: Peça.

    Returns:
        Candidatos (só o último da peça quando ``regra.ultima``).
    """
    candidatos = [c for pagina in peca.paginas for c in _na_pagina(regra, pagina)]
    if regra.ultima and candidatos:
        return candidatos[-1:]
    return candidatos


def regras_da_peca(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Aplica todas as regras do YAML previstas para o tipo da peça.

    Args:
        peca: Peça.
        padroes: Padrões versionados.

    Returns:
        Candidatos de todas as regras.
    """
    return [c for regra in padroes.regras_da_peca(peca.tipo) for c in aplicar_regra(regra, peca)]


def buscar(padrao: re.Pattern[str], peca: PecaTexto) -> Iterator[tuple[PaginaTexto, re.Match[str]]]:
    """Casamentos de uma expressão no texto dobrado das páginas da peça.

    Args:
        padrao: Expressão sobre o dobrado.
        peca: Peça.

    Yields:
        Página e casamento.
    """
    for pagina in peca.paginas:
        for casamento in padrao.finditer(pagina.analise.dobrado):
            yield pagina, casamento
