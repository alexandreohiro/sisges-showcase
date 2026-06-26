"""add compiler persistent memory tables

Revision ID: 20260518_0008
Revises: 20260515_0007
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260518_0008"
down_revision = "20260515_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = _existing_tables()
    if "compiler_run" not in tables:
        op.create_table(
            "compiler_run",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("tipo_compilacao", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("militar_id", sa.Integer(), sa.ForeignKey("militar.id"), nullable=True),
            sa.Column("nome_militar_snapshot", sa.String(length=200), nullable=True),
            sa.Column("identidade_snapshot", sa.String(length=40), nullable=True),
            sa.Column("posto_grad_snapshot", sa.String(length=120), nullable=True),
            sa.Column("periodo_inicio", sa.Date(), nullable=True),
            sa.Column("periodo_fim", sa.Date(), nullable=True),
            sa.Column("ano", sa.Integer(), nullable=True),
            sa.Column("semestre", sa.String(length=10), nullable=True),
            sa.Column("fonte_tempo", sa.String(length=120), nullable=True),
            sa.Column("fonte_eventos", sa.String(length=120), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "compiler_file" not in tables:
        op.create_table(
            "compiler_file",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("run_id", sa.String(), sa.ForeignKey("compiler_run.id"), nullable=True),
            sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("militar_id", sa.Integer(), sa.ForeignKey("militar.id"), nullable=True),
            sa.Column("role", sa.String(length=80), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("mime_type", sa.String(length=120), nullable=True),
            sa.Column("extension", sa.String(length=20), nullable=True),
            sa.Column("storage_path", sa.String(length=500), nullable=False),
            sa.Column("sha256", sa.String(length=128), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("source_kind", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "compiler_variable_snapshot" not in tables:
        op.create_table(
            "compiler_variable_snapshot",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("run_id", sa.String(), sa.ForeignKey("compiler_run.id"), nullable=True),
            sa.Column("file_id", sa.String(), sa.ForeignKey("compiler_file.id"), nullable=True),
            sa.Column("militar_id", sa.Integer(), sa.ForeignKey("militar.id"), nullable=True),
            sa.Column("schema_version", sa.String(length=40), nullable=False),
            sa.Column("variables_json", sa.JSON(), nullable=False),
            sa.Column("warnings_json", sa.JSON(), nullable=True),
            sa.Column("pending_json", sa.JSON(), nullable=True),
            sa.Column("confidence_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "compiler_validation" not in tables:
        op.create_table(
            "compiler_validation",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("run_id", sa.String(), sa.ForeignKey("compiler_run.id"), nullable=True),
            sa.Column("file_id", sa.String(), sa.ForeignKey("compiler_file.id"), nullable=True),
            sa.Column("level", sa.String(length=20), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("field", sa.String(length=120), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    _create_indexes()


def downgrade() -> None:
    for table in (
        "compiler_validation",
        "compiler_variable_snapshot",
        "compiler_file",
        "compiler_run",
    ):
        if table in _existing_tables():
            op.drop_table(table)


def _create_indexes() -> None:
    specs = {
        "compiler_run": [
            ("ix_compiler_run_trace_id", ["trace_id"]),
            ("ix_compiler_run_tipo_compilacao", ["tipo_compilacao"]),
            ("ix_compiler_run_status", ["status"]),
            ("ix_compiler_run_militar_id", ["militar_id"]),
            ("ix_compiler_run_ano", ["ano"]),
            ("ix_compiler_run_semestre", ["semestre"]),
            ("ix_compiler_run_tipo_status", ["tipo_compilacao", "status"]),
            ("ix_compiler_run_militar_periodo", ["militar_id", "ano", "semestre"]),
        ],
        "compiler_file": [
            ("ix_compiler_file_run_id", ["run_id"]),
            ("ix_compiler_file_document_id", ["document_id"]),
            ("ix_compiler_file_militar_id", ["militar_id"]),
            ("ix_compiler_file_role", ["role"]),
            ("ix_compiler_file_filename", ["filename"]),
            ("ix_compiler_file_sha256", ["sha256"]),
            ("ix_compiler_file_source_kind", ["source_kind"]),
            ("ix_compiler_file_role_sha", ["role", "sha256"]),
            ("ix_compiler_file_run_role", ["run_id", "role"]),
            ("ix_compiler_file_militar_role", ["militar_id", "role"]),
        ],
        "compiler_variable_snapshot": [
            ("ix_compiler_variable_snapshot_run_id", ["run_id"]),
            ("ix_compiler_variable_snapshot_file_id", ["file_id"]),
            ("ix_compiler_variable_snapshot_militar_id", ["militar_id"]),
            ("ix_compiler_snapshot_run_created", ["run_id", "created_at"]),
            ("ix_compiler_snapshot_file_created", ["file_id", "created_at"]),
        ],
        "compiler_validation": [
            ("ix_compiler_validation_run_id", ["run_id"]),
            ("ix_compiler_validation_file_id", ["file_id"]),
            ("ix_compiler_validation_level", ["level"]),
            ("ix_compiler_validation_code", ["code"]),
            ("ix_compiler_validation_run_level", ["run_id", "level"]),
            ("ix_compiler_validation_file_code", ["file_id", "code"]),
        ],
    }
    for table, indexes in specs.items():
        existing = _existing_indexes(table)
        for name, columns in indexes:
            if name not in existing:
                op.create_index(name, table, columns)


def _existing_tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _existing_indexes(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}
