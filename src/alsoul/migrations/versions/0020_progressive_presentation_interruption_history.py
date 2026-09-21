"""Add F6.A canonical interruption and Timeline presentation lineage.

Revision ID: 0020_progressive_presentation_interruption_history
Revises: 0019_progressive_presentation_reception
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import delete, insert, select

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

    # Pre-v20 sessions did not persist their session-open Timeline frontier. Backfill a
    # conservative current frontier: this may reject an older would-be interrupt after
    # upgrade, but it can never promote pre-session input into a false interruption.
    existing = bind.execute(
        select(
            schema_v20.progressive_presentation_session.c.presentation_session_id,
            schema_v20.progressive_presentation_session.c.relationship_id,
            schema_v20.relationship_timeline_head.c.last_timeline_seq,
        ).join(
            schema_v20.relationship_timeline_head,
            schema_v20.relationship_timeline_head.c.relationship_id
            == schema_v20.progressive_presentation_session.c.relationship_id,
        )
    ).mappings().all()
    migrated_at = datetime.now(timezone.utc)
    for row in existing:
        bind.execute(
            insert(schema_v20.progressive_presentation_session_frontier).values(
                presentation_session_id=row["presentation_session_id"],
                relationship_id=row["relationship_id"],
                open_timeline_frontier=int(row["last_timeline_seq"]),
                recorded_at=migrated_at,
            )
        )


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
