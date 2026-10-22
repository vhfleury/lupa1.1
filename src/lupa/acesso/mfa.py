"""MFA por aplicativo autenticador (TOTP, RFC 6238) com proteção contra reuso de código.

O QR code é a URI `otpauth://` devolvida por `uri_provisionamento`; a interface a desenha.
Janela de tolerância: um passo de 30 s para cada lado. O passo aceito é gravado em
`usuario.mfa_ultimo_passo`; códigos de passo igual ou anterior são recusados (replay).
"""

import hmac
from dataclasses import dataclass
from datetime import datetime

import pyotp

EMISSOR = "Lupa"
JANELA_PASSOS = 1


@dataclass(frozen=True)
class ProvisionamentoMfa:
    """Dados exibidos ao usuário para cadastrar o autenticador.

    Attributes:
        segredo: Segredo base32 (para digitação manual).
        uri: URI `otpauth://` (conteúdo do QR code).
    """

    segredo: str
    uri: str


def gerar_segredo() -> str:
    """Gera um segredo TOTP aleatório de 160 bits.

    Returns:
        Segredo em base32.
    """
    return pyotp.random_base32(length=32)


def provisionar(segredo: str, nome_usuario: str) -> ProvisionamentoMfa:
    """Monta os dados de cadastro do autenticador.

    Args:
        segredo: Segredo base32.
        nome_usuario: Nome mostrado no aplicativo.

    Returns:
        Segredo e URI para o QR code.
    """
    uri = pyotp.TOTP(segredo).provisioning_uri(name=nome_usuario, issuer_name=EMISSOR)
    return ProvisionamentoMfa(segredo=segredo, uri=uri)


def verificar_codigo(
    segredo: str, codigo: str, ultimo_passo: int | None, agora: datetime
) -> int | None:
    """Verifica o código dentro da janela e recusa passos já usados.

    Args:
        segredo: Segredo base32 do usuário.
        codigo: Código de 6 dígitos informado.
        ultimo_passo: Último passo aceito para este usuário, ou None.
        agora: Instante de referência.

    Returns:
        O passo aceito (para gravar), ou None se o código for inválido ou reutilizado.
    """
    totp = pyotp.TOTP(segredo)
    passo_atual = totp.timecode(agora)
    for passo in range(passo_atual - JANELA_PASSOS, passo_atual + JANELA_PASSOS + 1):
        if ultimo_passo is not None and passo <= ultimo_passo:
            continue
        if hmac.compare_digest(totp.generate_otp(passo), codigo):
            return passo
    return None
