"""Add F5.B calendar-create mutation transport and minimized effect evidence.

Revision ID: 0012_personal_calendar_create_transport
Revises: 0011_personal_calendar_create_execution
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v12
from alsoul.storage.schema_v11 import metadata as v11_metadata
from alsoul.storage.schema_v12 import metadata as v12_metadata

revision = "0012_personal_calendar_create_transport"
down_revision = "0011_personal_calendar_create_execution"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v12_metadata.tables).difference(v11_metadata.tables)
_RECEIPT_SCOPES = ("DispatchPersonalCalendarCreateMutation",)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v12_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v12.operation_receipt).where(
            schema_v12.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v12_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
