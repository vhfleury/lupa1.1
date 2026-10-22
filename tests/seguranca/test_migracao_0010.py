"""Migração 0010 com dados existentes: cifra em lote, idempotente e reversível (Etapa 7.5)."""

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from lupa.dominio.tabelas import MensagemTabela, PaginaTabela
from lupa.seguranca.chaves import carregador_sql
from lupa.seguranca.contexto import contexto_cifra
from tests.conftest import migrar

pytestmark = pytest.mark.integracao

TEXTO = "Termo sintético Vortilampesco na página antiga."


@pytest.fixture
def engine_0009() -> Iterator[Engine]:
    """Banco próprio migrado só até a 0009 (o da sessão já está na cabeça)."""
    url = os.environ.get("LUPA_DATABASE_URL")
    if url is None:
        pytest.skip("LUPA_DATABASE_URL não definida")
    nome = f"lupa_teste_0010_{os.getpid()}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conexao:
            conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
            conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    except Exception:
        admin.dispose()
        pytest.skip("PostgreSQL inacessível")
    engine = create_engine(make_url(url).set(database=nome))
    migrar(engine, "0009")
    yield engine
    engine.dispose()
    with admin.connect() as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
    admin.dispose()


def _semear_em_claro(engine: Engine) -> dict[str, Any]:
    ids = {nome: uuid4() for nome in ("g", "u", "p", "a", "pg", "e", "c", "m", "r")}
    comandos = [
        "INSERT INTO gabinete (id, nome) VALUES (:g, 'Gabinete migração')",
        "INSERT INTO usuario (id, gabinete_id, nome_usuario, papel, senha_hash, mfa_confirmado,"
        " ativo, troca_senha_obrigatoria) VALUES (:u, :g, 'mig_' || left(:u_txt, 8), 'assessor',"
        " 'x', false, true, false)",
        "INSERT INTO processo (id, gabinete_id, numero_cnj, classe, materia, sigiloso, status,"
        " criado_por) VALUES (:p, :g, '0000001-00.2025.8.09.0001', 'Apelação', 'criminal', false,"
        " 'pronto', :u)",
        "INSERT INTO arquivo (id, gabinete_id, processo_id, sha256, tamanho_bytes, nome_original,"
        " mime, chave_storage, enviado_por) VALUES (:a, :g, :p, 'h', 10, 'a.pdf',"
        " 'application/pdf', 'k', :u)",
        "INSERT INTO pagina (id, gabinete_id, arquivo_id, numero, tipo, texto, hash_texto,"
        " texto_normalizado, trechos_ocultos) VALUES (:pg, :g, :a, 1, 'nativa', :t, 'h', :t,"
        " CAST(:oc AS jsonb))",
        "INSERT INTO evidencia (id, gabinete_id, pagina_id, trecho, hash_trecho, inicio, fim)"
        " VALUES (:e, :g, :pg, 'Vortilampesco', 'h', 0, 5)",
        "INSERT INTO conversa (id, gabinete_id, processo_id, usuario_id) VALUES (:c, :g, :p, :u)",
        "INSERT INTO mensagem (id, gabinete_id, conversa_id, papel, status, texto)"
        " VALUES (:m, :g, :c, 'usuario', 'pergunta', 'Pergunta Vortilampesco?')",
        "INSERT INTO reu (id, gabinete_id, processo_id, pseudonimo) VALUES (:r, :g, :p, 'REU-01')",
        "INSERT INTO reu_identidade (reu_id, gabinete_id, nome, documento)"
        " VALUES (:r, :g, 'Nome Vortilampesco', NULL)",
    ]
    parametros = {**ids, "u_txt": str(ids["u"]), "t": TEXTO, "oc": '[{"texto": "Vortilampesco"}]'}
    with engine.begin() as conexao:
        for comando in comandos:
            conexao.execute(text(comando), parametros)
    return parametros


def _dump(engine: Engine) -> str:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT p.texto || p.texto_normalizado || p.trechos_ocultos::text || e.trecho"
                " || m.texto || i.nome FROM pagina p, evidencia e, mensagem m, reu_identidade i"
            )
        ).scalars()
        return "".join(linhas)


def test_migracao_cifra_dados_existentes_idempotente_e_reversivel(engine_0009: Engine) -> None:
    """Upgrade cifra tudo; downgrade devolve o claro; novo upgrade cifra de novo."""
    ids = _semear_em_claro(engine_0009)
    assert "Vortilampesco" in _dump(engine_0009)
    migrar(engine_0009, "head")
    cifrado = _dump(engine_0009)
    assert "Vortilampesco" not in cifrado and "lupa1:" in cifrado
    fabrica = sessionmaker(engine_0009, expire_on_commit=False)
    with contexto_cifra(carregador_sql(fabrica)), Session(engine_0009) as session:
        pagina = session.get_one(PaginaTabela, ids["pg"])
        assert pagina.texto == TEXTO and pagina.trechos_ocultos == [{"texto": "Vortilampesco"}]
        assert session.scalars(select(MensagemTabela.texto)).one() == "Pergunta Vortilampesco?"
    migrar(engine_0009, "0009", descer=True)
    assert "Vortilampesco" in _dump(engine_0009)
    migrar(engine_0009, "head")
    assert "Vortilampesco" not in _dump(engine_0009)
