"""Add F6.A per-frame inherited personal-calendar authority evidence.

Revision ID: 0021_progressive_personal_calendar_authority
Revises: 0020_progressive_presentation_interruption_history
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete, select

from alsoul.storage import schema_v21
from alsoul.storage.schema_v20 import metadata as v20_metadata
from alsoul.storage.schema_v21 import metadata as v21_metadata


revision = "0021_progressive_personal_calendar_authority"
down_revision = "0020_progressive_presentation_interruption_history"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v21_metadata.tables).difference(v20_metadata.tables)
_RECEIPT_SCOPE = "DispatchPersonalCalendarProgressiveFrame"


def upgrade() -> None:
    bind = op.get_bind()
    for table in v21_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()

    # A v20 store cannot represent which exact F5 freshness/disclosure decision
    # authorized an already-fenced personal-data frame. Dropping that evidence would
    # leave a payload-bearing transport that looks generically authorized, so refuse
    # the destructive downgrade whenever such evidence exists.
    authority = bind.execute(
        select(
            schema_v21.progressive_personal_calendar_frame_authority.c.presentation_attempt_id
        ).limit(1)
    ).first()
    if authority is not None:
        raise RuntimeError(
            "cannot downgrade F6.A personal-calendar frame authority while "
            "payload-transport authority evidence exists"
        )

    bind.execute(
        delete(schema_v21.operation_receipt).where(
            schema_v21.operation_receipt.c.operation_scope == _RECEIPT_SCOPE
        )
    )
    for table in reversed(v21_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
