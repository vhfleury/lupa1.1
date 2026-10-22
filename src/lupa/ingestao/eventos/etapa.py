"""Etapa de eventos da ingestão: réus, fatos e achados de um processo (4F.5 a 4F.8).

Roda no fim da extração (worker, depois do índice) e também sozinha, quando só a versão do
extrator de eventos mudou: lê as peças vigentes e as páginas já gravadas, sem tocar em páginas
nem peças, regrava os fatos da versão nova e executa o catálogo da matéria do processo pelo
adaptador da 4A.1. Tudo na transação do chamador. O resumo devolvido só tem contagens.
"""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from lupa.dominio.correcoes import fatos_vigentes
from lupa.dominio.esquemas import Achado
from lupa.dominio.repositorios import listar_fatos_por_processo
from lupa.dominio.tabelas import ProcessoTabela
from lupa.ingestao import repositorio_eventos
from lupa.ingestao.eventos.fatos import extrair_fatos
from lupa.ingestao.eventos.padroes import Padroes, padroes_padrao
from lupa.ingestao.eventos.reus import identificar_reus
from lupa.logging import get_logger
from lupa.validacoes.adaptador import para_dominio, para_modelo
from lupa.validacoes.modelo import AchadoValidacao, ModeloProcesso
from lupa.validacoes.motor import executar_catalogo

log = get_logger(__name__)


def _com_reu(achado: AchadoValidacao, reu_id: str) -> AchadoValidacao:
    return achado.model_copy(update={"valores": {**achado.valores, "reu_id": reu_id}})


def executar_validacoes(
    modelo: ModeloProcesso, materia: str, referencia: date
) -> list[AchadoValidacao]:
    """Catálogo da matéria sobre o processo; com mais de um réu, uma rodada por réu.

    Args:
        modelo: Fatos do processo.
        materia: Matéria do processo.
        referencia: Data de referência.

    Returns:
        Achados do motor (com ``valores.reu_id`` quando por réu).
    """
    reus = modelo.reus()
    if len(reus) <= 1:
        return executar_catalogo(modelo, materia, referencia)
    return [
        _com_reu(a, reu)
        for reu in reus
        for a in executar_catalogo(modelo.por_reu(reu), materia, referencia)
    ]


def achados_do_processo(
    session: Session, processo_id: UUID, materia: str, referencia: date
) -> list[Achado]:
    """Achados do catálogo sobre os fatos vigentes do processo.

    Fatos substituídos por correção ou confirmação humana (6.7) ficam de fora: o catálogo só vê
    o fato vigente de cada cadeia.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.
        materia: Matéria.
        referencia: Data de referência.

    Returns:
        Achados do domínio.
    """
    modelo = para_modelo(fatos_vigentes(listar_fatos_por_processo(session, processo_id)))
    return [para_dominio(a, processo_id) for a in executar_validacoes(modelo, materia, referencia)]


def processar_eventos(
    session: Session,
    gabinete_id: UUID,
    processo_id: UUID,
    referencia: date,
    padroes: Padroes | None = None,
) -> dict[str, Any]:
    """Extrai e grava réus e fatos, executa o catálogo e grava os achados.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        gabinete_id: Gabinete.
        processo_id: Processo.
        referencia: Data de referência das validações.
        padroes: Padrões (padrão: os YAML empacotados).

    Returns:
        Resumo com contagens (sem texto nem nomes).
    """
    padroes = padroes or padroes_padrao()
    processo = session.get_one(ProcessoTabela, processo_id)
    pecas = repositorio_eventos.pecas_do_processo(session, processo_id)
    reus = identificar_reus(pecas)
    ids_reu = repositorio_eventos.gravar_reus(session, gabinete_id, processo_id, reus)
    extracao = extrair_fatos(processo_id, pecas, reus, ids_reu, padroes)
    removidos = repositorio_eventos.remover_fatos_obsoletos(
        session, processo_id, padroes.versao_extrator
    )
    gravados = repositorio_eventos.gravar_fatos(session, extracao.fatos)
    achados = achados_do_processo(session, processo_id, processo.materia, referencia)
    novos_achados = repositorio_eventos.gravar_achados(session, processo_id, achados)
    resumo = {
        "versao_extrator": padroes.versao_extrator,
        "pecas": len(pecas),
        "reus": len(reus),
        **extracao.resumo(),
        "fatos_gravados": gravados,
        "fatos_removidos": removidos,
        "achados": {a.validacao: a.resultado.value for a in achados},
        "achados_gravados": novos_achados,
        "data_referencia": referencia.isoformat(),
    }
    log.info(
        "eventos_processados",
        processo_id=str(processo_id),
        fatos=len(extracao.fatos),
        gravados=gravados,
        removidos=removidos,
        achados=novos_achados,
    )
    return resumo
