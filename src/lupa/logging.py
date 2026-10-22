"""Configuração de logging estruturado em JSON sem conteúdo sensível."""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

CAMPOS_PROIBIDOS = frozenset(
    {"senha", "password", "token", "texto", "conteudo", "pergunta", "resposta"}
)


class CampoProibidoError(ValueError):
    """Indica que um evento de log carregava um campo sensível proibido."""


class FiltroCamposProibidos:
    """Processador structlog que rejeita ou remove campos sensíveis."""

    def __init__(self, *, estrito: bool) -> None:
        """Cria o filtro.

        Args:
            estrito: Se verdadeiro, lança erro ao achar campo proibido; senão, remove-o.
        """
        self._estrito = estrito

    def __call__(
        self, logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        """Filtra o evento de log.

        Args:
            logger: Logger de origem (não usado).
            method_name: Nome do método de log (não usado).
            event_dict: Campos do evento.

        Returns:
            O evento sem campos proibidos.

        Raises:
            CampoProibidoError: Em modo estrito, se houver campo proibido.
        """
        encontrados = CAMPOS_PROIBIDOS.intersection(k.lower() for k in event_dict)
        if not encontrados:
            return event_dict
        if self._estrito:
            raise CampoProibidoError(f"campos proibidos no log: {sorted(encontrados)}")
        return {k: v for k, v in event_dict.items() if k.lower() not in CAMPOS_PROIBIDOS}


def _garantir_request_id(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict.setdefault("request_id", None)
    return event_dict


def configurar_logging(*, nivel: str = "INFO", estrito: bool = False) -> None:
    """Configura structlog para emitir JSON com campos fixos.

    Args:
        nivel: Nível mínimo de log.
        estrito: Se verdadeiro, campos proibidos lançam erro (usado em testes).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            FiltroCamposProibidos(estrito=estrito),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _garantir_request_id,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(nivel)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(nome: str) -> Any:
    """Retorna um logger estruturado.

    Args:
        nome: Nome lógico do componente.

    Returns:
        Logger structlog vinculado ao nome.
    """
    return structlog.get_logger(nome)
