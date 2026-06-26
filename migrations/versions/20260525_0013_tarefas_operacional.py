"""extend tarefas with operational workflow fields

Revision ID: 20260525_0013
Revises: 20260522_0012
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0013"
down_revision = "20260522_0012"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(bind, name: str, column: sa.Column) -> None:
    if name not in _columns(bind, "tarefa"):
        op.add_column("tarefa", column)


def _create_index_if_missing(bind, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name not in _indexes(bind, "tarefa"):
        op.create_index(index_name, "tarefa", columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    _add_column_if_missing(bind, "fingerprint", sa.Column("fingerprint", sa.String(length=180), nullable=True))
    _add_column_if_missing(bind, "secao_responsavel", sa.Column("secao_responsavel", sa.String(length=120), nullable=True))
    _add_column_if_missing(
        bind,
        "divisao_responsavel",
        sa.Column("divisao_responsavel", sa.String(length=120), nullable=True),
    )
    _add_column_if_missing(bind, "referencia_tipo", sa.Column("referencia_tipo", sa.String(length=80), nullable=True))
    _add_column_if_missing(bind, "referencia_id", sa.Column("referencia_id", sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, "workflow_item_id", sa.Column("workflow_item_id", sa.Integer(), nullable=True))
    _add_column_if_missing(bind, "document_id", sa.Column("document_id", sa.String(), nullable=True))
    _add_column_if_missing(
        bind,
        "completed_by_user_id",
        sa.Column("completed_by_user_id", sa.String(), nullable=True),
    )
    _add_column_if_missing(bind, "closed_by_user_id", sa.Column("closed_by_user_id", sa.String(), nullable=True))
    _add_column_if_missing(bind, "blocked_by_task_id", sa.Column("blocked_by_task_id", sa.Integer(), nullable=True))
    _add_column_if_missing(bind, "closed_at", sa.Column("closed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(bind, "artefato_tipo", sa.Column("artefato_tipo", sa.String(length=80), nullable=True))
    _add_column_if_missing(bind, "artefato_path", sa.Column("artefato_path", sa.String(length=500), nullable=True))
    _add_column_if_missing(bind, "artefato_sha256", sa.Column("artefato_sha256", sa.String(length=128), nullable=True))
    _add_column_if_missing(bind, "checklist_json", sa.Column("checklist_json", sa.JSON(), nullable=True))
    _add_column_if_missing(
        bind,
        "created_from_rule",
        sa.Column("created_from_rule", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    indexes = [
        ("ix_tarefa_fingerprint", ["fingerprint"], True),
        ("ix_tarefa_secao_responsavel", ["secao_responsavel"], False),
        ("ix_tarefa_divisao_responsavel", ["divisao_responsavel"], False),
        ("ix_tarefa_referencia_tipo", ["referencia_tipo"], False),
        ("ix_tarefa_referencia_id", ["referencia_id"], False),
        ("ix_tarefa_workflow_item_id", ["workflow_item_id"], False),
        ("ix_tarefa_document_id", ["document_id"], False),
        ("ix_tarefa_completed_by_user_id", ["completed_by_user_id"], False),
        ("ix_tarefa_closed_by_user_id", ["closed_by_user_id"], False),
        ("ix_tarefa_blocked_by_task_id", ["blocked_by_task_id"], False),
        ("ix_tarefa_artefato_sha256", ["artefato_sha256"], False),
        ("ix_tarefa_created_from_rule", ["created_from_rule"], False),
        ("ix_tarefa_status_prioridade", ["status", "prioridade"], False),
        ("ix_tarefa_secao_status", ["secao_responsavel", "status"], False),
        ("ix_tarefa_referencia", ["referencia_tipo", "referencia_id"], False),
    ]
    for index_name, columns, unique in indexes:
        _create_index_if_missing(bind, index_name, columns, unique=unique)

    if "tarefa_evento" not in _tables(bind):
        op.create_table(
            "tarefa_evento",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tarefa_id", sa.Integer(), sa.ForeignKey("tarefa.id"), nullable=False),
            sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("before_json", sa.JSON(), nullable=True),
            sa.Column("after_json", sa.JSON(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_tarefa_evento_tarefa_id", "tarefa_evento", ["tarefa_id"])
        op.create_index("ix_tarefa_evento_actor_user_id", "tarefa_evento", ["actor_user_id"])
        op.create_index("ix_tarefa_evento_event_type", "tarefa_evento", ["event_type"])
        op.create_index("ix_tarefa_evento_tarefa_created", "tarefa_evento", ["tarefa_id", "created_at"])
        op.create_index("ix_tarefa_evento_actor_created", "tarefa_evento", ["actor_user_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "tarefa_evento" in _tables(bind):
        for index_name in (
            "ix_tarefa_evento_actor_created",
            "ix_tarefa_evento_tarefa_created",
            "ix_tarefa_evento_event_type",
            "ix_tarefa_evento_actor_user_id",
            "ix_tarefa_evento_tarefa_id",
        ):
            if index_name in _indexes(bind, "tarefa_evento"):
                op.drop_index(index_name, table_name="tarefa_evento")
        op.drop_table("tarefa_evento")

    for index_name in (
        "ix_tarefa_referencia",
        "ix_tarefa_secao_status",
        "ix_tarefa_status_prioridade",
        "ix_tarefa_created_from_rule",
        "ix_tarefa_artefato_sha256",
        "ix_tarefa_blocked_by_task_id",
        "ix_tarefa_closed_by_user_id",
        "ix_tarefa_completed_by_user_id",
        "ix_tarefa_document_id",
        "ix_tarefa_workflow_item_id",
        "ix_tarefa_referencia_id",
        "ix_tarefa_referencia_tipo",
        "ix_tarefa_divisao_responsavel",
        "ix_tarefa_secao_responsavel",
        "ix_tarefa_fingerprint",
    ):
        if index_name in _indexes(bind, "tarefa"):
            op.drop_index(index_name, table_name="tarefa")

    existing_columns = _columns(bind, "tarefa")
    for column_name in (
        "created_from_rule",
        "checklist_json",
        "artefato_sha256",
        "artefato_path",
        "artefato_tipo",
        "closed_at",
        "blocked_by_task_id",
        "closed_by_user_id",
        "completed_by_user_id",
        "document_id",
        "workflow_item_id",
        "referencia_id",
        "referencia_tipo",
        "divisao_responsavel",
        "secao_responsavel",
        "fingerprint",
    ):
        if column_name in existing_columns:
            op.drop_column("tarefa", column_name)
