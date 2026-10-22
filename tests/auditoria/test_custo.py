"""Custo estimado em dinheiro no relatório de uso (Etapa 6.9; revisão 5, item 5)."""

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from lupa.agente.precos import CAMINHO_PRECOS, Preco, custo, ler_tabela, tabela_padrao
from lupa.auditoria import registrador
from lupa.auditoria.consulta import FiltroAuditoria, custo_estimado
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento
from lupa.dominio.tabelas import ChamadaModeloTabela, ConversaTabela, ProcessoTabela


def test_tabela_versionada_tem_fonte_e_modelo_configurado() -> None:
    """A tabela tem versão, fonte, ressalva e o preço do modelo padrão."""
    tabela = tabela_padrao()
    assert tabela.versao and tabela.fonte and "fatura" in tabela.observacao
    assert tabela.preco_de("claude-opus-5-5") == Preco(Decimal("4.00"), Decimal("20.00"))
    assert tabela.preco_de("claude-opus-5-5-20261001") is not None
    assert tabela.preco_de("modelo-desconhecido") is None
    assert ler_tabela(CAMINHO_PRECOS) == tabela


def test_custo_por_milhao_de_tokens() -> None:
    """Um milhão de tokens de entrada e meio de saída a 4 e 20 dólares custam 14 dólares."""
    assert custo(Preco(Decimal(4), Decimal(20)), 1_000_000, 500_000) == Decimal("14.0000")


def test_tabela_alternativa_e_lida(tmp_path: Path) -> None:
    """Outra tabela (nova versão) pode ser lida do disco."""
    arquivo = tmp_path / "precos.yaml"
    arquivo.write_text(
        'versao: "x"\nfonte: "f"\nmoeda: "USD"\nobservacao: "o"\n'
        "modelos:\n  m:\n    entrada_por_milhao: 1\n    saida_por_milhao: 2\n",
        encoding="utf-8",
    )
    assert ler_tabela(arquivo).preco_de("m") == Preco(Decimal(1), Decimal(2))


def _chamada(
    session: Session, processo: ProcessoTabela, conversa: UUID | None, modelo: str
) -> UUID:
    chamada_id = uuid4()
    session.add(
        ChamadaModeloTabela(
            id=chamada_id, gabinete_id=processo.gabinete_id, processo_id=processo.id,
            conversa_id=conversa, modelo=modelo, versao_prompt="v", hash_prompt_sistema="h",
            hash_entrada="h", hash_saida="h", tokens_entrada=250_000, tokens_saida=50_000,
            latencia_ms=1, resultado="ok",
        )
    )  # fmt: skip
    return chamada_id


@pytest.mark.integracao
def test_custo_estimado_por_processo_e_por_usuario(sessao: Session, processo_id: UUID) -> None:
    """Por processo soma tudo; por usuário só as conversas dele; modelo fora da tabela é None."""
    processo = sessao.get(ProcessoTabela, processo_id)
    assert processo is not None
    conversa = ConversaTabela(
        id=uuid4(), gabinete_id=processo.gabinete_id, processo_id=processo.id,
        usuario_id=processo.criado_por, encerrada=False, tokens_entrada=0, tokens_saida=0,
        paginas_originais=0, citacoes_descartadas=0,
    )  # fmt: skip
    sessao.add(conversa)
    sessao.flush()
    _chamada(sessao, processo, conversa.id, "claude-opus-5-5")
    _chamada(sessao, processo, None, "claude-opus-5-5")
    _chamada(sessao, processo, None, "modelo-x")
    sessao.flush()
    por_processo = custo_estimado(
        sessao, FiltroAuditoria(gabinete_id=processo.gabinete_id, processo_id=processo.id)
    )
    assert por_processo["total"] == "4.0000" and por_processo["moeda"] == "USD"
    assert {m["modelo"]: m["custo"] for m in por_processo["por_modelo"]} == {
        "claude-opus-5-5": "4.0000",
        "modelo-x": None,
    }
    por_usuario = custo_estimado(sessao, FiltroAuditoria(usuario_id=processo.criado_por))
    assert por_usuario["total"] == "2.0000"


@pytest.mark.integracao
def test_custo_por_usuario_inclui_resumos_do_dossie_que_ele_pediu(
    sessao: Session, processo_id: UUID
) -> None:
    """Resumo do dossiê (sem conversa) entra no custo de quem o pediu, e só dele (6.10)."""
    processo = sessao.get(ProcessoTabela, processo_id)
    assert processo is not None
    resumo = _chamada(sessao, processo, None, "claude-opus-5-5")
    _chamada(sessao, processo, None, "claude-opus-5-5")  # resumo de outro usuário
    sessao.flush()
    registrador.registrar(
        sessao,
        NovoEvento(
            acao=AcaoAuditoria.CHAMADA_MODELO, usuario_id=processo.criado_por,
            gabinete_id=processo.gabinete_id, processo_id=processo.id,
            objeto_tipo="chamada_modelo", objeto_id=str(resumo),
        ),
    )  # fmt: skip
    por_usuario = custo_estimado(sessao, FiltroAuditoria(usuario_id=processo.criado_por))
    assert por_usuario["total"] == "2.0000"
    assert custo_estimado(sessao, FiltroAuditoria(usuario_id=uuid4()))["total"] == "0.0000"
