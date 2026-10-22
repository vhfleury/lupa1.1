"""Fronteiras, peças e índice (Etapa 4E).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0006`.
"""

from lupa.migrations.esquema_v0006 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
