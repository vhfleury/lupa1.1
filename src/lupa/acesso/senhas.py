"""Hash de senhas com argon2id e política mínima de senha.

Parâmetros do argon2id (perfil "baixa memória" da RFC 9106, padrão do `argon2-cffi` 25):
`time_cost=3`, `memory_cost=65536` KiB (64 MiB), `parallelism=4`, `hash_len=32`,
`salt_len=16`. Ficam fixos aqui para que uma atualização da biblioteca não os mude em silêncio;
`precisa_rehash` indica hashes antigos que devem ser regravados no próximo login.
"""

import secrets
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

TAMANHO_MINIMO = 12
TAMANHO_SENHA_TEMPORARIA = 18

HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID
)


class SenhaFracaError(ValueError):
    """A senha não atende à política mínima."""


@lru_cache(maxsize=1)
def senhas_comuns() -> frozenset[str]:
    """Carrega a lista embutida das 10 mil senhas mais comuns.

    Returns:
        Conjunto de senhas em minúsculas.
    """
    texto = resources.files("lupa.acesso").joinpath("dados/senhas_comuns.txt").read_text("utf-8")
    return frozenset(linha.strip().lower() for linha in texto.splitlines() if linha.strip())


def validar_politica(senha: str, nome_usuario: str) -> None:
    """Confere a política: 12 caracteres, fora da lista comum e diferente do usuário.

    Não exige caracteres especiais.

    Args:
        senha: Senha proposta.
        nome_usuario: Nome do usuário dono da senha.

    Raises:
        SenhaFracaError: Com o motivo, sem repetir a senha.
    """
    if len(senha) < TAMANHO_MINIMO:
        raise SenhaFracaError(f"a senha precisa ter ao menos {TAMANHO_MINIMO} caracteres")
    if senha.lower() in senhas_comuns():
        raise SenhaFracaError("a senha está entre as mais comuns")
    if nome_usuario.lower() in senha.lower():
        raise SenhaFracaError("a senha não pode conter o nome de usuário")
    if len(set(senha)) < 4:
        raise SenhaFracaError("a senha tem caracteres repetidos demais")


def gerar_hash(senha: str) -> str:
    """Gera o hash argon2id da senha.

    Args:
        senha: Senha em texto.

    Returns:
        Hash no formato PHC (`$argon2id$...`).
    """
    return HASHER.hash(senha)


def verificar_senha(senha_hash: str, senha: str) -> bool:
    """Verifica a senha contra o hash, sem lançar exceção.

    Args:
        senha_hash: Hash armazenado.
        senha: Senha informada.

    Returns:
        Verdadeiro se confere.
    """
    try:
        return HASHER.verify(senha_hash, senha)
    except (VerificationError, InvalidHashError):
        return False


def precisa_rehash(senha_hash: str) -> bool:
    """Indica se o hash foi gerado com parâmetros diferentes dos atuais.

    Args:
        senha_hash: Hash armazenado.

    Returns:
        Verdadeiro se deve ser regravado.
    """
    return HASHER.check_needs_rehash(senha_hash)


@lru_cache(maxsize=1)
def hash_ficticio() -> str:
    """Hash de uma senha aleatória, para igualar o tempo de resposta de usuário inexistente.

    Returns:
        Hash argon2id que nunca confere.
    """
    return gerar_hash(secrets.token_urlsafe(16))


def gerar_senha_temporaria() -> str:
    """Gera senha temporária aleatória para reset manual.

    Returns:
        Senha com cerca de 144 bits de entropia.
    """
    return secrets.token_urlsafe(TAMANHO_SENHA_TEMPORARIA)
