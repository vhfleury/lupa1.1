"""Teste de carga: 1 milhão de eventos sintéticos e consulta filtrada em menos de 200 ms."""

import random
import statistics
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from lupa.acesso.servico import definir_contexto
from lupa.auditoria import consulta
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.logging import get_logger
from tests.conftest import migrar

pytestmark = [pytest.mark.integracao, pytest.mark.carga]

TOTAL_EVENTOS = 1_000_000
TOTAL_GABINETES = 40
USUARIOS_POR_GABINETE = 25
LIMITE_MS = 200
INICIO = datetime(2025, 1, 1, tzinfo=UTC)
ACOES = ("pagina_vista", "processo_aberto", "busca", "pergunta_chat", "login_ok", "mfa_ok")
COLUNAS = (
    "id, ocorrido_em, usuario_id, gabinete_id, processo_id, acao, ip, localizacao, resultado, "
    "hash_anterior, hash_evento, sequencia"
)


@pytest.fixture(scope="module")
def banco_carga(engine_teste: Engine) -> Iterator[Engine]:
    """Banco próprio para a carga, para não pesar nos demais testes."""
    nome = f"{engine_teste.url.database}_carga"
    with engine_teste.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
        conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    engine = create_engine(engine_teste.url.set(database=nome))
    migrar(engine, "head")
    yield engine
    engine.dispose()
    with engine_teste.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))


def _semear_donos(engine: Engine) -> list[tuple[UUID, UUID]]:
    pares = [
        (uuid4(), gabinete)
        for gabinete in (uuid4() for _ in range(TOTAL_GABINETES))
        for _ in range(USUARIOS_POR_GABINETE)
    ]
    with engine.begin() as conexao:
        for gabinete in {g for _, g in pares}:
            conexao.execute(
                text("INSERT INTO gabinete (id, nome) VALUES (:g, 'carga')"), {"g": gabinete}
            )
        conexao.execute(
            text(
                "INSERT INTO usuario (id, gabinete_id, nome_usuario, papel, senha_hash, "
                "mfa_confirmado, ativo, troca_senha_obrigatoria) "
                "VALUES (:u, :g, :n, 'assessor', 'x', true, true, false)"
            ),
            [{"u": u, "g": g, "n": f"carga_{u.hex[:12]}"} for u, g in pares],
        )
    return pares


def _linhas(pares: list[tuple[UUID, UUID]]) -> Iterator[tuple[object, ...]]:
    sorteio = random.Random(20261020)  # noqa: S311
    sequencias: dict[UUID, int] = {}
    passo = timedelta(days=365) / TOTAL_EVENTOS
    for indice in range(TOTAL_EVENTOS):
        usuario, gabinete = pares[sorteio.randrange(len(pares))]
        sequencias[gabinete] = sequencias.get(gabinete, 0) + 1
        yield (
            uuid4(),
            INICIO + passo * indice,
            usuario,
            gabinete,
            uuid4(),
            ACOES[indice % len(ACOES)],
            f"10.0.{indice % 256}.{indice % 200}",
            "rede interna",
            "ok",
            None,
            f"{indice:064x}",
            sequencias[gabinete],
        )


def _copiar(engine: Engine, pares: list[tuple[UUID, UUID]]) -> float:
    inicio = time.perf_counter()
    with engine.begin() as conexao:
        cursor = conexao.connection.driver_connection.cursor()  # type: ignore[union-attr]
        with cursor.copy(f"COPY evento_auditoria ({COLUNAS}) FROM STDIN") as copia:
            for linha in _linhas(pares):
                copia.write_row(linha)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text("ANALYZE evento_auditoria"))
    return time.perf_counter() - inicio


def _medir_consulta(engine: Engine, usuario: UUID, gabinete: UUID) -> list[float]:
    filtro = consulta.FiltroAuditoria(
        usuario_id=usuario, inicio=INICIO + timedelta(days=90), fim=INICIO + timedelta(days=180)
    )
    tempos = []
    with Session(engine) as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.DESEMBARGADOR.value, gabinete)
        for _ in range(10):
            inicio = time.perf_counter()
            pagina = consulta.consultar(session, filtro, limite=50)
            tempos.append((time.perf_counter() - inicio) * 1000)
        assert pagina.eventos and all(e.usuario_id == usuario for e in pagina.eventos)
    return tempos


def test_um_milhao_de_eventos_consulta_por_usuario_e_intervalo_abaixo_de_200ms(
    banco_carga: Engine,
) -> None:
    """Consulta por usuário e intervalo, sob RLS de desembargador, com mediana < 200 ms."""
    pares = _semear_donos(banco_carga)
    segundos_carga = _copiar(banco_carga, pares)
    with banco_carga.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM evento_auditoria")).scalar() == (
            TOTAL_EVENTOS
        )
    usuario, gabinete = pares[7]
    tempos = _medir_consulta(banco_carga, usuario, gabinete)
    mediana = statistics.median(tempos)
    get_logger(__name__).info(
        "teste_carga",
        eventos=TOTAL_EVENTOS,
        segundos_carga=round(segundos_carga, 1),
        mediana_ms=round(mediana, 1),
        maximo_ms=round(max(tempos), 1),
    )
    assert mediana < LIMITE_MS
