"""Rota do dossiê do processo (Etapa 5.10).

`GET /processos/{id}/dossie` devolve o dossiê em esquema fixo, montado dos dados estruturados
sem modelo. Com `?resumos=true`, o modelo preenche `resumo_peca` (rotulado `gerado`, com
citação conferida) nas primeiras peças. Leitura de conteúdo: `processo_aberto`, com
`admin_acesso_conteudo` para o administrador. Processo de outro gabinete responde 404.
"""

from typing import Any

from fastapi import APIRouter

from lupa.acesso.autorizacao import SessaoBanco
from lupa.agente.dossie import montar_dossie, preencher_resumos
from lupa.api.middleware import auditar_rota
from lupa.api.rotas.chat import Chat, Configuracao, Processo
from lupa.auditoria.eventos import AcaoAuditoria

router = APIRouter()


@router.get("/processos/{processo_id}/dossie")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_dossie(
    processo: Processo,
    sessao: SessaoBanco,
    chat: Chat,
    settings: Configuracao,
    resumos: bool = False,
) -> dict[str, Any]:
    """Dossiê do processo.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.
        chat: Contexto do agente (usado só com `resumos`).
        settings: Configuração (quantas peças resumir).
        resumos: Se pede `resumo_peca` ao modelo.

    Returns:
        Dossiê serializado.
    """
    dossie = montar_dossie(sessao, processo, chat.usuario_id)
    if resumos:
        dossie = preencher_resumos(chat, dossie, settings.agente_max_resumos_dossie)
    return dossie.model_dump(mode="json")
