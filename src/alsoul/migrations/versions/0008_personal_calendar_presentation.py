"""Add F5.A personal-calendar first-presentation authority and reconciliation.

Revision ID: 0008_personal_calendar_presentation
Revises: 0007_personal_calendar_cognition
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v8
from alsoul.storage.schema_v7 import metadata as v7_metadata
from alsoul.storage.schema_v8 import metadata as v8_metadata

revision = "0008_personal_calendar_presentation"
down_revision = "0007_personal_calendar_cognition"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v8_metadata.tables).difference(v7_metadata.tables)
_RECEIPT_SCOPES = (
    "SetPersonalCalendarDisclosurePolicy",
    "PresentPersonalCalendarOutput",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v8_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v8.operation_receipt).where(
            schema_v8.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v8_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
