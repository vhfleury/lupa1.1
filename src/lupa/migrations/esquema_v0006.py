"""Revisão 0006, escrita à mão: fronteiras, peças e índice (Etapa 4E).

- `pagina`: sinais de fronteira por página (JSON).
- `peca`: data da peça com tipo e evidência, versão substituída (reclassificação manual),
  vigência, flags agregadas das páginas e detalhes da classificação (pontuação, versão das
  regras, divergência com o índice de origem).
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


def _json(nome: str, padrao: str) -> sa.Column[Any]:
    return sa.Column(nome, JSONB, server_default=padrao, nullable=False)


def upgrade() -> None:
    """Acrescenta as colunas da 4E."""
    op.add_column("pagina", _json("sinais_fronteira", "{}"))
    op.add_column("peca", sa.Column("data", sa.Date(), nullable=True))
    op.add_column("peca", sa.Column("tipo_data", sa.Text(), nullable=True))
    op.add_column("peca", sa.Column("data_evidencia_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("peca", sa.Column("substitui_peca_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("peca", sa.Column("vigente", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("peca", _json("flags", "{}"))
    op.add_column("peca", _json("classificacao", "{}"))
    op.create_unique_constraint("uq_peca_id_gabinete_id", "peca", ["id", "gabinete_id"])
    op.create_foreign_key(
        "fk_peca_data_evidencia_id_gabinete_id",
        "peca",
        "evidencia",
        ["data_evidencia_id", "gabinete_id"],
        ["id", "gabinete_id"],
    )
    op.create_foreign_key(
        "fk_peca_substitui_peca_id_gabinete_id",
        "peca",
        "peca",
        ["substitui_peca_id", "gabinete_id"],
        ["id", "gabinete_id"],
    )
    op.create_check_constraint(
        "tipo_data_valido",
        "peca",
        "tipo_data IS NULL OR tipo_data IN ('assinatura', 'protocolo', 'juntada')",
    )
    op.create_index("ix_peca_arquivo_id_vigente", "peca", ["arquivo_id", "vigente"])


def downgrade() -> None:
    """Remove as colunas da 4E."""
    op.drop_index("ix_peca_arquivo_id_vigente", "peca")
    op.drop_constraint("tipo_data_valido", "peca", type_="check")
    op.drop_constraint("fk_peca_substitui_peca_id_gabinete_id", "peca", type_="foreignkey")
    op.drop_constraint("fk_peca_data_evidencia_id_gabinete_id", "peca", type_="foreignkey")
    op.drop_constraint("uq_peca_id_gabinete_id", "peca", type_="unique")
    for coluna in (
        "classificacao", "flags", "vigente", "substitui_peca_id", "data_evidencia_id",
        "tipo_data", "data",
    ):  # fmt: skip
        op.drop_column("peca", coluna)
    op.drop_column("pagina", "sinais_fronteira")
