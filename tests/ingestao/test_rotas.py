"""Testes das rotas de envio de arquivo e de métricas."""

from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lupa.config import Settings, get_settings
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import ArquivoTabela, JobIngestaoTabela, ProcessoTabela
from lupa.ingestao.fila import FilaMemoria
from lupa.ingestao.storage import ArmazenamentoMemoria
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
)
from tests.ingestao.arquivos import pdf_minimo, zip_por_peca

pytestmark = pytest.mark.integracao

OCTET = {"Content-Type": "application/octet-stream"}


@pytest.fixture
def app_ingestao(app_teste: FastAPI) -> FastAPI:
    """Aplicação de teste com storage e fila em memória."""
    app_teste.state.storage = ArmazenamentoMemoria()
    app_teste.state.fila = FilaMemoria()
    return app_teste


def _assessor(engine: Engine) -> UsuarioTeste:
    return criar_usuario_teste(engine, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine))


def _processo(engine: Engine, autor: UsuarioTeste, *, sigiloso: bool = False) -> UUID:
    from tests.api.test_processos import _criar_processo

    processo_id = _criar_processo(engine, autor)
    if sigiloso:
        with Session(engine) as session, session.begin():
            processo = session.get(ProcessoTabela, processo_id)
            assert processo is not None
            processo.sigiloso = True
    return processo_id


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


def _enviar(cliente: TestClient, processo: UUID, dados: bytes, nome: str) -> httpx.Response:
    return cliente.post(
        f"/processos/{processo}/arquivos", params={"nome": nome}, content=dados, headers=OCTET
    )


def _contar_arquivos(engine: Engine, processo: UUID) -> int:
    with Session(engine) as session:
        return int(
            session.scalar(select(func.count()).where(ArquivoTabela.processo_id == processo)) or 0
        )


def test_envio_de_pdf_cria_arquivo_job_objeto_evento_e_pedido_na_fila(
    app_ingestao: FastAPI, engine_teste: Engine
) -> None:
    """201, job em `recebido`, objeto no storage, `arquivo_enviado` e job enfileirado."""
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    cliente = _cliente(app_ingestao, engine_teste, assessor)
    resposta = _enviar(cliente, processo, pdf_minimo(), "autos.pdf")
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert (corpo["estado"], corpo["mime"], corpo["duplicado"]) == (
        "recebido",
        "application/pdf",
        False,
    )
    storage: ArmazenamentoMemoria = app_ingestao.state.storage
    chave = f"gabinete/{assessor.gabinete_id}/processo/{processo}/{corpo['sha256']}"
    assert storage.ler(chave) == pdf_minimo()
    with Session(engine_teste) as session:
        job = session.get(JobIngestaoTabela, UUID(corpo["job_id"]))
        assert job is not None
        assert job.estado == "recebido"
    assert app_ingestao.state.fila.pedidos == [(UUID(corpo["job_id"]), assessor.gabinete_id)]
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="arquivo_enviado")
    assert [(e.resultado, e.objeto_id) for e in eventos] == [("ok", corpo["arquivo_id"])]


def test_mesmo_arquivo_duas_vezes_nao_duplica(app_ingestao: FastAPI, engine_teste: Engine) -> None:
    """Segundo envio: 200, mesmo arquivo e job, nada novo na fila."""
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    cliente = _cliente(app_ingestao, engine_teste, assessor)
    primeiro = _enviar(cliente, processo, zip_por_peca(2), "autos.zip").json()
    resposta = _enviar(cliente, processo, zip_por_peca(2), "outro-nome.zip")
    assert resposta.status_code == 200
    segundo = resposta.json()
    assert segundo["duplicado"] is True
    assert (segundo["arquivo_id"], segundo["job_id"]) == (
        primeiro["arquivo_id"],
        primeiro["job_id"],
    )
    assert _contar_arquivos(engine_teste, processo) == 1
    assert len(app_ingestao.state.fila.pedidos) == 1


@pytest.mark.parametrize(
    ("dados", "nome", "status"),
    [
        (b"MZ\x90\x00 executavel sintetico", "autos.pdf", 415),
        (zip_por_peca(1), "autos.pdf", 415),
        (b"", "autos.pdf", 422),
    ],
    ids=["extensao_falsa", "zip_com_nome_de_pdf", "vazio"],
)
def test_conteudo_invalido_e_recusado_e_auditado(
    app_ingestao: FastAPI, engine_teste: Engine, dados: bytes, nome: str, status: int
) -> None:
    """Recusa pelo conteúdo, nada gravado, evento `arquivo_enviado` com `negado`."""
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    resposta = _enviar(_cliente(app_ingestao, engine_teste, assessor), processo, dados, nome)
    assert resposta.status_code == status
    assert _contar_arquivos(engine_teste, processo) == 0
    assert app_ingestao.state.storage.listar("gabinete/") == []
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="arquivo_enviado")
    assert [e.resultado for e in eventos] == ["negado"]


def test_arquivo_acima_do_limite_recebe_413(
    app_ingestao: FastAPI, engine_teste: Engine, settings_ficticias: Settings
) -> None:
    """Limite configurável de tamanho."""
    pequeno = settings_ficticias.model_copy(update={"upload_limite_bytes": 100})
    app_ingestao.dependency_overrides[get_settings] = lambda: pequeno
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    cliente = _cliente(app_ingestao, engine_teste, assessor)
    assert _enviar(cliente, processo, pdf_minimo(), "a.pdf").status_code == 413


def test_processo_de_outro_gabinete_da_404(app_ingestao: FastAPI, engine_teste: Engine) -> None:
    """A rota usa `exige_processo`: 404 e tentativa registrada."""
    assessor_a, assessor_b = _assessor(engine_teste), _assessor(engine_teste)
    processo_b = _processo(engine_teste, assessor_b)
    resposta = _enviar(
        _cliente(app_ingestao, engine_teste, assessor_a), processo_b, pdf_minimo(), "a.pdf"
    )
    assert resposta.status_code == 404
    assert _contar_arquivos(engine_teste, processo_b) == 0


def test_processo_sigiloso_e_bloqueado(app_ingestao: FastAPI, engine_teste: Engine) -> None:
    """Primeira versão só aceita processos públicos."""
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor, sigiloso=True)
    resposta = _enviar(
        _cliente(app_ingestao, engine_teste, assessor), processo, pdf_minimo(), "a.pdf"
    )
    assert resposta.status_code == 403
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="arquivo_enviado")
    assert [e.resultado for e in eventos] == ["negado"]


def test_fila_fora_do_ar_nao_derruba_o_envio(app_ingestao: FastAPI, engine_teste: Engine) -> None:
    """O job fica em `recebido` e o varredor do worker o recupera depois."""

    class FilaQuebrada:
        def enfileirar(self, job_id: UUID, gabinete_id: UUID) -> None:
            raise ConnectionError("redis fora do ar")

    app_ingestao.state.fila = FilaQuebrada()
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    resposta = _enviar(
        _cliente(app_ingestao, engine_teste, assessor), processo, pdf_minimo(), "a.pdf"
    )
    assert resposta.status_code == 201


def test_metricas_so_para_administrador(app_ingestao: FastAPI, engine_teste: Engine) -> None:
    """Admin lê o texto Prometheus; assessor recebe 403; anônimo 401."""
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    assessor = _assessor(engine_teste)
    processo = _processo(engine_teste, assessor)
    _enviar(_cliente(app_ingestao, engine_teste, assessor), processo, pdf_minimo(), "a.pdf")
    resposta = _cliente(app_ingestao, engine_teste, admin).get("/metricas")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/plain")
    for nome in (
        "lupa_ingestao_jobs",
        "lupa_ingestao_idade_fila_segundos",
        "lupa_ingestao_paginas_por_segundo",
        "lupa_ingestao_retries_total",
        "lupa_ingestao_falhas_total",
    ):
        assert nome in resposta.text
    assert _cliente(app_ingestao, engine_teste, assessor).get("/metricas").status_code == 403
    anonimo = TestClient(app_ingestao, base_url="https://testserver")
    assert anonimo.get("/metricas").status_code == 401
