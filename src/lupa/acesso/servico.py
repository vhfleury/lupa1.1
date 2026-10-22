"""Casos de uso de acesso: login em dois passos, troca e reset de senha, gestão de usuários.

Toda função recebe a sessão do banco já sob o papel `lupa_app`; quem define o contexto da RLS
(`lupa.papel` e `lupa.gabinete_id`) é `definir_contexto`, chamado aqui no login e em
`autorizacao` nas demais requisições. Cada ação relevante grava um evento de auditoria.
"""

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypedDict, Unpack
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from lupa.acesso import mfa, senhas, sessoes
from lupa.acesso.erros import (
    ConflitoError,
    CredenciaisInvalidasError,
    DadosInvalidosError,
    LoginBloqueadoError,
    NaoAutenticadoError,
    NaoEncontradoError,
    PermissaoNegadaError,
)
from lupa.acesso.papeis import (
    PERMISSAO_PARA_GERIR,
    PERMISSAO_PARA_RESETAR,
    Permissao,
    pode,
)
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento, ResultadoEvento
from lupa.auditoria.registrador import registrar
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.sessao import definir_gabinete, definir_papel
from lupa.dominio.tabelas import (
    BloqueioLoginTabela,
    DesafioMfaTabela,
    FalhaLoginTabela,
    GabineteTabela,
    UsuarioTabela,
)
from lupa.seguranca.chaves import criar_chaves_gabinete
from lupa.seguranca.contexto import obter_cofre

MAXIMO_FALHAS = 5
JANELA_FALHAS = timedelta(hours=24)
DURACOES_BLOQUEIO = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
MAXIMO_FALHAS_IP = 20
JANELA_FALHAS_IP = timedelta(minutes=15)
PADRAO_NOME_USUARIO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
MENSAGEM_CREDENCIAIS = "usuário ou senha inválidos"
MENSAGEM_CODIGO = "código inválido"
MENSAGEM_BLOQUEIO = "muitas tentativas; tente novamente mais tarde"


class CamposEvento(TypedDict, total=False):
    """Campos opcionais de um evento de auditoria (ver `NovoEvento`)."""

    usuario_id: UUID | None
    gabinete_id: UUID | None
    processo_id: UUID | None
    objeto_tipo: str | None
    objeto_id: str | None
    versao_modelo: str | None
    versao_prompt: str | None


@dataclass(frozen=True)
class Contexto:
    """Dados da requisição usados na auditoria.

    Attributes:
        ip: IP de origem.
        localizacao: Localização aproximada.
        agora: Instante de referência da requisição.
    """

    ip: str | None
    localizacao: str | None
    agora: datetime


@dataclass(frozen=True)
class Ator:
    """Usuário autenticado que executa a ação.

    Attributes:
        usuario_id: Id do usuário.
        gabinete_id: Gabinete (None para o administrador).
        papel: Papel.
        nome_usuario: Nome de usuário.
        sessao_id: Id (hash) da sessão corrente.
        troca_senha_obrigatoria: Se a única ação permitida é trocar a senha.
    """

    usuario_id: UUID
    gabinete_id: UUID | None
    papel: PapelUsuario
    nome_usuario: str
    sessao_id: str
    troca_senha_obrigatoria: bool = False


@dataclass(frozen=True)
class ResultadoSenha:
    """Resultado do primeiro passo do login.

    Attributes:
        desafio: Token a enviar no segundo passo.
        provisionamento: Dados do autenticador quando o MFA ainda não foi configurado.
    """

    desafio: str
    provisionamento: mfa.ProvisionamentoMfa | None


@dataclass(frozen=True)
class ResultadoLogin:
    """Resultado do segundo passo do login.

    Attributes:
        token: Token da sessão criada.
        troca_senha_obrigatoria: Se o usuário precisa trocar a senha agora.
    """

    token: str
    troca_senha_obrigatoria: bool


@dataclass(frozen=True)
class UsuarioComSenha:
    """Usuário recém-criado ou resetado com a senha temporária (exibida uma única vez).

    Attributes:
        usuario: Registro do usuário.
        senha_temporaria: Senha temporária.
    """

    usuario: UsuarioTabela
    senha_temporaria: str


def definir_contexto(session: Session, papel: str, gabinete_id: UUID | None) -> None:
    """Define o contexto da RLS para a transação corrente.

    Args:
        session: Sessão do banco.
        papel: Papel do usuário.
        gabinete_id: Gabinete do usuário, ou None (administrador ou desconhecido).
    """
    definir_papel(session, papel)
    if gabinete_id is not None:
        definir_gabinete(session, gabinete_id)


def auditar(
    session: Session,
    ctx: Contexto,
    acao: AcaoAuditoria,
    resultado: ResultadoEvento = ResultadoEvento.OK,
    **campos: Unpack[CamposEvento],
) -> None:
    """Registra um evento com IP e localização do contexto.

    Args:
        session: Sessão do banco.
        ctx: Contexto da requisição.
        acao: Ação auditada.
        resultado: Desfecho.
        **campos: Demais campos de `NovoEvento`.
    """
    evento = NovoEvento.model_validate(
        {"acao": acao, "resultado": resultado, "ip": ctx.ip, "localizacao": ctx.localizacao}
        | dict(campos)
    )
    registrar(session, evento)


def _chave(nome_usuario: str) -> str:
    return calcular_hash(nome_usuario.strip().lower())


def _localizar(session: Session, nome_usuario: str) -> UsuarioTabela | None:
    linha = session.execute(
        text("SELECT id, gabinete_id, papel FROM lupa_localizar_usuario(:nome)"),
        {"nome": nome_usuario},
    ).first()
    if linha is None:
        return None
    definir_contexto(session, linha.papel, linha.gabinete_id)
    return session.get(UsuarioTabela, linha.id)


def _bloqueado(session: Session, chave: str, agora: datetime) -> bool:
    bloqueio = session.get(BloqueioLoginTabela, chave)
    return bloqueio is not None and bloqueio.bloqueado_ate > agora


def _campos_usuario(usuario: UsuarioTabela | None) -> CamposEvento:
    if usuario is None:
        return {"objeto_tipo": "usuario"}
    return {
        "usuario_id": usuario.id,
        "gabinete_id": usuario.gabinete_id,
        "objeto_tipo": "usuario",
        "objeto_id": str(usuario.id),
    }


def _contar_falhas(session: Session, chave: str, desde: datetime) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(FalhaLoginTabela)
            .where(FalhaLoginTabela.chave == chave)
            .where(FalhaLoginTabela.ocorrida_em > desde)
        )
        or 0
    )


def _chave_ip(ip: str | None) -> str | None:
    """Chave do rate limit por IP; None quando não há IP utilizável (ex.: cliente de teste)."""
    if ip is None:
        return None
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return calcular_hash(f"ip:{endereco.compressed}")


def duracao_bloqueio(falhas: int) -> timedelta | None:
    """Duração do bloqueio por nome depois de `falhas` falhas seguidas (progressivo).

    A 5ª falha bloqueia por 1 minuto, a 10ª por 5 e a 15ª (e cada 5 a mais) por 15 minutos.
    As falhas só zeram com um login certo ou depois de 24 horas sem falhar.

    Args:
        falhas: Falhas consecutivas na janela.

    Returns:
        Duração do bloqueio, ou None se a contagem não fecha um ciclo de 5.
    """
    if falhas == 0 or falhas % MAXIMO_FALHAS:
        return None
    nivel = min(falhas // MAXIMO_FALHAS, len(DURACOES_BLOQUEIO)) - 1
    return DURACOES_BLOQUEIO[nivel]


def _registrar_falha(
    session: Session,
    chave: str,
    usuario: UsuarioTabela | None,
    ctx: Contexto,
    acao: AcaoAuditoria,
) -> None:
    session.add(FalhaLoginTabela(id=uuid4(), chave=chave, ocorrida_em=ctx.agora))
    chave_ip = _chave_ip(ctx.ip)
    if chave_ip is not None:
        session.add(FalhaLoginTabela(id=uuid4(), chave=chave_ip, ocorrida_em=ctx.agora))
    session.flush()
    auditar(session, ctx, acao, ResultadoEvento.FALHA, **_campos_usuario(usuario))
    if (
        chave_ip is not None
        and _contar_falhas(session, chave_ip, ctx.agora - JANELA_FALHAS_IP) == MAXIMO_FALHAS_IP
    ):
        auditar(
            session, ctx, AcaoAuditoria.LOGIN_BLOQUEADO, ResultadoEvento.BLOQUEADO, objeto_tipo="ip"
        )
    duracao = duracao_bloqueio(_contar_falhas(session, chave, ctx.agora - JANELA_FALHAS))
    if duracao is None:
        return
    session.merge(BloqueioLoginTabela(chave=chave, bloqueado_ate=ctx.agora + duracao))
    auditar(
        session,
        ctx,
        AcaoAuditoria.LOGIN_BLOQUEADO,
        ResultadoEvento.BLOQUEADO,
        **_campos_usuario(usuario),
    )


def _recusar_se_ip_excedido(session: Session, ctx: Contexto) -> None:
    chave_ip = _chave_ip(ctx.ip)
    if chave_ip is None:
        return
    if _contar_falhas(session, chave_ip, ctx.agora - JANELA_FALHAS_IP) < MAXIMO_FALHAS_IP:
        return
    auditar(session, ctx, AcaoAuditoria.LOGIN_FALHA, ResultadoEvento.BLOQUEADO, objeto_tipo="ip")
    raise LoginBloqueadoError(MENSAGEM_BLOQUEIO)


def _recusar_se_bloqueado(
    session: Session, chave: str, usuario: UsuarioTabela | None, ctx: Contexto
) -> None:
    if not _bloqueado(session, chave, ctx.agora):
        return
    auditar(
        session,
        ctx,
        AcaoAuditoria.LOGIN_FALHA,
        ResultadoEvento.BLOQUEADO,
        **_campos_usuario(usuario),
    )
    raise LoginBloqueadoError(MENSAGEM_BLOQUEIO)


def _senha_confere(usuario: UsuarioTabela | None, senha: str) -> bool:
    if usuario is None:
        senhas.verificar_senha(senhas.hash_ficticio(), senha)
        return False
    return senhas.verificar_senha(usuario.senha_hash, senha) and usuario.ativo


def _iniciar_mfa(usuario: UsuarioTabela) -> mfa.ProvisionamentoMfa | None:
    if usuario.mfa_confirmado and usuario.mfa_segredo:
        return None
    usuario.mfa_segredo = mfa.gerar_segredo()
    usuario.mfa_ultimo_passo = None
    return mfa.provisionar(usuario.mfa_segredo, usuario.nome_usuario)


def autenticar_senha(
    session: Session, nome_usuario: str, senha: str, ctx: Contexto
) -> ResultadoSenha:
    """Primeiro passo do login: confere a senha e emite o desafio do TOTP.

    Usuário inexistente, inativo e senha errada produzem o mesmo erro e contam igualmente para
    o bloqueio progressivo por nome (5 falhas: 1 min; 10: 5 min; 15: 15 min). Além disso, 20
    falhas do mesmo IP em 15 minutos recusam qualquer login desse IP (rate limit por IP).

    Args:
        session: Sessão do banco.
        nome_usuario: Nome de usuário.
        senha: Senha informada.
        ctx: Contexto da requisição.

    Returns:
        Token do desafio e, no primeiro acesso, os dados para cadastrar o autenticador.

    Raises:
        LoginBloqueadoError: Se o nome ou o IP estiver bloqueado.
        CredenciaisInvalidasError: Se a senha não conferir.
    """
    _recusar_se_ip_excedido(session, ctx)
    chave = _chave(nome_usuario)
    usuario = _localizar(session, nome_usuario)
    _recusar_se_bloqueado(session, chave, usuario, ctx)
    if usuario is None or not _senha_confere(usuario, senha):
        _registrar_falha(session, chave, usuario, ctx, AcaoAuditoria.LOGIN_FALHA)
        raise CredenciaisInvalidasError(MENSAGEM_CREDENCIAIS)
    session.execute(delete(FalhaLoginTabela).where(FalhaLoginTabela.chave == chave))
    if senhas.precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = senhas.gerar_hash(senha)
    provisionamento = _iniciar_mfa(usuario)
    auditar(session, ctx, AcaoAuditoria.LOGIN_OK, **_campos_usuario(usuario))
    return ResultadoSenha(sessoes.criar_desafio(session, usuario, ctx.agora), provisionamento)


def _usuario_do_desafio(
    session: Session, token: str, ctx: Contexto
) -> tuple[UsuarioTabela, DesafioMfaTabela]:
    desafio = sessoes.carregar_desafio(session, token, ctx.agora)
    if desafio is None:
        raise CredenciaisInvalidasError(MENSAGEM_CODIGO)
    definir_contexto(session, desafio.papel, desafio.gabinete_id)
    usuario = session.get(UsuarioTabela, desafio.usuario_id)
    if usuario is None or not usuario.ativo or not usuario.mfa_segredo:
        raise CredenciaisInvalidasError(MENSAGEM_CODIGO)
    return usuario, desafio


def concluir_mfa(
    session: Session, token_desafio: str, codigo: str, ctx: Contexto, *, confirmando: bool
) -> ResultadoLogin:
    """Segundo passo do login: confere o TOTP e só então cria a sessão.

    Args:
        session: Sessão do banco.
        token_desafio: Token emitido no primeiro passo.
        codigo: Código TOTP.
        ctx: Contexto da requisição.
        confirmando: Verdadeiro no primeiro cadastro do autenticador (`/auth/mfa/confirmar`).

    Returns:
        Token da sessão e se a troca de senha é obrigatória.

    Raises:
        CredenciaisInvalidasError: Desafio inválido ou código errado/reutilizado.
        LoginBloqueadoError: Se o nome estiver bloqueado.
    """
    _recusar_se_ip_excedido(session, ctx)
    usuario, desafio = _usuario_do_desafio(session, token_desafio, ctx)
    chave = _chave(usuario.nome_usuario)
    _recusar_se_bloqueado(session, chave, usuario, ctx)
    if usuario.mfa_confirmado == confirmando:
        raise CredenciaisInvalidasError(MENSAGEM_CODIGO)
    passo = mfa.verificar_codigo(
        str(usuario.mfa_segredo), codigo, usuario.mfa_ultimo_passo, ctx.agora
    )
    if passo is None:
        _registrar_falha(session, chave, usuario, ctx, AcaoAuditoria.MFA_FALHA)
        raise CredenciaisInvalidasError(MENSAGEM_CODIGO)
    usuario.mfa_ultimo_passo = passo
    usuario.mfa_confirmado = True
    desafio.consumido = True
    session.execute(delete(FalhaLoginTabela).where(FalhaLoginTabela.chave == chave))
    token = sessoes.criar_sessao(session, usuario, ctx.ip, ctx.agora)
    auditar(session, ctx, AcaoAuditoria.MFA_OK, **_campos_usuario(usuario))
    return ResultadoLogin(token, usuario.troca_senha_obrigatoria)


def _campos_ator(ator: Ator) -> CamposEvento:
    return {"usuario_id": ator.usuario_id, "gabinete_id": ator.gabinete_id}


def sair(session: Session, ator: Ator, ctx: Contexto) -> None:
    """Revoga a sessão corrente.

    Args:
        session: Sessão do banco.
        ator: Usuário autenticado.
        ctx: Contexto da requisição.
    """
    sessoes.revogar_sessao(session, ator.sessao_id)
    auditar(session, ctx, AcaoAuditoria.LOGOUT, **_campos_ator(ator))


def trocar_senha(
    session: Session, ator: Ator, senha_atual: str, nova_senha: str, ctx: Contexto
) -> None:
    """Troca a senha do próprio usuário e revoga as demais sessões dele.

    Args:
        session: Sessão do banco.
        ator: Usuário autenticado.
        senha_atual: Senha em uso (ou a temporária).
        nova_senha: Nova senha.
        ctx: Contexto da requisição.

    Raises:
        CredenciaisInvalidasError: Se a senha atual não conferir.
        DadosInvalidosError: Se a nova senha violar a política ou repetir a atual.
    """
    usuario = session.get(UsuarioTabela, ator.usuario_id)
    if usuario is None:
        raise NaoAutenticadoError("sessão inválida")
    if not senhas.verificar_senha(usuario.senha_hash, senha_atual):
        falha = ResultadoEvento.FALHA
        auditar(session, ctx, AcaoAuditoria.SENHA_TROCADA, falha, **_campos_ator(ator))
        raise CredenciaisInvalidasError("senha atual inválida")
    if nova_senha == senha_atual:
        raise DadosInvalidosError("a nova senha deve ser diferente da atual")
    try:
        senhas.validar_politica(nova_senha, usuario.nome_usuario)
    except senhas.SenhaFracaError as erro:
        raise DadosInvalidosError(str(erro)) from erro
    usuario.senha_hash = senhas.gerar_hash(nova_senha)
    usuario.troca_senha_obrigatoria = False
    sessoes.revogar_sessoes_do_usuario(session, usuario.id, exceto=ator.sessao_id)
    auditar(session, ctx, AcaoAuditoria.SENHA_TROCADA, **_campos_ator(ator))


def _exigir(ator: Ator, permissao: Permissao, gabinete_alvo: UUID | None) -> None:
    if not pode(ator.papel, permissao, ator.gabinete_id, gabinete_alvo):
        raise PermissaoNegadaError("ação não permitida para o seu papel")


def listar_usuarios(session: Session, ator: Ator, gabinete_id: UUID | None) -> list[UsuarioTabela]:
    """Lista usuários de um gabinete (ou de todos, para o administrador).

    Args:
        session: Sessão do banco com o contexto do ator.
        ator: Usuário autenticado.
        gabinete_id: Gabinete desejado; o desembargador só pode pedir o próprio.

    Returns:
        Usuários ordenados por nome.

    Raises:
        PermissaoNegadaError: Se o papel não gere usuários naquele gabinete.
    """
    alvo = gabinete_id if gabinete_id is not None else ator.gabinete_id
    permissao = Permissao.GERIR_DESEMBARGADOR if alvo is None else Permissao.GERIR_ASSESSOR
    _exigir(ator, permissao, alvo)
    consulta = select(UsuarioTabela).order_by(UsuarioTabela.nome_usuario)
    if alvo is not None:
        consulta = consulta.where(UsuarioTabela.gabinete_id == alvo)
    return list(session.scalars(consulta))


def _validar_novo_usuario(session: Session, nome_usuario: str, papel: PapelUsuario) -> None:
    if papel is PapelUsuario.ADMINISTRADOR:
        raise DadosInvalidosError("o administrador é único e criado só pelo script")
    if not PADRAO_NOME_USUARIO.fullmatch(nome_usuario):
        raise DadosInvalidosError("nome de usuário: 3 a 64 caracteres em a-z, 0-9, '.', '_', '-'")
    existe = session.execute(
        text("SELECT 1 FROM lupa_localizar_usuario(:nome)"), {"nome": nome_usuario}
    ).first()
    if existe is not None:
        raise ConflitoError("nome de usuário já em uso")


def criar_usuario(
    session: Session,
    ator: Ator,
    nome_usuario: str,
    papel: PapelUsuario,
    gabinete_id: UUID | None,
    ctx: Contexto,
) -> UsuarioComSenha:
    """Cria assessor ou desembargador com senha temporária e troca obrigatória.

    Args:
        session: Sessão do banco.
        ator: Quem cria.
        nome_usuario: Nome de usuário.
        papel: Papel do novo usuário.
        gabinete_id: Gabinete; se omitido, o do ator.
        ctx: Contexto da requisição.

    Returns:
        O usuário criado e a senha temporária.

    Raises:
        PermissaoNegadaError: Se o ator não pode criar esse papel nesse gabinete.
        DadosInvalidosError: Papel administrador ou nome inválido.
        ConflitoError: Nome em uso.
        NaoEncontradoError: Gabinete inexistente.
    """
    alvo = gabinete_id if gabinete_id is not None else ator.gabinete_id
    permissao = PERMISSAO_PARA_GERIR.get(papel, Permissao.GERIR_DESEMBARGADOR)
    if not pode(ator.papel, permissao, ator.gabinete_id, alvo):
        auditar(
            session,
            ctx,
            AcaoAuditoria.USUARIO_CRIADO,
            ResultadoEvento.NEGADO,
            **_campos_ator(ator),
        )
        raise PermissaoNegadaError("ação não permitida para o seu papel")
    _validar_novo_usuario(session, nome_usuario, papel)
    if alvo is None or session.get(GabineteTabela, alvo) is None:
        raise NaoEncontradoError("gabinete não encontrado")
    senha = senhas.gerar_senha_temporaria()
    usuario = UsuarioTabela(
        id=uuid4(),
        gabinete_id=alvo,
        nome_usuario=nome_usuario,
        papel=papel.value,
        senha_hash=senhas.gerar_hash(senha),
        mfa_confirmado=False,
        ativo=True,
        troca_senha_obrigatoria=True,
    )
    session.add(usuario)
    session.flush()
    _auditar_sobre(session, ctx, AcaoAuditoria.USUARIO_CRIADO, ator, usuario)
    return UsuarioComSenha(usuario, senha)


def _auditar_sobre(
    session: Session, ctx: Contexto, acao: AcaoAuditoria, ator: Ator, alvo: UsuarioTabela
) -> None:
    auditar(
        session,
        ctx,
        acao,
        usuario_id=ator.usuario_id,
        gabinete_id=alvo.gabinete_id,
        objeto_tipo="usuario",
        objeto_id=str(alvo.id),
    )


def _alvo_gerido(
    session: Session,
    ator: Ator,
    alvo_id: UUID,
    tabela_permissao: dict[PapelUsuario, Permissao],
) -> UsuarioTabela:
    alvo = session.get(UsuarioTabela, alvo_id)
    if alvo is None:
        raise NaoEncontradoError("usuário não encontrado")
    papel_alvo = PapelUsuario(alvo.papel)
    if alvo.id == ator.usuario_id or papel_alvo not in tabela_permissao:
        raise PermissaoNegadaError("ação não permitida sobre este usuário")
    _exigir(ator, tabela_permissao[papel_alvo], alvo.gabinete_id)
    return alvo


def alterar_ativo(
    session: Session, ator: Ator, alvo_id: UUID, ativo: bool, ctx: Contexto
) -> UsuarioTabela:
    """Desativa ou reativa um usuário; desativar revoga as sessões e não apaga nada.

    Args:
        session: Sessão do banco.
        ator: Quem executa.
        alvo_id: Usuário alvo.
        ativo: Novo estado.
        ctx: Contexto da requisição.

    Returns:
        O usuário alterado.
    """
    alvo = _alvo_gerido(session, ator, alvo_id, dict(PERMISSAO_PARA_GERIR))
    alvo.ativo = ativo
    if not ativo:
        sessoes.revogar_sessoes_do_usuario(session, alvo.id)
    acao = AcaoAuditoria.USUARIO_REATIVADO if ativo else AcaoAuditoria.USUARIO_DESATIVADO
    _auditar_sobre(session, ctx, acao, ator, alvo)
    return alvo


def resetar_senha(session: Session, ator: Ator, alvo_id: UUID, ctx: Contexto) -> UsuarioComSenha:
    """Gera senha temporária com troca obrigatória e revoga as sessões do alvo.

    Args:
        session: Sessão do banco.
        ator: Quem executa.
        alvo_id: Usuário alvo.
        ctx: Contexto da requisição.

    Returns:
        O usuário e a senha temporária.
    """
    alvo = _alvo_gerido(session, ator, alvo_id, dict(PERMISSAO_PARA_RESETAR))
    senha = senhas.gerar_senha_temporaria()
    alvo.senha_hash = senhas.gerar_hash(senha)
    alvo.troca_senha_obrigatoria = True
    sessoes.revogar_sessoes_do_usuario(session, alvo.id)
    _auditar_sobre(session, ctx, AcaoAuditoria.SENHA_RESETADA, ator, alvo)
    return UsuarioComSenha(alvo, senha)


def resetar_mfa(session: Session, ator: Ator, alvo_id: UUID, ctx: Contexto) -> UsuarioTabela:
    """Apaga o segredo TOTP do alvo; o próximo login cadastra um novo autenticador.

    Args:
        session: Sessão do banco.
        ator: Quem executa.
        alvo_id: Usuário alvo.
        ctx: Contexto da requisição.

    Returns:
        O usuário alterado.
    """
    alvo = _alvo_gerido(session, ator, alvo_id, dict(PERMISSAO_PARA_RESETAR))
    alvo.mfa_segredo = None
    alvo.mfa_confirmado = False
    alvo.mfa_ultimo_passo = None
    sessoes.revogar_sessoes_do_usuario(session, alvo.id)
    _auditar_sobre(session, ctx, AcaoAuditoria.MFA_RESETADO, ator, alvo)
    return alvo


def criar_gabinete(session: Session, ator: Ator, nome: str, ctx: Contexto) -> GabineteTabela:
    """Cria um gabinete (só administrador).

    Args:
        session: Sessão do banco.
        ator: Quem executa.
        nome: Nome do gabinete.
        ctx: Contexto da requisição.

    Returns:
        O gabinete criado.
    """
    _exigir(ator, Permissao.GERIR_GABINETES, None)
    gabinete = GabineteTabela(id=uuid4(), nome=nome)
    session.add(gabinete)
    session.flush()
    criar_chaves_gabinete(obter_cofre(), gabinete.id)
    auditar(
        session,
        ctx,
        AcaoAuditoria.GABINETE_CRIADO,
        usuario_id=ator.usuario_id,
        gabinete_id=gabinete.id,
        objeto_tipo="gabinete",
        objeto_id=str(gabinete.id),
    )
    return gabinete


def listar_gabinetes(session: Session) -> list[GabineteTabela]:
    """Lista os gabinetes visíveis sob a RLS da sessão (todos, para o administrador).

    Args:
        session: Sessão do banco com o contexto do ator.

    Returns:
        Gabinetes ordenados por nome.
    """
    return list(session.scalars(select(GabineteTabela).order_by(GabineteTabela.nome)))


def criar_administrador(session: Session, nome_usuario: str, senha: str, ctx: Contexto) -> bool:
    """Cria o único administrador, se ainda não existir.

    Args:
        session: Sessão do banco sob `lupa_app`.
        nome_usuario: Nome do administrador.
        senha: Senha inicial (troca obrigatória no primeiro acesso).
        ctx: Contexto (IP None quando rodado por script).

    Returns:
        Verdadeiro se criou; falso se já havia administrador.

    Raises:
        DadosInvalidosError: Nome ou senha fora da política.
    """
    definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
    existente = session.scalar(
        select(UsuarioTabela.id).where(UsuarioTabela.papel == PapelUsuario.ADMINISTRADOR.value)
    )
    if existente is not None:
        return False
    if not PADRAO_NOME_USUARIO.fullmatch(nome_usuario):
        raise DadosInvalidosError("nome de usuário inválido")
    try:
        senhas.validar_politica(senha, nome_usuario)
    except senhas.SenhaFracaError as erro:
        raise DadosInvalidosError(str(erro)) from erro
    usuario = UsuarioTabela(
        id=uuid4(),
        gabinete_id=None,
        nome_usuario=nome_usuario,
        papel=PapelUsuario.ADMINISTRADOR.value,
        senha_hash=senhas.gerar_hash(senha),
        mfa_confirmado=False,
        ativo=True,
        troca_senha_obrigatoria=True,
    )
    session.add(usuario)
    session.flush()
    auditar(
        session,
        ctx,
        AcaoAuditoria.USUARIO_CRIADO,
        usuario_id=usuario.id,
        objeto_tipo="usuario",
        objeto_id=str(usuario.id),
    )
    return True
