"""Testes de banco da ingestão: lease, fencing token, lotes idempotentes, RLS e diagnóstico."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from lupa.dominio.enums import CenarioArquivo, EstadoJob, EstadoLote, MotivoQuarentena
from lupa.dominio.esquemas import DiagnosticoArquivo
from lupa.dominio.tabelas import JobIngestaoTabela, LoteIngestaoTabela
from lupa.ingestao import repositorio
from lupa.ingestao.estados import TransicaoInvalidaError
from lupa.ingestao.repositorio import LeasePerdidoError
from lupa.ingestao.worker import sessao_gabinete, sessao_sistema
from tests.ingestao.arquivos import pdf_minimo
from tests.ingestao.conftest import Relogio, SemearJob

pytestmark = pytest.mark.integracao

LEASE = timedelta(seconds=30)


def test_lease_exclusivo_expira_e_novo_dono_recebe_token_maior(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Segundo worker não toma lease válido; depois da expiração toma com token maior."""
    job = semear_job(pdf_minimo())
    gabinete = job.processo.gabinete_id
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        primeiro = repositorio.adquirir_lease(s, job.job_id, "a", relogio(), LEASE)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        assert repositorio.adquirir_lease(s, job.job_id, "b", relogio(), LEASE) is None
    relogio.avancar(31)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        segundo = repositorio.adquirir_lease(s, job.job_id, "b", relogio(), LEASE)
    assert primeiro is not None and segundo is not None
    assert (primeiro.token, segundo.token) == (1, 2)
    assert (primeiro.tentativa, segundo.tentativa) == (1, 2)


def test_heartbeat_estende_lease_e_dono_antigo_perde_tudo(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Heartbeat adia a expiração; worker com token velho não renova, não grava, não muda estado."""
    job = semear_job(pdf_minimo())
    gabinete = job.processo.gabinete_id
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        antigo = repositorio.adquirir_lease(s, job.job_id, "a", relogio(), LEASE)
    assert antigo is not None
    relogio.avancar(20)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        repositorio.renovar_lease(s, antigo, relogio(), LEASE)
    relogio.avancar(20)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        assert repositorio.adquirir_lease(s, job.job_id, "b", relogio(), LEASE) is None
    relogio.avancar(31)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        novo = repositorio.adquirir_lease(s, job.job_id, "b", relogio(), LEASE)
    assert novo is not None
    for operacao in (
        lambda s: repositorio.renovar_lease(s, antigo, relogio(), LEASE),
        lambda s: repositorio.gravar_lote(s, antigo, 1, EstadoLote.CONCLUIDO, {}),
        lambda s: repositorio.mudar_estado(s, antigo, EstadoJob.VALIDADO, relogio()),
        lambda s: repositorio.liberar_lease(s, antigo),
    ):
        with pytest.raises(LeasePerdidoError), sessao_gabinete(fabrica_sessao, gabinete) as s:
            operacao(s)


def test_lote_gravado_uma_unica_vez(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Segunda gravação do mesmo lote não duplica e devolve falso."""
    job = semear_job(pdf_minimo())
    gabinete = job.processo.gabinete_id
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        lease = repositorio.adquirir_lease(s, job.job_id, "a", relogio(), LEASE)
        assert lease is not None
        assert repositorio.gravar_lote(s, lease, 1, EstadoLote.CONCLUIDO, {"paginas": 1})
        assert not repositorio.gravar_lote(s, lease, 1, EstadoLote.CONCLUIDO, {"paginas": 9})
        lotes = repositorio.lotes_do_job(s, job.job_id)
    assert list(lotes) == [1]
    assert lotes[1].resultado == {"paginas": 1}


def test_mudar_estado_respeita_maquina_e_finaliza(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Transição inválida é recusada; quarentena grava motivo; job final não é mais tomado."""
    job = semear_job(pdf_minimo())
    gabinete = job.processo.gabinete_id
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        lease = repositorio.adquirir_lease(s, job.job_id, "a", relogio(), LEASE)
        assert lease is not None
        with pytest.raises(TransicaoInvalidaError):
            repositorio.mudar_estado(s, lease, EstadoJob.CONCLUIDO, relogio())
        linha = repositorio.mudar_estado(
            s,
            lease,
            EstadoJob.QUARENTENA,
            relogio(),
            motivo_quarentena=MotivoQuarentena.SENHA,
        )
        assert (linha.estado, linha.motivo_quarentena) == ("quarentena", "senha")
        assert linha.finalizado_em == relogio()
        repositorio.liberar_lease(s, lease)
    relogio.avancar(120)
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        assert repositorio.adquirir_lease(s, job.job_id, "b", relogio(), LEASE) is None


def test_banco_exige_motivo_em_quarentena(semear_job: SemearJob, engine_teste: Engine) -> None:
    """A constraint `quarentena_com_motivo` vale também fora do código."""
    job = semear_job(pdf_minimo())
    with pytest.raises(IntegrityError), Session(engine_teste) as s, s.begin():
        s.execute(
            text("UPDATE job_ingestao SET estado = 'quarentena' WHERE id = :id"),
            {"id": job.job_id},
        )


def test_rls_isola_jobs_e_lotes_por_gabinete(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Outro gabinete não vê o job nem consegue tomar o lease; o sistema vê todos."""
    job = semear_job(pdf_minimo())
    with sessao_gabinete(fabrica_sessao, uuid4()) as s:
        assert s.get(JobIngestaoTabela, job.job_id) is None
        assert repositorio.adquirir_lease(s, job.job_id, "x", relogio(), LEASE) is None
        assert s.scalars(select(LoteIngestaoTabela)).all() == []
    with sessao_sistema(fabrica_sessao) as s:
        assert s.get(JobIngestaoTabela, job.job_id) is not None


def test_job_unico_por_arquivo(semear_job: SemearJob, engine_teste: Engine) -> None:
    """Não existem dois jobs para o mesmo arquivo."""
    job = semear_job(pdf_minimo())
    with pytest.raises(IntegrityError), Session(engine_teste) as s, s.begin():
        repositorio.criar_job(s, job.processo.gabinete_id, job.processo.processo_id, job.arquivo_id)


def test_jobs_recuperaveis_inclui_lease_vencido_e_job_esquecido(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session], relogio: Relogio
) -> None:
    """Varredor vê job com lease vencido e job nunca tomado, mas não o ocupado."""
    ocupado, vencido, esquecido = (semear_job(pdf_minimo(n)) for n in (1, 2, 3))
    for job, duracao in ((ocupado, timedelta(hours=1)), (vencido, LEASE)):
        with sessao_gabinete(fabrica_sessao, job.processo.gabinete_id) as s:
            assert repositorio.adquirir_lease(s, job.job_id, "a", relogio(), duracao)
    relogio.avancar(61)
    with sessao_sistema(fabrica_sessao) as s:
        ids = {job_id for job_id, _ in repositorio.jobs_recuperaveis(s, relogio(), LEASE)}
    assert vencido.job_id in ids
    assert esquecido.job_id in ids
    assert ocupado.job_id not in ids


def test_diagnostico_gravado_lido_e_substituido(
    semear_job: SemearJob, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Um diagnóstico por arquivo; gravar de novo substitui."""
    job = semear_job(pdf_minimo())
    gabinete = job.processo.gabinete_id
    primeiro = DiagnosticoArquivo(
        arquivo_id=job.arquivo_id,
        cenario=CenarioArquivo.PDF_LISO,
        total_paginas=1,
        tem_indice=False,
        sinais={"bookmarks": 0},
    )
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        assert repositorio.obter_diagnostico(s, job.arquivo_id) is None
        repositorio.salvar_diagnostico(s, gabinete, primeiro)
    segundo = primeiro.model_copy(update={"cenario": CenarioArquivo.PDF_COM_INDICE})
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        repositorio.salvar_diagnostico(s, gabinete, segundo)
        lido = repositorio.obter_diagnostico(s, job.arquivo_id)
    assert lido is not None
    assert (lido.cenario, lido.sinais) == (CenarioArquivo.PDF_COM_INDICE, {"bookmarks": 0})
    with sessao_gabinete(fabrica_sessao, gabinete) as s:
        encontrado = repositorio.obter_job_por_arquivo(s, job.arquivo_id)
    assert encontrado is not None
    assert encontrado.id == job.job_id
