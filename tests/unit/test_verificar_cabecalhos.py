"""`scripts/verificar_cabecalhos.py`: falha se faltar cabeçalho ou se a CSP afrouxar (6.10)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

CAMINHO = Path(__file__).resolve().parents[2] / "scripts" / "verificar_cabecalhos.py"
CSP = (
    "default-src 'none'; script-src 'self'; "
    "style-src 'self' 'unsafe-hashes' 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='; "
    "img-src 'self'; font-src 'self'; "
    "connect-src 'self'; manifest-src 'self'; form-action 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; object-src 'none'"
)
BONS = {
    "Content-Security-Policy": CSP,
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _csp(velho: str, novo: str) -> dict[str, str | None]:
    return {"Content-Security-Policy": CSP.replace(velho, novo)}


@pytest.fixture(scope="module")
def modulo() -> ModuleType:
    """Carrega o script como módulo."""
    spec = importlib.util.spec_from_file_location("verificar_cabecalhos", CAMINHO)
    assert spec is not None and spec.loader is not None
    carregado = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(carregado)
    return carregado


def test_cabecalhos_do_proxy_passam(modulo: ModuleType) -> None:
    """A política aplicada no Caddyfile não tem problema."""
    assert modulo.problemas(BONS) == []
    caddy = Path(__file__).resolve().parents[2] / "proxy" / "Caddyfile"
    if caddy.exists():  # no contêiner da API o proxy/ não é copiado
        assert CSP in caddy.read_text("utf-8")


@pytest.mark.parametrize(
    ("alteracao", "esperado"),
    [
        ({"Content-Security-Policy": None}, "falta content-security-policy"),
        ({"Strict-Transport-Security": None}, "falta strict-transport-security"),
        ({"Permissions-Policy": None}, "falta permissions-policy"),
        ({"Cross-Origin-Opener-Policy": "unsafe-none"}, "cross-origin-opener-policy deve ser"),
        ({"Strict-Transport-Security": "max-age=60"}, "max-age menor"),
        ({"Permissions-Policy": "camera=()"}, "não bloqueia microphone"),
        ({"Server": "Caddy"}, "server exposto"),
        (
            _csp("script-src 'self'", "script-src 'self' 'unsafe-inline'"),
            "script-src deve ser",
        ),
        (
            _csp("style-src 'self'", "style-src 'self' 'unsafe-inline'"),
            "style-src tem 'unsafe-inline'",
        ),
        (_csp("S8qMpvofolR8", "outroHash000"), "style-src deve ser"),
        (
            _csp("img-src 'self'", "img-src *"),
            "img-src tem *",
        ),
        (
            _csp("style-src 'self'", "style-src https://cdn.x"),
            "style-src aceita origem externa",
        ),
        (
            _csp("frame-ancestors 'none'", "frame-ancestors 'self'"),
            "frame-ancestors deve ser",
        ),
        (
            _csp("; form-action 'self'", ""),
            "sem form-action",
        ),
        (
            {"Content-Security-Policy": "default-src 'self'"},
            "default-src deve ser",
        ),
    ],
)
def test_falha_se_faltar_ou_afrouxar(
    modulo: ModuleType, alteracao: dict[str, str | None], esperado: str
) -> None:
    """Cada afrouxamento vira um problema nomeado."""
    cabecalhos = {**BONS, **alteracao}
    filtrados = {k: v for k, v in cabecalhos.items() if v is not None}
    assert any(esperado in p for p in modulo.problemas(filtrados)), modulo.problemas(filtrados)


def test_main_com_proxy_fora_do_ar(modulo: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """Sem `--exigir` só avisa; com `--exigir` falha."""
    assert modulo.main(["--url", "https://127.0.0.1:1"]) == 0
    assert "pulado" in capsys.readouterr().out
    assert modulo.main(["--url", "https://127.0.0.1:1", "--exigir"]) == 1


def test_main_confere_cada_rota(
    modulo: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Todas as rotas boas: 0; uma rota sem CSP: 1, com a rota no relatório."""
    monkeypatch.setattr(modulo, "_buscar", lambda url: BONS)
    assert modulo.main([]) == 0
    assert "ok em 4 rotas" in capsys.readouterr().out
    sem_csp = {k: v for k, v in BONS.items() if k != "Content-Security-Policy"}
    monkeypatch.setattr(modulo, "_buscar", lambda url: sem_csp if url.endswith("/login") else BONS)
    assert modulo.main(["--exigir"]) == 1
    assert "/login: falta content-security-policy" in capsys.readouterr().out
