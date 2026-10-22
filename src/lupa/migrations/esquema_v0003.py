"""Revisão 0003, escrita à mão: tabelas da ingestão (job, lote, diagnóstico) com RLS e grants.

Segue o padrão das revisões anteriores: chaves estrangeiras compostas `(x_id, gabinete_id)`,
RLS forçada com a política por gabinete e a política do administrador, e grant explícito para
`lupa_app` (além do `ALTER DEFAULT PRIVILEGES` da 0002).
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from lupa.dominio.enums import CenarioArquivo, EstadoJob, EstadoLote, MotivoQuarentena
from lupa.dominio.tabelas import TABELAS_INGESTAO, checar_enum

PAPEL_APLICACAO = "lupa_app"


def _id() -> sa.Column[Any]:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _gabinete() -> sa.Column[Any]:
    return sa.Column("gabinete_id", UUID(as_uuid=True), nullable=False)


def _uuid(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, UUID(as_uuid=True), nullable=False)


def _texto(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, sa.Text(), nullable=nullable)


def _momento(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), nullable=True)


def _instante(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _fk(coluna: str, alvo: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [coluna, "gabinete_id"], [f"{alvo}.id", f"{alvo}.gabinete_id"], ondelete="CASCADE"
    )


def _criar_job() -> None:
    op.create_table(
        "job_ingestao",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _uuid("arquivo_id"),
        _texto("estado"),
        _texto("motivo_quarentena", nullable=True),
        _texto("motivo_falha", nullable=True),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), server_default="0", nullable=False),
        _texto("lease_dono", nullable=True),
        _momento("lease_expira_em"),
        _momento("heartbeat_em"),
        sa.Column("total_paginas", sa.Integer(), nullable=True),
        sa.Column("manifesto", JSONB, nullable=True),
        _instante("criado_em"),
        _momento("iniciado_em"),
        _momento("finalizado_em"),
        _fk("arquivo_id", "arquivo"),
        _fk("processo_id", "processo"),
        sa.UniqueConstraint("arquivo_id"),
        sa.UniqueConstraint("id", "gabinete_id"),
        checar_enum("estado", EstadoJob),
        checar_enum("motivo_quarentena", MotivoQuarentena),
        sa.CheckConstraint(
            "(estado = 'quarentena') = (motivo_quarentena IS NOT NULL)",
            name="quarentena_com_motivo",
        ),
    )
    op.create_index(
        "ix_job_ingestao_estado_lease_expira_em", "job_ingestao", ["estado", "lease_expira_em"]
    )


def _criar_lote_e_diagnostico() -> None:
    op.create_table(
        "lote_ingestao",
        _id(),
        _gabinete(),
        _uuid("job_id"),
        sa.Column("numero", sa.Integer(), nullable=False),
        _texto("estado"),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("resultado", JSONB, server_default="{}", nullable=False),
        _instante("gravado_em"),
        _fk("job_id", "job_ingestao"),
        sa.UniqueConstraint("job_id", "numero"),
        checar_enum("estado", EstadoLote),
    )
    op.create_table(
        "diagnostico_arquivo",
        _id(),
        _gabinete(),
        _uuid("arquivo_id"),
        _texto("cenario"),
        sa.Column("total_paginas", sa.Integer(), nullable=False),
        sa.Column("tem_indice", sa.Boolean(), nullable=False),
        sa.Column("sinais", JSONB, server_default="{}", nullable=False),
        _instante("criado_em"),
        _fk("arquivo_id", "arquivo"),
        sa.UniqueConstraint("arquivo_id"),
        checar_enum("cenario", CenarioArquivo),
        sa.CheckConstraint("total_paginas >= 0", name="paginas_nao_negativas"),
    )


def _criar_rls_e_grants() -> None:
    for tabela in TABELAS_INGESTAO:
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
    tabelas = ", ".join(TABELAS_INGESTAO)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabelas} TO {PAPEL_APLICACAO}")


def upgrade() -> None:
    """Cria as tabelas da ingestão com RLS por gabinete e grants para `lupa_app`."""
    _criar_job()
    _criar_lote_e_diagnostico()
    _criar_rls_e_grants()


def downgrade() -> None:
    """Remove as tabelas da ingestão (políticas e índices caem junto)."""
    for tabela in reversed(TABELAS_INGESTAO):
        op.drop_table(tabela)
