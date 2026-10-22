"""Rotas do processo em revisão após incidente do agente (Etapa 6.8).

`GET /processos/{id}/revisao`: situação (qualquer usuário que vê o processo).
`POST /processos/{id}/liberar-revisao`: desembargador do gabinete ou administrador (os papéis
com `ver_auditoria`, que analisam o incidente na trilha) devolvem o processo ao status anterior;
a liberação é auditada (`revisao_liberada`).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from lupa.acesso.autorizacao import ContextoReq, SessaoBanco, exige_papel, exige_processo
from lupa.acesso.papeis import Permissao
from lupa.acesso.servico import Ator
from lupa.agente import revisao
from lupa.dominio.tabelas import ProcessoTabela

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
Revisor = Annotated[Ator, Depends(exige_papel(Permissao.VER_AUDITORIA))]


@router.get("/processos/{processo_id}/revisao")
def situacao_revisao(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Se o processo está em revisão e por quê.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        Situação de revisão.
    """
    return revisao.situacao(sessao, processo)


@router.post("/processos/{processo_id}/liberar-revisao")
def liberar_revisao(
    processo: Processo, ator: Revisor, sessao: SessaoBanco, ctx: ContextoReq
) -> dict[str, Any]:
    """Libera o processo em revisão.

    Args:
        processo: Processo autorizado (próprio gabinete, ou qualquer para o administrador).
        ator: Desembargador ou administrador.
        sessao: Sessão da requisição.
        ctx: Contexto (auditoria).

    Returns:
        Situação depois da liberação.
    """
    return revisao.liberar(sessao, ctx, processo, ator.usuario_id)
