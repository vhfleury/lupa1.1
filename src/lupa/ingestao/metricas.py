"""Métricas Prometheus da pipeline, calculadas a cada coleta a partir do banco.

O banco é a fonte única (API e worker são processos distintos), então nada depende de
contadores em memória. Rótulos são só estados e motivos enumerados; nenhum id, nome ou texto.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import ColumnElement, Float, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from lupa.dominio.enums import EstadoJob, EstadoLote, MotivoFalha, MotivoQuarentena
from lupa.dominio.tabelas import JobIngestaoTabela, LoteIngestaoTabela

Job = JobIngestaoTabela
JANELA_VAZAO = timedelta(hours=1)
PREFIXO = "lupa_ingestao"


def _contar(
    session: Session, coluna: InstrumentedAttribute[Any], filtro: ColumnElement[bool] | None = None
) -> dict[str, int]:
    consulta = select(coluna, func.count()).group_by(coluna)
    if filtro is not None:
        consulta = consulta.where(filtro)
    return {str(chave): int(total) for chave, total in session.execute(consulta)}


class ColetorIngestao(Collector):
    """Coletor que lê o estado da pipeline numa sessão com visão de todos os gabinetes."""

    def __init__(self, session: Session, agora: datetime) -> None:
        """Cria o coletor.

        Args:
            session: Sessão com contexto de administrador.
            agora: Instante de referência.
        """
        self._session = session
        self._agora = agora

    def collect(self) -> Iterator[Metric]:
        """Produz as métricas.

        Yields:
            Famílias de métricas.
        """
        yield self._jobs_por_estado()
        yield self._lotes_por_estado()
        yield self._idade_fila()
        yield from self._paginas()
        yield self._retries()
        yield self._falhas()

    def _jobs_por_estado(self) -> Metric:
        contagem = _contar(self._session, Job.estado)
        familia = GaugeMetricFamily(
            f"{PREFIXO}_jobs", "Jobs de ingestão por estado", labels=["estado"]
        )
        for estado in EstadoJob:
            familia.add_metric([estado.value], contagem.get(estado.value, 0))
        return familia

    def _lotes_por_estado(self) -> Metric:
        contagem = _contar(self._session, LoteIngestaoTabela.estado)
        familia = GaugeMetricFamily(
            f"{PREFIXO}_lotes", "Lotes gravados por estado", labels=["estado"]
        )
        for estado in EstadoLote:
            familia.add_metric([estado.value], contagem.get(estado.value, 0))
        return familia

    def _idade_fila(self) -> Metric:
        mais_antigo = self._session.scalar(
            select(func.min(Job.criado_em)).where(Job.estado == EstadoJob.RECEBIDO.value)
        )
        idade = (self._agora - mais_antigo).total_seconds() if mais_antigo else 0.0
        return GaugeMetricFamily(
            f"{PREFIXO}_idade_fila_segundos",
            "Idade do job mais antigo ainda em recebido",
            value=max(idade, 0.0),
        )

    def _paginas(self) -> Iterator[Metric]:
        total = self._session.scalar(select(func.coalesce(func.sum(Job.total_paginas), 0)))
        yield CounterMetricFamily(
            f"{PREFIXO}_paginas", "Páginas validadas (soma dos jobs)", value=float(total or 0)
        )
        duracao = func.extract("epoch", Job.finalizado_em - Job.iniciado_em)
        paginas, segundos = self._session.execute(
            select(
                func.coalesce(func.sum(Job.total_paginas), 0),
                func.coalesce(func.sum(cast(duracao, Float)), 0.0),
            ).where(
                Job.total_paginas.is_not(None),
                Job.finalizado_em >= self._agora - JANELA_VAZAO,
            )
        ).one()
        vazao = float(paginas) / float(segundos) if segundos else 0.0
        yield GaugeMetricFamily(
            f"{PREFIXO}_paginas_por_segundo",
            "Vazão de validação na última hora",
            value=vazao,
        )

    def _retries(self) -> Metric:
        total = self._session.scalar(
            select(func.coalesce(func.sum(func.greatest(Job.tentativas - 1, 0)), 0))
        )
        return CounterMetricFamily(
            f"{PREFIXO}_retries", "Tentativas além da primeira", value=float(total or 0)
        )

    def _falhas(self) -> Metric:
        falhas = _contar(self._session, Job.motivo_falha, Job.estado == EstadoJob.FALHO.value)
        quarentenas = _contar(
            self._session, Job.motivo_quarentena, Job.motivo_quarentena.is_not(None)
        )
        familia = CounterMetricFamily(
            f"{PREFIXO}_falhas",
            "Jobs falhos ou em quarentena por motivo",
            labels=["tipo", "motivo"],
        )
        for motivo in MotivoFalha:
            familia.add_metric(["falho", motivo.value], falhas.get(motivo.value, 0))
        for motivo_q in MotivoQuarentena:
            familia.add_metric(["quarentena", motivo_q.value], quarentenas.get(motivo_q.value, 0))
        return familia


def gerar_metricas(session: Session, agora: datetime) -> bytes:
    """Gera o texto de exposição Prometheus.

    Args:
        session: Sessão com contexto de administrador.
        agora: Instante de referência.

    Returns:
        Corpo no formato de texto do Prometheus.
    """
    registro = CollectorRegistry(auto_describe=False)
    registro.register(ColetorIngestao(session, agora))
    return generate_latest(registro)
