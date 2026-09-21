"""Add F6.A canonical interruption and Timeline presentation lineage.

Revision ID: 0020_progressive_presentation_interruption_history
Revises: 0019_progressive_presentation_reception
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete

from alsoul.storage import schema_v20
from alsoul.storage.schema_v19 import metadata as v19_metadata
from alsoul.storage.schema_v20 import metadata as v20_metadata

revision = "0020_progressive_presentation_interruption_history"
down_revision = "0019_progressive_presentation_reception"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v20_metadata.tables).difference(v19_metadata.tables)
_RECEIPT_SCOPES = (
    "InterruptProgressivePresentationAttempt",
    "CommitProgressivePresentationHistory",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v20_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        delete(schema_v20.operation_receipt).where(
            schema_v20.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )
    for table in reversed(v20_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
