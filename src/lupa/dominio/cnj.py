"""Validação do número único de processo do CNJ (Resolução CNJ 65/2008)."""

import re

PADRAO_CNJ = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")


class NumeroCnjInvalidoError(ValueError):
    """Indica número CNJ com formato ou dígito verificador inválido."""


def calcular_digito_verificador(
    sequencial: str, ano: str, justica: str, tribunal: str, origem: str
) -> str:
    """Calcula o dígito verificador pelo módulo 97 (ISO 7064).

    Args:
        sequencial: NNNNNNN.
        ano: AAAA.
        justica: J.
        tribunal: TR.
        origem: OOOO.

    Returns:
        O dígito verificador com dois algarismos.
    """
    base = int(f"{sequencial}{ano}{justica}{tribunal}{origem}00")
    return f"{98 - base % 97:02d}"


def validar_numero_cnj(numero: str) -> str:
    """Valida formato NNNNNNN-DD.AAAA.J.TR.OOOO e dígito verificador.

    Args:
        numero: Número a validar.

    Returns:
        O próprio número, se válido.

    Raises:
        NumeroCnjInvalidoError: Se o formato ou o dígito estiver errado.
    """
    casamento = PADRAO_CNJ.match(numero)
    if casamento is None:
        raise NumeroCnjInvalidoError("formato CNJ inválido")
    sequencial, digito, ano, justica, tribunal, origem = casamento.groups()
    if calcular_digito_verificador(sequencial, ano, justica, tribunal, origem) != digito:
        raise NumeroCnjInvalidoError("dígito verificador CNJ inválido")
    return numero
