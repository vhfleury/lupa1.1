"""Acesso (sessões, rate limit) e auditoria append-only encadeada.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0002`.
"""

from lupa.migrations.esquema_v0002 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
