"""Add F5.B calendar-create ExecutionAttempt serialization and dispatch fence.

Revision ID: 0011_personal_calendar_create_execution
Revises: 0010_personal_calendar_create_approval
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v11
from alsoul.storage.schema_v10 import metadata as v10_metadata
from alsoul.storage.schema_v11 import metadata as v11_metadata

revision = "0011_personal_calendar_create_execution"
down_revision = "0010_personal_calendar_create_approval"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v11_metadata.tables).difference(v10_metadata.tables)
_RECEIPT_SCOPES = (
    "PreparePersonalCalendarCreateExecutionAttempt",
    "FencePersonalCalendarCreateExecutionAttempt",
    "AbandonPersonalCalendarCreateExecutionAttempt",
    "RecoverPersonalCalendarCreateFencedAttempt",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v11_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v11.operation_receipt).where(
            schema_v11.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v11_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
