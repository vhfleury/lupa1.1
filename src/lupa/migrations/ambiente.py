"""Execução das migrações (chamada por env.py): só modo online, URL vinda de `lupa.config`."""

from alembic import context
from sqlalchemy import Connection, create_engine

from lupa.config import get_settings
from lupa.dominio.tabelas import Base


def _migrar(conexao: Connection) -> None:
    context.configure(connection=conexao, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


def executar() -> None:
    """Executa as migrações na conexão recebida ou numa conexão nova a partir da configuração."""
    conexao = context.config.attributes.get("connection")
    if conexao is not None:
        _migrar(conexao)
        return
    engine = create_engine(get_settings().database_url.get_secret_value())
    try:
        with engine.begin() as nova:
            _migrar(nova)
    finally:
        engine.dispose()
