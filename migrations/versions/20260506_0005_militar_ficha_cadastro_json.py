"""add full SiCaPEx ficha cadastro storage

Revision ID: 20260506_0005
Revises: 20260503_0004
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0005"
down_revision = "20260503_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = _existing_columns("militar")
    if "ficha_cadastro_json" not in columns:
        op.add_column("militar", sa.Column("ficha_cadastro_json", sa.JSON(), nullable=True))
    if "ficha_cadastro_pdf_hash" not in columns:
        op.add_column(
            "militar",
            sa.Column("ficha_cadastro_pdf_hash", sa.String(length=128), nullable=True),
        )
    if "ficha_cadastro_origem" not in columns:
        op.add_column(
            "militar",
            sa.Column("ficha_cadastro_origem", sa.String(length=255), nullable=True),
        )
    if "ficha_cadastro_importado_em" not in columns:
        op.add_column(
            "militar",
            sa.Column("ficha_cadastro_importado_em", sa.DateTime(), nullable=True),
        )

    indexes = _existing_indexes("militar")
    if "ix_militar_ficha_cadastro_pdf_hash" not in indexes:
        op.create_index(
            "ix_militar_ficha_cadastro_pdf_hash",
            "militar",
            ["ficha_cadastro_pdf_hash"],
            unique=False,
        )


def downgrade() -> None:
    indexes = _existing_indexes("militar")
    if "ix_militar_ficha_cadastro_pdf_hash" in indexes:
        op.drop_index("ix_militar_ficha_cadastro_pdf_hash", table_name="militar")

    columns = _existing_columns("militar")
    for column_name in (
        "ficha_cadastro_importado_em",
        "ficha_cadastro_origem",
        "ficha_cadastro_pdf_hash",
        "ficha_cadastro_json",
    ):
        if column_name in columns:
            op.drop_column("militar", column_name)


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}
