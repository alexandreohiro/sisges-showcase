"""add user operational profile fields

Revision ID: 20260522_0011
Revises: 20260522_0010
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0011"
down_revision = "20260522_0010"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(bind, column_name: str, column: sa.Column) -> None:
    if column_name not in _columns(bind, "users"):
        op.add_column("users", column)


def _create_index_if_missing(bind, index_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes("users")}
    if index_name not in existing:
        op.create_index(index_name, "users", columns)


def upgrade() -> None:
    bind = op.get_bind()
    _add_column_if_missing(bind, "identidade", sa.Column("identidade", sa.String(length=40), nullable=True))
    _add_column_if_missing(
        bind,
        "posto_graduacao",
        sa.Column("posto_graduacao", sa.String(length=80), nullable=True),
    )
    _add_column_if_missing(bind, "nome_guerra", sa.Column("nome_guerra", sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, "telefone", sa.Column("telefone", sa.String(length=40), nullable=True))
    _add_column_if_missing(bind, "contato", sa.Column("contato", sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, "divisao", sa.Column("divisao", sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, "secao", sa.Column("secao", sa.String(length=120), nullable=True))
    _create_index_if_missing(bind, "ix_users_identidade", ["identidade"])
    _create_index_if_missing(bind, "ix_users_divisao", ["divisao"])
    _create_index_if_missing(bind, "ix_users_secao", ["secao"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    for index_name in ("ix_users_secao", "ix_users_divisao", "ix_users_identidade"):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="users")

    existing_columns = _columns(bind, "users")
    for column_name in (
        "secao",
        "divisao",
        "contato",
        "telefone",
        "nome_guerra",
        "posto_graduacao",
        "identidade",
    ):
        if column_name in existing_columns:
            op.drop_column("users", column_name)
