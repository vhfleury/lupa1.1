"""Adaptador validações ↔ domínio: conversão pura e ida e volta pelo banco."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from lupa.dominio.enums import ResultadoAchado, TipoFato
from lupa.dominio.repositorios import (
    listar_achados,
    listar_fatos_por_processo,
    salvar_achado,
    salvar_fato,
)
from lupa.validacoes.adaptador import para_dominio, para_modelo
from lupa.validacoes.apoio import data_de
from lupa.validacoes.motor import executar_catalogo
from tests.conftest import FabricaFato, criar_pagina
from tests.validacoes.conftest import criar_fato

REFERENCIA = date(2026, 10, 20)


def test_data_de_aceita_string_iso_e_date() -> None:
    """data_de lê string ISO (banco) e date (código Python)."""
    assert data_de(criar_fato("data_fato", "2030-01-02")) == date(2030, 1, 2)
    assert data_de(criar_fato("data_fato", date(2030, 1, 2))) == date(2030, 1, 2)


def test_para_dominio_vincula_processo_e_mantem_valores_json() -> None:
    """para_dominio produz Achado do domínio com fatos_usados UUID e valores serializáveis."""
    fatos = [
        criar_fato(TipoFato.TIPO_RECURSO, {"tipo": "apelacao", "recorrente": "defesa"}),
        criar_fato(TipoFato.DATA_INTIMACAO_DEFESA, "2026-09-01"),
        criar_fato(TipoFato.DATA_INTERPOSICAO_RECURSO, "2026-09-04"),
    ]
    processo = uuid4()
    for achado_validacao in executar_catalogo(para_modelo(fatos), "criminal", REFERENCIA):
        achado = para_dominio(achado_validacao, processo)
        assert achado.processo_id == processo
        assert tuple(achado.fatos_usados) == tuple(achado_validacao.fatos_usados)
        assert achado.model_dump_json()


@pytest.mark.integracao
def test_ida_e_volta_pelo_banco(
    sessao: Session, processo_id: UUID, fabrica_fato: FabricaFato
) -> None:
    """Fatos salvos e lidos do banco alimentam o catálogo; achados voltam iguais."""
    pagina_id = criar_pagina(sessao, processo_id)
    entradas = [
        (TipoFato.TIPO_RECURSO, {"tipo": "apelacao", "recorrente": "defesa"}),
        (TipoFato.DATA_INTIMACAO_DEFESA, "2026-09-01"),
        (TipoFato.DATA_INTERPOSICAO_RECURSO, "2026-09-04"),
        (TipoFato.DATA_FATO, "2020-01-10"),
        (TipoFato.DATA_RECEBIMENTO_DENUNCIA, "2021-02-01"),
        (TipoFato.PENA_MAXIMA_ABSTRATA, 48),
    ]
    for tipo, valor in entradas:
        salvar_fato(sessao, fabrica_fato(processo_id, pagina_id, tipo, valor))
    sessao.flush()

    lidos = listar_fatos_por_processo(sessao, processo_id)
    assert len(lidos) == len(entradas)
    resultados = executar_catalogo(para_modelo(lidos), "criminal", REFERENCIA)
    assert any(r.resultado is not ResultadoAchado.VERIFICAR for r in resultados)
    ids_lidos = {f.id for f in lidos}
    achados = [para_dominio(r, processo_id) for r in resultados]
    for achado in achados:
        assert set(achado.fatos_usados) <= ids_lidos
        salvar_achado(sessao, achado)
    sessao.flush()

    voltaram = {a.id: a for a in listar_achados(sessao, processo_id)}
    assert len(voltaram) == len(achados)
    for achado in achados:
        volta = voltaram[achado.id]
        assert volta.model_dump(exclude={"criado_em"}) == achado.model_dump(exclude={"criado_em"})
