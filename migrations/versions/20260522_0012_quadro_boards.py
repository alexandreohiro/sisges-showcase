"""add quadro board persistence

Revision ID: 20260522_0012
Revises: 20260522_0011
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0012"
down_revision = "20260522_0011"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "quadro_board"):
        return

    op.create_table(
        "quadro_board",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("owner_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("thumbnail_png", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_quadro_board_titulo", "quadro_board", ["titulo"])
    op.create_index("ix_quadro_board_visibility", "quadro_board", ["visibility"])
    op.create_index("ix_quadro_board_owner_user_id", "quadro_board", ["owner_user_id"])
    op.create_index("ix_quadro_owner_updated", "quadro_board", ["owner_user_id", "updated_at"])
    op.create_index("ix_quadro_visibility_updated", "quadro_board", ["visibility", "updated_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "quadro_board"):
        return

    op.drop_index("ix_quadro_visibility_updated", table_name="quadro_board")
    op.drop_index("ix_quadro_owner_updated", table_name="quadro_board")
    op.drop_index("ix_quadro_board_owner_user_id", table_name="quadro_board")
    op.drop_index("ix_quadro_board_visibility", table_name="quadro_board")
    op.drop_index("ix_quadro_board_titulo", table_name="quadro_board")
    op.drop_table("quadro_board")
