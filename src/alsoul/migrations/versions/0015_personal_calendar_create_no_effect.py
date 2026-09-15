"""Add F5.B terminal calendar-create no-effect proof and retry consumption.

Revision ID: 0015_personal_calendar_create_no_effect
Revises: 0014_personal_calendar_create_reconciliation
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v15
from alsoul.storage.schema_v14 import metadata as v14_metadata
from alsoul.storage.schema_v15 import metadata as v15_metadata

revision = "0015_personal_calendar_create_no_effect"
down_revision = "0014_personal_calendar_create_reconciliation"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v15_metadata.tables).difference(v14_metadata.tables)
_RECEIPT_SCOPES = (
    "ReconcilePersonalCalendarCreateNoEffect",
    "PreparePersonalCalendarCreateRetryAttempt",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v15_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v15.operation_receipt).where(
            schema_v15.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v15_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
