"""add workflow inbox items

Revision ID: 20260503_0004
Revises: 20260503_0003
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0004"
down_revision = "20260503_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "workflow_items" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "workflow_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column("modulo", sa.String(length=80), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=False),
        sa.Column("severidade", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.String(length=40), nullable=False, default="aberto"),
        sa.Column("militar_id", sa.Integer(), nullable=True),
        sa.Column("referencia_tipo", sa.String(length=80), nullable=True),
        sa.Column("referencia_id", sa.String(length=80), nullable=True),
        sa.Column("titulo", sa.String(length=220), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("acao_recomendada", sa.String(length=120), nullable=False),
        sa.Column("motivo_regra", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["militar_id"], ["militar.id"]),
    )
    op.create_index("ix_workflow_items_fingerprint", "workflow_items", ["fingerprint"], unique=True)
    op.create_index("ix_workflow_items_modulo", "workflow_items", ["modulo"], unique=False)
    op.create_index("ix_workflow_items_tipo", "workflow_items", ["tipo"], unique=False)
    op.create_index("ix_workflow_items_severidade", "workflow_items", ["severidade"], unique=False)
    op.create_index("ix_workflow_items_score", "workflow_items", ["score"], unique=False)
    op.create_index("ix_workflow_items_status", "workflow_items", ["status"], unique=False)
    op.create_index("ix_workflow_items_militar_id", "workflow_items", ["militar_id"], unique=False)
    op.create_index(
        "ix_workflow_items_referencia_tipo",
        "workflow_items",
        ["referencia_tipo"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_items_referencia_id",
        "workflow_items",
        ["referencia_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_items_resolved_by_user_id",
        "workflow_items",
        ["resolved_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_status_severidade",
        "workflow_items",
        ["status", "severidade"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_modulo_status",
        "workflow_items",
        ["modulo", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_militar_status",
        "workflow_items",
        ["militar_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    if "workflow_items" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("workflow_items")
