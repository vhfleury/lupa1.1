"""Testes de observabilidade: valores das métricas e logs do worker sem texto dos autos."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from lupa.dominio.enums import EstadoJob
from lupa.dominio.tabelas import JobIngestaoTabela
from lupa.ingestao.metricas import gerar_metricas
from lupa.ingestao.worker import Dependencias, processar_job, sessao_sistema
from lupa.logging import CAMPOS_PROIBIDOS, configurar_logging
from tests.ingestao.arquivos import TEXTO_SENTINELA, pdf_com_senha, pdf_minimo, zip_por_peca
from tests.ingestao.conftest import Relogio, SemearJob

pytestmark = pytest.mark.integracao


def _amostras(
    fabrica: sessionmaker[Session], agora: datetime
) -> dict[tuple[str, tuple[str, ...]], float]:
    with sessao_sistema(fabrica) as session:
        texto = gerar_metricas(session, agora).decode()
    valores: dict[tuple[str, tuple[str, ...]], float] = {}
    for familia in text_string_to_metric_families(texto):
        for amostra in familia.samples:
            valores[(amostra.name, tuple(sorted(amostra.labels.values())))] = amostra.value
    return valores


IDADE_SEMEADA = timedelta(seconds=30)


def _fixar_criado_em(engine: Engine, job_ids: list[object], instante: datetime) -> None:
    """Fixa `criado_em` dos jobs do teste: a idade da fila deixa de depender do relógio real."""
    with Session(engine) as session, session.begin():
        session.execute(
            update(JobIngestaoTabela)
            .where(JobIngestaoTabela.id.in_(job_ids))
            .values(criado_em=instante)
        )


def _mais_antigo_em_recebido(engine: Engine) -> datetime:
    """Menor `criado_em` em `recebido` (inclui jobs que outros testes deixaram na fila)."""
    with Session(engine) as session:
        valor = session.scalar(
            select(func.min(JobIngestaoTabela.criado_em)).where(
                JobIngestaoTabela.estado == EstadoJob.RECEBIDO.value
            )
        )
    assert valor is not None
    return valor


def test_metricas_refletem_jobs_paginas_retries_e_falhas(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio, engine_teste: Engine
) -> None:
    """Contagens por estado, fila, páginas, vazão, retries e falhas por motivo.

    A idade da fila é verificada de forma exata: os jobs do teste têm `criado_em` fixado em
    relação ao relógio injetado, e o valor esperado é calculado sobre o estado real da fila
    no banco compartilhado (jobs que outros testes deixaram em `recebido` só podem aumentá-la).
    """
    antes = _amostras(deps.fabrica, relogio())
    validado = semear_job(pdf_minimo(4), "a.pdf")
    quarentena = semear_job(pdf_com_senha(), "b.pdf")
    pendente = semear_job(zip_por_peca(1), "c.zip")
    _fixar_criado_em(
        engine_teste,
        [validado.job_id, quarentena.job_id, pendente.job_id],
        relogio() - IDADE_SEMEADA,
    )
    relogio.avancar(2)
    processar_job(deps, validado.job_id, validado.processo.gabinete_id)
    processar_job(deps, quarentena.job_id, quarentena.processo.gabinete_id)
    depois = _amostras(deps.fabrica, relogio())

    def delta(nome: str, *rotulos: str) -> float:
        chave = (nome, tuple(sorted(rotulos)))
        return depois[chave] - antes.get(chave, 0.0)

    assert delta("lupa_ingestao_jobs", "validado") == 1
    assert delta("lupa_ingestao_jobs", "quarentena") == 1
    assert delta("lupa_ingestao_jobs", "recebido") == 1
    assert delta("lupa_ingestao_paginas_total") == 4
    assert delta("lupa_ingestao_falhas_total", "quarentena", "senha") == 1
    assert depois[("lupa_ingestao_falhas_total", ("falho", "limite_memoria"))] >= 0
    idade = depois[("lupa_ingestao_idade_fila_segundos", ())]
    esperada = (relogio() - _mais_antigo_em_recebido(engine_teste)).total_seconds()
    assert idade == pytest.approx(esperada)
    assert idade >= (IDADE_SEMEADA + timedelta(seconds=2)).total_seconds()
    assert depois[("lupa_ingestao_paginas_por_segundo", ())] >= 0
    assert ("lupa_ingestao_retries_total", ()) in depois
    assert delta("lupa_ingestao_lotes", "concluido") == 1
    assert delta("lupa_ingestao_lotes", "falho") == 1


def test_fila_vazia_tem_idade_zero(deps: Dependencias) -> None:
    """Sem job em `recebido` mais antigo que o instante, a idade não fica negativa."""
    passado = datetime(2000, 1, 1, tzinfo=UTC)
    assert _amostras(deps.fabrica, passado)[("lupa_ingestao_idade_fila_segundos", ())] == 0


def test_nenhum_log_do_worker_carrega_texto_dos_autos(
    deps: Dependencias, semear_job: SemearJob, capsys: pytest.CaptureFixture[str]
) -> None:
    """Logs só com ids, estados e contagens: sem o texto sentinela, sem nome de arquivo."""
    configurar_logging(nivel="DEBUG", estrito=True)
    nome_sensivel = f"{TEXTO_SENTINELA}-nome.zip"
    trabalhos = [
        semear_job(zip_por_peca(2), nome_sensivel),
        semear_job(pdf_minimo(2), f"{TEXTO_SENTINELA}.pdf"),
        semear_job(pdf_com_senha(), "senha.pdf"),
    ]
    capsys.readouterr()
    for job in trabalhos:
        processar_job(deps, job.job_id, job.processo.gabinete_id)
    saida = capsys.readouterr()
    linhas = [json.loads(linha) for linha in saida.out.splitlines() if linha.strip()]
    assert linhas, "o worker deveria ter emitido logs"
    assert TEXTO_SENTINELA not in saida.out + saida.err
    for linha in linhas:
        assert not CAMPOS_PROIBIDOS & {chave.lower() for chave in linha}
    eventos = {linha["event"] for linha in linhas}
    assert {"lote_gravado", "job_finalizado"} <= eventos
