"""Add durable F4 ConversationOpenLoop persistence.

Revision ID: 0002_conversation_open_loop
Revises: 0001_f4_foundation
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_conversation_open_loop"
down_revision = "0001_f4_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep this migration self-contained. Importing the current schema here would
    # mutate the metadata object intentionally frozen into migration 0001 before
    # 0001 executes on a fresh database.
    op.create_table(
        "conversation_open_loop",
        sa.Column("open_loop_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("relationship_identity.relationship_id"),
            nullable=False,
        ),
        sa.Column("loop_kind", sa.String(64), nullable=False),
        sa.Column(
            "opened_by_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("interaction_event.event_id"),
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "loop_kind IN ('DECISION')",
            name="ck_conversation_open_loop_kind_f4",
        ),
        sa.UniqueConstraint(
            "opened_by_event_id",
            name="uq_conversation_open_loop_opened_by_event",
        ),
    )
    op.create_index(
        "ix_conversation_open_loop_relationship_kind",
        "conversation_open_loop",
        ["relationship_id", "loop_kind", "opened_at"],
    )

    op.create_table(
        "conversation_open_loop_closure",
        sa.Column(
            "open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
            primary_key=True,
        ),
        sa.Column("closure_kind", sa.String(32), nullable=False),
        sa.Column(
            "source_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("interaction_event.event_id"),
        ),
        sa.Column(
            "superseding_open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "closure_kind IN ('RESOLVED', 'CANCELLED', 'SUPERSEDED', 'EXPIRED')",
            name="ck_conversation_open_loop_closure_kind_f4",
        ),
        sa.CheckConstraint(
            "((closure_kind = 'SUPERSEDED' AND superseding_open_loop_id IS NOT NULL) "
            "OR (closure_kind <> 'SUPERSEDED' AND superseding_open_loop_id IS NULL))",
            name="ck_conversation_open_loop_supersession_ref_f4",
        ),
        sa.UniqueConstraint(
            "source_event_id",
            name="uq_conversation_open_loop_closure_source_event",
        ),
    )

    op.create_table(
        "context_projection_open_loop_item",
        sa.Column(
            "projection_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("context_projection.projection_id"),
            primary_key=True,
        ),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column(
            "open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
            nullable=False,
        ),
        sa.Column("selection_basis", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "projection_id",
            "open_loop_id",
            name="uq_projection_open_loop",
        ),
        sa.CheckConstraint(
            "selection_basis IN ('CURRENT_OPEN_DECISION_LOOP')",
            name="ck_projection_open_loop_basis_f4",
        ),
    )


def downgrade() -> None:
    op.drop_table("context_projection_open_loop_item")
    op.drop_table("conversation_open_loop_closure")
    op.drop_index(
        "ix_conversation_open_loop_relationship_kind",
        table_name="conversation_open_loop",
    )
    op.drop_table("conversation_open_loop")
