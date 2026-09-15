"""Add F5.B first-party calendar mutation presentation truth.

Revision ID: 0017_personal_calendar_mutation_presentation
Revises: 0016_personal_calendar_mutation_completion
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v17
from alsoul.storage.schema_v16 import metadata as v16_metadata
from alsoul.storage.schema_v17 import metadata as v17_metadata

revision = "0017_personal_calendar_mutation_presentation"
down_revision = "0016_personal_calendar_mutation_completion"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v17_metadata.tables).difference(v16_metadata.tables)
_RECEIPT_SCOPES = (
    "PresentPersonalCalendarMutationOutput",
    "CommitPersonalCalendarMutationAcceptedPresentation",
    "BindPersonalCalendarMutationPresentedEventProvenance",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v17_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v17.operation_receipt).where(
            schema_v17.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v17_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
