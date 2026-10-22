"""Ponta a ponta da ingestão: upload pela API, fila Redis, worker RQ, MinIO e banco.

Desde a Etapa 4C o fluxo segue do `validado` para a extração: o job termina `concluido`, com as
páginas gravadas, e o processo fica `pronto`.

Usa os serviços reais do compose (PostgreSQL, MinIO e Redis); pula se algum estiver fora.
"""

import os
from dataclasses import replace
from typing import NoReturn
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue, SimpleWorker
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lupa.config import Settings
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import JobIngestaoTabela
from lupa.ingestao import worker
from lupa.ingestao.fila import FilaRQ
from lupa.ingestao.storage import ArmazenamentoS3, chave_objeto, criar_cliente_s3
from lupa.ingestao.worker import Dependencias
from tests.conftest import criar_gabinete_teste, criar_usuario_teste, logar
from tests.ingestao.arquivos import pdf_minimo, zip_por_peca

pytestmark = pytest.mark.integracao

EXIGIR = "LUPA_EXIGIR_INTEGRACAO"


def _indisponivel(motivo: str) -> NoReturn:
    """Pula o teste, ou falha quando `LUPA_EXIGIR_INTEGRACAO=1` (como no `verificar.sh`).

    Args:
        motivo: Serviço ausente.
    """
    if os.environ.get(EXIGIR) == "1":
        pytest.fail(f"{motivo} (exigido por {EXIGIR})")
    pytest.skip(motivo)


@pytest.fixture
def storage_s3() -> ArmazenamentoS3:
    """Storage S3 do compose (MinIO)."""
    if not os.environ.get("LUPA_MINIO_ENDPOINT"):
        _indisponivel("MinIO não configurado")
    settings = Settings()
    cliente = criar_cliente_s3(settings)
    try:
        cliente.head_bucket(Bucket=settings.minio_bucket)
    except Exception:
        _indisponivel("MinIO inacessível")
    return ArmazenamentoS3(cliente, settings.minio_bucket)


@pytest.fixture
def conexao_redis() -> Redis:
    """Redis do compose."""
    if not os.environ.get("LUPA_MINIO_ENDPOINT"):
        _indisponivel("compose não configurado")
    conexao = Redis.from_url(Settings().redis_url.get_secret_value())
    try:
        conexao.ping()
    except Exception:
        _indisponivel("Redis inacessível")
    return conexao


def test_upload_de_pdf_e_zip_ate_concluido_com_objeto_manifesto_e_paginas(
    app_teste: FastAPI,
    engine_teste: Engine,
    deps: Dependencias,
    storage_s3: ArmazenamentoS3,
    conexao_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF e ZIP sintéticos: API → MinIO → Redis → worker RQ → job `concluido` com páginas."""
    nome_fila = f"ingestao-teste-{uuid4().hex[:8]}"
    fila = FilaRQ(conexao_redis, nome_fila)
    app_teste.state.storage = storage_s3
    app_teste.state.fila = fila
    deps_s3 = replace(deps, storage=storage_s3, extrair=True)
    monkeypatch.setattr(worker, "dependencias_padrao", lambda: deps_s3)

    assessor = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    from tests.api.test_processos import _criar_processo

    processo = _criar_processo(engine_teste, assessor)
    gabinete = assessor.gabinete_id
    assert gabinete is not None
    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, assessor)

    enviados = {}
    for nome, dados in (("autos.pdf", pdf_minimo(2)), ("autos.zip", zip_por_peca(3))):
        resposta = cliente.post(
            f"/processos/{processo}/arquivos",
            params={"nome": nome},
            content=dados,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert resposta.status_code == 201, resposta.text
        enviados[nome] = resposta.json()
    assert Queue(nome_fila, connection=conexao_redis).count == 2

    SimpleWorker([Queue(nome_fila, connection=conexao_redis)], connection=conexao_redis).work(
        burst=True, with_scheduler=False
    )

    try:
        with Session(engine_teste) as session:
            for nome, paginas, entradas in (("autos.pdf", 2, 1), ("autos.zip", 3, 3)):
                job = session.get(JobIngestaoTabela, UUID(enviados[nome]["job_id"]))
                assert job is not None
                assert (job.estado, job.total_paginas) == ("concluido", paginas)
                assert job.relatorio is not None
                assert job.relatorio["paginas_extraidas"] == paginas
                assert job.manifesto is not None
                assert len(job.manifesto) == entradas
                chave = chave_objeto(gabinete, processo, enviados[nome]["sha256"])
                assert storage_s3.existe(chave)
                for entrada in job.manifesto:
                    chave_entrada = chave_objeto(gabinete, processo, entrada["sha256"])
                    assert storage_s3.existe(chave_entrada)
    finally:
        for chave in storage_s3.listar(f"gabinete/{assessor.gabinete_id}/"):
            storage_s3.apagar(chave)
        Queue(nome_fila, connection=conexao_redis).delete(delete_jobs=True)
