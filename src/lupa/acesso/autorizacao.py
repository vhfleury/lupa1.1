"""Dependências FastAPI de autenticação e autorização, verificadas no servidor a cada requisição.

`usuario_autenticado` carrega a sessão do cookie, define o contexto da RLS (`lupa.papel` e
`lupa.gabinete_id`) e devolve o `Ator`. `exige_papel` confere a matriz de `papeis.py`.
`exige_gabinete` resolve o gabinete-alvo de consultas. `exige_processo` carrega o processo sob
RLS e responde 404 (nunca 403) quando ele é de outro gabinete, registrando a tentativa; depois
abre a DEK do processo no contexto de cifra da requisição (Etapa 7.3).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from lupa.acesso import sessoes
from lupa.acesso.erros import (
    NaoAutenticadoError,
    NaoEncontradoError,
    PermissaoNegadaError,
    TrocaSenhaObrigatoriaError,
)
from lupa.acesso.papeis import Permissao, pode, tem_permissao
from lupa.acesso.servico import Ator, Contexto, auditar, definir_contexto
from lupa.api.banco import obter_sessao_banco
from lupa.auditoria.eventos import AcaoAuditoria, ResultadoEvento
from lupa.dominio.enums import PapelUsuario, StatusProcesso
from lupa.dominio.tabelas import ProcessoTabela, UsuarioTabela
from lupa.seguranca.contexto import ativar_processo

SessaoBanco = Annotated[Session, Depends(obter_sessao_banco)]


def relogio() -> datetime:
    """Instante atual em UTC (dependência substituível nos testes).

    Returns:
        Agora, com fuso.
    """
    return datetime.now(UTC)


def contexto_requisicao(request: Request, agora: Annotated[datetime, Depends(relogio)]) -> Contexto:
    """Monta IP, localização e instante da requisição.

    O IP é o da conexão; atrás de proxy reverso, configure o uvicorn com `--proxy-headers` e
    `--forwarded-allow-ips` apenas para o proxy confiável.

    Args:
        request: Requisição corrente.
        agora: Instante atual.

    Returns:
        Contexto para auditoria.
    """
    ip = request.client.host if request.client else None
    return Contexto(ip=ip, localizacao=request.app.state.resolvedor.resolver(ip), agora=agora)


ContextoReq = Annotated[Contexto, Depends(contexto_requisicao)]


def _ator(session: Session, request: Request, ctx: Contexto) -> Ator:
    token = request.cookies.get(sessoes.NOME_COOKIE)
    registro = sessoes.carregar_sessao(session, token, ctx.agora) if token else None
    if registro is None:
        raise NaoAutenticadoError("não autenticado")
    definir_contexto(session, registro.papel, registro.gabinete_id)
    usuario = session.get(UsuarioTabela, registro.usuario_id)
    if usuario is None or not usuario.ativo:
        raise NaoAutenticadoError("não autenticado")
    ator = Ator(
        usuario_id=usuario.id,
        gabinete_id=usuario.gabinete_id,
        papel=PapelUsuario(usuario.papel),
        nome_usuario=usuario.nome_usuario,
        sessao_id=registro.id,
        troca_senha_obrigatoria=usuario.troca_senha_obrigatoria,
    )
    request.state.ator = ator
    return ator


def usuario_autenticado_permitindo_troca(
    request: Request, session: SessaoBanco, ctx: ContextoReq
) -> Ator:
    """Autentica sem barrar quem precisa trocar a senha (só para a rota de troca).

    Args:
        request: Requisição corrente.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O ator autenticado.

    Raises:
        NaoAutenticadoError: Sem sessão válida.
    """
    return _ator(session, request, ctx)


def usuario_autenticado(
    ator: Annotated[Ator, Depends(usuario_autenticado_permitindo_troca)],
) -> Ator:
    """Autentica e barra quem tem troca de senha pendente.

    Args:
        ator: Ator carregado da sessão.

    Returns:
        O ator autenticado.

    Raises:
        TrocaSenhaObrigatoriaError: Se a troca de senha estiver pendente.
    """
    if ator.troca_senha_obrigatoria:
        raise TrocaSenhaObrigatoriaError("troca de senha obrigatória")
    return ator


AtorAutenticado = Annotated[Ator, Depends(usuario_autenticado)]


def exige_papel(permissao: Permissao) -> Callable[[Ator], Ator]:
    """Cria dependência que exige que o papel do ator tenha a permissão.

    Args:
        permissao: Permissão exigida (em qualquer escopo).

    Returns:
        Dependência que devolve o ator ou lança `PermissaoNegadaError`.
    """

    def _dependencia(ator: AtorAutenticado) -> Ator:
        if not tem_permissao(ator.papel, permissao):
            raise PermissaoNegadaError("ação não permitida para o seu papel")
        return ator

    return _dependencia


def exige_gabinete(permissao: Permissao) -> Callable[[Ator, UUID | None], UUID | None]:
    """Cria dependência que resolve o gabinete-alvo de uma consulta (`?gabinete_id=`).

    Para quem tem escopo de gabinete, o alvo é sempre o próprio gabinete (pedir outro dá 403).
    Para o administrador, o alvo é o informado, ou None (todos / cadeia global).

    Args:
        permissao: Permissão exigida.

    Returns:
        Dependência que devolve o gabinete-alvo.
    """

    def _dependencia(ator: AtorAutenticado, gabinete_id: UUID | None = None) -> UUID | None:
        alvo = gabinete_id if gabinete_id is not None else ator.gabinete_id
        if not pode(ator.papel, permissao, ator.gabinete_id, alvo):
            raise PermissaoNegadaError("ação não permitida para o seu papel")
        return alvo

    return _dependencia


def exige_processo(
    processo_id: UUID,
    request: Request,
    ator: AtorAutenticado,
    session: SessaoBanco,
    ctx: ContextoReq,
) -> ProcessoTabela:
    """Carrega o processo do caminho conferindo gabinete e papel.

    A tentativa negada é gravada na transação da requisição, que é confirmada mesmo com o 404
    porque `NaoEncontradoError` é uma recusa prevista.

    Args:
        processo_id: Id do processo (parâmetro de caminho).
        request: Requisição corrente.
        ator: Ator autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O processo.

    Raises:
        NaoEncontradoError: Processo inexistente ou de outro gabinete.
    """
    processo = session.get(ProcessoTabela, processo_id)
    if processo is None or not pode(
        ator.papel, Permissao.VER_PROCESSO, ator.gabinete_id, processo.gabinete_id
    ):
        auditar(
            session,
            ctx,
            AcaoAuditoria.PROCESSO_ABERTO,
            ResultadoEvento.NEGADO,
            usuario_id=ator.usuario_id,
            gabinete_id=ator.gabinete_id,
            processo_id=processo_id,
            objeto_tipo="processo",
            objeto_id=str(processo_id),
        )
        raise NaoEncontradoError("processo não encontrado")
    if processo.status == StatusProcesso.DESCARTADO.value:
        raise NaoEncontradoError("processo descartado")
    ativar_processo(processo.id, processo.gabinete_id, processo.chave_dados_cifrada)
    request.state.processo = (processo.id, processo.gabinete_id)
    return processo
