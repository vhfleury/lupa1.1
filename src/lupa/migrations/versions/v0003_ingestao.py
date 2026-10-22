"""Ingestão: job, lote e diagnóstico de arquivo.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0003`.
"""

from lupa.migrations.esquema_v0003 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
