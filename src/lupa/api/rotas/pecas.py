"""Rotas do índice do processo e das peças (Etapas 4E.7, 4E.8 e 4E.10).

`GET /processos/{id}/indice` exporta o índice em JSON (peças vigentes com tipo, origem,
páginas, data com evidência, confiança, método e resumo de flags). `GET .../pecas/{peca_id}`
devolve uma peça com a classificação e o histórico de versões. As duas leituras são auditadas
automaticamente como `processo_aberto` (com `admin_acesso_conteudo` para o administrador).
`POST .../pecas/{peca_id}/reclassificar` grava a correção do assessor como peça nova e registra
`peca_reclassificada` na auditoria. Processo de outro gabinete responde 404 (`exige_processo`).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, model_validator

from lupa.acesso.autorizacao import AtorAutenticado, ContextoReq, SessaoBanco, exige_processo
from lupa.acesso.erros import DadosInvalidosError, NaoEncontradoError, PermissaoNegadaError
from lupa.acesso.papeis import Permissao, pode
from lupa.acesso.servico import auditar
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.enums import OrigemPeca, TipoPeca
from lupa.dominio.tabelas import ProcessoTabela
from lupa.ingestao import repositorio_pecas
from lupa.ingestao.repositorio_pecas import PedidoReclassificacao, ReclassificacaoInvalidaError

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]


class CorpoReclassificacao(BaseModel):
    """Correção pedida: tipo e/ou origem, ou nova fronteira (dividir ou unir)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoPeca | None = None
    origem: OrigemPeca | None = None
    dividir_em: int | None = None
    unir_com: UUID | None = None

    @model_validator(mode="after")
    def _uma_fronteira(self) -> "CorpoReclassificacao":
        if self.dividir_em is not None and self.unir_com is not None:
            raise ValueError("escolha dividir ou unir, não os dois")
        return self


@router.get("/processos/{processo_id}/indice")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_indice(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Índice do processo em JSON.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, pecas: [...]}` com as peças vigentes em ordem.
    """
    return {
        "processo_id": str(processo.id),
        "pecas": repositorio_pecas.indice_processo(sessao, processo.id),
    }


@router.get("/processos/{processo_id}/pecas/{peca_id}")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_peca(processo: Processo, peca_id: UUID, sessao: SessaoBanco) -> dict[str, Any]:
    """Peça com a classificação e as versões anteriores.

    Args:
        processo: Processo autorizado.
        peca_id: Peça.
        sessao: Sessão da requisição.

    Returns:
        Peça serializada com `classificacao` e `historico`.

    Raises:
        NaoEncontradoError: Peça inexistente ou de outro processo.
    """
    peca = repositorio_pecas.obter_peca(sessao, processo.id, peca_id)
    if peca is None:
        raise NaoEncontradoError("peça não encontrada")
    return repositorio_pecas.detalhar_peca(sessao, peca)


@router.post("/processos/{processo_id}/pecas/{peca_id}/reclassificar", status_code=201)
def reclassificar_peca(
    processo: Processo,
    peca_id: UUID,
    corpo: CorpoReclassificacao,
    ator: AtorAutenticado,
    sessao: SessaoBanco,
    ctx: ContextoReq,
) -> dict[str, Any]:
    """Grava a correção do assessor como nova versão da peça.

    Args:
        processo: Processo autorizado.
        peca_id: Peça vigente a corrigir.
        corpo: Tipo, origem, `dividir_em` (página do arquivo) ou `unir_com` (peça vizinha).
        ator: Quem corrige.
        sessao: Sessão da requisição.
        ctx: Contexto para a auditoria.

    Returns:
        `{pecas: [...], substituidas: [...]}`.

    Raises:
        PermissaoNegadaError: Papel sem permissão de anotar no gabinete.
        NaoEncontradoError: Peça inexistente ou de outro processo.
        DadosInvalidosError: Pedido incoerente.
    """
    if not pode(ator.papel, Permissao.ANOTAR, ator.gabinete_id, processo.gabinete_id):
        raise PermissaoNegadaError("ação não permitida para o seu papel")
    peca = repositorio_pecas.obter_peca(sessao, processo.id, peca_id)
    if peca is None:
        raise NaoEncontradoError("peça não encontrada")
    pedido = PedidoReclassificacao(corpo.tipo, corpo.origem, corpo.dividir_em, corpo.unir_com)
    try:
        novas = repositorio_pecas.reclassificar(sessao, peca, pedido, ator.usuario_id)
    except ReclassificacaoInvalidaError as erro:
        raise DadosInvalidosError(str(erro)) from None
    for nova in novas:
        auditar(
            sessao,
            ctx,
            AcaoAuditoria.PECA_RECLASSIFICADA,
            usuario_id=ator.usuario_id,
            gabinete_id=processo.gabinete_id,
            processo_id=processo.id,
            objeto_tipo="peca",
            objeto_id=str(nova.id),
        )
    detalhes = [repositorio_pecas.detalhar_peca(sessao, nova) for nova in novas]
    substituidas = sorted({h["id"] for d in detalhes for h in d["historico"]})
    return {"pecas": detalhes, "substituidas": substituidas}
