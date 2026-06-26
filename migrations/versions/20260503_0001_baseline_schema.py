"""baseline schema from current SQLAlchemy metadata

Revision ID: 20260503_0001
Revises:
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base


revision = "20260503_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
