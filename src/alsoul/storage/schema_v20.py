from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v19 as _schema_v19


metadata = MetaData()
for _table in _schema_v19.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v19).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


progressive_presentation_session_frontier = Table(
    "progressive_presentation_session_frontier",
    metadata,
    Column(
        "presentation_session_id",
        Uuid(as_uuid=True),
        ForeignKey("progressive_presentation_session.presentation_session_id"),
        primary_key=True,
    ),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column("open_timeline_frontier", BigInteger, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "open_timeline_frontier >= 0",
        name="ck_progressive_session_frontier_f6a",
    ),
)


progressive_presentation_interruption = Table(
    "progressive_presentation_interruption",
    metadata,
    Column("interruption_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_session_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_key", String(128), nullable=False),
    Column("attempt_generation", Integer, nullable=False),
    Column("presentation_transport_fence_scope_id", Uuid(as_uuid=True), nullable=False),
    Column(
        "interrupting_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column("interrupting_timeline_seq", BigInteger, nullable=False),
    Column("interruption_key", String(128), nullable=False, unique=True),
    Column("cancellation_request_state", String(32), nullable=False),
    Column("interrupted_at", DateTime(timezone=True), nullable=False),
    Column("cancellation_requested_at", DateTime(timezone=True)),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id"],
        [
            "progressive_presentation_attempt.presentation_attempt_id",
            "progressive_presentation_attempt.presentation_session_id",
        ],
        name="fk_progressive_interruption_attempt_session_f6a",
    ),
    UniqueConstraint(
        "presentation_attempt_id",
        name="uq_progressive_interruption_attempt_f6a",
    ),
    CheckConstraint(
        "attempt_generation >= 1",
        name="ck_progressive_interruption_generation_f6a",
    ),
    CheckConstraint(
        "interrupting_timeline_seq >= 1",
        name="ck_progressive_interruption_timeline_f6a",
    ),
    CheckConstraint(
        "cancellation_request_state IN ('PENDING', 'REQUESTED', 'UNKNOWN', 'NOT_REQUIRED_TERMINAL')",
        name="ck_progressive_interruption_cancellation_state_f6a",
    ),
)


progressive_presentation_timeline_lineage = Table(
    "progressive_presentation_timeline_lineage",
    metadata,
    Column(
        "interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        primary_key=True,
    ),
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("companion_output.companion_output_id"),
        nullable=False,
    ),
    Column(
        "presentation_session_id",
        Uuid(as_uuid=True),
        ForeignKey("progressive_presentation_session.presentation_session_id"),
        nullable=False,
        unique=True,
    ),
    Column("terminal_presentation_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column(
        "terminal_status_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey(
            "progressive_presentation_status_evidence.presentation_status_evidence_id"
        ),
        nullable=False,
        unique=True,
    ),
    Column(
        "interrupting_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
    ),
    Column("first_presented_frame", Integer, nullable=False),
    Column("last_presented_frame", Integer, nullable=False),
    Column("frame_contract_version", String(128), nullable=False),
    Column("presented_content_digest", String(64), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["terminal_presentation_attempt_id", "presentation_session_id"],
        [
            "progressive_presentation_attempt.presentation_attempt_id",
            "progressive_presentation_attempt.presentation_session_id",
        ],
        name="fk_progressive_timeline_attempt_session_f6a",
    ),
    CheckConstraint(
        "first_presented_frame = 1",
        name="ck_progressive_timeline_first_frame_f6a",
    ),
    CheckConstraint(
        "last_presented_frame >= first_presented_frame",
        name="ck_progressive_timeline_last_frame_f6a",
    ),
)
