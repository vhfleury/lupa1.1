"""Testes da rota de saúde e do middleware de request_id."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from lupa.api import saude
from lupa.api.app import create_app
from lupa.config import Settings, get_settings
from lupa.logging import get_logger
from lupa.seguranca.cofre import CHAVE_SAUDE, CofreError, CofreMemoria


def _cliente(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_saude_responde_ok_quando_dependencias_respondem(
    settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com banco e MinIO saudáveis, responde 200 e tudo ok."""
    monkeypatch.setattr(saude, "verificar_db", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_minio", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: True)
    resposta = _cliente(settings_ficticias).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"api": "ok", "db": "ok", "minio": "ok", "cofre": "ok"}


def test_saude_responde_503_quando_banco_falha(
    settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com banco fora, responde 503 indicando a falha."""
    monkeypatch.setattr(saude, "verificar_db", lambda _s: False)
    monkeypatch.setattr(saude, "verificar_minio", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: True)
    resposta = _cliente(settings_ficticias).get("/saude")
    assert resposta.status_code == 503
    assert resposta.json()["db"] == "falha"


def test_verificacoes_retornam_falso_sem_servicos(settings_ficticias: Settings) -> None:
    """Endereços inalcançáveis resultam em falha, sem exceção."""
    inalcancavel = settings_ficticias.model_copy(
        update={
            "minio_endpoint": "127.0.0.1:1",
            "timeout_saude_segundos": 0.2,
            "database_url": SecretStr("postgresql+psycopg://x:y@127.0.0.1:1/z"),
        }
    )
    assert saude.verificar_db(inalcancavel) is False
    assert saude.verificar_minio(inalcancavel) is False


def test_cada_requisicao_recebe_request_id_unico(
    settings_ficticias: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """O middleware gera request_id distinto por requisição e o injeta no log."""
    monkeypatch.setattr(saude, "verificar_db", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_minio", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: True)
    cliente = _cliente(settings_ficticias)
    primeiro = cliente.get("/saude").headers["X-Request-ID"]
    segundo = cliente.get("/saude").headers["X-Request-ID"]
    assert primeiro != segundo
    assert len(primeiro) == 32
    capsys.readouterr()


def test_log_dentro_da_requisicao_carrega_request_id(
    settings_ficticias: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Eventos logados durante a requisição carregam o request_id do cabeçalho."""

    def _db(_s: Settings) -> bool:
        get_logger("teste").info("verificando_db")
        return True

    monkeypatch.setattr(saude, "verificar_db", _db)
    monkeypatch.setattr(saude, "verificar_minio", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: True)
    cliente = _cliente(settings_ficticias)
    capsys.readouterr()
    request_id = cliente.get("/saude").headers["X-Request-ID"]
    linhas = [json.loads(linha) for linha in capsys.readouterr().out.strip().splitlines()]
    assert any(linha.get("request_id") == request_id for linha in linhas)


@pytest.mark.integracao
@pytest.mark.usefixtures("ambiente_ficticio")
def test_saude_integracao_com_servicos_reais() -> None:
    """Com PostgreSQL e MinIO acessíveis (compose), /saude responde 200 de verdade."""
    settings = get_settings()
    if not (
        saude.verificar_db(settings)
        and saude.verificar_minio(settings)
        and saude.verificar_cofre(settings)
    ):
        pytest.skip("PostgreSQL, MinIO ou cofre inacessível neste ambiente")
    resposta = TestClient(create_app(settings)).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"api": "ok", "db": "ok", "minio": "ok", "cofre": "ok"}


def test_saude_responde_503_com_cofre_selado(
    settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cofre selado ou fora: 503 com `cofre: falha` (achado da 7.10)."""
    monkeypatch.setattr(saude, "verificar_db", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_minio", lambda _s: True)
    monkeypatch.setattr(saude, "verificar_cofre", lambda _s: False)
    resposta = _cliente(settings_ficticias).get("/saude")
    assert resposta.status_code == 503
    assert resposta.json()["cofre"] == "falha"


def test_verificar_cofre_memoria_cifra_e_decifra(settings_ficticias: Settings) -> None:
    """Com o cofre em memória, cria a chave de verificação e confere a ida e volta."""
    cofre = CofreMemoria()
    assert saude.verificar_cofre(settings_ficticias, cofre) is True
    assert cofre.existe_chave(CHAVE_SAUDE)


class _CofreSelado(CofreMemoria):
    def cifrar(self, nome: str, dados: bytes) -> str:
        raise CofreError("vault respondeu 503")


class _CofreTrocado(CofreMemoria):
    def decifrar(self, nome: str, token: str) -> bytes:
        return b"outro"


def test_verificar_cofre_falso_quando_selado_ou_inconsistente(
    settings_ficticias: Settings,
) -> None:
    """Erro do cofre (selado) ou valor decifrado diferente resultam em falso, sem exceção."""
    assert saude.verificar_cofre(settings_ficticias, _CofreSelado()) is False
    assert saude.verificar_cofre(settings_ficticias, _CofreTrocado()) is False


def test_verificar_cofre_vault_inalcancavel(settings_ficticias: Settings) -> None:
    """Vault inalcançável (configuração padrão) resulta em falso."""
    inalcancavel = settings_ficticias.model_copy(
        update={
            "cofre_backend": "vault",
            "vault_endereco": "http://127.0.0.1:1",
            "vault_timeout_segundos": 0.2,
        }
    )
    assert saude.verificar_cofre(inalcancavel) is False
