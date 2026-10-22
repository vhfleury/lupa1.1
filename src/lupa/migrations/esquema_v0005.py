"""Revisão 0005, escrita à mão: saneamento contra injeção (Etapa 4D).

- `pagina`: texto normalizado (o original continua em `texto`), trechos ocultos e trechos
  suspeitos (JSON).
- `diagnostico_arquivo`: metadados, anotações e campos descartados (só hash, nunca o valor).
  Fica no diagnóstico porque `arquivo` é imutável (trigger `arquivo_imutavel`).
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


def _json(nome: str, padrao: str) -> sa.Column[Any]:
    return sa.Column(nome, JSONB, server_default=padrao, nullable=False)


def upgrade() -> None:
    """Acrescenta as colunas do saneamento."""
    op.add_column("pagina", sa.Column("texto_normalizado", sa.Text(), nullable=True))
    op.add_column("pagina", _json("trechos_ocultos", "[]"))
    op.add_column("pagina", _json("trechos_suspeitos", "[]"))
    op.add_column("diagnostico_arquivo", _json("metadados_descartados", "[]"))


def downgrade() -> None:
    """Remove as colunas do saneamento."""
    op.drop_column("diagnostico_arquivo", "metadados_descartados")
    for coluna in ("trechos_suspeitos", "trechos_ocultos", "texto_normalizado"):
        op.drop_column("pagina", coluna)
