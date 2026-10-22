"""Testes de consulta, exportação, relatório de uso e ausência de conteúdo nos eventos."""

import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from lupa.acesso.servico import definir_contexto
from lupa.auditoria import consulta
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento
from lupa.auditoria.registrador import registrar
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.esquemas import EventoAuditoria
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.dominio.tabelas import EventoAuditoriaTabela
from lupa.logging import CAMPOS_PROIBIDOS
from tests.conftest import (
    SENHA_TESTE,
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    logar,
)

pytestmark = pytest.mark.integracao


def _gravar(fabrica: sessionmaker[Session], *eventos: NovoEvento) -> None:
    with fabrica() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
        for evento in eventos:
            registrar(session, evento)


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


@pytest.fixture
def desembargador(engine_teste: Engine) -> UsuarioTeste:
    """Desembargador de um gabinete novo."""
    return criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )


def test_consulta_filtra_pagina_por_cursor_e_registra_o_ato(
    app_teste: FastAPI,
    fabrica_sessao: sessionmaker[Session],
    engine_teste: Engine,
    desembargador: UsuarioTeste,
) -> None:
    """Filtro por processo e ação; páginas sem repetição; `auditoria_consultada` gravada."""
    processo = uuid4()
    gabinete = desembargador.gabinete_id
    _gravar(
        fabrica_sessao,
        *[
            NovoEvento(acao=AcaoAuditoria.PAGINA_VISTA, gabinete_id=gabinete, processo_id=processo)
            for _ in range(5)
        ],
        NovoEvento(acao=AcaoAuditoria.BUSCA, gabinete_id=gabinete, processo_id=processo),
    )
    cliente = _cliente(app_teste, engine_teste, desembargador)
    parametros: dict[str, str | int] = {
        "processo_id": str(processo),
        "acao": "pagina_vista",
        "limite": 2,
    }
    vistos: list[str] = []
    cursor = None
    while True:
        pagina = cliente.get(
            "/auditoria", params=parametros | ({"cursor": cursor} if cursor else {})
        ).json()
        vistos += [e["id"] for e in pagina["eventos"]]
        cursor = pagina["proximo_cursor"]
        if cursor is None:
            break
    assert len(vistos) == len(set(vistos)) == 5
    assert eventos_do_banco(engine_teste, usuario_id=desembargador.id, acao="auditoria_consultada")
    invalido = cliente.get("/auditoria", params={"cursor": "lixo"})
    assert invalido.status_code == 422


def test_desembargador_so_ve_auditoria_do_proprio_gabinete(
    app_teste: FastAPI,
    fabrica_sessao: sessionmaker[Session],
    engine_teste: Engine,
    desembargador: UsuarioTeste,
) -> None:
    """Pedir outro gabinete dá 403; eventos de outro gabinete não aparecem."""
    outro = criar_gabinete_teste(engine_teste)
    processo = uuid4()
    _gravar(
        fabrica_sessao,
        NovoEvento(acao=AcaoAuditoria.BUSCA, gabinete_id=outro, processo_id=processo),
    )
    cliente = _cliente(app_teste, engine_teste, desembargador)
    assert cliente.get("/auditoria", params={"gabinete_id": str(outro)}).status_code == 403
    assert cliente.get("/auditoria", params={"processo_id": str(processo)}).json()["eventos"] == []


def test_assessor_nao_ve_auditoria(app_teste: FastAPI, engine_teste: Engine) -> None:
    """Assessor não tem permissão de auditoria."""
    assessor = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    cliente = _cliente(app_teste, engine_teste, assessor)
    for rota in ("/auditoria", "/auditoria/verificar", "/auditoria/exportar"):
        assert cliente.get(rota).status_code == 403, rota


@pytest.mark.parametrize("formato", ["csv", "json"])
def test_exportacao_em_csv_e_json_registra_o_proprio_ato(
    app_teste: FastAPI,
    fabrica_sessao: sessionmaker[Session],
    engine_teste: Engine,
    desembargador: UsuarioTeste,
    formato: str,
) -> None:
    """Exporta os eventos filtrados e grava `auditoria_exportada`."""
    processo = uuid4()
    _gravar(
        fabrica_sessao,
        NovoEvento(
            acao=AcaoAuditoria.BUSCA, gabinete_id=desembargador.gabinete_id, processo_id=processo
        ),
    )
    cliente = _cliente(app_teste, engine_teste, desembargador)
    resposta = cliente.get(
        "/auditoria/exportar", params={"formato": formato, "processo_id": str(processo)}
    )
    assert resposta.status_code == 200
    assert f"auditoria.{formato}" in resposta.headers["content-disposition"]
    if formato == "csv":
        linhas = list(csv.DictReader(io.StringIO(resposta.text)))
    else:
        linhas = resposta.json()
    assert [linha["acao"] for linha in linhas] == ["busca"]
    exportacoes = eventos_do_banco(
        engine_teste, usuario_id=desembargador.id, acao="auditoria_exportada"
    )
    assert exportacoes[-1].processo_id == processo


def test_relatorio_de_uso_por_processo_e_por_usuario(
    app_teste: FastAPI,
    fabrica_sessao: sessionmaker[Session],
    engine_teste: Engine,
    desembargador: UsuarioTeste,
) -> None:
    """Contagem por ação, primeiro/último acesso e versões das chamadas ao modelo."""
    processo = uuid4()
    gabinete = desembargador.gabinete_id
    chamada = AcaoAuditoria.CHAMADA_MODELO
    _gravar(
        fabrica_sessao,
        NovoEvento(acao=AcaoAuditoria.PROCESSO_ABERTO, gabinete_id=gabinete, processo_id=processo),
        NovoEvento(
            acao=chamada,
            gabinete_id=gabinete,
            processo_id=processo,
            versao_modelo="modelo-x",
            versao_prompt="p1",
        ),
        NovoEvento(
            acao=chamada,
            gabinete_id=gabinete,
            processo_id=processo,
            versao_modelo="modelo-x",
            versao_prompt="p1",
        ),
    )
    cliente = _cliente(app_teste, engine_teste, desembargador)
    relatorio = cliente.get("/auditoria/relatorio-uso", params={"processo": str(processo)}).json()
    assert relatorio["contagem_por_acao"] == {"processo_aberto": 1, "chamada_modelo": 2}
    assert relatorio["chamadas_modelo"] == [
        {"versao_modelo": "modelo-x", "versao_prompt": "p1", "total": 2}
    ]
    assert relatorio["primeiro_acesso"] <= relatorio["ultimo_acesso"]
    por_usuario = cliente.get(
        "/auditoria/relatorio-uso", params={"usuario": str(desembargador.id)}
    ).json()
    assert por_usuario["contagem_por_acao"]["mfa_ok"] == 1
    assert cliente.get("/auditoria/relatorio-uso").status_code == 422


def test_admin_consulta_qualquer_gabinete_e_verifica_cadeia_global(
    app_teste: FastAPI, engine_teste: Engine
) -> None:
    """Administrador sem filtro vê todos os gabinetes e verifica a cadeia global."""
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    cliente = _cliente(app_teste, engine_teste, admin)
    gabinetes = {
        e["gabinete_id"]
        for e in cliente.get("/auditoria", params={"limite": 500}).json()["eventos"]
    }
    assert None in gabinetes
    verificacao = cliente.get("/auditoria/verificar").json()
    assert verificacao["gabinete_id"] is None and verificacao["integra"] is True


def test_filtros_por_intervalo_usuario_e_ip(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """Intervalo é [inicio, fim); IP e usuário filtram por igualdade."""
    gabinete = criar_gabinete_teste(engine_teste)
    usuario = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, gabinete)
    antes = datetime.now(UTC)
    _gravar(
        fabrica_sessao,
        NovoEvento(
            acao=AcaoAuditoria.BUSCA, gabinete_id=gabinete, usuario_id=usuario.id, ip="10.0.0.1"
        ),
        NovoEvento(acao=AcaoAuditoria.BUSCA, gabinete_id=gabinete, ip="10.0.0.2"),
    )
    with Session(engine_teste) as session:
        filtro = consulta.FiltroAuditoria(
            gabinete_id=gabinete, inicio=antes, fim=antes + timedelta(hours=1)
        )
        assert len(consulta.consultar(session, filtro).eventos) == 2
        so_ip = consulta.FiltroAuditoria(gabinete_id=gabinete, ip="10.0.0.1")
        assert [e.usuario_id for e in consulta.consultar(session, so_ip).eventos] == [usuario.id]
        futuro = consulta.FiltroAuditoria(gabinete_id=gabinete, inicio=antes + timedelta(hours=1))
        assert consulta.consultar(session, futuro).eventos == []


def _valores_texto(evento: EventoAuditoria) -> list[str]:
    return [str(v) for v in evento.model_dump().values() if v is not None]


def test_nenhum_evento_contem_campo_proibido_nem_segredo(
    app_teste: FastAPI, engine_teste: Engine, desembargador: UsuarioTeste
) -> None:
    """Varre todos os eventos gravados depois de fluxos reais: nada de senha, token ou texto."""
    cliente = _cliente(app_teste, engine_teste, desembargador)
    criado = cliente.post(
        "/usuarios", json={"nome_usuario": f"x_{uuid4().hex[:8]}", "papel": "assessor"}
    )
    temporaria = criado.json()["senha_temporaria"]
    cliente.post(
        "/auth/login", json={"nome_usuario": "senha-digitada-no-usuario", "senha": "y" * 12}
    )
    cliente.post(
        "/auth/trocar-senha", json={"senha_atual": SENHA_TESTE, "nova_senha": "z" * 6 + "abcdef"}
    )
    cookie = cliente.cookies.get("lupa_sessao") or ""
    segredos = {SENHA_TESTE, temporaria, "senha-digitada-no-usuario", cookie}
    with Session(engine_teste) as session:
        linhas = session.scalars(select(EventoAuditoriaTabela)).all()
        eventos = [
            EventoAuditoria(**{c: getattr(linha, c) for c in EventoAuditoria.model_fields})
            for linha in linhas
        ]
    assert eventos
    for evento in eventos:
        assert not CAMPOS_PROIBIDOS & set(evento.model_dump())
        assert (evento.objeto_tipo or "") not in CAMPOS_PROIBIDOS
        assert not segredos & set(_valores_texto(evento))
    assert not CAMPOS_PROIBIDOS & set(NovoEvento.model_fields)
    with pytest.raises(ValueError, match="extra"):
        NovoEvento.model_validate({"acao": "busca", "texto": "conteúdo dos autos"})


def test_cursor_codifica_e_decodifica() -> None:
    """Ida e volta do cursor opaco."""
    evento = EventoAuditoria(
        usuario_id=None, gabinete_id=None, acao="busca", resultado="ok", hash_evento="h"
    )
    instante, ident = consulta.decodificar_cursor(consulta.codificar_cursor(evento))
    assert (instante, ident) == (evento.ocorrido_em, evento.id)
    assert isinstance(ident, UUID)
