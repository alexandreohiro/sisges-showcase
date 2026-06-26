"""add sicapex service time relational metadata

Revision ID: 20260515_0007
Revises: 20260513_0006
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0007"
down_revision = "20260513_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    militar_columns = _existing_columns("militar")
    for column_name in (
        "tempo_servico_publico_anos",
        "tempo_servico_publico_meses",
        "tempo_servico_publico_dias",
    ):
        if column_name not in militar_columns:
            op.add_column(
                "militar",
                sa.Column(column_name, sa.Integer(), nullable=False, server_default="0"),
            )

    periodo_columns = _existing_columns("militar_periodo_servico")
    if "source_file_id" not in periodo_columns:
        op.add_column("militar_periodo_servico", sa.Column("source_file_id", sa.String(), nullable=True))
    if "payload_json" not in periodo_columns:
        op.add_column("militar_periodo_servico", sa.Column("payload_json", sa.JSON(), nullable=True))
    if "hash_evento" not in periodo_columns:
        op.add_column(
            "militar_periodo_servico",
            sa.Column("hash_evento", sa.String(length=128), nullable=True),
        )
    if "origem_documental" not in periodo_columns:
        op.add_column(
            "militar_periodo_servico",
            sa.Column("origem_documental", sa.String(length=80), nullable=True),
        )
    if "confianca_parse" not in periodo_columns:
        op.add_column(
            "militar_periodo_servico",
            sa.Column("confianca_parse", sa.String(length=40), nullable=True),
        )

    indexes = _existing_indexes("militar_periodo_servico")
    if "ix_militar_periodo_servico_source_file_id" not in indexes:
        op.create_index(
            "ix_militar_periodo_servico_source_file_id",
            "militar_periodo_servico",
            ["source_file_id"],
        )
    if "ix_militar_periodo_servico_hash_evento" not in indexes:
        op.create_index(
            "ix_militar_periodo_servico_hash_evento",
            "militar_periodo_servico",
            ["hash_evento"],
        )
    if "ix_periodo_sicapex_source_file" not in indexes:
        op.create_index(
            "ix_periodo_sicapex_source_file",
            "militar_periodo_servico",
            ["source_file_id"],
        )
    if "ix_periodo_sicapex_hash_evento" not in indexes:
        op.create_index(
            "ix_periodo_sicapex_hash_evento",
            "militar_periodo_servico",
            ["hash_evento"],
        )


def downgrade() -> None:
    indexes = _existing_indexes("militar_periodo_servico")
    for index_name in (
        "ix_periodo_sicapex_hash_evento",
        "ix_periodo_sicapex_source_file",
        "ix_militar_periodo_servico_hash_evento",
        "ix_militar_periodo_servico_source_file_id",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name="militar_periodo_servico")

    periodo_columns = _existing_columns("militar_periodo_servico")
    for column_name in (
        "confianca_parse",
        "origem_documental",
        "hash_evento",
        "payload_json",
        "source_file_id",
    ):
        if column_name in periodo_columns:
            op.drop_column("militar_periodo_servico", column_name)

    militar_columns = _existing_columns("militar")
    for column_name in (
        "tempo_servico_publico_dias",
        "tempo_servico_publico_meses",
        "tempo_servico_publico_anos",
    ):
        if column_name in militar_columns:
            op.drop_column("militar", column_name)


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}
