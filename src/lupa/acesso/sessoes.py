"""Sessões server-side e desafios de MFA guardados em tabela.

O token entregue ao navegador tem 256 bits aleatórios; o banco guarda só o SHA-256 dele, de
modo que uma cópia do banco não permite sequestrar sessões. Expiração absoluta de 8 horas e
por inatividade de 30 minutos. O cookie é `HttpOnly`, `Secure` e `SameSite=Strict`.
"""

import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Response
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.tabelas import DesafioMfaTabela, SessaoTabela, UsuarioTabela

NOME_COOKIE = "lupa_sessao"
BYTES_TOKEN = 32
DURACAO_ABSOLUTA = timedelta(hours=8)
INATIVIDADE_MAXIMA = timedelta(minutes=30)
DURACAO_DESAFIO = timedelta(minutes=5)


def gerar_token() -> str:
    """Gera token aleatório de 256 bits.

    Returns:
        Token url-safe.
    """
    return secrets.token_urlsafe(BYTES_TOKEN)


def id_do_token(token: str) -> str:
    """Deriva o id armazenado a partir do token.

    Args:
        token: Token recebido do cliente.

    Returns:
        SHA-256 hexadecimal do token.
    """
    return calcular_hash(token)


def criar_sessao(session: Session, usuario: UsuarioTabela, ip: str | None, agora: datetime) -> str:
    """Cria a sessão do usuário (só depois do TOTP).

    Args:
        session: Sessão do banco.
        usuario: Usuário autenticado.
        ip: IP de criação.
        agora: Instante atual.

    Returns:
        Token a entregar no cookie.
    """
    token = gerar_token()
    session.add(
        SessaoTabela(
            id=id_do_token(token),
            usuario_id=usuario.id,
            gabinete_id=usuario.gabinete_id,
            papel=usuario.papel,
            criada_em=agora,
            expira_em=agora + DURACAO_ABSOLUTA,
            ultimo_acesso_em=agora,
            ip_criacao=ip,
            revogada=False,
        )
    )
    session.flush()
    return token


def carregar_sessao(session: Session, token: str, agora: datetime) -> SessaoTabela | None:
    """Carrega a sessão válida e renova o marcador de inatividade.

    Args:
        session: Sessão do banco.
        token: Token do cookie.
        agora: Instante atual.

    Returns:
        A sessão, ou None se inexistente, revogada ou expirada.
    """
    registro = session.get(SessaoTabela, id_do_token(token))
    if registro is None or registro.revogada:
        return None
    if agora >= registro.expira_em or agora - registro.ultimo_acesso_em >= INATIVIDADE_MAXIMA:
        return None
    registro.ultimo_acesso_em = agora
    session.flush()
    return registro


def revogar_sessao(session: Session, sessao_id: str) -> None:
    """Revoga uma sessão.

    Args:
        session: Sessão do banco.
        sessao_id: Id (hash) da sessão.
    """
    session.execute(update(SessaoTabela).where(SessaoTabela.id == sessao_id).values(revogada=True))


def revogar_sessoes_do_usuario(
    session: Session, usuario_id: UUID, exceto: str | None = None
) -> None:
    """Revoga todas as sessões do usuário, opcionalmente preservando uma.

    Args:
        session: Sessão do banco.
        usuario_id: Usuário dono das sessões.
        exceto: Id da sessão a preservar.
    """
    comando = update(SessaoTabela).where(
        SessaoTabela.usuario_id == usuario_id, SessaoTabela.revogada.is_(False)
    )
    if exceto is not None:
        comando = comando.where(SessaoTabela.id != exceto)
    session.execute(comando.values(revogada=True))
    session.execute(delete(DesafioMfaTabela).where(DesafioMfaTabela.usuario_id == usuario_id))


def criar_desafio(session: Session, usuario: UsuarioTabela, agora: datetime) -> str:
    """Cria o desafio do segundo passo do login.

    Args:
        session: Sessão do banco.
        usuario: Usuário que acertou a senha.
        agora: Instante atual.

    Returns:
        Token do desafio, a devolver ao cliente.
    """
    token = gerar_token()
    session.add(
        DesafioMfaTabela(
            id=id_do_token(token),
            usuario_id=usuario.id,
            gabinete_id=usuario.gabinete_id,
            papel=usuario.papel,
            criado_em=agora,
            expira_em=agora + DURACAO_DESAFIO,
            consumido=False,
        )
    )
    session.flush()
    return token


def carregar_desafio(session: Session, token: str, agora: datetime) -> DesafioMfaTabela | None:
    """Carrega o desafio ainda válido.

    Args:
        session: Sessão do banco.
        token: Token do desafio.
        agora: Instante atual.

    Returns:
        O desafio, ou None se inexistente, consumido ou expirado.
    """
    desafio = session.get(DesafioMfaTabela, id_do_token(token))
    if desafio is None or desafio.consumido or agora >= desafio.expira_em:
        return None
    return desafio


def definir_cookie(response: Response, token: str) -> None:
    """Grava o cookie de sessão com as flags de segurança.

    Args:
        response: Resposta HTTP.
        token: Token da sessão.
    """
    response.set_cookie(
        NOME_COOKIE,
        token,
        max_age=int(DURACAO_ABSOLUTA.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def apagar_cookie(response: Response) -> None:
    """Remove o cookie de sessão.

    Args:
        response: Resposta HTTP.
    """
    response.delete_cookie(NOME_COOKIE, httponly=True, secure=True, samesite="strict", path="/")
