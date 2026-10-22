"""Origem por trecho (Etapa 4D.8).

Cada trecho suspeito (e cada evidência futura) carrega a origem da peça a que a página
pertence: juízo, MP, defesa ou terceiro. Na ingestão a origem ainda não é conhecida (a
classificação de peças vem da 4E), então o trecho nasce `desconhecida`; quando há peça
classificada que cobre a página, a origem é lida de `peca.origem`. Nunca há trecho sem rótulo.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lupa.dominio.enums import OrigemPeca
from lupa.dominio.tabelas import PaginaTabela, PecaTabela


def origem_da_pagina(session: Session, pagina_id: UUID) -> OrigemPeca:
    """Origem da peça que contém a página.

    Só contam as peças vigentes (a reclassificação manual encerra a versão anterior); com mais
    de uma cobrindo a página, vale a de maior confiança; sem peça, `desconhecida`.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        pagina_id: Página.

    Returns:
        Origem da peça, ou `desconhecida`.
    """
    pagina = session.get(PaginaTabela, pagina_id)
    if pagina is None:
        return OrigemPeca.DESCONHECIDA
    consulta = (
        select(PecaTabela.origem)
        .where(
            PecaTabela.arquivo_id == pagina.arquivo_id,
            PecaTabela.vigente.is_(True),
            PecaTabela.pagina_inicial <= pagina.numero,
            PecaTabela.pagina_final >= pagina.numero,
        )
        .order_by(PecaTabela.confianca.desc(), PecaTabela.id)
        .limit(1)
    )
    origem = session.scalar(consulta)
    return OrigemPeca(origem) if origem else OrigemPeca.DESCONHECIDA


def rotular(trechos: list[dict[str, Any]], origem: OrigemPeca) -> list[dict[str, Any]]:
    """Aplica a origem a trechos (o rótulo ausente vira `desconhecida`).

    Args:
        trechos: Trechos suspeitos.
        origem: Origem da peça (use `desconhecida` quando não houver).

    Returns:
        Cópias dos trechos com `origem`.
    """
    return [t | {"origem": (origem or OrigemPeca.DESCONHECIDA).value} for t in trechos]


def trechos_rotulados(session: Session, pagina_id: UUID) -> list[dict[str, Any]]:
    """Trechos suspeitos da página com a origem da peça.

    Args:
        session: Sessão com transação aberta.
        pagina_id: Página.

    Returns:
        Trechos com `origem`; lista vazia se a página não existe.
    """
    pagina = session.get(PaginaTabela, pagina_id)
    if pagina is None:
        return []
    return rotular(list(pagina.trechos_suspeitos or []), origem_da_pagina(session, pagina_id))
