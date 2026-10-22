"""Criptografia em repouso: DEK por processo, colunas cifradas e descarte (Etapa 7).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21

O conteúdo, escrito à mão, está em `lupa.migrations.esquema_v0010`.
"""

from lupa.migrations.esquema_v0010 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None
