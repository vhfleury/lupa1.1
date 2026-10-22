"""Revisão 0009, escrita à mão: processo em revisão após incidente do agente (Etapa 6.8).

- `processo.status` aceita `em_revisao` (o CHECK é recriado com o valor novo; só acréscimo).
- `revisao_processo`: incidente aberto pela conferência da resposta do modelo e liberado por
  desembargador ou administrador. RLS forçada por gabinete, como as demais tabelas.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

PAPEL_APLICACAO = "lupa_app"
STATUS_ANTIGOS = ("criado", "em_ingestao", "pronto", "bloqueado", "arquivado")
STATUS_NOVOS = (*STATUS_ANTIGOS, "em_revisao")
CHECK_STATUS = "ck_processo_status_valido"


def _check_status(valores: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{v}'" for v in valores)
    op.execute(f"ALTER TABLE processo DROP CONSTRAINT {CHECK_STATUS}")
    op.execute(f"ALTER TABLE processo ADD CONSTRAINT {CHECK_STATUS} CHECK (status IN ({lista}))")


def _uuid(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, UUID(as_uuid=True), nullable=nullable)


def _criar_tabela() -> None:
    op.create_table(
        "revisao_processo",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _uuid("gabinete_id"),
        _uuid("processo_id"),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("status_anterior", sa.Text(), nullable=False),
        sa.Column(
            "aberta_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("liberada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("liberada_por", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.ForeignKeyConstraint(
            ["processo_id", "gabinete_id"],
            ["processo.id", "processo.gabinete_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_revisao_processo_processo_id", "revisao_processo", ["processo_id"])
    op.create_index("ix_revisao_processo_gabinete_id", "revisao_processo", ["gabinete_id"])


def _rls() -> None:
    op.execute("ALTER TABLE revisao_processo ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE revisao_processo FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY revisao_processo_por_gabinete ON revisao_processo
            USING (gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid)
            WITH CHECK (
                gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid
            )
        """
    )
    op.execute(
        """
        CREATE POLICY revisao_processo_administrador ON revisao_processo
            USING (current_setting('lupa.papel', true) = 'administrador')
            WITH CHECK (current_setting('lupa.papel', true) = 'administrador')
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON revisao_processo TO {PAPEL_APLICACAO}")
    op.execute(f"REVOKE DELETE ON revisao_processo FROM {PAPEL_APLICACAO}")


def upgrade() -> None:
    """Aceita `em_revisao` e cria `revisao_processo` com RLS."""
    _check_status(STATUS_NOVOS)
    _criar_tabela()
    _rls()


def downgrade() -> None:
    """Remove a tabela e devolve processos em revisão ao status anterior."""
    op.execute(
        """
        UPDATE processo p SET status = r.status_anterior
          FROM revisao_processo r
         WHERE r.processo_id = p.id AND r.liberada_em IS NULL AND p.status = 'em_revisao'
        """
    )
    op.execute("UPDATE processo SET status = 'pronto' WHERE status = 'em_revisao'")
    op.drop_table("revisao_processo")
    _check_status(STATUS_ANTIGOS)
