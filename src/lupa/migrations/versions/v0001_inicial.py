"""Modelo de domínio inicial.

Revision ID: 0001
Revises:
Create Date: 2026-10-20

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0001`.
"""

from lupa.migrations.esquema_v0001 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
