"""add user avatar path

Revision ID: 20260522_0009
Revises: 20260518_0008
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0009"
down_revision = "20260518_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "avatar_path" not in columns:
        op.add_column("users", sa.Column("avatar_path", sa.String(length=255), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "avatar_path" in columns:
        op.drop_column("users", "avatar_path")
