"""add credential audit vault table

Revision ID: 20260522_0010
Revises: 20260522_0009
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0010"
down_revision = "20260522_0009"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "credential_audit"):
        return

    op.create_table(
        "credential_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=128), nullable=False),
        sa.Column("crypto_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credential_audit_user_id", "credential_audit", ["user_id"])
    op.create_index("ix_credential_audit_event_type", "credential_audit", ["event_type"])
    op.create_index("ix_credential_audit_actor_user_id", "credential_audit", ["actor_user_id"])
    op.create_index("ix_credential_audit_payload_sha256", "credential_audit", ["payload_sha256"])
    op.create_index("ix_credential_audit_user_event", "credential_audit", ["user_id", "event_type"])
    op.create_index("ix_credential_audit_created", "credential_audit", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "credential_audit"):
        return

    op.drop_index("ix_credential_audit_created", table_name="credential_audit")
    op.drop_index("ix_credential_audit_user_event", table_name="credential_audit")
    op.drop_index("ix_credential_audit_payload_sha256", table_name="credential_audit")
    op.drop_index("ix_credential_audit_actor_user_id", table_name="credential_audit")
    op.drop_index("ix_credential_audit_event_type", table_name="credential_audit")
    op.drop_index("ix_credential_audit_user_id", table_name="credential_audit")
    op.drop_table("credential_audit")
