"""Testes de GET /metricas/servico (Etapa 8.1): raspagem do Prometheus por token de serviço."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from lupa.api import saude
from lupa.config import Settings, get_settings

TOKEN = "token-ficticio-de-teste-metricas"  # noqa: S105


def _app(app_teste: FastAPI, settings: Settings, token: str | None) -> TestClient:
    configurado = settings.model_copy(
        update={"metricas_token": SecretStr(token) if token else None}
    )
    app_teste.dependency_overrides[get_settings] = lambda: configurado
    return TestClient(app_teste, base_url="https://testserver")


def test_metricas_servico_com_token(
    app_teste: FastAPI, settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com o token certo, devolve ingestão, modelo, auditoria e cofre."""
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: True)
    cliente = _app(app_teste, settings_ficticias, TOKEN)
    resposta = cliente.get("/metricas/servico", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 200
    for nome in (
        "lupa_ingestao_jobs",
        "lupa_ingestao_idade_fila_segundos",
        "lupa_ingestao_falhas_total",
        "lupa_cofre_ok 1.0",
        "lupa_modelo_chamadas_24h",
        'lupa_modelo_tokens_24h{tipo="entrada"}',
        "lupa_auditoria_eventos_24h",
    ):
        assert nome in resposta.text


def test_metricas_servico_recusa_token_errado_ou_ausente(
    app_teste: FastAPI, settings_ficticias: Settings
) -> None:
    """Token errado ou ausente: 401."""
    cliente = _app(app_teste, settings_ficticias, TOKEN)
    assert cliente.get("/metricas/servico").status_code == 401
    errado = cliente.get("/metricas/servico", headers={"Authorization": "Bearer outro"})
    assert errado.status_code == 401


def test_metricas_servico_desligada_sem_token_configurado(
    app_teste: FastAPI, settings_ficticias: Settings
) -> None:
    """Sem LUPA_METRICAS_TOKEN a rota não existe para fora (404)."""
    cliente = _app(app_teste, settings_ficticias, None)
    resposta = cliente.get("/metricas/servico", headers={"Authorization": "Bearer x"})
    assert resposta.status_code == 404
