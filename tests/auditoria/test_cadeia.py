"""Testes da cadeia de auditoria: append-only, encadeamento, verificação e concorrência."""

import threading
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from lupa.acesso.servico import definir_contexto
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento, hash_confere
from lupa.auditoria.registrador import registrar, verificar_cadeia
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.esquemas import EventoAuditoria
from lupa.dominio.sessao import assumir_papel_aplicacao
from tests.conftest import criar_gabinete_teste, criar_usuario_teste, eventos_do_banco, logar

pytestmark = pytest.mark.integracao


def _registrar_n(fabrica: sessionmaker[Session], gabinete_id: UUID | None, n: int) -> None:
    for _ in range(n):
        with fabrica() as session, session.begin():
            assumir_papel_aplicacao(session)
            definir_contexto(session, PapelUsuario.ASSESSOR.value, gabinete_id)
            registrar(session, NovoEvento(acao=AcaoAuditoria.BUSCA, gabinete_id=gabinete_id))


def test_eventos_encadeiam_hash_e_sequencia(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """Cada evento aponta o hash do anterior e o hash confere com os campos."""
    gabinete = criar_gabinete_teste(engine_teste)
    _registrar_n(fabrica_sessao, gabinete, 3)
    eventos = eventos_do_banco(engine_teste, gabinete_id=gabinete)
    assert [e.sequencia for e in eventos] == [1, 2, 3]
    assert eventos[0].hash_anterior is None
    assert eventos[1].hash_anterior == eventos[0].hash_evento
    assert eventos[2].hash_anterior == eventos[1].hash_evento
    for linha in eventos:
        esquema = EventoAuditoria(**{c: getattr(linha, c) for c in EventoAuditoria.model_fields})
        assert hash_confere(esquema)


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE evento_auditoria SET resultado = 'falha' WHERE gabinete_id = :g",
        "DELETE FROM evento_auditoria WHERE gabinete_id = :g",
        "TRUNCATE evento_auditoria",
    ],
)
def test_update_ou_delete_em_evento_auditoria_falha_no_banco(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine, comando: str
) -> None:
    """O trigger recusa UPDATE, DELETE e TRUNCATE mesmo para o superusuário."""
    gabinete = criar_gabinete_teste(engine_teste)
    _registrar_n(fabrica_sessao, gabinete, 1)
    with engine_teste.connect() as conexao, pytest.raises(DBAPIError, match="append-only"):
        conexao.execute(text(comando), {"g": gabinete})


def test_papel_da_aplicacao_nao_tem_privilegio_de_update(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """Sob `lupa_app`, a recusa vem antes do trigger, por falta de privilégio."""
    gabinete = criar_gabinete_teste(engine_teste)
    _registrar_n(fabrica_sessao, gabinete, 1)
    with fabrica_sessao() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.DESEMBARGADOR.value, gabinete)
        with pytest.raises(DBAPIError, match="permission denied"):
            session.execute(text("DELETE FROM evento_auditoria"))


def _adulterar(engine: Engine, evento_id: UUID) -> None:
    with engine.begin() as conexao:
        conexao.execute(
            text("ALTER TABLE evento_auditoria DISABLE TRIGGER evento_auditoria_append_only")
        )
        conexao.execute(
            text("UPDATE evento_auditoria SET objeto_id = 'adulterado' WHERE id = :id"),
            {"id": evento_id},
        )
        conexao.execute(
            text("ALTER TABLE evento_auditoria ENABLE TRIGGER evento_auditoria_append_only")
        )


def test_alterar_evento_no_meio_da_cadeia_faz_verificar_apontar_aquele_evento(
    app_teste: FastAPI, fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """`GET /auditoria/verificar` aponta exatamente o evento adulterado."""
    desembargador = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, criar_gabinete_teste(engine_teste)
    )
    gabinete = desembargador.gabinete_id
    _registrar_n(fabrica_sessao, gabinete, 5)
    cliente = TestClient(app_teste, base_url="https://testserver")
    logar(cliente, engine_teste, desembargador)
    integra = cliente.get("/auditoria/verificar").json()
    assert integra["integra"] is True and integra["total"] >= 7
    meio = eventos_do_banco(engine_teste, gabinete_id=gabinete)[3]
    _adulterar(engine_teste, meio.id)
    quebrada = cliente.get("/auditoria/verificar").json()
    assert quebrada["integra"] is False
    assert quebrada["primeiro_evento_quebrado"] == str(meio.id)
    assert quebrada["motivo"] == "hash"


def test_verificacao_detecta_elo_e_sequencia_quebrados(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """Hash anterior trocado e salto de sequência também são apontados."""
    gabinete = criar_gabinete_teste(engine_teste)
    _registrar_n(fabrica_sessao, gabinete, 3)
    eventos = eventos_do_banco(engine_teste, gabinete_id=gabinete)
    with engine_teste.begin() as conexao:
        conexao.execute(text("ALTER TABLE evento_auditoria DISABLE TRIGGER USER"))
        conexao.execute(
            text("UPDATE evento_auditoria SET hash_anterior = 'x' WHERE id = :id"),
            {"id": eventos[1].id},
        )
        conexao.execute(
            text("UPDATE evento_auditoria SET sequencia = 9 WHERE id = :id"), {"id": eventos[2].id}
        )
        conexao.execute(text("ALTER TABLE evento_auditoria ENABLE TRIGGER USER"))
    with Session(engine_teste) as session:
        resultado = verificar_cadeia(session, gabinete)
    assert (resultado.primeiro_evento_quebrado, resultado.motivo) == (eventos[1].id, "encadeamento")
    gabinete2 = criar_gabinete_teste(engine_teste)
    _registrar_n(fabrica_sessao, gabinete2, 2)
    segundo = eventos_do_banco(engine_teste, gabinete_id=gabinete2)[1]
    with engine_teste.begin() as conexao:
        conexao.execute(text("ALTER TABLE evento_auditoria DISABLE TRIGGER USER"))
        conexao.execute(
            text("UPDATE evento_auditoria SET sequencia = 7 WHERE id = :id"), {"id": segundo.id}
        )
        conexao.execute(text("ALTER TABLE evento_auditoria ENABLE TRIGGER USER"))
    with Session(engine_teste) as session:
        assert verificar_cadeia(session, gabinete2).motivo == "sequencia"


def test_dois_registros_concorrentes_no_mesmo_gabinete_produzem_cadeia_valida(
    fabrica_sessao: sessionmaker[Session], engine_teste: Engine
) -> None:
    """Quatro threads gravando ao mesmo tempo: sem `hash_anterior` repetido, cadeia íntegra."""
    gabinete = criar_gabinete_teste(engine_teste)
    barreira = threading.Barrier(4)
    erros: list[BaseException] = []

    def _trabalho() -> None:
        try:
            barreira.wait()
            _registrar_n(fabrica_sessao, gabinete, 10)
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    threads = [threading.Thread(target=_trabalho) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert erros == []
    eventos = eventos_do_banco(engine_teste, gabinete_id=gabinete)
    anteriores = [e.hash_anterior for e in eventos]
    assert len(eventos) == 40
    assert len(set(anteriores)) == len(anteriores)
    with Session(engine_teste) as session:
        assert verificar_cadeia(session, gabinete).integra


def test_eventos_sem_gabinete_formam_a_cadeia_global(
    cliente: TestClient, engine_teste: Engine
) -> None:
    """Falha de login de usuário inexistente entra na cadeia global, sem nome digitado."""
    nome = f"ninguem_{uuid4().hex[:8]}"
    cliente.post("/auth/login", json={"nome_usuario": nome, "senha": "senha-qualquer-x"})
    with Session(engine_teste) as session:
        assert verificar_cadeia(session, None).integra
        ultimo = session.execute(
            text(
                "SELECT acao, usuario_id, objeto_id FROM evento_auditoria "
                "WHERE gabinete_id IS NULL ORDER BY sequencia DESC LIMIT 1"
            )
        ).one()
    assert (ultimo.acao, ultimo.usuario_id, ultimo.objeto_id) == ("login_falha", None, None)
