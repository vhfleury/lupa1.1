"""Identidades inventadas: nomes, CPFs inválidos, números CNJ de teste e endereços.

CPFs são gerados com o segundo dígito verificador propositalmente errado, de modo que nenhum CPF
sintético é válido. Números CNJ têm dígito verificador correto (passam em ``validar_numero_cnj``),
mas usam o tribunal ``99`` do segmento estadual (``8``), que não existe (os tribunais estaduais
vão de ``01`` a ``27``), e sequencial na faixa ``9900000`` a ``9999999``, reservada pelo Lupa a
dados de teste. Assim nunca coincidem com processo real.
"""

import random
from datetime import date

from lupa.dominio.cnj import calcular_digito_verificador

JUSTICA_TESTE = "8"
TRIBUNAL_TESTE = "99"
FAIXA_SEQUENCIAL_TESTE = (9_900_000, 9_999_999)
COMARCA = "Comarca de Vila Esperança"

_PRENOMES = (
    "Abelardo", "Benedita", "Cleiton", "Doralice", "Eustáquio", "Filomena", "Gumercindo",
    "Hermínia", "Ivanildo", "Jucelina", "Lindomar", "Marisvalda", "Nivaldo", "Odete", "Péricles",
    "Quitéria", "Rosivaldo", "Sebastiana", "Tobias", "Valdirene", "Wanderlei", "Zulmira",
)  # fmt: skip
_SOBRENOMES = (
    "Albuquerque Neto", "Bragança", "Cavalcante", "Damasceno", "Esteves", "Figueiró", "Gusmão",
    "Holanda", "Ipiranga", "Jatobá", "Lacerda", "Macedo", "Nogueira", "Orleans", "Piracema",
    "Quintanilha", "Rebouças", "Sampaio", "Tavares", "Uchôa", "Vasconcelos", "Xavier",
)  # fmt: skip
_LOGRADOUROS = (
    "Rua das Acácias", "Avenida dos Ipês", "Travessa do Cerrado", "Rua Pequi", "Alameda Buriti",
)  # fmt: skip


def gerar_nome(rng: random.Random) -> str:
    """Gera um nome completo inventado.

    Args:
        rng: Gerador semeado.

    Returns:
        Nome com prenome e dois sobrenomes.
    """
    sobrenomes = rng.sample(_SOBRENOMES, 2)
    return f"{rng.choice(_PRENOMES)} {sobrenomes[0]} {sobrenomes[1]}"


def _digito_cpf(digitos: list[int]) -> int:
    peso = len(digitos) + 1
    soma = sum(d * (peso - i) for i, d in enumerate(digitos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(cpf: str) -> bool:
    """Confere os dígitos verificadores de um CPF.

    Args:
        cpf: CPF com ou sem pontuação.

    Returns:
        ``True`` se os dois dígitos verificadores conferem.
    """
    digitos = [int(c) for c in cpf if c.isdigit()]
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    primeiro = _digito_cpf(digitos[:9])
    segundo = _digito_cpf([*digitos[:9], primeiro])
    return digitos[9] == primeiro and digitos[10] == segundo


def gerar_cpf_invalido(rng: random.Random) -> str:
    """Gera um CPF formatado cujo segundo dígito verificador está errado.

    Args:
        rng: Gerador semeado.

    Returns:
        CPF no formato ``000.000.000-00``, sempre inválido.
    """
    base = [rng.randint(0, 9) for _ in range(9)]
    primeiro = _digito_cpf(base)
    segundo = (_digito_cpf([*base, primeiro]) + rng.randint(1, 9)) % 10
    d = "".join(str(x) for x in [*base, primeiro, segundo])
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def gerar_numero_cnj(rng: random.Random, ano: int) -> str:
    """Gera número CNJ válido pelo dígito, na faixa reservada a testes.

    Args:
        rng: Gerador semeado.
        ano: Ano de ajuizamento.

    Returns:
        Número ``NNNNNNN-DD.AAAA.8.99.OOOO``.
    """
    sequencial = f"{rng.randint(*FAIXA_SEQUENCIAL_TESTE):07d}"
    origem = f"{rng.randint(1, 50):04d}"
    digito = calcular_digito_verificador(
        sequencial, str(ano), JUSTICA_TESTE, TRIBUNAL_TESTE, origem
    )
    return f"{sequencial}-{digito}.{ano}.{JUSTICA_TESTE}.{TRIBUNAL_TESTE}.{origem}"


def gerar_endereco(rng: random.Random) -> str:
    """Gera um endereço inventado na comarca fictícia.

    Args:
        rng: Gerador semeado.

    Returns:
        Endereço por extenso.
    """
    return f"{rng.choice(_LOGRADOUROS)}, nº {rng.randint(10, 999)}, Vila Esperança"


def gerar_hash_falso(rng: random.Random) -> str:
    """Gera um código de autenticação falso (40 algarismos hexadecimais).

    Args:
        rng: Gerador semeado.

    Returns:
        Código hexadecimal em maiúsculas.
    """
    return f"{rng.getrandbits(160):040X}"


_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro",
)  # fmt: skip


def data_por_extenso(dia: date) -> str:
    """Formata a data por extenso.

    Args:
        dia: Data.

    Returns:
        Por exemplo, ``3 de março de 2024``.
    """
    return f"{dia.day} de {_MESES[dia.month - 1]} de {dia.year}"


def formatar_data(dia: date, rng: random.Random) -> str:
    """Formata a data em ``dd/mm/aaaa`` ou por extenso, sorteando o formato.

    Args:
        dia: Data.
        rng: Gerador semeado.

    Returns:
        Data formatada.
    """
    if rng.random() < 0.7:
        return dia.strftime("%d/%m/%Y")
    return data_por_extenso(dia)
