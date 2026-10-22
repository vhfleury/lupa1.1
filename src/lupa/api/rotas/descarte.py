"""Rotas da Etapa 7: exclusão criptográfica do processo e rotação da chave do gabinete.

`POST /processos/{id}/descartar`: desembargador do gabinete ou administrador (papéis com
`ver_auditoria`). Apaga o conteúdo e a DEK; o processo vira tombstone `descartado`. Auditado
(`processo_descartado`, com o SHA-256 da DEK cifrada apagada).

`POST /gabinetes/{id}/rotacionar-chave`: só administrador. Nova versão da chave Transit do
gabinete e rewrap das DEKs. Auditado (`chave_rotacionada`).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from lupa.acesso.autorizacao import ContextoReq, SessaoBanco, exige_papel, exige_processo
from lupa.acesso.papeis import Permissao
from lupa.acesso.servico import Ator, auditar
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.tabelas import ProcessoTabela
from lupa.seguranca.chaves import rotacionar_gabinete
from lupa.seguranca.descarte import descartar

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
Revisor = Annotated[Ator, Depends(exige_papel(Permissao.VER_AUDITORIA))]
Administrador = Annotated[Ator, Depends(exige_papel(Permissao.GERIR_GABINETES))]


@router.post("/processos/{processo_id}/descartar")
def descartar_processo(
    request: Request, processo: Processo, ator: Revisor, sessao: SessaoBanco, ctx: ContextoReq
) -> dict[str, Any]:
    """Exclusão criptográfica do processo.

    Args:
        request: Requisição (storage da aplicação).
        processo: Processo autorizado.
        ator: Desembargador ou administrador.
        sessao: Sessão da requisição.
        ctx: Contexto (auditoria).

    Returns:
        `{processo_id, status, objetos_apagados}`.
    """
    resultado = descartar(sessao, request.app.state.storage, processo.gabinete_id, processo.id)
    auditar(
        sessao,
        ctx,
        AcaoAuditoria.PROCESSO_DESCARTADO,
        usuario_id=ator.usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo="dek_sha256",
        objeto_id=resultado.hash_chave,
    )
    return {
        "processo_id": str(processo.id),
        "status": "descartado",
        "objetos_apagados": resultado.objetos_apagados,
    }


@router.post("/gabinetes/{gabinete_id}/rotacionar-chave")
def rotacionar_chave(
    gabinete_id: UUID,
    request: Request,
    ator: Administrador,
    sessao: SessaoBanco,
    ctx: ContextoReq,
) -> dict[str, Any]:
    """Rotaciona a chave do gabinete e recifra as DEKs.

    Args:
        gabinete_id: Gabinete.
        request: Requisição (cofre da aplicação).
        ator: Administrador.
        sessao: Sessão da requisição (RLS de administrador).
        ctx: Contexto (auditoria).

    Returns:
        `{gabinete_id, deks_recifradas}`.
    """
    quantidade = rotacionar_gabinete(sessao, request.app.state.cofre, gabinete_id)
    auditar(
        sessao,
        ctx,
        AcaoAuditoria.CHAVE_ROTACIONADA,
        usuario_id=ator.usuario_id,
        gabinete_id=gabinete_id,
        objeto_tipo="gabinete",
        objeto_id=str(gabinete_id),
    )
    return {"gabinete_id": str(gabinete_id), "deks_recifradas": quantidade}
