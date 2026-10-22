"""Testes dos pontos herdados da Etapa 1: usuário sem superusuário, login sob RLS, admin, grants."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from lupa.acesso import instalacao
from lupa.acesso.servico import definir_contexto
from lupa.config import Settings
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.dominio.tabelas import UsuarioTabela
from tests.conftest import criar_gabinete_teste, criar_usuario_teste, migrar

pytestmark = pytest.mark.integracao

SENHA_PAPEL = "senha-do-papel-de-teste"  # noqa: S105
RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def papel_conexao(engine_teste: Engine) -> Iterator[Engine]:
    """Cria papel de login sem superusuário (nome único) e devolve um engine com ele."""
    nome = f"lupa_api_teste_{os.getpid()}"
    with engine_teste.begin() as conexao:
        instalacao.garantir_usuario_conexao(conexao, nome, "provisoria-123456")
        instalacao.garantir_usuario_conexao(conexao, nome, SENHA_PAPEL)
    url = make_url(str(engine_teste.url.render_as_string(hide_password=False)))
    engine = create_engine(url.set(username=nome, password=SENHA_PAPEL))
    yield engine
    engine.dispose()
    with engine_teste.begin() as conexao:
        conexao.execute(text(f'DROP OWNED BY "{nome}"'))
        conexao.execute(text(f'DROP ROLE "{nome}"'))


def test_usuario_de_conexao_nao_e_superusuario_e_assume_lupa_app(papel_conexao: Engine) -> None:
    """Sem superusuário nem BYPASSRLS, mas membro de `lupa_app`: `SET LOCAL ROLE` funciona."""
    with papel_conexao.begin() as conexao:
        atributos = conexao.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(atributos) == (False, False)
        conexao.execute(text("SET LOCAL ROLE lupa_app"))
        assert conexao.execute(text("SELECT current_user")).scalar() == "lupa_app"


def test_login_sob_rls_localiza_usuario_pela_funcao_e_nao_lista_os_demais(
    papel_conexao: Engine, engine_teste: Engine
) -> None:
    """Sem contexto, nenhuma linha de `usuario` aparece; a função devolve só id/gabinete/papel."""
    usuario = criar_usuario_teste(
        engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste)
    )
    with Session(papel_conexao) as session, session.begin():
        assumir_papel_aplicacao(session)
        assert session.scalars(select(UsuarioTabela)).all() == []
        linha = session.execute(
            text("SELECT * FROM lupa_localizar_usuario(:n)"), {"n": usuario.nome}
        ).one()
        assert set(linha._mapping) == {"id", "gabinete_id", "papel"}
        definir_contexto(session, linha.papel, linha.gabinete_id)
        assert session.get(UsuarioTabela, usuario.id) is not None


def test_politica_do_administrador_libera_todos_os_gabinetes(
    papel_conexao: Engine, engine_teste: Engine
) -> None:
    """Com `lupa.papel = administrador`, usuários de gabinetes distintos aparecem."""
    a = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste))
    b = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine_teste))
    with Session(papel_conexao) as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
        ids = set(session.scalars(select(UsuarioTabela.id)))
    assert {a.id, b.id} <= ids


def test_tabelas_novas_tem_grant_para_lupa_app(engine_teste: Engine) -> None:
    """Toda tabela do esquema (inclusive as da 0002) tem SELECT para `lupa_app`."""
    with engine_teste.connect() as conexao:
        sem_grant = (
            conexao.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                    "AND c.relname <> 'alembic_version' "
                    "AND NOT has_table_privilege('lupa_app', c.oid, 'SELECT')"
                )
            )
            .scalars()
            .all()
        )
        padrao = conexao.execute(
            text(
                "SELECT count(*) FROM pg_default_acl, unnest(defaclacl) AS item "
                "WHERE defaclobjtype = 'r' AND item::text LIKE 'lupa_app=arwd/%'"
            )
        ).scalar()
    assert sem_grant == []
    assert padrao == 1


@pytest.fixture
def banco_vazio(engine_teste: Engine) -> Iterator[Engine]:
    """Banco recém-migrado só para este teste (sem administradores semeados)."""
    nome = f"{engine_teste.url.database}_vazio"
    with engine_teste.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    engine = create_engine(engine_teste.url.set(database=nome))
    migrar(engine, "head")
    yield engine
    engine.dispose()
    with engine_teste.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))


def _settings(engine: Engine, **extra: object) -> Settings:
    return Settings(
        ambiente="teste",
        database_url=SecretStr(engine.url.render_as_string(hide_password=False)),
        minio_endpoint="localhost:9000",
        minio_bucket="lupa-autos",
        minio_access_key=SecretStr("x"),
        minio_secret_key=SecretStr("y"),
        **extra,  # type: ignore[arg-type]
    )


def test_url_da_aplicacao_troca_usuario_quando_configurado(engine_teste: Engine) -> None:
    """Com usuário e senha da aplicação, a URL muda só nas credenciais."""
    sem = _settings(engine_teste)
    assert sem.url_banco_aplicacao() == sem.database_url.get_secret_value()
    com = _settings(engine_teste, db_usuario_app="lupa_api", db_senha_app=SecretStr("s3"))
    url = make_url(com.url_banco_aplicacao())
    assert (url.username, url.password, url.database) == (
        "lupa_api",
        "s3",
        engine_teste.url.database,
    )


def test_scripts_de_instalacao(engine_teste: Engine) -> None:
    """`criar_usuario_banco` e `criar_admin` validam a configuração e são idempotentes."""
    nome = f"lupa_api_script_{os.getpid()}"
    assert instalacao.criar_usuario_banco(_settings(engine_teste)) == 2
    configurado = _settings(engine_teste, db_usuario_app=nome, db_senha_app=SecretStr("s-123456"))
    assert instalacao.criar_usuario_banco(configurado) == 0
    with pytest.raises(ValueError, match="inválido"):
        with engine_teste.begin() as conexao:
            instalacao.garantir_usuario_conexao(conexao, "Nome Ruim;", "x")
    with engine_teste.begin() as conexao:
        conexao.execute(text(f'DROP OWNED BY "{nome}"'))
        conexao.execute(text(f'DROP ROLE "{nome}"'))


def test_criar_admin_cria_um_unico_administrador(banco_vazio: Engine) -> None:
    """Sem variáveis: 2. Senha fraca: 2. Válido: cria; repetir não cria outro."""
    configuracao = _settings(banco_vazio)
    assert instalacao.criar_admin(configuracao, {}) == 2
    fraco = {"LUPA_ADMIN_USUARIO": "adm_fraco", "LUPA_ADMIN_SENHA": "curta"}
    assert instalacao.criar_admin(configuracao, fraco) == 2
    nome_ruim = {"LUPA_ADMIN_USUARIO": "Adm Ruim", "LUPA_ADMIN_SENHA": "frase-longa-do-admin"}
    assert instalacao.criar_admin(configuracao, nome_ruim) == 2
    for nome in ("adm_principal", "adm_segundo"):
        valido = {"LUPA_ADMIN_USUARIO": nome, "LUPA_ADMIN_SENHA": "frase-longa-do-admin"}
        assert instalacao.criar_admin(configuracao, valido) == 0
    with banco_vazio.connect() as conexao:
        admins = conexao.execute(
            text("SELECT nome_usuario, troca_senha_obrigatoria FROM usuario")
        ).all()
        eventos = conexao.execute(text("SELECT acao, gabinete_id FROM evento_auditoria")).all()
    assert [tuple(a) for a in admins] == [("adm_principal", True)]
    assert [tuple(e) for e in eventos] == [("usuario_criado", None)]


def test_script_criar_admin_roda_como_programa(engine_teste: Engine) -> None:
    """O script lê o ambiente e termina com código 2 sem as variáveis."""
    ambiente = {
        k: v for k, v in os.environ.items() if k not in {"LUPA_ADMIN_USUARIO", "LUPA_ADMIN_SENHA"}
    }
    ambiente["LUPA_DATABASE_URL"] = engine_teste.url.render_as_string(hide_password=False)
    ambiente.setdefault("PYTHONPATH", str(RAIZ / "src"))
    for script in ("criar_admin.py", "criar_usuario_banco.py"):
        processo = subprocess.run(  # noqa: S603
            [sys.executable, str(RAIZ / "scripts" / script)],
            env=ambiente | {"LUPA_DB_USUARIO_APP": ""},
            capture_output=True,
            check=False,
        )
        assert processo.returncode == 2, processo.stdout


def test_lupa_app_nao_altera_auditoria_mesmo_com_contexto_de_admin(papel_conexao: Engine) -> None:
    """O privilégio de UPDATE em `evento_auditoria` foi revogado de `lupa_app`."""
    with Session(papel_conexao) as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
        with pytest.raises(DBAPIError, match="permission denied"):
            session.execute(text("UPDATE evento_auditoria SET resultado = 'x'"))
