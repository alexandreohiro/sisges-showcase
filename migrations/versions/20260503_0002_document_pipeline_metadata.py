"""add document pipeline metadata

Revision ID: 20260503_0002
Revises: 20260503_0001
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0002"
down_revision = "20260503_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = _existing_columns("documents")
    if "trace_id" not in columns:
        op.add_column("documents", sa.Column("trace_id", sa.String(length=64), nullable=True))
    if "template_sha256" not in columns:
        op.add_column("documents", sa.Column("template_sha256", sa.String(length=128), nullable=True))
    if "template_version" not in columns:
        op.add_column("documents", sa.Column("template_version", sa.String(length=64), nullable=True))
    if "input_sha256" not in columns:
        op.add_column("documents", sa.Column("input_sha256", sa.String(length=128), nullable=True))
    if "output_sha256" not in columns:
        op.add_column("documents", sa.Column("output_sha256", sa.String(length=128), nullable=True))
    if "metadata_json" not in columns:
        op.add_column("documents", sa.Column("metadata_json", sa.JSON(), nullable=True))

    indexes = _existing_indexes("documents")
    if "ix_documents_trace_id" not in indexes:
        op.create_index("ix_documents_trace_id", "documents", ["trace_id"], unique=False)
    if "ix_documents_template_version" not in indexes:
        op.create_index("ix_documents_template_version", "documents", ["template_version"], unique=False)


def downgrade() -> None:
    indexes = _existing_indexes("documents")
    if "ix_documents_template_version" in indexes:
        op.drop_index("ix_documents_template_version", table_name="documents")
    if "ix_documents_trace_id" in indexes:
        op.drop_index("ix_documents_trace_id", table_name="documents")

    columns = _existing_columns("documents")
    for column_name in (
        "metadata_json",
        "output_sha256",
        "input_sha256",
        "template_version",
        "template_sha256",
        "trace_id",
    ):
        if column_name in columns:
            op.drop_column("documents", column_name)


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}
