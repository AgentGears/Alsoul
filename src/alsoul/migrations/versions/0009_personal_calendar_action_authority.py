"""Add F5.B calendar-create Action and write-authority foundation.

Revision ID: 0009_personal_calendar_action_authority
Revises: 0008_personal_calendar_presentation
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v9
from alsoul.storage.schema_v8 import metadata as v8_metadata
from alsoul.storage.schema_v9 import metadata as v9_metadata

revision = "0009_personal_calendar_action_authority"
down_revision = "0008_personal_calendar_presentation"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v9_metadata.tables).difference(v8_metadata.tables)
_RECEIPT_SCOPES = (
    "SetCalendarCreatePolicy",
    "GrantCalendarCreatePermission",
    "ConsumeCalendarCreatePermissionGrantEvent",
    "SetCalendarCreatePermissionStatus",
    "PreparePersonalCalendarCreateAction",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v9_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v9.operation_receipt).where(
            schema_v9.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v9_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
