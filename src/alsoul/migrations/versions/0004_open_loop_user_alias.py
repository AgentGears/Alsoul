"""Add counterpart-authored F4 ConversationOpenLoop aliases.

Revision ID: 0004_open_loop_user_alias
Revises: 0003_open_loop_reference
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_open_loop_user_alias"
down_revision = "0003_open_loop_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_open_loop_alias",
        sa.Column("open_loop_alias_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
            nullable=False,
        ),
        sa.Column("alias_kind", sa.String(64), nullable=False),
        sa.Column("alias_contract_version", sa.String(64), nullable=False),
        sa.Column("display_label", sa.String(240), nullable=False),
        sa.Column("canonical_alias_key", sa.String(512), nullable=False),
        sa.Column(
            "source_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("interaction_event.event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "alias_kind IN ('USER_LABEL')",
            name="ck_conversation_open_loop_alias_kind_f4",
        ),
        sa.CheckConstraint(
            "alias_contract_version IN ('USER_LABEL_V1')",
            name="ck_conversation_open_loop_alias_contract_f4",
        ),
    )
    op.create_index(
        "ix_conversation_open_loop_alias_lookup",
        "conversation_open_loop_alias",
        ["alias_kind", "alias_contract_version", "canonical_alias_key"],
    )

    op.create_table(
        "conversation_open_loop_alias_retirement",
        sa.Column("alias_retirement_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "open_loop_alias_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("retirement_kind", sa.String(32), nullable=False),
        sa.Column(
            "source_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("interaction_event.event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "replacement_alias_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "retirement_kind IN ('REMOVED', 'RENAMED')",
            name="ck_conversation_open_loop_alias_retirement_kind_f4",
        ),
        sa.CheckConstraint(
            "((retirement_kind = 'REMOVED' AND replacement_alias_id IS NULL) "
            "OR (retirement_kind = 'RENAMED' AND replacement_alias_id IS NOT NULL))",
            name="ck_conversation_open_loop_alias_retirement_shape_f4",
        ),
    )

    op.create_table(
        "context_projection_open_loop_alias_selector",
        sa.Column(
            "projection_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("context_projection.projection_id"),
            primary_key=True,
        ),
        sa.Column(
            "open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
            nullable=False,
        ),
        sa.Column(
            "open_loop_alias_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
            nullable=False,
        ),
        sa.Column("selection_basis", sa.String(64), nullable=False),
        sa.Column("selector_contract_version", sa.String(64), nullable=False),
        sa.Column("selector_key", sa.String(512), nullable=False),
        sa.CheckConstraint(
            "selection_basis IN ('EXPLICIT_USER_ALIAS')",
            name="ck_projection_open_loop_alias_selector_basis_f4",
        ),
        sa.CheckConstraint(
            "selector_contract_version IN ('USER_LABEL_V1')",
            name="ck_projection_open_loop_alias_selector_contract_f4",
        ),
        sa.UniqueConstraint(
            "projection_id",
            "open_loop_alias_id",
            name="uq_projection_open_loop_alias_selector",
        ),
    )

    # Deliberately no alias backfill. Earlier schema versions contain no canonical
    # counterpart-authored alias-assignment contract from which USER_LABEL_V1 could
    # be reconstructed without inventing semantic state.


def downgrade() -> None:
    op.drop_table("context_projection_open_loop_alias_selector")
    op.drop_table("conversation_open_loop_alias_retirement")
    op.drop_index(
        "ix_conversation_open_loop_alias_lookup",
        table_name="conversation_open_loop_alias",
    )
    op.drop_table("conversation_open_loop_alias")
