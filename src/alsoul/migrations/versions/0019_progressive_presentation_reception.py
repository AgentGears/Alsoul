"""Add F6.A reception and presentation-status evidence.

Revision ID: 0019_progressive_presentation_reception
Revises: 0018_progressive_presentation
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v19
from alsoul.storage.schema_v18 import metadata as v18_metadata
from alsoul.storage.schema_v19 import metadata as v19_metadata

revision = "0019_progressive_presentation_reception"
down_revision = "0018_progressive_presentation"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v19_metadata.tables).difference(v18_metadata.tables)
_RECEIPT_SCOPES = (
    "RecordProgressivePresentationReception",
    "ReconcileProgressivePresentationAttempt",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v19_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v19.operation_receipt).where(
            schema_v19.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v19_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
