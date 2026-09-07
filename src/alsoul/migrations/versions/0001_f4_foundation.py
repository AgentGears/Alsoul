"""Create the frozen F4 foundation schema.

Revision ID: 0001_f4_foundation
Revises: None
"""
from __future__ import annotations

from alembic import op

from alsoul.storage.schema_v1 import metadata as f4_v1_metadata

revision = "0001_f4_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    f4_v1_metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    f4_v1_metadata.drop_all(bind=op.get_bind(), checkfirst=False)
