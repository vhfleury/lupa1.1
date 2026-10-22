"""Eventos no banco: worker até achados, pseudonimização, idempotência, versão e cache (4F.5-4F.8).

Usa a extração da sessão (`extracao_sessao`): o PDF sintético com índice é extraído uma vez e
cada teste recebe um processo novo do mesmo gabinete, servido pelo cache por SHA-256.
"""

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from structlog.testing import capture_logs

from lupa.dominio.enums import EstadoJob, PapelUsuario, StatusFato, StatusProcesso
from lupa.dominio.tabelas import (
    AchadoTabela,
    AnotacaoTabela,
    ArquivoTabela,
    EventoAuditoriaTabela,
    EvidenciaTabela,
    FatoEvidenciaTabela,
    FatoTabela,
    JobIngestaoTabela,
    PaginaTabela,
    PecaTabela,
    ProcessoTabela,
    ReuIdentidadeTabela,
    ReuTabela,
)
from lupa.ingestao import cache
from lupa.ingestao.eventos.etapa import achados_do_processo, processar_eventos
from lupa.ingestao.eventos.padroes import padroes_padrao
from lupa.ingestao.extrator_paginas import VERSAO_EXTRATOR
from lupa.ingestao.sandbox import ResultadoSandbox
from lupa.ingestao.worker import sessao_gabinete
from lupa.seguranca.chaves import decifrar_identidade
from lupa.seguranca.contexto import obter_cofre
from lupa.sinteticos.achados import comparar
from lupa.sinteticos.gabarito import Cenario
from tests.conftest import criar_gabinete_teste, criar_usuario_teste, eventos_do_banco, logar
from tests.ingestao.conftest import AutosSinteticos, ExtracaoSessao, lacrar_e_processar

pytestmark = pytest.mark.integracao


@pytest.fixture
def processado(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> dict[str, Any]:
    """Processo novo do assessor da sessão, processado até achados."""
    return lacrar_e_processar(extracao_sessao, engine_teste, tmp_path)


def _contar(engine: Engine, tabela: Any, **filtros: Any) -> int:
    with Session(engine) as session:
        return int(
            session.scalar(select(func.count()).select_from(tabela).filter_by(**filtros)) or 0
        )


def _identidade(engine: Engine, processo: UUID) -> ReuIdentidadeTabela:
    with Session(engine) as session:
        return session.scalars(
            select(ReuIdentidadeTabela)
            .join(ReuTabela, ReuTabela.id == ReuIdentidadeTabela.reu_id)
            .where(ReuTabela.processo_id == processo)
        ).one()


def _texto_do_processo(engine: Engine, processo: UUID, arquivo: UUID) -> str:
    with Session(engine) as session:
        fatos = list(session.scalars(select(FatoTabela).where(FatoTabela.processo_id == processo)))
        trechos = session.scalars(
            select(EvidenciaTabela.trecho)
            .join(FatoEvidenciaTabela, FatoEvidenciaTabela.evidencia_id == EvidenciaTabela.id)
            .where(FatoEvidenciaTabela.fato_id.in_([f.id for f in fatos]))
        ).all()
        achados = session.scalars(select(AchadoTabela).where(AchadoTabela.processo_id == processo))
        suspeitos = session.scalars(
            select(PaginaTabela.trechos_suspeitos).where(PaginaTabela.arquivo_id == arquivo)
        ).all()
        eventos = session.scalars(
            select(EventoAuditoriaTabela).where(EventoAuditoriaTabela.processo_id == processo)
        ).all()
        partes = [
            [f.valor for f in fatos],
            list(trechos),
            [(a.valores, a.explicacao) for a in achados],
            list(suspeitos),
            [{c.name: str(getattr(e, c.name)) for c in e.__table__.columns} for e in eventos],
        ]
    return json.dumps(partes, ensure_ascii=False, default=str)


def test_worker_grava_reus_fatos_e_achados_sem_nome_real(
    app_teste: FastAPI,
    engine_teste: Engine,
    extracao_sessao: ExtracaoSessao,
    tmp_path: Path,
) -> None:
    """Job concluído grava réu pseudonimizado, fatos automáticos e achados, sem o nome real.

    O nome e o CPF do réu não aparecem em fato, evidência de fato, achado, trecho suspeito,
    auditoria nem log; a rota de achados é auditada.
    """
    with capture_logs() as logs:
        processado = lacrar_e_processar(extracao_sessao, engine_teste, tmp_path)
    processo, lacre = processado["processo"], processado["lacre"]
    with Session(engine_teste) as session:
        job = session.get_one(JobIngestaoTabela, lacre.job_id)
        status = session.get_one(ProcessoTabela, processo).status
        reus = list(session.scalars(select(ReuTabela).where(ReuTabela.processo_id == processo)))
        fatos = list(session.scalars(select(FatoTabela).where(FatoTabela.processo_id == processo)))
    assert job.relatorio is not None
    resumo = job.relatorio["eventos"]
    assert "erro" not in resumo
    assert resumo["fatos"] == len(fatos) > 0
    assert resumo["sem_trecho"] == 0
    assert status == StatusProcesso.PRONTO.value
    assert [r.pseudonimo for r in reus] == ["REU-01"]
    assert all(f.status == StatusFato.AUTOMATICO.value and f.extraido_por == "regra" for f in fatos)
    assert {f.versao_extrator for f in fatos} == {padroes_padrao().versao_extrator}
    assert any(
        isinstance(f.valor, dict) and f.valor.get("reu_id") == str(reus[0].id) for f in fatos
    )

    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, processado["assessor"])
    resposta = cliente.get(f"/processos/{processo}/achados")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "pronto"
    assert sorted(a["validacao"] for a in corpo["achados"]) == [
        "prescricao_abstrata",
        "revisao_preventiva",
        "tempestividade_recurso",
    ]
    eventos = eventos_do_banco(engine_teste, processo_id=processo, acao="processo_aberto")
    assert any(e.objeto_id == f"/processos/{processo}/achados" for e in eventos)

    identidade = _identidade(engine_teste, processo)
    cofre = obter_cofre()
    nome = decifrar_identidade(cofre, identidade.gabinete_id, identidade.nome) or ""
    documento = decifrar_identidade(cofre, identidade.gabinete_id, identidade.documento) or ""
    assert identidade.nome.startswith(("vault:v", "mem:v"))
    assert len(nome.split()) >= 2 and documento
    texto = _texto_do_processo(engine_teste, processo, lacre.arquivo_id)
    registro = json.dumps(logs, ensure_ascii=False, default=str)
    for termo in (nome, documento):
        assert termo not in texto
        assert termo not in registro


def test_rota_de_achados_isolada_por_gabinete(
    app_teste: FastAPI, engine_teste: Engine, processado: dict[str, Any]
) -> None:
    """Assessor de outro gabinete recebe 404."""
    outro = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, outro)
    assert cliente.get(f"/processos/{processado['processo']}/achados").status_code == 404


def test_achados_batem_com_o_resultado_esperado_do_gabarito(
    extracao_sessao: ExtracaoSessao,
    processado: dict[str, Any],
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Na data de referência do gabarito, os achados sobre os fatos gravados batem (4F.7)."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_INDICE]
    gabinete = processado["assessor"].gabinete_id
    with sessao_gabinete(extracao_sessao.deps.fabrica, gabinete) as session:
        achados = achados_do_processo(
            session, processado["processo"], "criminal", gabarito.processo.data_referencia
        )
    comparacao = comparar(gabarito.resultado_esperado, achados)
    assert all(c.resultado_igual for c in comparacao), comparacao
    assert all(c.valores_iguais for c in comparacao), comparacao


def _paginas_e_pecas(engine: Engine, arquivo: UUID) -> tuple[list[Any], list[Any]]:
    with Session(engine) as session:
        paginas = session.execute(
            select(PaginaTabela.id, PaginaTabela.hash_texto, PaginaTabela.versao_extrator)
            .where(PaginaTabela.arquivo_id == arquivo)
            .order_by(PaginaTabela.numero)
        ).all()
        pecas = session.execute(
            select(PecaTabela.id, PecaTabela.tipo).where(PecaTabela.arquivo_id == arquivo)
        ).all()
    return list(paginas), list(pecas)


def test_reprocessar_mesma_versao_nao_duplica_e_nova_versao_refaz_so_os_eventos(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, processado: dict[str, Any]
) -> None:
    """Mesma versão não grava nada; versão nova refaz só os fatos (4F.6 e 4F.8).

    O fato anotado fica com a versão antiga e, por ter a mesma chave natural, não é duplicado;
    páginas e peças ficam intocadas.
    """
    processo, gabinete = processado["processo"], processado["assessor"].gabinete_id
    arquivo = processado["lacre"].arquivo_id
    fabrica = extracao_sessao.deps.fabrica
    antes = _paginas_e_pecas(engine_teste, arquivo)
    total = _contar(engine_teste, FatoTabela, processo_id=processo)
    achados = _contar(engine_teste, AchadoTabela, processo_id=processo)
    with sessao_gabinete(fabrica, gabinete) as session:
        resumo = processar_eventos(
            session, gabinete, processo, extracao_sessao.deps.relogio().date()
        )
    assert (resumo["fatos_gravados"], resumo["fatos_removidos"], resumo["achados_gravados"]) == (
        0,
        0,
        0,
    )
    assert _contar(engine_teste, FatoTabela, processo_id=processo) == total
    assert _contar(engine_teste, AchadoTabela, processo_id=processo) == achados

    with Session(engine_teste) as session, session.begin():
        anotado = session.scalars(
            select(FatoTabela).where(FatoTabela.processo_id == processo)
        ).first()
        assert anotado is not None
        session.add(
            AnotacaoTabela(
                id=uuid4(),
                gabinete_id=gabinete,
                fato_id=anotado.id,
                usuario_id=processado["assessor"].id,
                texto="conferir",
            )
        )
    nova = replace(padroes_padrao(), versao="teste-nova")
    with sessao_gabinete(fabrica, gabinete) as session:
        resumo = processar_eventos(
            session, gabinete, processo, extracao_sessao.deps.relogio().date(), nova
        )
    assert resumo["fatos_removidos"] == total - 1
    assert resumo["fatos_gravados"] == total - 1
    with Session(engine_teste) as session:
        versoes = list(
            session.scalars(
                select(FatoTabela.versao_extrator).where(FatoTabela.processo_id == processo)
            )
        )
    assert sorted(set(versoes)) == sorted({nova.versao_extrator, padroes_padrao().versao_extrator})
    assert versoes.count(nova.versao_extrator) == total - 1
    assert len(versoes) == total
    assert _paginas_e_pecas(engine_teste, arquivo) == antes


def _executor_proibido(*_args: Any, **_kwargs: Any) -> ResultadoSandbox:
    raise AssertionError("extração não deveria rodar: as páginas vêm do cache")


def test_segundo_upload_do_mesmo_arquivo_vem_do_cache_em_segundos(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> None:
    """Outro processo do mesmo gabinete: nenhuma página é extraída de novo (4F.8)."""
    sem_extracao = replace(
        extracao_sessao, deps=replace(extracao_sessao.deps, executor=_executor_proibido)
    )
    inicio = time.perf_counter()
    processado = lacrar_e_processar(sem_extracao, engine_teste, tmp_path)
    segundos = time.perf_counter() - inicio
    arquivo = processado["lacre"].arquivo_id
    paginas = _contar(engine_teste, PaginaTabela, arquivo_id=arquivo)
    assert paginas > 0
    assert _contar(engine_teste, PecaTabela, arquivo_id=arquivo) > 0
    assert _contar(engine_teste, FatoTabela, processo_id=processado["processo"]) > 0
    assert segundos < 30


def test_cache_nunca_atravessa_gabinete_nem_versao(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, processado: dict[str, Any]
) -> None:
    """A fonte do cache é do mesmo gabinete e da mesma versão do extrator de páginas."""
    fabrica = extracao_sessao.deps.fabrica
    gabinete = processado["assessor"].gabinete_id
    arquivo = processado["lacre"].arquivo_id
    total = _contar(engine_teste, PaginaTabela, arquivo_id=arquivo)
    with Session(engine_teste) as session:
        sha256 = session.get_one(ArquivoTabela, arquivo).sha256
    novo = UUID(int=1)
    with sessao_gabinete(fabrica, gabinete) as session:
        assert cache.fonte_em_cache(session, gabinete, novo, sha256, VERSAO_EXTRATOR, total)
        assert cache.fonte_em_cache(session, gabinete, novo, sha256, "outra", total) is None
        assert cache.fonte_em_cache(session, gabinete, novo, sha256, VERSAO_EXTRATOR, 0) is None
    outro = criar_gabinete_teste(engine_teste)
    with sessao_gabinete(fabrica, outro) as session:
        assert cache.fonte_em_cache(session, outro, novo, sha256, VERSAO_EXTRATOR, total) is None
    with Session(engine_teste) as session:
        assert cache.fonte_em_cache(session, outro, novo, sha256, VERSAO_EXTRATOR, total) is None


def test_falha_nos_eventos_nao_desfaz_paginas_nem_indice(
    engine_teste: Engine,
    extracao_sessao: ExtracaoSessao,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Erro na etapa de eventos fica no relatório; o job conclui com páginas e peças."""
    from lupa.ingestao import worker

    def explode(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("falha sintética")

    monkeypatch.setattr(worker, "processar_eventos", explode)
    processado = lacrar_e_processar(extracao_sessao, engine_teste, tmp_path)
    with Session(engine_teste) as session:
        job = session.get_one(JobIngestaoTabela, processado["lacre"].job_id)
    assert job.estado == EstadoJob.CONCLUIDO.value
    assert job.relatorio is not None and job.relatorio["eventos"] == {"erro": "RuntimeError"}
    assert _contar(engine_teste, PecaTabela, arquivo_id=processado["lacre"].arquivo_id) > 0
    assert _contar(engine_teste, FatoTabela, processo_id=processado["processo"]) == 0


def test_worker_sem_eventos_nao_grava_fatos(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> None:
    """Com `eventos=False` o worker para no índice (comportamento da 4E)."""
    sem = replace(extracao_sessao, deps=replace(extracao_sessao.deps, eventos=False))
    processado = lacrar_e_processar(sem, engine_teste, tmp_path)
    with Session(engine_teste) as session:
        job = session.get_one(JobIngestaoTabela, processado["lacre"].job_id)
    assert job.relatorio is not None and "eventos" not in job.relatorio
    assert _contar(engine_teste, FatoTabela, processo_id=processado["processo"]) == 0
