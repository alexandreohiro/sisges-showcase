"""add sicapex batch import audit tables

Revision ID: 20260513_0006
Revises: 20260506_0005
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0006"
down_revision = "20260506_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "sicapex_import_batch" not in tables:
        op.create_table(
            "sicapex_import_batch",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("source_folder", sa.String(length=255), nullable=True),
            sa.Column("total_files", sa.Integer(), nullable=False, default=0),
            sa.Column("success_count", sa.Integer(), nullable=False, default=0),
            sa.Column("failed_count", sa.Integer(), nullable=False, default=0),
            sa.Column("pending_count", sa.Integer(), nullable=False, default=0),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, default=0),
            sa.Column("report_json", sa.JSON(), nullable=True),
        )

    if "sicapex_import_file" not in tables:
        op.create_table(
            "sicapex_import_file",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("batch_id", sa.String(), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("sha256", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("militar_id", sa.Integer(), nullable=True),
            sa.Column("identidade_militar_hash", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("warnings_json", sa.JSON(), nullable=True),
            sa.Column("parsed_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["batch_id"], ["sicapex_import_batch.id"]),
            sa.ForeignKeyConstraint(["militar_id"], ["militar.id"]),
        )
        op.create_index("ix_sicapex_import_file_batch_id", "sicapex_import_file", ["batch_id"])
        op.create_index("ix_sicapex_import_file_filename", "sicapex_import_file", ["filename"])
        op.create_index("ix_sicapex_import_file_militar_id", "sicapex_import_file", ["militar_id"])
        op.create_index("ix_sicapex_import_file_sha256", "sicapex_import_file", ["sha256"])
        op.create_index("ix_sicapex_import_file_status", "sicapex_import_file", ["status"])
        op.create_index(
            "ix_sicapex_file_batch_status",
            "sicapex_import_file",
            ["batch_id", "status"],
        )

    if "sicapex_evento_funcional" not in tables:
        op.create_table(
            "sicapex_evento_funcional",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("militar_id", sa.Integer(), nullable=False),
            sa.Column("source_file_id", sa.String(), nullable=True),
            sa.Column("tipo_evento", sa.String(length=80), nullable=False),
            sa.Column("subtipo_evento", sa.String(length=120), nullable=True),
            sa.Column("data_inicio", sa.Date(), nullable=True),
            sa.Column("data_fim", sa.Date(), nullable=True),
            sa.Column("documento", sa.String(length=180), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["militar_id"], ["militar.id"]),
            sa.ForeignKeyConstraint(["source_file_id"], ["sicapex_import_file.id"]),
        )
        op.create_index("ix_sicapex_evento_funcional_militar_id", "sicapex_evento_funcional", ["militar_id"])
        op.create_index("ix_sicapex_evento_funcional_source_file_id", "sicapex_evento_funcional", ["source_file_id"])
        op.create_index("ix_sicapex_evento_funcional_tipo_evento", "sicapex_evento_funcional", ["tipo_evento"])
        op.create_index("ix_sicapex_evento_funcional_subtipo_evento", "sicapex_evento_funcional", ["subtipo_evento"])
        op.create_index("ix_sicapex_evento_funcional_data_inicio", "sicapex_evento_funcional", ["data_inicio"])
        op.create_index("ix_sicapex_evento_funcional_data_fim", "sicapex_evento_funcional", ["data_fim"])
        op.create_index(
            "ix_sicapex_evento_militar_tipo",
            "sicapex_evento_funcional",
            ["militar_id", "tipo_evento"],
        )
        op.create_index(
            "ix_sicapex_evento_source_file",
            "sicapex_evento_funcional",
            ["source_file_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "sicapex_evento_funcional" in tables:
        op.drop_table("sicapex_evento_funcional")
    if "sicapex_import_file" in tables:
        op.drop_table("sicapex_import_file")
    if "sicapex_import_batch" in tables:
        op.drop_table("sicapex_import_batch")
