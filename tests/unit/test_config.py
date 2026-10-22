"""Testes da configuração."""

import pytest
from pydantic import ValidationError

from lupa.api.app import create_app
from lupa.config import get_settings


def test_aplicacao_nao_inicia_sem_variavel_obrigatoria(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem LUPA_DATABASE_URL a criação da aplicação falha."""
    for chave in (
        "LUPA_DATABASE_URL",
        "LUPA_MINIO_ENDPOINT",
        "LUPA_MINIO_BUCKET",
        "LUPA_MINIO_ACCESS_KEY",
        "LUPA_MINIO_SECRET_KEY",
    ):
        monkeypatch.delenv(chave, raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError, match="database_url"):
        create_app()
    get_settings.cache_clear()


@pytest.mark.usefixtures("ambiente_ficticio")
def test_configuracao_le_variaveis_do_ambiente() -> None:
    """Variáveis com prefixo LUPA_ preenchem a configuração."""
    settings = get_settings()
    assert settings.minio_bucket == "lupa-autos"
    assert "segredo" not in repr(settings)


@pytest.mark.usefixtures("ambiente_ficticio")
def test_ambiente_invalido_e_rejeitado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valor fora da lista de ambientes falha na validação."""
    monkeypatch.setenv("LUPA_AMBIENTE", "qualquer")
    with pytest.raises(ValidationError):
        get_settings()
