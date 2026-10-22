"""Registra o marcador `backup` (sem editar o pyproject)."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Declara o marcador dos testes de backup.

    Args:
        config: Configuração do pytest.
    """
    config.addinivalue_line(
        "markers", "backup: backup e restauração cifrados pelo compose (LUPA_VERIFICAR_BACKUP=1)"
    )
