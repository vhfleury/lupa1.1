"""Data da peça por regra, com evidência literal (Etapa 4E.6).

A data é procurada no texto das páginas da peça, da última para a primeira, nesta ordem de
preferência: data de protocolo ("protocolada em"), data da assinatura eletrônica ("assinado
eletronicamente por ..., em dd/mm/aaaa"), data de local e data ("Vila Esperança, 16
de março de 2019") e data de juntada ou autuação ("juntado em", "autuado em"). A evidência é o
literal da data na página, com offsets no texto da página e o hash do trecho. Sem nenhuma
dessas formas, a peça fica sem data: a data nunca é inventada nem tirada de outra peça. A
procura vai da última página para a primeira, exceto a de juntada, que fica no início da peça
("Junto a estes autos os documentos ... recebidos em"). A assinatura é reconhecida com
tolerância a erro de OCR ("assinado eletronicame:«e por ..."), recusando o rodapé de
autenticação ("Código de autenticação").
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from lupa.dominio.esquemas import calcular_hash

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}  # fmt: skip
ANO_MINIMO = 1900
ANO_MAXIMO = 2100
NUMERICA = r"(?P<data>\d{1,2}/\d{1,2}/\d{4})"
EXTENSO = r"(?P<ext>\d{1,2}º? de [a-zç]+ de \d{4})"
QUALQUER = rf"(?:{NUMERICA}|{EXTENSO})"
_I = re.IGNORECASE
SEM_RODAPE = r"(?:(?!c[óo]digo|autentica)[\s\S])"
REGRAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("protocolo", re.compile(rf"protocolad[oa]\s+em\s+{QUALQUER}", _I)),
    ("assinatura", re.compile(rf"assinad[oa]\b{SEM_RODAPE}{{0,220}}?\be[mn]\s+{NUMERICA}", _I)),
    ("assinatura", re.compile(rf"^[A-ZÀ-Ú][^\n,]{{2,60}},\s+{QUALQUER}\.?\s*$", re.MULTILINE)),
    ("juntada", re.compile(rf"(?:juntad[oa]s?|autuad[oa]|recebid[oa]s?)\s+em\s+{QUALQUER}", _I)),
)


@dataclass(frozen=True)
class DataPeca:
    """Data da peça com a evidência.

    Attributes:
        data: Data.
        tipo_data: `assinatura`, `protocolo` ou `juntada`.
        pagina: Posição da página dentro da lista recebida (0-based).
        inicio: Offset inicial do literal no texto da página.
        fim: Offset final.
        trecho: Literal da data como está na página.
        hash_trecho: SHA-256 do trecho.
    """

    data: date
    tipo_data: str
    pagina: int
    inicio: int
    fim: int
    trecho: str
    hash_trecho: str


def interpretar(literal: str) -> date | None:
    """Converte `dd/mm/aaaa` ou `d de mês de aaaa` em data, se válida.

    Args:
        literal: Data como escrita.

    Returns:
        Data, ou None se inválida ou fora de 1900 a 2100.
    """
    numerica = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", literal.strip())
    if numerica:
        dia, mes, ano = (int(g) for g in numerica.groups())
    else:
        extenso = re.fullmatch(r"(\d{1,2})º? de ([a-zç]+) de (\d{4})", literal.strip(), _I)
        if not extenso or extenso.group(2).lower() not in MESES:
            return None
        dia, mes, ano = (
            int(extenso.group(1)),
            MESES[extenso.group(2).lower()],
            int(extenso.group(3)),
        )
    if not ANO_MINIMO <= ano <= ANO_MAXIMO:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _grupo(achado: re.Match[str]) -> tuple[str, int, int] | None:
    for nome in ("data", "ext"):
        if nome in achado.re.groupindex and achado.group(nome):
            return achado.group(nome), achado.start(nome), achado.end(nome)
    return None


def _na_pagina(
    texto: str, padrao: re.Pattern[str], do_fim: bool
) -> tuple[date, str, int, int] | None:
    achados = list(padrao.finditer(texto))
    for achado in reversed(achados) if do_fim else achados:
        grupo = _grupo(achado)
        if grupo is None:
            continue
        literal, inicio, fim = grupo
        valor = interpretar(literal)
        if valor is not None:
            return valor, literal, inicio, fim
    return None


def data_da_peca(textos: Sequence[str]) -> DataPeca | None:
    """Data da peça a partir do texto das suas páginas.

    Args:
        textos: Texto final de cada página da peça, em ordem.

    Returns:
        Data com evidência, ou None quando a peça não traz data reconhecível.
    """
    for tipo_data, padrao in REGRAS:
        ordem = range(len(textos)) if tipo_data == "juntada" else range(len(textos) - 1, -1, -1)
        for posicao in ordem:
            achado = _na_pagina(textos[posicao], padrao, tipo_data != "juntada")
            if achado is not None:
                valor, literal, inicio, fim = achado
                return DataPeca(
                    valor, tipo_data, posicao, inicio, fim, literal, calcular_hash(literal)
                )
    return None
