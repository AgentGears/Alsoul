"""Add the first F5.A personal-calendar authority foundation.

Revision ID: 0005_personal_calendar_authority
Revises: 0004_open_loop_user_alias
"""
from __future__ import annotations

from alembic import op

from alsoul.storage.schema_v4 import metadata as v4_metadata
from alsoul.storage.schema_v5 import metadata as v5_metadata

revision = "0005_personal_calendar_authority"
down_revision = "0004_open_loop_user_alias"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v5_metadata.tables).difference(v4_metadata.tables)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v5_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(v5_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
