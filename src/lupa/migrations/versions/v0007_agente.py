"""Agente e chat: conversa, mensagem e chamada ao modelo (Etapa 5).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-21

O conteúdo, escrito e revisado à mão, está em `lupa.migrations.esquema_v0007`.
"""

from lupa.migrations.esquema_v0007 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
