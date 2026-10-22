"""Fixtures sintéticas das validações: fábrica de fatos e dados jurídicos de teste."""

import itertools
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID, uuid5

import pytest

from lupa.dominio.esquemas import Evidencia, Fato
from lupa.validacoes.calendario import Calendario, Periodo
from lupa.validacoes.criminal.tempestividade import DadosTempestividade
from lupa.validacoes.dados import RegraRecurso, TabelaPrazosRecursos
from lupa.validacoes.modelo import ModeloProcesso

FabricaFato = Callable[..., Fato]
_contador = itertools.count(1)
_ESPACO = UUID("6c757061-0000-4000-8000-000000000000")
PROCESSO_SINTETICO = uuid5(_ESPACO, "proc-sintetico")
PAGINA_SINTETICA = uuid5(_ESPACO, "pag-1")


def id_sintetico(nome: str) -> UUID:
    """Id determinístico a partir de um nome legível."""
    return uuid5(_ESPACO, nome)


def criar_fato(tipo: str, valor: Any, *, fato_id: str | None = None) -> Fato:
    """Cria um fato sintético (esquema do domínio) com uma evidência sintética."""
    numero = next(_contador)
    trecho = f"trecho sintético {numero}"
    evidencia = Evidencia(
        id=id_sintetico(f"ev-{numero}"),
        pagina_id=PAGINA_SINTETICA,
        trecho=trecho,
        inicio=0,
        fim=len(trecho),
    )
    return Fato(
        id=id_sintetico(fato_id or f"fato-{numero}"),
        processo_id=PROCESSO_SINTETICO,
        tipo=tipo,
        valor=valor,
        evidencias=(evidencia,),
        extraido_por="teste",
        versao_extrator="0",
        confianca=1.0,
        status="confirmado",
    )


def modelo_de(*fatos: Fato) -> ModeloProcesso:
    """Monta um modelo com os fatos dados."""
    return ModeloProcesso(fatos)


@pytest.fixture
def fato() -> FabricaFato:
    """Fábrica de fatos sintéticos."""
    return criar_fato


def dados_tempestividade(
    feriados: dict[date, str] | None = None, suspensoes: tuple[Periodo, ...] = ()
) -> DadosTempestividade:
    """Dados sintéticos de tempestividade com calendário controlado."""
    prazos = TabelaPrazosRecursos(
        versao="teste",
        fonte="sintética",
        contagem_base_legal="art. 798 CPP",
        recursos={
            "apelacao": RegraRecurso(nome="Apelação", dias=5, base_legal="art. 593 CPP"),
            "rese": RegraRecurso(nome="RESE", dias=5, base_legal="art. 586 CPP"),
            "embargos_declaracao": RegraRecurso(
                nome="Embargos de declaração", dias=2, base_legal="art. 619 CPP"
            ),
        },
    )
    calendario = Calendario(feriados=feriados or {}, suspensoes=suspensoes)
    return DadosTempestividade(prazos, calendario, {"teste": "sintético"})
