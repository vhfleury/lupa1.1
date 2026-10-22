"""Verificações de saúde das dependências externas."""

import urllib.request

from sqlalchemy import create_engine, text

from lupa.config import Settings
from lupa.seguranca.cofre import CHAVE_SAUDE, Cofre, CofreMemoria, criar_cofre

VALOR_TESTE_SAUDE = b"lupa-saude"


def verificar_db(settings: Settings) -> bool:
    """Verifica se o banco responde a uma consulta trivial.

    Args:
        settings: Configuração da aplicação.

    Returns:
        Verdadeiro se o banco respondeu.
    """
    engine = create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"connect_timeout": max(1, int(settings.timeout_saude_segundos))},
    )
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def verificar_minio(settings: Settings) -> bool:
    """Verifica se o MinIO está vivo pelo endpoint de saúde.

    Args:
        settings: Configuração da aplicação.

    Returns:
        Verdadeiro se o MinIO respondeu 200.
    """
    esquema = "https" if settings.minio_secure else "http"
    url = f"{esquema}://{settings.minio_endpoint}/minio/health/live"
    try:
        with urllib.request.urlopen(url, timeout=settings.timeout_saude_segundos) as resposta:  # noqa: S310
            return bool(resposta.status == 200)
    except Exception:
        return False


def verificar_cofre(settings: Settings, cofre: Cofre | None = None) -> bool:
    """Verifica se o cofre responde e decifra um valor de teste.

    Usa a chave Transit de verificação `lupa-saude` (criada por `vault_inicializar`): cifra um
    valor fixo e confere que volta igual. Selado, fora do ar, sem AppRole ou sem a chave: falso.

    Args:
        settings: Configuração da aplicação.
        cofre: Cofre a usar (injetável nos testes); padrão, o da configuração.

    Returns:
        Verdadeiro se cifrar e decifrar deram certo.
    """
    try:
        alvo = cofre or criar_cofre(settings)
        if isinstance(alvo, CofreMemoria):
            alvo.criar_chave(CHAVE_SAUDE)
        token = alvo.cifrar(CHAVE_SAUDE, VALOR_TESTE_SAUDE)
        return alvo.decifrar(CHAVE_SAUDE, token) == VALOR_TESTE_SAUDE
    except Exception:
        return False
