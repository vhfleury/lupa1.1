"""Testes do login em dois passos, rate limit, sessões e troca de senha (API + PostgreSQL)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import pyotp
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lupa.acesso import servico, sessoes
from lupa.acesso.autorizacao import contexto_requisicao, relogio
from lupa.acesso.servico import Contexto
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import SessaoTabela, UsuarioTabela
from tests.conftest import (
    SENHA_TESTE,
    UsuarioTeste,
    codigo_totp,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
    relogio_fixo,
)

pytestmark = pytest.mark.integracao

NOVA_SENHA = "outra-frase-bem-comprida-2026"  # noqa: S105


def _login(cliente: TestClient, nome: str, senha: str = SENHA_TESTE) -> dict[str, str]:
    resposta = cliente.post("/auth/login", json={"nome_usuario": nome, "senha": senha})
    return {"status": str(resposta.status_code), **resposta.json()}


def _sessoes_ativas(engine: Engine, usuario_id: UUID) -> int:
    with Session(engine) as session:
        return len(
            session.scalars(
                select(SessaoTabela).where(
                    SessaoTabela.usuario_id == usuario_id, SessaoTabela.revogada.is_(False)
                )
            ).all()
        )


def _codigo_errado(codigo: str) -> str:
    return f"{(int(codigo) + 1) % 1_000_000:06d}"


@pytest.fixture
def assessor(engine_teste: Engine) -> UsuarioTeste:
    """Assessor com MFA configurado."""
    return criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )


def test_login_com_senha_certa_e_totp_errado_nao_cria_sessao(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Senha certa só emite desafio; TOTP errado não cria sessão nem cookie."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    assert usuario.segredo is not None
    passo1 = _login(cliente, usuario.nome)
    assert passo1["etapa"] == "mfa"
    assert _sessoes_ativas(engine_teste, usuario.id) == 0
    errado = _codigo_errado(codigo_totp(engine_teste, usuario.id, usuario.segredo))
    resposta = cliente.post("/auth/mfa", json={"desafio": passo1["desafio"], "codigo": errado})
    assert resposta.status_code == 401
    assert sessoes.NOME_COOKIE not in cliente.cookies
    assert _sessoes_ativas(engine_teste, usuario.id) == 0
    assert eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="mfa_falha")


def test_codigo_totp_reutilizado_dentro_da_janela_e_rejeitado(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """O mesmo código aceito uma vez é recusado num segundo login."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    assert usuario.segredo is not None
    codigo = codigo_totp(engine_teste, usuario.id, usuario.segredo)
    with relogio_fixo(cliente.app):
        primeiro = cliente.post(
            "/auth/mfa",
            json={"desafio": _login(cliente, usuario.nome)["desafio"], "codigo": codigo},
        )
        assert primeiro.status_code == 200
        segundo = cliente.post(
            "/auth/mfa",
            json={"desafio": _login(cliente, usuario.nome)["desafio"], "codigo": codigo},
        )
    assert segundo.status_code == 401
    assert _sessoes_ativas(engine_teste, usuario.id) == 1


def test_cinco_falhas_bloqueiam_e_geram_evento_login_bloqueado(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Na quinta falha o nome é bloqueado; nem a senha certa entra depois."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    for _ in range(5):
        assert _login(cliente, usuario.nome, "senha-errada-qualquer")["status"] == "401"
    bloqueado = _login(cliente, usuario.nome)
    assert bloqueado["status"] == "429"
    assert len(eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="login_bloqueado")) == 1
    falhas = eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="login_falha")
    assert [e.resultado for e in falhas] == ["falha"] * 5 + ["bloqueado"]


def test_primeiro_bloqueio_expira_depois_de_um_minuto(
    app_teste: FastAPI, cliente: TestClient, engine_teste: Engine
) -> None:
    """O primeiro bloqueio dura 1 minuto; passado esse prazo o login volta a funcionar."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    for _ in range(5):
        _login(cliente, usuario.nome, "senha-errada-qualquer")
    app_teste.dependency_overrides[relogio] = lambda: datetime.now(UTC) + timedelta(seconds=50)
    assert _login(cliente, usuario.nome)["status"] == "429"
    app_teste.dependency_overrides[relogio] = lambda: datetime.now(UTC) + timedelta(minutes=2)
    assert _login(cliente, usuario.nome)["status"] == "200"


def _no_instante(app: FastAPI, instante: datetime) -> None:
    app.dependency_overrides[relogio] = lambda: instante


def test_bloqueio_por_nome_e_progressivo_1_5_15_minutos(
    app_teste: FastAPI, cliente: TestClient, engine_teste: Engine
) -> None:
    """5 falhas: 1 min; 10: 5 min; 15: 15 min. Cada bloqueio gera `login_bloqueado`."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    inicio = datetime.now(UTC)

    def falhar_cinco(minuto: int) -> None:
        _no_instante(app_teste, inicio + timedelta(minutes=minuto))
        for _ in range(5):
            assert _login(cliente, usuario.nome, "senha-errada-qualquer")["status"] == "401"

    falhar_cinco(0)
    falhar_cinco(2)
    _no_instante(app_teste, inicio + timedelta(minutes=6))
    assert _login(cliente, usuario.nome)["status"] == "429"
    falhar_cinco(8)
    _no_instante(app_teste, inicio + timedelta(minutes=22))
    assert _login(cliente, usuario.nome)["status"] == "429"
    _no_instante(app_teste, inicio + timedelta(minutes=24))
    assert _login(cliente, usuario.nome)["status"] == "200"
    bloqueios = eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="login_bloqueado")
    assert len(bloqueios) == 3


def test_duracao_do_bloqueio_progressivo() -> None:
    """Tabela da progressão: só múltiplos de 5 bloqueiam; o teto é 15 minutos."""
    assert [servico.duracao_bloqueio(n) for n in (0, 4, 6)] == [None, None, None]
    assert servico.duracao_bloqueio(5) == timedelta(minutes=1)
    assert servico.duracao_bloqueio(10) == timedelta(minutes=5)
    assert servico.duracao_bloqueio(15) == timedelta(minutes=15)
    assert servico.duracao_bloqueio(40) == timedelta(minutes=15)


def _contexto_com_ip(ip: str) -> Callable[..., Contexto]:
    def _ctx(agora: Annotated[datetime, Depends(relogio)]) -> Contexto:
        return Contexto(ip=ip, localizacao="desconhecida", agora=agora)

    return _ctx


def test_rate_limit_por_ip_recusa_depois_de_20_falhas_e_registra(
    app_teste: FastAPI, cliente: TestClient, engine_teste: Engine
) -> None:
    """20 falhas do mesmo IP em 15 min recusam até login certo desse IP; outro IP entra."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    ip = f"203.0.113.{uuid4().int % 250 + 1}"
    app_teste.dependency_overrides[contexto_requisicao] = _contexto_com_ip(ip)
    for _ in range(20):
        nome = f"nao_existe_{uuid4().hex[:8]}"
        assert _login(cliente, nome, "senha-errada-qualquer")["status"] == "401"
    recusado = _login(cliente, usuario.nome)
    assert recusado["status"] == "429"
    assert recusado["detail"] == servico.MENSAGEM_BLOQUEIO
    bloqueios_ip = eventos_do_banco(engine_teste, ip=ip, acao="login_bloqueado", objeto_tipo="ip")
    recusas_ip = eventos_do_banco(
        engine_teste, ip=ip, acao="login_falha", resultado="bloqueado", objeto_tipo="ip"
    )
    assert (len(bloqueios_ip), len(recusas_ip)) >= (1, 1)
    app_teste.dependency_overrides[contexto_requisicao] = _contexto_com_ip("198.51.100.77")
    assert _login(cliente, usuario.nome)["status"] == "200"
    app_teste.dependency_overrides[contexto_requisicao] = _contexto_com_ip(ip)
    app_teste.dependency_overrides[relogio] = lambda: datetime.now(UTC) + timedelta(minutes=16)
    assert _login(cliente, usuario.nome)["status"] == "200"


def test_ip_invalido_nao_entra_no_rate_limit_por_ip() -> None:
    """Sem IP utilizável não há chave por IP (o limite por nome continua valendo)."""
    assert servico._chave_ip(None) is None
    assert servico._chave_ip("testclient") is None
    assert servico._chave_ip("::ffff:10.0.0.1") is not None


def test_usuario_inexistente_e_senha_errada_tem_resposta_identica(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Mesmo status e mesmo corpo; usuário desconhecido também é bloqueado."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    errada = cliente.post(
        "/auth/login", json={"nome_usuario": usuario.nome, "senha": "senha-errada-qualquer"}
    )
    inexistente = cliente.post(
        "/auth/login", json={"nome_usuario": "nao_existe_ninguem", "senha": "senha-qualquer-x"}
    )
    assert (errada.status_code, errada.json()) == (inexistente.status_code, inexistente.json())
    for _ in range(5):
        _login(cliente, "fantasma_sem_conta", "senha-qualquer-x")
    assert _login(cliente, "fantasma_sem_conta", "senha-qualquer-x")["status"] == "429"


def test_usuario_desativado_nao_entra(cliente: TestClient, engine_teste: Engine) -> None:
    """Usuário inativo recebe a mesma resposta de senha errada."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    with Session(engine_teste) as session, session.begin():
        registro = session.get(UsuarioTabela, usuario.id)
        assert registro is not None
        registro.ativo = False
    assert _login(cliente, usuario.nome)["status"] == "401"


def test_primeiro_acesso_cadastra_e_confirma_o_autenticador(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Sem MFA, o login devolve segredo e URI; a confirmação com código válido cria a sessão."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste), mfa=False
    )
    passo1 = _login(cliente, usuario.nome)
    assert passo1["etapa"] == "configurar_mfa"
    assert passo1["uri_qr"].startswith("otpauth://totp/")
    with relogio_fixo(cliente.app) as instante:
        codigo = pyotp.TOTP(passo1["segredo"]).at(instante)
        pelo_caminho_errado = cliente.post(
            "/auth/mfa", json={"desafio": passo1["desafio"], "codigo": codigo}
        )
        assert pelo_caminho_errado.status_code == 401
        confirmado = cliente.post(
            "/auth/mfa/confirmar", json={"desafio": passo1["desafio"], "codigo": codigo}
        )
    assert confirmado.status_code == 200
    with Session(engine_teste) as session:
        registro = session.get(UsuarioTabela, usuario.id)
        assert registro is not None and registro.mfa_confirmado
    reuso = cliente.post(
        "/auth/mfa/confirmar", json={"desafio": passo1["desafio"], "codigo": codigo}
    )
    assert reuso.status_code == 401


def test_desafio_invalido_e_recusado(cliente: TestClient) -> None:
    """Desafio desconhecido não cria sessão."""
    resposta = cliente.post("/auth/mfa", json={"desafio": "inventado", "codigo": "123456"})
    assert resposta.status_code == 401


def test_cookie_de_sessao_tem_flags_de_seguranca(
    cliente: TestClient, engine_teste: Engine, assessor: UsuarioTeste
) -> None:
    """HttpOnly, Secure e SameSite=Strict."""
    assert assessor.segredo is not None
    desafio = _login(cliente, assessor.nome)["desafio"]
    codigo = codigo_totp(engine_teste, assessor.id, assessor.segredo)
    with relogio_fixo(cliente.app):
        resposta = cliente.post("/auth/mfa", json={"desafio": desafio, "codigo": codigo})
    cabecalho = resposta.headers["set-cookie"].lower()
    for flag in ("httponly", "secure", "samesite=strict", "max-age=28800"):
        assert flag in cabecalho


def test_usuario_com_troca_senha_obrigatoria_so_acessa_rota_de_troca(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Com troca pendente, tudo devolve 403, exceto `/auth/trocar-senha`."""
    gabinete = criar_gabinete_teste(engine_teste)
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, gabinete, troca_senha=True
    )
    logar(cliente, engine_teste, usuario)
    for metodo, rota in (
        ("get", "/usuarios"),
        ("get", "/auditoria"),
        ("post", "/auth/logout"),
        ("get", f"/processos/{gabinete}"),
    ):
        resposta = cliente.request(metodo, rota)
        assert resposta.status_code == 403, rota
        assert resposta.json()["detail"] == "troca de senha obrigatória"
    troca = cliente.post(
        "/auth/trocar-senha", json={"senha_atual": SENHA_TESTE, "nova_senha": NOVA_SENHA}
    )
    assert troca.status_code == 204
    assert cliente.get("/usuarios").status_code == 200


def test_troca_de_senha_revoga_as_demais_sessoes(app_teste: FastAPI, engine_teste: Engine) -> None:
    """A sessão que trocou continua; a outra é revogada."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )
    primeiro = TestClient(app_teste, base_url="https://testserver")
    segundo = TestClient(app_teste, base_url="https://testserver")
    logar(primeiro, engine_teste, usuario)
    logar(segundo, engine_teste, usuario)
    assert segundo.get("/usuarios").status_code == 200
    troca = primeiro.post(
        "/auth/trocar-senha", json={"senha_atual": SENHA_TESTE, "nova_senha": NOVA_SENHA}
    )
    assert troca.status_code == 204
    assert primeiro.get("/usuarios").status_code == 200
    assert segundo.get("/usuarios").status_code == 401
    assert _sessoes_ativas(engine_teste, usuario.id) == 1
    assert eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="senha_trocada")


def test_troca_de_senha_recusa_senha_atual_errada_e_senha_fraca(
    cliente: TestClient, engine_teste: Engine, assessor: UsuarioTeste
) -> None:
    """Senha atual errada dá 401; nova fraca ou igual dá 422."""
    logar(cliente, engine_teste, assessor)
    rota = "/auth/trocar-senha"
    errada = cliente.post(rota, json={"senha_atual": "nao-e-esta-senha", "nova_senha": NOVA_SENHA})
    assert errada.status_code == 401
    fraca = cliente.post(rota, json={"senha_atual": SENHA_TESTE, "nova_senha": "curta"})
    assert fraca.status_code == 422
    igual = cliente.post(rota, json={"senha_atual": SENHA_TESTE, "nova_senha": SENHA_TESTE})
    assert igual.status_code == 422


def test_logout_revoga_a_sessao(cliente: TestClient, engine_teste: Engine) -> None:
    """Depois do logout o cookie antigo não vale mais."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )
    logar(cliente, engine_teste, usuario)
    token = cliente.cookies[sessoes.NOME_COOKIE]
    assert cliente.post("/auth/logout").status_code == 204
    cliente.cookies.set(sessoes.NOME_COOKIE, token)
    assert cliente.get("/usuarios").status_code == 401
    assert eventos_do_banco(engine_teste, usuario_id=usuario.id, acao="logout")


@pytest.mark.parametrize("minutos", [31, 60 * 8 + 1])
def test_sessao_expira_por_inatividade_e_por_prazo_absoluto(
    app_teste: FastAPI, cliente: TestClient, engine_teste: Engine, minutos: int
) -> None:
    """30 minutos sem uso, ou 8 horas desde a criação, encerram a sessão."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )
    logar(cliente, engine_teste, usuario)
    app_teste.dependency_overrides[relogio] = lambda: datetime.now(UTC) + timedelta(minutes=minutos)
    assert cliente.get("/usuarios").status_code == 401


def test_sem_cookie_nao_autentica(cliente: TestClient) -> None:
    """Rota protegida sem cookie responde 401."""
    assert cliente.get("/usuarios").status_code == 401
