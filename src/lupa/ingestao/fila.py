"""Fila de jobs de ingestão: RQ sobre Redis em produção, lista em memória nos testes.

A mensagem carrega só ids opacos (`job_id`, `gabinete_id`); o estado verdadeiro está no banco.
Mensagem perdida não perde job: o varredor do worker reenfileira jobs parados.
"""

from typing import Protocol
from uuid import UUID

from redis import Redis
from rq import Queue

from lupa.config import Settings

FUNCAO_JOB = "lupa.ingestao.worker.executar_job"


class FilaIngestao(Protocol):
    """Contrato da fila usada pela recepção e pelo varredor."""

    def enfileirar(self, job_id: UUID, gabinete_id: UUID) -> None:
        """Põe o job na fila."""


class FilaMemoria:
    """Fila em memória: guarda os pedidos para inspeção nos testes."""

    def __init__(self) -> None:
        """Cria a fila vazia."""
        self.pedidos: list[tuple[UUID, UUID]] = []

    def enfileirar(self, job_id: UUID, gabinete_id: UUID) -> None:
        """Guarda o pedido.

        Args:
            job_id: Job.
            gabinete_id: Gabinete do job.
        """
        self.pedidos.append((job_id, gabinete_id))


class FilaRQ:
    """Fila RQ; a conexão com o Redis só é aberta no primeiro uso."""

    def __init__(self, conexao: Redis, nome: str) -> None:
        """Cria a fila.

        Args:
            conexao: Cliente Redis.
            nome: Nome da fila.
        """
        self.fila = Queue(nome, connection=conexao)

    def enfileirar(self, job_id: UUID, gabinete_id: UUID) -> None:
        """Enfileira a execução de `executar_job`.

        Args:
            job_id: Job.
            gabinete_id: Gabinete do job.
        """
        self.fila.enqueue(FUNCAO_JOB, str(job_id), str(gabinete_id))


def conectar_redis(settings: Settings) -> Redis:
    """Cria o cliente Redis (sem conectar).

    Args:
        settings: Configuração com `redis_url`.

    Returns:
        Cliente Redis.
    """
    return Redis.from_url(settings.redis_url.get_secret_value())


def criar_fila(settings: Settings) -> FilaRQ:
    """Cria a fila RQ da configuração.

    Args:
        settings: Configuração.

    Returns:
        Fila RQ.
    """
    return FilaRQ(conectar_redis(settings), settings.fila_ingestao)
