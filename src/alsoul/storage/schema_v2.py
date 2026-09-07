from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Uuid,
)

from .schema_v1 import *  # noqa: F401,F403


conversation_open_loop = Table(
    "conversation_open_loop",
    metadata,
    Column("open_loop_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column("loop_kind", String(64), nullable=False),
    Column(
        "opened_by_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
        unique=True,
    ),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("loop_kind IN ('DECISION')", name="ck_conversation_open_loop_kind_f4"),
)

conversation_open_loop_closure = Table(
    "conversation_open_loop_closure",
    metadata,
    Column(
        "open_loop_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop.open_loop_id"),
        primary_key=True,
    ),
    Column("closure_kind", String(32), nullable=False),
    Column(
        "source_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
    ),
    Column(
        "superseding_open_loop_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop.open_loop_id"),
    ),
    Column("closed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "closure_kind IN ('RESOLVED', 'CANCELLED', 'SUPERSEDED', 'EXPIRED')",
        name="ck_conversation_open_loop_closure_kind_f4",
    ),
    CheckConstraint(
        "((closure_kind = 'SUPERSEDED' AND superseding_open_loop_id IS NOT NULL) "
        "OR (closure_kind <> 'SUPERSEDED' AND superseding_open_loop_id IS NULL))",
        name="ck_conversation_open_loop_supersession_ref_f4",
    ),
)

Index(
    "ix_conversation_open_loop_relationship_kind",
    conversation_open_loop.c.relationship_id,
    conversation_open_loop.c.loop_kind,
    conversation_open_loop.c.opened_at,
)
