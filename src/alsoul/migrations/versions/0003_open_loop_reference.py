"""Add targetable F4 ConversationOpenLoop references.

Revision ID: 0003_open_loop_reference
Revises: 0002_conversation_open_loop
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0003_open_loop_reference"
down_revision = "0002_conversation_open_loop"
branch_labels = None
depends_on = None

_REFERENCE_NAMESPACE = UUID("7c7f3c6d-58a8-4b4e-b13b-13d5bf56663c")
_DECISION_OPEN = re.compile(
    r"^\s*i\s+need\s+to\s+decide\s+between\s+"
    r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
    r"(?P<option_b>[^\n.]{1,120}?)\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)


def _normalize_option(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.strip().split())
    return normalized.casefold()


def _reference_key(option_a: str, option_b: str) -> str:
    return json.dumps(
        sorted((_normalize_option(option_a), _normalize_option(option_b))),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def upgrade() -> None:
    op.create_table(
        "conversation_open_loop_reference",
        sa.Column("open_loop_reference_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "open_loop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop.open_loop_id"),
            nullable=False,
        ),
        sa.Column("reference_kind", sa.String(64), nullable=False),
        sa.Column("reference_contract_version", sa.String(64), nullable=False),
        sa.Column("canonical_reference_key", sa.String(512), nullable=False),
        sa.Column(
            "source_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("interaction_event.event_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reference_kind IN ('DECISION_OPTION_PAIR')",
            name="ck_conversation_open_loop_reference_kind_f4",
        ),
        sa.CheckConstraint(
            "reference_contract_version IN ('DECISION_OPTION_PAIR_V1')",
            name="ck_conversation_open_loop_reference_contract_f4",
        ),
        sa.UniqueConstraint(
            "open_loop_id",
            "reference_kind",
            "reference_contract_version",
            name="uq_conversation_open_loop_reference_contract",
        ),
    )
    op.create_index(
        "ix_conversation_open_loop_reference_lookup",
        "conversation_open_loop_reference",
        ["reference_kind", "reference_contract_version", "canonical_reference_key"],
    )

    op.create_table(
        "context_projection_open_loop_selector",
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
            "open_loop_reference_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_open_loop_reference.open_loop_reference_id"),
        ),
        sa.Column("selection_basis", sa.String(64), nullable=False),
        sa.Column("selector_contract_version", sa.String(64)),
        sa.Column("selector_key", sa.String(512)),
        sa.CheckConstraint(
            "selection_basis IN ('CURRENT_OPEN_DECISION_LOOP', 'EXPLICIT_DECISION_REFERENCE')",
            name="ck_projection_open_loop_selector_basis_f4",
        ),
        sa.CheckConstraint(
            "((selection_basis = 'CURRENT_OPEN_DECISION_LOOP' "
            "AND open_loop_reference_id IS NULL "
            "AND selector_contract_version IS NULL "
            "AND selector_key IS NULL) "
            "OR (selection_basis = 'EXPLICIT_DECISION_REFERENCE' "
            "AND open_loop_reference_id IS NOT NULL "
            "AND selector_contract_version IS NOT NULL "
            "AND selector_key IS NOT NULL))",
            name="ck_projection_open_loop_selector_shape_f4",
        ),
    )

    # Backfill only references that are mechanically reconstructable from canonical
    # v2 opening sources under the exact grammar that admitted those decision loops.
    # No model or semantic similarity participates in this migration.
    bind = op.get_bind()
    metadata = sa.MetaData()
    loop = sa.Table("conversation_open_loop", metadata, autoload_with=bind)
    event = sa.Table("interaction_event", metadata, autoload_with=bind)
    relationship = sa.Table("relationship_identity", metadata, autoload_with=bind)
    reference = sa.Table("conversation_open_loop_reference", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            loop.c.open_loop_id,
            loop.c.relationship_id,
            loop.c.opened_by_event_id,
            loop.c.opened_at,
            event.c.content_text,
            event.c.event_kind,
            event.c.actor_kind,
            event.c.actor_ref,
            event.c.relationship_id.label("event_relationship_id"),
            relationship.c.counterpart_id,
        )
        .join(event, event.c.event_id == loop.c.opened_by_event_id)
        .join(
            relationship,
            relationship.c.relationship_id == loop.c.relationship_id,
        )
        .where(loop.c.loop_kind == "DECISION")
    ).mappings().all()

    backfilled_at = datetime.now(timezone.utc)
    for row in rows:
        if (
            row["event_kind"] != "COUNTERPART_INPUT"
            or row["actor_kind"] != "COUNTERPART"
            or row["actor_ref"] != row["counterpart_id"]
            or row["event_relationship_id"] != row["relationship_id"]
        ):
            continue
        match = _DECISION_OPEN.fullmatch(row["content_text"])
        if match is None:
            continue
        open_loop_reference_id = uuid5(
            _REFERENCE_NAMESPACE,
            f"{row['open_loop_id']}|DECISION_OPTION_PAIR_V1",
        )
        bind.execute(
            reference.insert().values(
                open_loop_reference_id=open_loop_reference_id,
                open_loop_id=row["open_loop_id"],
                reference_kind="DECISION_OPTION_PAIR",
                reference_contract_version="DECISION_OPTION_PAIR_V1",
                canonical_reference_key=_reference_key(
                    match.group("option_a"), match.group("option_b")
                ),
                source_event_id=row["opened_by_event_id"],
                created_at=backfilled_at,
            )
        )


def downgrade() -> None:
    op.drop_table("context_projection_open_loop_selector")
    op.drop_index(
        "ix_conversation_open_loop_reference_lookup",
        table_name="conversation_open_loop_reference",
    )
    op.drop_table("conversation_open_loop_reference")
