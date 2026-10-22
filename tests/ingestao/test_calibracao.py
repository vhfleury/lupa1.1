"""Execução local e relatório de calibração (4F.10) sobre um processo sintético."""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from lupa.dominio.cnj import validar_numero_cnj
from lupa.dominio.enums import EstadoJob
from lupa.ingestao.calibracao import (
    coletar,
    enviar_e_processar,
    numero_cnj,
    para_markdown,
    semear_gabinete,
)
from lupa.ingestao.worker import sessao_gabinete
from lupa.sinteticos.gabarito import Cenario
from tests.ingestao.conftest import AutosSinteticos, ExtracaoSessao

pytestmark = pytest.mark.integracao


def test_numero_cnj_sintetico_e_valido() -> None:
    """O número gerado passa na validação do domínio."""
    for sequencial in (1, 42, 10**12 + 7):
        assert validar_numero_cnj(numero_cnj(sequencial)) == numero_cnj(sequencial)


def test_calibracao_de_processo_sintetico_gera_relatorio_para_conferencia(
    engine_teste: Engine,
    extracao_sessao: ExtracaoSessao,
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Pipeline até achados e relatório com diagnóstico, peças, eventos com trecho e achados."""
    dono = sessionmaker(engine_teste)
    assessor = extracao_sessao.assessor
    assert assessor.gabinete_id is not None
    caminho = autos_sinteticos.arquivos[Cenario.PDF_INDICE]
    execucao = enviar_e_processar(
        extracao_sessao.deps, dono, assessor.gabinete_id, assessor.id, caminho
    )
    assert execucao.estado is EstadoJob.CONCLUIDO
    with sessao_gabinete(extracao_sessao.deps.fabrica, assessor.gabinete_id) as session:
        dados = coletar(session, execucao.processo_id, execucao.arquivo_id)
    assert dados["diagnostico"]["cenario"] == "pdf_com_bookmarks_e_indice"
    assert dados["reus"] == ["REU-01"]
    assert dados["fatos"] and all(f["trecho"] for f in dados["fatos"])
    assert len(dados["achados"]) == 3
    texto = para_markdown(dados, "sintético")
    for secao in ("## 1. Diagnóstico", "## 2. Peças", "## 3. Eventos", "## 4. Achados"):
        assert secao in texto
    assert texto.count("| |") >= len(dados["indice"]) + len(dados["fatos"])


def test_semear_gabinete_e_arquivo_que_nao_e_pdf_nem_zip(
    engine_teste: Engine, extracao_sessao: ExtracaoSessao, tmp_path: Path
) -> None:
    """Gabinete local criado; arquivo de outro tipo é recusado antes de lacrar."""
    dono = sessionmaker(engine_teste)
    with dono() as session, session.begin():
        gabinete, usuario = semear_gabinete(session, "Gabinete de teste")
    texto = tmp_path / "nota.txt"
    texto.write_text("não é PDF", encoding="utf-8")
    with pytest.raises(ValueError, match="PDF nem ZIP"):
        enviar_e_processar(extracao_sessao.deps, dono, gabinete, usuario, texto)
