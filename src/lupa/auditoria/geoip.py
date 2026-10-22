"""Localização aproximada por IP com base offline (GeoLite2 City, formato `.mmdb`).

A base exige conta gratuita na MaxMind e não vem no repositório; o caminho é configurado em
`LUPA_GEOIP_CAMINHO`. Sem base, o resolvedor nulo devolve `"desconhecida"`. IP privado,
loopback ou link-local resolve para `"rede interna"` sem consultar a base. Qualquer falha de
resolução vira `"desconhecida"` e nunca impede o registro do evento.
"""

import ipaddress
from pathlib import Path
from typing import Protocol

import geoip2.database
import geoip2.errors

from lupa.config import Settings
from lupa.logging import get_logger

DESCONHECIDA = "desconhecida"
REDE_INTERNA = "rede interna"


class ResolvedorLocalizacao(Protocol):
    """Converte IP em localização aproximada legível."""

    def resolver(self, ip: str | None) -> str:
        """Resolve o IP.

        Args:
            ip: Endereço IPv4 ou IPv6, ou None.

        Returns:
            Texto como `"Goiânia, Goiás, Brasil"`, `"rede interna"` ou `"desconhecida"`.
        """
        ...


def _ip_interno(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local


class ResolvedorBase:
    """Trata IP ausente, inválido ou interno e delega o resto a `consultar`."""

    def consultar(self, ip: str) -> str:
        """Consulta a base para um IP público.

        Args:
            ip: IP público válido.

        Returns:
            Localização encontrada.
        """
        return DESCONHECIDA

    def resolver(self, ip: str | None) -> str:
        """Resolve o IP sem lançar exceção.

        Args:
            ip: Endereço IP, ou None.

        Returns:
            Localização aproximada.
        """
        try:
            endereco = ipaddress.ip_address(ip or "")
        except ValueError:
            return DESCONHECIDA
        if _ip_interno(endereco):
            return REDE_INTERNA
        try:
            return self.consultar(str(endereco))
        except Exception:
            get_logger(__name__).warning("geoip_falhou")
            return DESCONHECIDA


class ResolvedorNulo(ResolvedorBase):
    """Resolvedor sem base: IP público vira `"desconhecida"`."""


class ResolvedorMaxMind(ResolvedorBase):
    """Resolvedor que lê um arquivo GeoLite2 City (`.mmdb`)."""

    def __init__(self, caminho: Path) -> None:
        """Abre a base.

        Args:
            caminho: Caminho do arquivo `.mmdb`.
        """
        self._leitor = geoip2.database.Reader(str(caminho))

    def consultar(self, ip: str) -> str:
        """Consulta cidade, estado e país.

        Args:
            ip: IP público válido.

        Returns:
            Partes encontradas separadas por vírgula, ou `"desconhecida"`.
        """
        try:
            cidade = self._leitor.city(ip)
        except geoip2.errors.AddressNotFoundError:
            return DESCONHECIDA
        partes = [
            cidade.city.name,
            cidade.subdivisions.most_specific.name,
            cidade.country.name,
        ]
        texto = ", ".join(parte for parte in partes if parte)
        return texto or DESCONHECIDA


def criar_resolvedor(settings: Settings) -> ResolvedorLocalizacao:
    """Escolhe o resolvedor conforme a configuração.

    Args:
        settings: Configuração da aplicação.

    Returns:
        `ResolvedorMaxMind` se a base existir; senão `ResolvedorNulo`.
    """
    caminho = settings.geoip_caminho
    if caminho is None:
        return ResolvedorNulo()
    try:
        return ResolvedorMaxMind(caminho)
    except Exception:
        get_logger(__name__).warning("geoip_base_indisponivel", caminho=str(caminho))
        return ResolvedorNulo()
