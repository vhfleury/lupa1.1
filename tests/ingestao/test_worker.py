"""Testes do worker: validação por lotes, recuperação de lease, fencing, quarentena e falhas."""

import zipfile
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from lupa.config import Settings
from lupa.dominio.enums import EstadoJob, EstadoLote, MotivoFalha, MotivoQuarentena
from lupa.dominio.tabelas import JobIngestaoTabela, LoteIngestaoTabela
from lupa.ingestao import repositorio
from lupa.ingestao.fila import FilaMemoria
from lupa.ingestao.quarentena import pode_extrair
from lupa.ingestao.sandbox import LimitesSandbox
from lupa.ingestao.storage import ArmazenamentoMemoria, chave_objeto
from lupa.ingestao.worker import (
    Dependencias,
    dependencias_da_configuracao,
    desfecho_dos_lotes,
    processar_job,
    sessao_gabinete,
    sessao_sistema,
    varrer,
)
from tests.ingestao.arquivos import (
    pdf_assinado,
    pdf_bomba,
    pdf_com_senha,
    pdf_corrompido,
    pdf_minimo,
    pdf_truncado,
    zip_cifrado,
    zip_com_info,
    zip_de,
    zip_por_peca,
)
from tests.ingestao.conftest import JobSemeado, Relogio, SemearJob, outro_worker

pytestmark = pytest.mark.integracao


class MorteSimulada(BaseException):
    """Simula a morte do processo worker (não é capturada como `Exception`)."""


def _job(fabrica: sessionmaker[Session], job: JobSemeado) -> JobIngestaoTabela:
    with sessao_sistema(fabrica) as s:
        linha = s.get(JobIngestaoTabela, job.job_id)
        assert linha is not None
        s.expunge(linha)
        return linha


def _lotes(fabrica: sessionmaker[Session], job_id: UUID) -> list[LoteIngestaoTabela]:
    with sessao_sistema(fabrica) as s:
        linhas = list(
            s.scalars(
                select(LoteIngestaoTabela)
                .where(LoteIngestaoTabela.job_id == job_id)
                .order_by(LoteIngestaoTabela.numero)
            )
        )
        s.expunge_all()
        return linhas


def _processar(deps: Dependencias, job: JobSemeado) -> EstadoJob | None:
    return processar_job(deps, job.job_id, job.processo.gabinete_id)


def test_pdf_valido_chega_a_validado_com_manifesto(
    deps: Dependencias, semear_job: SemearJob
) -> None:
    """PDF sintético: um lote, total de páginas e manifesto com o hash do arquivo."""
    dados = pdf_minimo(3)
    job = semear_job(dados, "autos.pdf")
    assert _processar(deps, job) is EstadoJob.VALIDADO
    linha = _job(deps.fabrica, job)
    assert (linha.estado, linha.total_paginas, linha.lease_dono) == ("validado", 3, None)
    assert linha.manifesto is not None
    assert [e["nome"] for e in linha.manifesto] == ["autos.pdf"]
    assert linha.manifesto[0]["tamanho_bytes"] == len(dados)
    assert [lote.numero for lote in _lotes(deps.fabrica, job.job_id)] == [1]
    assert pode_extrair(EstadoJob(linha.estado))


def test_zip_por_peca_vira_um_lote_por_entrada_em_ordem_de_nome(
    deps: Dependencias, semear_job: SemearJob, storage_memoria: ArmazenamentoMemoria
) -> None:
    """ZIP com três PDFs: manifesto ordenado por nome, hash por entrada, entradas no storage."""
    job = semear_job(zip_por_peca(3), "autos.zip")
    assert _processar(deps, job) is EstadoJob.VALIDADO
    linha = _job(deps.fabrica, job)
    assert linha.manifesto is not None
    assert [e["nome"] for e in linha.manifesto] == ["01-peca.pdf", "02-peca.pdf", "03-peca.pdf"]
    assert [e["ordem"] for e in linha.manifesto] == [1, 2, 3]
    assert linha.total_paginas == 3
    for entrada in linha.manifesto:
        chave = chave_objeto(job.processo.gabinete_id, job.processo.processo_id, entrada["sha256"])
        assert storage_memoria.existe(chave)
    assert len(_lotes(deps.fabrica, job.job_id)) == 3


def test_worker_morto_no_meio_tem_lease_recuperado_sem_duplicar_lotes(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio
) -> None:
    """Morte depois do lote 1; outro worker retoma após a expiração e grava só 2 e 3."""
    job = semear_job(zip_por_peca(3), "autos.zip")

    def _morrer(numero: int) -> None:
        if numero == 1:
            raise MorteSimulada

    with pytest.raises(MorteSimulada):
        processar_job(deps, job.job_id, job.processo.gabinete_id, ao_gravar_lote=_morrer)
    assert _job(deps.fabrica, job).lease_dono == "worker-teste-a"
    sucessor = outro_worker(deps, "worker-teste-b")
    assert _processar(sucessor, job) is None
    relogio.avancar(deps.duracao_lease.total_seconds() + 1)
    with sessao_sistema(deps.fabrica) as s:
        recuperaveis = repositorio.jobs_recuperaveis(s, relogio(), deps.duracao_lease)
    assert (job.job_id, job.processo.gabinete_id) in recuperaveis
    assert _processar(sucessor, job) is EstadoJob.VALIDADO
    lotes = _lotes(deps.fabrica, job.job_id)
    assert [(lote.numero, lote.fencing_token) for lote in lotes] == [(1, 1), (2, 2), (3, 2)]
    linha = _job(deps.fabrica, job)
    assert (linha.tentativas, linha.fencing_token, linha.total_paginas) == (2, 2, 3)


def test_worker_antigo_que_volta_nao_grava_depois_do_sucessor(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio
) -> None:
    """Fencing: o worker que perdeu o lease tenta gravar o lote 2 e é recusado."""
    job = semear_job(zip_por_peca(2), "autos.zip")
    gabinete = job.processo.gabinete_id
    with sessao_gabinete(deps.fabrica, gabinete) as s:
        antigo = repositorio.adquirir_lease(s, job.job_id, "a", relogio(), deps.duracao_lease)
    assert antigo is not None
    relogio.avancar(deps.duracao_lease.total_seconds() + 1)
    assert _processar(outro_worker(deps, "b"), job) is EstadoJob.VALIDADO
    with pytest.raises(repositorio.LeasePerdidoError), sessao_gabinete(deps.fabrica, gabinete) as s:
        repositorio.gravar_lote(s, antigo, 2, EstadoLote.CONCLUIDO, {"paginas": 99})
    with sessao_sistema(deps.fabrica) as s:
        total = s.scalar(select(func.count()).where(LoteIngestaoTabela.job_id == job.job_id))
    assert total == 2


def test_lease_perdido_no_meio_interrompe_sem_gravar(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio
) -> None:
    """Se outro worker toma o job durante o processamento, o primeiro para e devolve None."""
    job = semear_job(zip_por_peca(2), "autos.zip")
    sucessor = outro_worker(deps, "b")

    def _ser_atropelado(numero: int) -> None:
        relogio.avancar(deps.duracao_lease.total_seconds() + 1)
        with sessao_gabinete(deps.fabrica, job.processo.gabinete_id) as s:
            assert repositorio.adquirir_lease(
                s, job.job_id, sucessor.dono, relogio(), deps.duracao_lease
            )

    resultado = processar_job(
        deps, job.job_id, job.processo.gabinete_id, ao_gravar_lote=_ser_atropelado
    )
    assert resultado is None
    assert [lote.numero for lote in _lotes(deps.fabrica, job.job_id)] == [1]


@pytest.mark.parametrize(
    ("dados", "nome", "motivo"),
    [
        (pdf_com_senha(), "autos.pdf", MotivoQuarentena.SENHA),
        (pdf_truncado(), "autos.pdf", MotivoQuarentena.TRUNCADO),
        (pdf_corrompido(), "autos.pdf", MotivoQuarentena.CORROMPIDO),
        (pdf_assinado(cobre_tudo=False), "autos.pdf", MotivoQuarentena.ASSINATURA_INVALIDA),
        (
            zip_de({"a.pdf": pdf_minimo(), "b.txt": b"texto"}),
            "a.zip",
            MotivoQuarentena.TIPO_INVALIDO,
        ),
        (zip_de({"../fora.pdf": pdf_minimo()}), "a.zip", MotivoQuarentena.ZIP_MALICIOSO),
        (zip_de({"p.pdf": pdf_com_senha()}), "a.zip", MotivoQuarentena.SENHA),
        (zip_cifrado(), "a.zip", MotivoQuarentena.SENHA),
        (b"PK\x03\x04" + b"\x00" * 64, "a.zip", MotivoQuarentena.CORROMPIDO),
    ],
    ids=[
        "senha",
        "truncado",
        "corrompido",
        "assinatura",
        "tipo",
        "zip_malicioso",
        "zip_senha",
        "zip_cifrado",
        "zip_corrompido",
    ],
)
def test_cada_falha_vai_para_quarentena_com_motivo_e_nao_avanca(
    deps: Dependencias,
    semear_job: SemearJob,
    relogio: Relogio,
    dados: bytes,
    nome: str,
    motivo: MotivoQuarentena,
) -> None:
    """Quarentena com motivo legível; job final, não é retomado nem pode ir à extração."""
    job = semear_job(dados, nome)
    assert _processar(deps, job) is EstadoJob.QUARENTENA
    linha = _job(deps.fabrica, job)
    assert (linha.estado, linha.motivo_quarentena) == ("quarentena", motivo.value)
    assert not pode_extrair(EstadoJob(linha.estado))
    relogio.avancar(3600)
    assert _processar(outro_worker(deps, "b"), job) is None
    assert _job(deps.fabrica, job).estado == "quarentena"


def test_pdf_com_stream_gigante_e_morto_pelo_limite_e_job_falha(
    deps: Dependencias, semear_job: SemearJob, tmp_path: Path
) -> None:
    """Bomba de descompressão: o sandbox é morto pelo limite de memória; job `falho`."""
    caminho = tmp_path / "bomba.pdf"
    pdf_bomba(caminho, 768)
    job = semear_job(caminho.read_bytes(), "bomba.pdf")
    limitado = replace(deps, limites_sandbox=LimitesSandbox(512, 20, 60))
    assert _processar(limitado, job) is EstadoJob.FALHO
    linha = _job(deps.fabrica, job)
    assert (linha.estado, linha.motivo_falha) == ("falho", MotivoFalha.LIMITE_MEMORIA.value)
    assert linha.estado != EstadoJob.CONCLUIDO.value


def test_tempo_esgotado_no_sandbox_marca_falho(deps: Dependencias, semear_job: SemearJob) -> None:
    """Limite de tempo de parede também termina em `falho` com motivo."""
    job = semear_job(pdf_minimo(), "autos.pdf")
    lento = replace(deps, limites_sandbox=LimitesSandbox(512, 20, 0.001))
    assert _processar(lento, job) is EstadoJob.FALHO
    assert _job(deps.fabrica, job).motivo_falha == MotivoFalha.TEMPO_ESGOTADO.value


def test_objeto_ausente_no_storage_marca_falho(
    deps: Dependencias, semear_job: SemearJob, storage_memoria: ArmazenamentoMemoria
) -> None:
    """Arquivo registrado mas sumido do storage: `falho` com `arquivo_ausente`."""
    job = semear_job(pdf_minimo(), "autos.pdf")
    for chave in storage_memoria.listar("gabinete/"):
        storage_memoria.apagar(chave)
    assert _processar(deps, job) is EstadoJob.FALHO
    assert _job(deps.fabrica, job).motivo_falha == MotivoFalha.ARQUIVO_AUSENTE.value


def test_tentativas_esgotadas_marcam_falho(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio
) -> None:
    """Depois de `max_tentativas` leases vencidos, a próxima aquisição marca `falho`."""
    job = semear_job(pdf_minimo(), "autos.pdf")
    for _ in range(deps.max_tentativas):
        with sessao_gabinete(deps.fabrica, job.processo.gabinete_id) as s:
            assert repositorio.adquirir_lease(s, job.job_id, "x", relogio(), deps.duracao_lease)
        relogio.avancar(deps.duracao_lease.total_seconds() + 1)
    assert _processar(deps, job) is EstadoJob.FALHO
    assert _job(deps.fabrica, job).motivo_falha == MotivoFalha.ERRO_INTERNO.value


def test_job_ja_validado_nao_e_reprocessado(deps: Dependencias, semear_job: SemearJob) -> None:
    """Mensagem repetida na fila não refaz o job."""
    job = semear_job(pdf_minimo(), "autos.pdf")
    assert _processar(deps, job) is EstadoJob.VALIDADO
    assert _processar(deps, job) is None
    assert len(_lotes(deps.fabrica, job.job_id)) == 1


def test_varredor_reenfileira_job_esquecido(
    deps: Dependencias, semear_job: SemearJob, relogio: Relogio
) -> None:
    """Job em `recebido` sem lease há mais de 30 s volta para a fila."""
    job = semear_job(pdf_minimo(), "autos.pdf")
    fila = FilaMemoria()
    relogio.avancar(31)
    assert varrer(deps, fila) >= 1
    assert (job.job_id, job.processo.gabinete_id) in fila.pedidos


def test_desfecho_falha_vence_quarentena() -> None:
    """Combinação dos lotes: falha antes de quarentena antes de validado."""
    assert desfecho_dos_lotes([{"paginas": 1}]).estado is EstadoJob.VALIDADO
    misto = [{"motivo_quarentena": "senha"}, {"motivo_falha": "limite_cpu"}]
    assert desfecho_dos_lotes(misto).motivo_falha is MotivoFalha.LIMITE_CPU


def test_zip_com_link_simbolico_vai_para_quarentena(
    deps: Dependencias, semear_job: SemearJob
) -> None:
    """Entrada marcada como link simbólico é recusada antes de extrair."""
    info = zipfile.ZipInfo("link.pdf")
    info.external_attr = 0o120777 << 16
    job = semear_job(zip_com_info(info, b"/etc/passwd"), "a.zip")
    assert _processar(deps, job) is EstadoJob.QUARENTENA
    assert _job(deps.fabrica, job).motivo_quarentena == MotivoQuarentena.ZIP_MALICIOSO.value


def test_dependencias_montadas_da_configuracao(
    settings_ficticias: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configuração vira dependências; `dependencias_padrao` é criada uma vez."""
    from lupa.ingestao import worker

    memoria = settings_ficticias.model_copy(update={"storage_backend": "memoria"})
    montadas = dependencias_da_configuracao(memoria)
    assert isinstance(getattr(montadas.storage, "interno", None), ArmazenamentoMemoria)
    assert montadas.duracao_lease.total_seconds() == memoria.lease_segundos
    assert montadas.dono.count(":") == 2
    monkeypatch.setattr(worker, "get_settings", lambda: memoria)
    worker.dependencias_padrao.cache_clear()
    try:
        assert worker.dependencias_padrao() is worker.dependencias_padrao()
    finally:
        worker.dependencias_padrao.cache_clear()


def test_executar_job_recebe_ids_em_texto(
    deps: Dependencias, semear_job: SemearJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ponto de entrada do RQ converte os ids e usa as dependências do processo."""
    from lupa.ingestao import worker

    job = semear_job(pdf_minimo(), "autos.pdf")
    monkeypatch.setattr(worker, "dependencias_padrao", lambda: deps)
    worker.executar_job(str(job.job_id), str(job.processo.gabinete_id))
    assert _job(deps.fabrica, job).estado == "validado"
