"""Processo em revisão após incidente do agente (Etapa 6.8).

Revision ID: 0009
Revises: 0007
Create Date: 2026-10-21

O conteúdo, escrito à mão, está em `lupa.migrations.esquema_v0009`. Número 0009 reservado
para não colidir com a 0008 das subetapas 6.4 a 6.7; `down_revision` aponta para a cabeça
vigente quando esta revisão foi aplicada.
"""

from lupa.migrations.esquema_v0009 import downgrade, upgrade

__all__ = ["downgrade", "upgrade"]

revision = "0009"
down_revision = "0007"
branch_labels = None
depends_on = None
