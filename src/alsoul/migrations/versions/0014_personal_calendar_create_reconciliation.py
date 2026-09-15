"""Add F5.B calendar-create read-side reconciliation probes.

Revision ID: 0014_personal_calendar_create_reconciliation
Revises: 0013_personal_calendar_create_effect
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v14
from alsoul.storage.schema_v13 import metadata as v13_metadata
from alsoul.storage.schema_v14 import metadata as v14_metadata

revision = "0014_personal_calendar_create_reconciliation"
down_revision = "0013_personal_calendar_create_effect"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v14_metadata.tables).difference(v13_metadata.tables)
_RECEIPT_SCOPES = ("ReconcilePersonalCalendarCreateUnknownEffect",)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v14_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v14.operation_receipt).where(
            schema_v14.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v14_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
