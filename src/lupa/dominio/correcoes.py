"""Correção e confirmação humana de fatos (Etapa 6.7).

O fato original nunca é alterado: a correção grava um fato NOVO com `status=corrigido` (ou
`confirmado`), `substitui_fato_id` apontando para o original e as mesmas evidências. Um fato
substituído deixa de ser vigente: o catálogo só enxerga os fatos vigentes.
"""

import json
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lupa.dominio.enums import StatusFato
from lupa.dominio.esquemas import Fato
from lupa.dominio.repositorios import listar_fatos_por_processo, salvar_fato
from lupa.dominio.tabelas import FatoTabela

EXTRAIDO_POR_PESSOA = "assessor"
VERSAO_CORRECAO = "manual"


class CorrecaoInvalidaError(ValueError):
    """Pedido de correção incoerente com o fato original."""


class FatoJaSubstituidoError(ValueError):
    """O fato já foi corrigido ou confirmado; corrija o vigente."""


def fatos_vigentes(fatos: Iterable[Fato]) -> list[Fato]:
    """Remove os fatos que outro fato substituiu.

    Args:
        fatos: Fatos do processo.

    Returns:
        Só os fatos que ninguém substitui, na ordem recebida.
    """
    lista = list(fatos)
    substituidos = {f.substitui_fato_id for f in lista if f.substitui_fato_id is not None}
    return [f for f in lista if f.id not in substituidos]


def _desembrulhar(valor: Any) -> tuple[Any, str | None]:
    if isinstance(valor, dict) and "reu_id" in valor and "valor" in valor:
        return valor["valor"], str(valor["reu_id"])
    return valor, None


def _e_data(valor: Any) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _tipo_json(valor: Any) -> str:
    if isinstance(valor, bool):
        return "booleano"
    if isinstance(valor, int | float):
        return "numero"
    if _e_data(valor):
        return "data"
    return type(valor).__name__


def valor_corrigido(original: Any, novo: Any) -> Any:
    """Confere o valor novo contra o original e reaplica o réu, quando o fato é por réu.

    Args:
        original: Valor gravado no fato original.
        novo: Valor informado pela pessoa (sem o envelope do réu).

    Returns:
        Valor a gravar.

    Raises:
        CorrecaoInvalidaError: Tipo diferente do original (data por texto, número por data...).
    """
    base, reu_id = _desembrulhar(original)
    if _tipo_json(base) != _tipo_json(novo):
        esperado = _tipo_json(base)
        raise CorrecaoInvalidaError(f"valor deve ser do mesmo tipo do original ({esperado})")
    if json.dumps(novo, sort_keys=True) == json.dumps(base, sort_keys=True):
        raise CorrecaoInvalidaError("valor igual ao original: use confirmar")
    return {"valor": novo, "reu_id": reu_id} if reu_id is not None else novo


def obter_fato(session: Session, processo_id: UUID, fato_id: UUID) -> Fato | None:
    """Fato do processo, com evidências.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.
        fato_id: Fato.

    Returns:
        O fato, ou None se não existe no processo.
    """
    for fato in listar_fatos_por_processo(session, processo_id):
        if fato.id == fato_id:
            return fato
    return None


def corrigir_fato(session: Session, original: Fato, status: StatusFato, valor: Any = None) -> Fato:
    """Grava o fato novo que substitui o original.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        original: Fato vigente a corrigir ou confirmar.
        status: `corrigido` (valor novo obrigatório) ou `confirmado` (mantém o valor).
        valor: Valor novo, sem o envelope do réu.

    Returns:
        Fato novo gravado.

    Raises:
        FatoJaSubstituidoError: O original já tem substituto.
        CorrecaoInvalidaError: Status não aceito ou valor incoerente.
    """
    ja = session.scalar(select(FatoTabela.id).where(FatoTabela.substitui_fato_id == original.id))
    if ja is not None:
        raise FatoJaSubstituidoError("fato já corrigido ou confirmado")
    if status is StatusFato.CORRIGIDO:
        gravar = valor_corrigido(original.valor, valor)
    elif status is StatusFato.CONFIRMADO:
        gravar = original.valor
    else:
        raise CorrecaoInvalidaError("status deve ser corrigido ou confirmado")
    novo = Fato(
        processo_id=original.processo_id,
        tipo=original.tipo,
        valor=gravar,
        evidencias=original.evidencias,
        extraido_por=EXTRAIDO_POR_PESSOA,
        versao_extrator=VERSAO_CORRECAO,
        confianca=1.0,
        status=status,
        substitui_fato_id=original.id,
    )
    salvar_fato(session, novo)
    session.flush()
    return novo


def cadeia_de_substituicao(fatos: Sequence[Fato]) -> dict[UUID, UUID]:
    """Mapa fato substituído → fato que o substitui.

    Args:
        fatos: Fatos do processo.

    Returns:
        Mapa de ids.
    """
    return {f.substitui_fato_id: f.id for f in fatos if f.substitui_fato_id is not None}
