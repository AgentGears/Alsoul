"""Add F5.B mechanically constrained calendar mutation completion cognition.

Revision ID: 0016_personal_calendar_mutation_completion
Revises: 0015_personal_calendar_create_no_effect
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v16
from alsoul.storage.schema_v15 import metadata as v15_metadata
from alsoul.storage.schema_v16 import metadata as v16_metadata

revision = "0016_personal_calendar_mutation_completion"
down_revision = "0015_personal_calendar_create_no_effect"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v16_metadata.tables).difference(v15_metadata.tables)
_RECEIPT_SCOPES = (
    "BuildPersonalCalendarMutationCompletionProjection",
    "GeneratePersonalCalendarMutationResultPlan",
    "AdoptPersonalCalendarMutationOutput",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v16_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v16.operation_receipt).where(
            schema_v16.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v16_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
