"""Testes contra PostgreSQL real: integridade, imutabilidade, RLS, repositórios e migração."""

from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, delete, insert, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from lupa.dominio.enums import ResultadoAchado, TipoFato
from lupa.dominio.esquemas import Achado
from lupa.dominio.repositorios import (
    ProcessoNaoEncontradoError,
    listar_achados,
    listar_fatos_por_processo,
    salvar_achado,
    salvar_fato,
)
from lupa.dominio.sessao import assumir_papel_aplicacao, definir_gabinete
from lupa.dominio.tabelas import (
    TABELAS_COM_GABINETE,
    AchadoTabela,
    Base,
    FatoEvidenciaTabela,
    FatoTabela,
    ProcessoTabela,
)
from tests.conftest import FabricaFato, FabricaProcesso, criar_pagina, migrar

pytestmark = pytest.mark.integracao


def _forcar_constraints(sessao: Session) -> None:
    sessao.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def _achado(processo_id: UUID, fatos: tuple[UUID, ...] = ()) -> Achado:
    return Achado(
        processo_id=processo_id,
        validacao="tempestividade_recurso",
        versao_catalogo="2025.1",
        resultado=ResultadoAchado.CONFORME,
        fatos_usados=fatos,
        valores={"prazo_dias": 5, "base_legal": "art. 593 CPP"},
        explicacao="Recurso tempestivo.",
    )


def test_fato_sem_evidencia_e_rejeitado_pelo_banco(
    sessao: Session, processo_id: UUID, gabinete_id: UUID
) -> None:
    """O trigger adiado recusa fato sem linha em `fato_evidencia`."""
    sessao.add(
        FatoTabela(
            id=uuid4(),
            gabinete_id=gabinete_id,
            processo_id=processo_id,
            tipo=TipoFato.DATA_FATO.value,
            valor="2024-01-01",
            extraido_por="teste",
            versao_extrator="0",
            confianca=1.0,
            status="automatico",
        )
    )
    sessao.flush()
    with pytest.raises(DBAPIError, match="sem evidência"):
        _forcar_constraints(sessao)


def test_remover_ultima_evidencia_de_fato_e_rejeitado_pelo_banco(
    sessao: Session, processo_id: UUID, pagina_id: UUID, fabrica_fato: FabricaFato
) -> None:
    """Apagar a única associação deixa o fato órfão, o que o banco recusa."""
    fato = fabrica_fato(processo_id=processo_id, pagina_id=pagina_id)
    salvar_fato(sessao, fato)
    _forcar_constraints(sessao)
    with pytest.raises(DBAPIError, match="sem evidência"):
        sessao.execute(delete(FatoEvidenciaTabela).where(FatoEvidenciaTabela.fato_id == fato.id))


def test_fato_salvo_volta_com_evidencias(
    sessao: Session, processo_id: UUID, pagina_id: UUID, fabrica_fato: FabricaFato
) -> None:
    """`salvar_fato` e `listar_fatos_por_processo` preservam o contrato do `Fato`."""
    primeiro = fabrica_fato(processo_id=processo_id, pagina_id=pagina_id)
    segundo = fabrica_fato(
        processo_id=processo_id, pagina_id=pagina_id, tipo=TipoFato.PENA_MAXIMA_ABSTRATA, valor=48
    )
    salvar_fato(sessao, primeiro)
    salvar_fato(sessao, segundo)
    _forcar_constraints(sessao)
    fatos = {fato.id: fato for fato in listar_fatos_por_processo(sessao, processo_id)}
    assert set(fatos) == {primeiro.id, segundo.id}
    assert fatos[primeiro.id].evidencias == primeiro.evidencias
    assert fatos[segundo.id].valor == 48
    assert fatos[segundo.id].tipo is TipoFato.PENA_MAXIMA_ABSTRATA


def test_salvar_fato_de_processo_inexistente_falha(
    sessao: Session, fabrica_fato: FabricaFato
) -> None:
    """Processo desconhecido (ou invisível pela RLS) gera erro claro."""
    with pytest.raises(ProcessoNaoEncontradoError):
        salvar_fato(sessao, fabrica_fato())
    with pytest.raises(ProcessoNaoEncontradoError):
        salvar_achado(sessao, _achado(uuid4()))


def test_achado_salvo_e_listado(sessao: Session, processo_id: UUID) -> None:
    """`salvar_achado` e `listar_achados` fazem ida e volta completa."""
    fatos_usados = (uuid4(), uuid4())
    achado = _achado(processo_id, fatos_usados)
    salvar_achado(sessao, achado)
    assert listar_achados(sessao, processo_id) == [achado]


def test_achado_nao_pode_ser_atualizado(sessao: Session, processo_id: UUID) -> None:
    """O trigger bloqueia qualquer UPDATE em `achado`."""
    achado = _achado(processo_id)
    salvar_achado(sessao, achado)
    with pytest.raises(DBAPIError, match="imutável"):
        sessao.execute(
            update(AchadoTabela).where(AchadoTabela.id == achado.id).values(explicacao="outra")
        )


def test_rls_isola_gabinetes(
    sessao: Session,
    fabrica_processo: FabricaProcesso,
    fabrica_fato: FabricaFato,
) -> None:
    """Com `lupa.gabinete_id` = A, nenhuma linha do gabinete B aparece."""
    gabinete_a, gabinete_b = uuid4(), uuid4()
    processo_a, processo_b = fabrica_processo(gabinete_a), fabrica_processo(gabinete_b)
    for processo in (processo_a, processo_b):
        salvar_fato(sessao, fabrica_fato(processo, criar_pagina(sessao, processo)))
        salvar_achado(sessao, _achado(processo))
    _forcar_constraints(sessao)

    assumir_papel_aplicacao(sessao)
    definir_gabinete(sessao, gabinete_a)

    gabinetes_visiveis = set(sessao.scalars(select(ProcessoTabela.gabinete_id)).all())
    assert gabinetes_visiveis == {gabinete_a}
    assert set(sessao.scalars(select(FatoTabela.processo_id)).all()) == {processo_a}
    assert listar_fatos_por_processo(sessao, processo_b) == []
    assert listar_achados(sessao, processo_b) == []
    assert len(listar_achados(sessao, processo_a)) == 1


def test_rls_sem_gabinete_definido_nao_mostra_nada(sessao: Session, processo_id: UUID) -> None:
    """Sem a variável de sessão, o papel da aplicação não vê nenhuma linha."""
    assumir_papel_aplicacao(sessao)
    assert sessao.scalars(select(ProcessoTabela)).all() == []


def test_rls_impede_gravar_em_outro_gabinete(
    sessao: Session, fabrica_processo: FabricaProcesso, fabrica_fato: FabricaFato
) -> None:
    """O WITH CHECK da política recusa inserir linha de outro gabinete."""
    gabinete_a, gabinete_b = uuid4(), uuid4()
    fabrica_processo(gabinete_a)
    processo_b = fabrica_processo(gabinete_b)
    assumir_papel_aplicacao(sessao)
    definir_gabinete(sessao, gabinete_a)
    with pytest.raises(DBAPIError, match="row-level security"):
        sessao.execute(
            insert(AchadoTabela).values(
                id=uuid4(),
                gabinete_id=gabinete_b,
                processo_id=processo_b,
                validacao="x",
                versao_catalogo="1",
                resultado="conforme",
                explicacao="-",
            )
        )


def test_rls_ativa_em_todas_as_tabelas_com_gabinete(engine_teste: Engine) -> None:
    """Toda tabela com `gabinete_id` tem RLS habilitada e forçada."""
    with engine_teste.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity "
                "AND relkind = 'r'"
            )
        ).scalars()
        assert set(linhas) == set(TABELAS_COM_GABINETE)


def test_migracao_coincide_com_tabelas(engine_teste: Engine) -> None:
    """A migração escrita à mão gera o mesmo esquema que `lupa.dominio.tabelas`."""
    with engine_teste.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == []


def test_downgrade_base_remove_e_upgrade_head_recria(engine_teste: Engine) -> None:
    """`alembic downgrade base` apaga todas as tabelas e `upgrade head` as recria."""
    esperadas = set(Base.metadata.tables)
    migrar(engine_teste, "base", descer=True)
    assert set(inspect(engine_teste).get_table_names()) <= {"alembic_version"}
    migrar(engine_teste, "head")
    assert esperadas <= set(inspect(engine_teste).get_table_names())


def test_nome_real_so_existe_em_reu_identidade_e_usuario() -> None:
    """Nenhuma coluna de nome de pessoa fora das tabelas autorizadas."""
    suspeitas = {"nome", "nome_completo", "nome_reu", "nome_parte", "documento", "cpf"}
    for tabela in Base.metadata.tables.values():
        if tabela.name in {"reu_identidade", "usuario", "gabinete"}:
            continue
        assert not suspeitas & set(tabela.columns.keys()), tabela.name
