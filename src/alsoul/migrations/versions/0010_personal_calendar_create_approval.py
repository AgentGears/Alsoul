"""Add F5.B faithful approval presentation and exact Action Approval.

Revision ID: 0010_personal_calendar_create_approval
Revises: 0009_personal_calendar_action_authority
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v10
from alsoul.storage.schema_v9 import metadata as v9_metadata
from alsoul.storage.schema_v10 import metadata as v10_metadata

revision = "0010_personal_calendar_create_approval"
down_revision = "0009_personal_calendar_action_authority"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v10_metadata.tables).difference(v9_metadata.tables)
_RECEIPT_SCOPES = (
    "PresentPersonalCalendarCreateApproval",
    "AdmitPersonalCalendarCreateApproval",
    "RevokePersonalCalendarCreateApproval",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v10_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v10.operation_receipt).where(
            schema_v10.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v10_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
