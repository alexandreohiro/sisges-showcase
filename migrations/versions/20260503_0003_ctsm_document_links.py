"""add ctsm document and folha links

Revision ID: 20260503_0003
Revises: 20260503_0002
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0003"
down_revision = "20260503_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = _existing_columns("ctsm")
    if "document_id" not in columns:
        op.add_column("ctsm", sa.Column("document_id", sa.String(), nullable=True))
    if "folha_id" not in columns:
        op.add_column("ctsm", sa.Column("folha_id", sa.Integer(), nullable=True))
    if "emitido_em" not in columns:
        op.add_column("ctsm", sa.Column("emitido_em", sa.DateTime(), nullable=True))
    if "emitido_por_user_id" not in columns:
        op.add_column("ctsm", sa.Column("emitido_por_user_id", sa.String(), nullable=True))

    indexes = _existing_indexes("ctsm")
    if "ix_ctsm_document_id" not in indexes:
        op.create_index("ix_ctsm_document_id", "ctsm", ["document_id"], unique=False)
    if "ix_ctsm_folha_id" not in indexes:
        op.create_index("ix_ctsm_folha_id", "ctsm", ["folha_id"], unique=False)
    if "ix_ctsm_emitido_por_user_id" not in indexes:
        op.create_index(
            "ix_ctsm_emitido_por_user_id",
            "ctsm",
            ["emitido_por_user_id"],
            unique=False,
        )


def downgrade() -> None:
    indexes = _existing_indexes("ctsm")
    for index_name in (
        "ix_ctsm_emitido_por_user_id",
        "ix_ctsm_folha_id",
        "ix_ctsm_document_id",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name="ctsm")

    columns = _existing_columns("ctsm")
    for column_name in ("emitido_por_user_id", "emitido_em", "folha_id", "document_id"):
        if column_name in columns:
            op.drop_column("ctsm", column_name)


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}
