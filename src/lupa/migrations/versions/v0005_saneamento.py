"""Saneamento contra injeção: texto normalizado, trechos e metadados descartados (Etapa 4D).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0005`.
"""

from lupa.migrations.esquema_v0005 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
