"""Endpoints de autenticação, usuários e gabinetes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from lupa.acesso import servico, sessoes
from lupa.acesso.autorizacao import (
    AtorAutenticado,
    ContextoReq,
    SessaoBanco,
    exige_papel,
    usuario_autenticado_permitindo_troca,
)
from lupa.acesso.papeis import MATRIZ, Permissao
from lupa.acesso.servico import Ator, Contexto
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import UsuarioTabela

router = APIRouter()


class EntradaLogin(BaseModel):
    """Primeiro passo do login."""

    nome_usuario: str = Field(min_length=1, max_length=64)
    senha: str = Field(min_length=1, max_length=256, repr=False)


class EntradaMfa(BaseModel):
    """Segundo passo do login (ou confirmação do autenticador)."""

    desafio: str = Field(min_length=1, max_length=128, repr=False)
    codigo: str = Field(pattern=r"^\d{6}$", repr=False)


class EntradaTrocaSenha(BaseModel):
    """Troca da própria senha."""

    senha_atual: str = Field(min_length=1, max_length=256, repr=False)
    nova_senha: str = Field(min_length=1, max_length=256, repr=False)


class EntradaUsuario(BaseModel):
    """Criação de usuário."""

    nome_usuario: str = Field(min_length=1, max_length=64)
    papel: PapelUsuario
    gabinete_id: UUID | None = None


class EntradaGabinete(BaseModel):
    """Criação de gabinete."""

    nome: str = Field(min_length=1, max_length=200)


class SaidaUsuario(BaseModel):
    """Usuário sem segredos."""

    id: UUID
    nome_usuario: str
    papel: PapelUsuario
    gabinete_id: UUID | None
    ativo: bool
    mfa_confirmado: bool
    troca_senha_obrigatoria: bool


class SaidaUsuarioComSenha(SaidaUsuario):
    """Usuário com a senha temporária, exibida uma única vez."""

    senha_temporaria: str


def _saida(usuario: UsuarioTabela) -> SaidaUsuario:
    return SaidaUsuario(
        id=usuario.id,
        nome_usuario=usuario.nome_usuario,
        papel=PapelUsuario(usuario.papel),
        gabinete_id=usuario.gabinete_id,
        ativo=usuario.ativo,
        mfa_confirmado=usuario.mfa_confirmado,
        troca_senha_obrigatoria=usuario.troca_senha_obrigatoria,
    )


def _saida_com_senha(resultado: servico.UsuarioComSenha) -> SaidaUsuarioComSenha:
    return SaidaUsuarioComSenha(
        **_saida(resultado.usuario).model_dump(), senha_temporaria=resultado.senha_temporaria
    )


@router.post("/auth/login")
def login(entrada: EntradaLogin, session: SessaoBanco, ctx: ContextoReq) -> dict[str, object]:
    """Confere usuário e senha e devolve o desafio do TOTP; não cria sessão.

    Args:
        entrada: Usuário e senha.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        `desafio` e a próxima etapa (`mfa` ou `configurar_mfa`, com segredo e URI do QR).
    """
    resultado = servico.autenticar_senha(session, entrada.nome_usuario, entrada.senha, ctx)
    if resultado.provisionamento is None:
        return {"etapa": "mfa", "desafio": resultado.desafio}
    return {
        "etapa": "configurar_mfa",
        "desafio": resultado.desafio,
        "segredo": resultado.provisionamento.segredo,
        "uri_qr": resultado.provisionamento.uri,
    }


def _concluir(
    entrada: EntradaMfa, response: Response, session: SessaoBanco, ctx: Contexto, confirmando: bool
) -> dict[str, object]:
    resultado = servico.concluir_mfa(
        session, entrada.desafio, entrada.codigo, ctx, confirmando=confirmando
    )
    sessoes.definir_cookie(response, resultado.token)
    return {"troca_senha_obrigatoria": resultado.troca_senha_obrigatoria}


@router.post("/auth/mfa")
def mfa(
    entrada: EntradaMfa, response: Response, session: SessaoBanco, ctx: ContextoReq
) -> dict[str, object]:
    """Confere o TOTP e cria a sessão (cookie `HttpOnly`, `Secure`, `SameSite=Strict`).

    Args:
        entrada: Desafio e código.
        response: Resposta, para gravar o cookie.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        Se a troca de senha é obrigatória.
    """
    return _concluir(entrada, response, session, ctx, confirmando=False)


@router.post("/auth/mfa/confirmar")
def confirmar_mfa(
    entrada: EntradaMfa, response: Response, session: SessaoBanco, ctx: ContextoReq
) -> dict[str, object]:
    """Ativa o autenticador recém-cadastrado com um código válido e cria a sessão.

    Args:
        entrada: Desafio e código.
        response: Resposta, para gravar o cookie.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        Se a troca de senha é obrigatória.
    """
    return _concluir(entrada, response, session, ctx, confirmando=True)


@router.post("/auth/logout", status_code=204)
def logout(
    ator: AtorAutenticado, response: Response, session: SessaoBanco, ctx: ContextoReq
) -> None:
    """Revoga a sessão corrente e apaga o cookie.

    Args:
        ator: Usuário autenticado.
        response: Resposta.
        session: Sessão do banco.
        ctx: Contexto da requisição.
    """
    servico.sair(session, ator, ctx)
    sessoes.apagar_cookie(response)


class SaidaSessao(BaseModel):
    """Quem está logado e o que o papel pode fazer (para a interface esconder botões)."""

    usuario_id: UUID
    nome_usuario: str
    papel: PapelUsuario
    gabinete_id: UUID | None
    troca_senha_obrigatoria: bool
    permissoes: list[str]


@router.get("/auth/sessao")
def sessao_atual(
    ator: Annotated[Ator, Depends(usuario_autenticado_permitindo_troca)],
) -> SaidaSessao:
    """Devolve o usuário da sessão corrente e as permissões do papel (matriz de `papeis.py`).

    A interface usa as permissões só para esconder ações; o servidor reconfere cada uma.

    Args:
        ator: Usuário autenticado (mesmo com troca de senha pendente).

    Returns:
        Dados da sessão, sem segredos.
    """
    return SaidaSessao(
        usuario_id=ator.usuario_id,
        nome_usuario=ator.nome_usuario,
        papel=ator.papel,
        gabinete_id=ator.gabinete_id,
        troca_senha_obrigatoria=ator.troca_senha_obrigatoria,
        permissoes=sorted(p.value for p in MATRIZ[ator.papel]),
    )


@router.post("/auth/trocar-senha", status_code=204)
def trocar_senha(
    entrada: EntradaTrocaSenha,
    ator: Annotated[Ator, Depends(usuario_autenticado_permitindo_troca)],
    session: SessaoBanco,
    ctx: ContextoReq,
) -> None:
    """Troca a própria senha; as demais sessões do usuário são revogadas.

    Args:
        entrada: Senha atual e nova.
        ator: Usuário autenticado (mesmo com troca pendente).
        session: Sessão do banco.
        ctx: Contexto da requisição.
    """
    servico.trocar_senha(session, ator, entrada.senha_atual, entrada.nova_senha, ctx)


@router.get("/usuarios")
def listar_usuarios(
    ator: AtorAutenticado, session: SessaoBanco, gabinete_id: UUID | None = None
) -> list[SaidaUsuario]:
    """Lista usuários do gabinete (administrador: de qualquer gabinete ou de todos).

    Args:
        ator: Usuário autenticado.
        session: Sessão do banco.
        gabinete_id: Gabinete desejado.

    Returns:
        Usuários sem segredos.
    """
    return [_saida(u) for u in servico.listar_usuarios(session, ator, gabinete_id)]


@router.post("/usuarios", status_code=201)
def criar_usuario(
    entrada: EntradaUsuario, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> SaidaUsuarioComSenha:
    """Cria assessor (desembargador ou admin) ou desembargador (admin).

    Args:
        entrada: Dados do novo usuário.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O usuário e a senha temporária.
    """
    resultado = servico.criar_usuario(
        session, ator, entrada.nome_usuario, entrada.papel, entrada.gabinete_id, ctx
    )
    return _saida_com_senha(resultado)


@router.post("/usuarios/{usuario_id}/desativar")
def desativar(
    usuario_id: UUID, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> SaidaUsuario:
    """Desativa o usuário (não apaga nada) e revoga as sessões dele.

    Args:
        usuario_id: Usuário alvo.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O usuário alterado.
    """
    return _saida(servico.alterar_ativo(session, ator, usuario_id, False, ctx))


@router.post("/usuarios/{usuario_id}/reativar")
def reativar(
    usuario_id: UUID, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> SaidaUsuario:
    """Reativa o usuário.

    Args:
        usuario_id: Usuário alvo.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O usuário alterado.
    """
    return _saida(servico.alterar_ativo(session, ator, usuario_id, True, ctx))


@router.post("/usuarios/{usuario_id}/resetar-senha")
def resetar_senha(
    usuario_id: UUID, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> SaidaUsuarioComSenha:
    """Gera senha temporária com troca obrigatória.

    Args:
        usuario_id: Usuário alvo.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O usuário e a senha temporária.
    """
    return _saida_com_senha(servico.resetar_senha(session, ator, usuario_id, ctx))


@router.post("/usuarios/{usuario_id}/resetar-mfa")
def resetar_mfa(
    usuario_id: UUID, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> SaidaUsuario:
    """Apaga o autenticador do usuário; o próximo login cadastra outro.

    Args:
        usuario_id: Usuário alvo.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        O usuário alterado.
    """
    return _saida(servico.resetar_mfa(session, ator, usuario_id, ctx))


@router.post("/gabinetes", status_code=201)
def criar_gabinete(
    entrada: EntradaGabinete, ator: AtorAutenticado, session: SessaoBanco, ctx: ContextoReq
) -> dict[str, object]:
    """Cria gabinete (só administrador).

    Args:
        entrada: Nome do gabinete.
        ator: Usuário autenticado.
        session: Sessão do banco.
        ctx: Contexto da requisição.

    Returns:
        Id e nome do gabinete.
    """
    gabinete = servico.criar_gabinete(session, ator, entrada.nome, ctx)
    return {"id": str(gabinete.id), "nome": gabinete.nome}


@router.get("/gabinetes")
def listar_gabinetes(
    _ator: Annotated[Ator, Depends(exige_papel(Permissao.GERIR_GABINETES))],
    session: SessaoBanco,
) -> list[dict[str, object]]:
    """Lista os gabinetes (só administrador), para criar desembargadores.

    Args:
        _ator: Administrador autenticado.
        session: Sessão do banco.

    Returns:
        Id e nome de cada gabinete, por nome.
    """
    return [{"id": str(g.id), "nome": g.nome} for g in servico.listar_gabinetes(session)]
