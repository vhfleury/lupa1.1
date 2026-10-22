"""Testes da máquina de estados do job e dos esquemas da ingestão (sem banco)."""

from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lupa.dominio.enums import CenarioArquivo, EstadoJob, EstadoLote, MotivoQuarentena
from lupa.dominio.esquemas import (
    DiagnosticoArquivo,
    EntradaManifesto,
    JobIngestao,
    LoteIngestao,
)
from lupa.ingestao.estados import (
    ESTADOS_FINAIS,
    TransicaoInvalidaError,
    exigir_transicao,
    transicao,
)

E = EstadoJob

PERMITIDAS = {
    (E.RECEBIDO, E.VALIDADO),
    (E.RECEBIDO, E.FALHO),
    (E.RECEBIDO, E.QUARENTENA),
    (E.VALIDADO, E.EM_EXTRACAO),
    (E.VALIDADO, E.FALHO),
    (E.VALIDADO, E.QUARENTENA),
    (E.EM_EXTRACAO, E.PARCIAL),
    (E.EM_EXTRACAO, E.EM_REVISAO),
    (E.EM_EXTRACAO, E.CONCLUIDO),
    (E.EM_EXTRACAO, E.FALHO),
    (E.EM_EXTRACAO, E.QUARENTENA),
    (E.PARCIAL, E.EM_EXTRACAO),
    (E.PARCIAL, E.EM_REVISAO),
    (E.PARCIAL, E.FALHO),
    (E.EM_REVISAO, E.EM_EXTRACAO),
    (E.EM_REVISAO, E.CONCLUIDO),
    (E.EM_REVISAO, E.FALHO),
    (E.FALHO, E.RECEBIDO),
}


@pytest.mark.parametrize(("atual", "novo"), list(product(E, E)))
def test_matriz_completa_de_transicoes(atual: EstadoJob, novo: EstadoJob) -> None:
    """Cada um dos 64 pares tem exatamente o resultado da tabela acima."""
    assert transicao(atual, novo) is ((atual, novo) in PERMITIDAS)


def test_concluido_nunca_volta_para_em_extracao() -> None:
    """O critério da subetapa, explícito."""
    assert not transicao(E.CONCLUIDO, E.EM_EXTRACAO)
    with pytest.raises(TransicaoInvalidaError):
        exigir_transicao(E.CONCLUIDO, E.EM_EXTRACAO)


def test_concluido_e_quarentena_sao_finais() -> None:
    """Estados finais não têm destino."""
    assert frozenset({E.CONCLUIDO, E.QUARENTENA}) == ESTADOS_FINAIS
    assert not any(transicao(E.QUARENTENA, novo) for novo in E)


def test_exigir_transicao_valida_nao_lanca() -> None:
    """Transição permitida passa em silêncio."""
    exigir_transicao(E.RECEBIDO, E.VALIDADO)


def test_job_em_quarentena_exige_motivo_e_so_ele() -> None:
    """`motivo_quarentena` existe se e somente se o estado é `quarentena`."""
    base = {"processo_id": uuid4(), "arquivo_id": uuid4()}
    with pytest.raises(ValidationError):
        JobIngestao(**base, estado=E.QUARENTENA)
    with pytest.raises(ValidationError):
        JobIngestao(**base, motivo_quarentena=MotivoQuarentena.SENHA)
    job = JobIngestao(**base, estado=E.QUARENTENA, motivo_quarentena=MotivoQuarentena.SENHA)
    assert job.motivo_quarentena is MotivoQuarentena.SENHA
    assert JobIngestao(**base).estado is E.RECEBIDO


def test_entrada_de_manifesto_exige_hash_valido() -> None:
    """Hash precisa ter 64 hexadecimais."""
    with pytest.raises(ValidationError):
        EntradaManifesto(ordem=1, nome="a.pdf", tamanho_bytes=1, sha256="x")
    entrada = EntradaManifesto(ordem=1, nome="a.pdf", tamanho_bytes=1, sha256="a" * 64)
    assert entrada.ordem == 1


def test_lote_e_diagnostico_validam_campos() -> None:
    """Lote começa em 1 e exige token; diagnóstico usa o cenário enumerado."""
    with pytest.raises(ValidationError):
        LoteIngestao(job_id=uuid4(), numero=0, estado=EstadoLote.CONCLUIDO, fencing_token=1)
    lote = LoteIngestao(job_id=uuid4(), numero=1, estado=EstadoLote.CONCLUIDO, fencing_token=1)
    assert lote.resultado == {}
    with pytest.raises(ValidationError):
        DiagnosticoArquivo(arquivo_id=uuid4(), cenario="outro", total_paginas=1, tem_indice=False)
    diagnostico = DiagnosticoArquivo(
        arquivo_id=uuid4(), cenario=CenarioArquivo.PDF_LISO, total_paginas=3, tem_indice=False
    )
    assert diagnostico.sinais == {}


def test_quarentena_tem_texto_legivel_para_cada_motivo() -> None:
    """Toda entrada do enum tem descrição; resultado do parser vira motivo."""
    from lupa.ingestao.quarentena import descrever, motivo_do_parser

    assert all(descrever(motivo) for motivo in MotivoQuarentena)
    assert motivo_do_parser({"ok": True}) is None
    assert motivo_do_parser({"ok": False, "motivo_quarentena": "senha"}) is MotivoQuarentena.SENHA
    assert motivo_do_parser({"ok": False, "motivo_quarentena": "?"}) is (
        MotivoQuarentena.CORROMPIDO
    )
