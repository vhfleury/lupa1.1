"""Testes da localização aproximada por IP (sem base real da MaxMind)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import geoip2.database
import geoip2.errors
import pytest

from lupa.auditoria import geoip
from lupa.config import Settings


class LeitorFalso:
    """Imita `geoip2.database.Reader.city` com respostas fixas."""

    def __init__(self, caminho: str) -> None:
        """Guarda o caminho recebido.

        Args:
            caminho: Caminho do `.mmdb`.
        """
        self.caminho = caminho

    def city(self, ip: str) -> Any:
        """Responde conforme o IP.

        Args:
            ip: IP consultado.

        Returns:
            Objeto com cidade, subdivisão e país.

        Raises:
            AddressNotFoundError: Para 8.8.4.4.
            RuntimeError: Para 1.1.1.1.
        """
        if ip == "8.8.4.4":
            raise geoip2.errors.AddressNotFoundError("não achou")
        if ip == "1.1.1.1":
            raise RuntimeError("base corrompida")
        nome = SimpleNamespace
        vazio = ip == "9.9.9.9"
        return nome(
            city=nome(name=None if vazio else "Goiânia"),
            subdivisions=nome(most_specific=nome(name=None if vazio else "Goiás")),
            country=nome(name=None if vazio else "Brasil"),
        )


@pytest.fixture
def resolvedor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> geoip.ResolvedorMaxMind:
    """Resolvedor MaxMind com leitor falso."""
    monkeypatch.setattr(geoip2.database, "Reader", LeitorFalso)
    return geoip.ResolvedorMaxMind(tmp_path / "GeoLite2-City.mmdb")


@pytest.mark.parametrize("ip", ["10.1.2.3", "192.168.0.10", "172.16.5.4", "127.0.0.1", "::1"])
def test_ip_privado_resolve_para_rede_interna_sem_consultar_base(
    resolvedor: geoip.ResolvedorMaxMind, ip: str
) -> None:
    """IP interno não chega à base."""
    assert resolvedor.resolver(ip) == "rede interna"


@pytest.mark.parametrize(
    ("ip", "esperado"),
    [
        ("200.1.2.3", "Goiânia, Goiás, Brasil"),
        ("9.9.9.9", "desconhecida"),
        ("8.8.4.4", "desconhecida"),
        ("1.1.1.1", "desconhecida"),
        ("testclient", "desconhecida"),
        (None, "desconhecida"),
    ],
)
def test_resolucao_por_base_e_falhas_nao_impedem(
    resolvedor: geoip.ResolvedorMaxMind, ip: str | None, esperado: str
) -> None:
    """IP público consulta a base; qualquer falha vira `desconhecida`."""
    assert resolvedor.resolver(ip) == esperado


def test_resolvedor_nulo_devolve_desconhecida() -> None:
    """Sem base, IP público fica `desconhecida`."""
    assert geoip.ResolvedorNulo().resolver("200.1.2.3") == "desconhecida"


def test_criar_resolvedor_conforme_configuracao(
    settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sem caminho ou com arquivo ilegível: nulo; com arquivo: MaxMind."""
    assert isinstance(geoip.criar_resolvedor(settings_ficticias), geoip.ResolvedorNulo)
    inexistente = settings_ficticias.model_copy(update={"geoip_caminho": tmp_path / "nao.mmdb"})
    assert isinstance(geoip.criar_resolvedor(inexistente), geoip.ResolvedorNulo)
    monkeypatch.setattr(geoip2.database, "Reader", LeitorFalso)
    assert isinstance(geoip.criar_resolvedor(inexistente), geoip.ResolvedorMaxMind)
