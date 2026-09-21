"""Add F6.A progressive presentation persistence.

Revision ID: 0018_progressive_presentation
Revises: 0017_personal_calendar_mutation_presentation
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v18
from alsoul.storage.schema_v17 import metadata as v17_metadata
from alsoul.storage.schema_v18 import metadata as v18_metadata

revision = "0018_progressive_presentation"
down_revision = "0017_personal_calendar_mutation_presentation"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v18_metadata.tables).difference(v17_metadata.tables)
_RECEIPT_SCOPES = (
    "OpenProgressivePresentation",
    "FenceProgressivePresentationAttempt",
    "DispatchProgressivePresentationFrame",
    "RecordProgressivePresentationReceipt",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v18_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v18.operation_receipt).where(
            schema_v18.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v18_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
