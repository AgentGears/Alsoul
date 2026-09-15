"""Add F5.B calendar-create confirmed Effect and SUPPORTS lineage.

Revision ID: 0013_personal_calendar_create_effect
Revises: 0012_personal_calendar_create_transport
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v13
from alsoul.storage.schema_v12 import metadata as v12_metadata
from alsoul.storage.schema_v13 import metadata as v13_metadata

revision = "0013_personal_calendar_create_effect"
down_revision = "0012_personal_calendar_create_transport"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v13_metadata.tables).difference(v12_metadata.tables)
_RECEIPT_SCOPES = ("AdmitPersonalCalendarCreateConfirmedEffect",)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v13_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v13.operation_receipt).where(
            schema_v13.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v13_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
