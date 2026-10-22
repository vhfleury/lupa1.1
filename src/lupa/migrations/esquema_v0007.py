"""Revisão 0007, escrita à mão: tabelas do agente e do chat (Etapa 5).

- `conversa`: conversa de um usuário sobre um processo, com contadores dos tetos.
- `mensagem`: pergunta ou resposta; `texto` em coluna própria, para ser cifrada na Etapa 7.
- `chamada_modelo`: metadados de cada chamada ao modelo (hashes, tokens, latência), sem
  conteúdo; o evento `chamada_modelo` da auditoria aponta para a linha.

Mesmo padrão das revisões anteriores: chaves estrangeiras compostas `(x_id, gabinete_id)`, RLS
forçada com a política por gabinete e a do administrador, e grant explícito para `lupa_app`.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from lupa.dominio.enums import PapelMensagem, ResultadoChamada, StatusMensagem
from lupa.dominio.tabelas import checar_enum

PAPEL_APLICACAO = "lupa_app"
TABELAS = ("conversa", "mensagem", "chamada_modelo")


def _id() -> sa.Column[Any]:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _gabinete() -> sa.Column[Any]:
    return sa.Column("gabinete_id", UUID(as_uuid=True), nullable=False)


def _uuid(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, UUID(as_uuid=True), nullable=nullable)


def _texto(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, sa.Text(), nullable=nullable)


def _inteiro(nome: str, tipo: Any = sa.Integer) -> sa.Column[Any]:
    return sa.Column(nome, tipo(), server_default="0", nullable=False)


def _instante(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _fk(coluna: str, alvo: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [coluna, "gabinete_id"], [f"{alvo}.id", f"{alvo}.gabinete_id"], ondelete="CASCADE"
    )


def _criar_conversa() -> None:
    op.create_table(
        "conversa",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        _instante("criada_em"),
        sa.Column("encerrada", sa.Boolean(), server_default="false", nullable=False),
        _texto("motivo_encerramento", nullable=True),
        _inteiro("tokens_entrada", sa.BigInteger),
        _inteiro("tokens_saida", sa.BigInteger),
        _inteiro("paginas_originais"),
        _inteiro("citacoes_descartadas"),
        _fk("processo_id", "processo"),
        sa.UniqueConstraint("id", "gabinete_id"),
    )
    op.create_index("ix_conversa_processo_id_usuario_id", "conversa", ["processo_id", "usuario_id"])


def _criar_mensagem() -> None:
    op.create_table(
        "mensagem",
        _id(),
        _gabinete(),
        _uuid("conversa_id"),
        _texto("papel"),
        _texto("status"),
        _texto("texto"),
        sa.Column("citacoes", JSONB, server_default="[]", nullable=False),
        sa.Column("avisos", JSONB, server_default="[]", nullable=False),
        _instante("criado_em"),
        _fk("conversa_id", "conversa"),
        checar_enum("papel", PapelMensagem),
        checar_enum("status", StatusMensagem),
    )
    op.create_index("ix_mensagem_conversa_id_criado_em", "mensagem", ["conversa_id", "criado_em"])


def _criar_chamada() -> None:
    op.create_table(
        "chamada_modelo",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _uuid("conversa_id", nullable=True),
        _texto("modelo"),
        _texto("versao_prompt"),
        _texto("hash_prompt_sistema"),
        _texto("hash_entrada"),
        _texto("hash_saida"),
        sa.Column("tokens_entrada", sa.Integer(), nullable=False),
        sa.Column("tokens_saida", sa.Integer(), nullable=False),
        sa.Column("latencia_ms", sa.Integer(), nullable=False),
        sa.Column("ferramentas", ARRAY(sa.Text()), server_default="{}", nullable=False),
        _texto("resultado"),
        _instante("criado_em"),
        _fk("processo_id", "processo"),
        checar_enum("resultado", ResultadoChamada),
    )
    op.create_index(
        "ix_chamada_modelo_processo_id_criado_em", "chamada_modelo", ["processo_id", "criado_em"]
    )


def _criar_rls_e_grants() -> None:
    for tabela in TABELAS:
        op.create_index(f"ix_{tabela}_gabinete_id", tabela, ["gabinete_id"])
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabela}_por_gabinete ON {tabela}
                USING (gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid)
                WITH CHECK (
                    gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid
                )
            """
        )
        op.execute(
            f"""
            CREATE POLICY {tabela}_administrador ON {tabela}
                USING (current_setting('lupa.papel', true) = 'administrador')
                WITH CHECK (current_setting('lupa.papel', true) = 'administrador')
            """
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON conversa TO {PAPEL_APLICACAO}")
    op.execute(f"GRANT SELECT, INSERT ON mensagem, chamada_modelo TO {PAPEL_APLICACAO}")
    op.execute(f"REVOKE UPDATE, DELETE ON mensagem, chamada_modelo FROM {PAPEL_APLICACAO}")
    op.execute(f"REVOKE DELETE ON conversa FROM {PAPEL_APLICACAO}")


def upgrade() -> None:
    """Cria as tabelas do agente com RLS por gabinete e grants para `lupa_app`."""
    _criar_conversa()
    _criar_mensagem()
    _criar_chamada()
    _criar_rls_e_grants()


def downgrade() -> None:
    """Remove as tabelas do agente (políticas e índices caem junto)."""
    for tabela in reversed(TABELAS):
        op.drop_table(tabela)
