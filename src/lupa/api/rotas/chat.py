"""Rotas do chat sobre os autos (Etapa 5).

`POST /processos/{id}/chat` recebe a pergunta e devolve a resposta com citações conferidas, a
recusa explicada ou a mensagem de teto; registra `pergunta_chat` e `chamada_modelo`.
`GET /processos/{id}/chat` devolve o histórico das conversas do usuário no processo (leitura de
conteúdo: `processo_aberto`, com `admin_acesso_conteudo` para o administrador). Processo de
outro gabinete responde 404 (`exige_processo`).
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from lupa.acesso.autorizacao import AtorAutenticado, ContextoReq, SessaoBanco, exige_processo
from lupa.acesso.erros import DadosInvalidosError
from lupa.agente import repositorio
from lupa.agente.cliente import ClienteAgente
from lupa.agente.servico import ContextoChat, limites_de, perguntar
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.config import Settings, get_settings
from lupa.dominio.tabelas import ProcessoTabela

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
Configuracao = Annotated[Settings, Depends(get_settings)]


class CorpoPergunta(BaseModel):
    """Pergunta do assessor."""

    model_config = ConfigDict(extra="forbid")

    pergunta: str = Field(min_length=1, max_length=20_000)


def cliente_agente(request: Request) -> ClienteAgente:
    """Cliente do modelo da aplicação (substituível nos testes).

    Args:
        request: Requisição.

    Returns:
        Cliente.
    """
    cliente: ClienteAgente = request.app.state.cliente_agente
    return cliente


Cliente = Annotated[ClienteAgente, Depends(cliente_agente)]


def contexto_chat(
    processo: Processo,
    ator: AtorAutenticado,
    sessao: SessaoBanco,
    ctx: ContextoReq,
    cliente: Cliente,
    settings: Configuracao,
) -> ContextoChat:
    """Monta o contexto do caso de uso do chat.

    Args:
        processo: Processo autorizado.
        ator: Quem pergunta.
        sessao: Sessão da requisição.
        ctx: Contexto (IP, localização, instante).
        cliente: Cliente do modelo.
        settings: Configuração.

    Returns:
        Contexto.
    """
    return ContextoChat(
        session=sessao,
        processo=processo,
        usuario_id=ator.usuario_id,
        ctx=ctx,
        cliente=cliente,
        limites=limites_de(settings),
        referencia=date.today(),
    )


Chat = Annotated[ContextoChat, Depends(contexto_chat)]


@router.post("/processos/{processo_id}/chat")
def perguntar_ao_chat(chat: Chat, corpo: CorpoPergunta, settings: Configuracao) -> dict[str, Any]:
    """Responde uma pergunta sobre o processo.

    Args:
        chat: Contexto do chat.
        corpo: Pergunta.
        settings: Configuração (tamanho máximo da pergunta).

    Returns:
        Mensagem do agente com citações conferidas, recusa ou teto.

    Raises:
        DadosInvalidosError: Pergunta acima do tamanho máximo.
    """
    pergunta = corpo.pergunta.strip()
    if not pergunta or len(pergunta) > settings.agente_max_caracteres_pergunta:
        raise DadosInvalidosError(
            f"a pergunta deve ter de 1 a {settings.agente_max_caracteres_pergunta} caracteres"
        )
    return perguntar(chat, pergunta)


@router.get("/processos/{processo_id}/chat")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def historico_do_chat(
    processo: Processo, ator: AtorAutenticado, sessao: SessaoBanco
) -> dict[str, Any]:
    """Histórico das conversas do usuário no processo.

    Args:
        processo: Processo autorizado.
        ator: Usuário.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, conversas: [...]}`.
    """
    return {
        "processo_id": str(processo.id),
        "conversas": repositorio.historico(sessao, processo.id, ator.usuario_id),
    }
