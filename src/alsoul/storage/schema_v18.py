from __future__ import annotations

from sqlalchemy import (
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

from . import schema_v17 as _schema_v17


metadata = MetaData()
for _table in _schema_v17.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v17).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


progressive_presentation_session = Table(
    "progressive_presentation_session",
    metadata,
    Column("presentation_session_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("companion_output.companion_output_id"),
        nullable=False,
    ),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column(
        "surface_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("surface_binding.surface_binding_id"),
        nullable=False,
    ),
    Column(
        "channel_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("channel_binding.channel_binding_id"),
        nullable=False,
    ),
    Column("presentation_key", String(128), nullable=False, unique=True),
    Column("presentation_contract_version", String(128), nullable=False),
    Column("frame_contract_version", String(128), nullable=False),
    Column("source_content_digest", String(64), nullable=False),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "companion_output_id",
        "surface_binding_id",
        "channel_binding_id",
        "presentation_contract_version",
        name="uq_progressive_presentation_semantic_target_f6a",
    ),
)


progressive_presentation_frame = Table(
    "progressive_presentation_frame",
    metadata,
    Column(
        "presentation_session_id",
        Uuid(as_uuid=True),
        ForeignKey("progressive_presentation_session.presentation_session_id"),
        primary_key=True,
    ),
    Column("frame_ordinal", Integer, primary_key=True),
    Column("source_start", Integer, nullable=False),
    Column("source_end", Integer, nullable=False),
    Column("content_text", String, nullable=False),
    Column("content_digest", String(64), nullable=False),
    CheckConstraint("frame_ordinal >= 1", name="ck_progressive_frame_ordinal_f6a"),
    CheckConstraint("source_start >= 0", name="ck_progressive_frame_start_f6a"),
    CheckConstraint("source_end >= source_start", name="ck_progressive_frame_range_f6a"),
)


progressive_presentation_attempt = Table(
    "progressive_presentation_attempt",
    metadata,
    Column("presentation_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "presentation_session_id",
        Uuid(as_uuid=True),
        ForeignKey("progressive_presentation_session.presentation_session_id"),
        nullable=False,
    ),
    Column("attempt_generation", Integer, nullable=False),
    Column(
        "presentation_transport_fence_scope_id",
        Uuid(as_uuid=True),
        nullable=False,
        unique=True,
    ),
    Column("attempt_state", String(32), nullable=False),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "presentation_session_id",
        "attempt_generation",
        name="uq_progressive_presentation_attempt_generation_f6a",
    ),
    UniqueConstraint(
        "presentation_attempt_id",
        "presentation_session_id",
        name="uq_progressive_presentation_attempt_session_f6a",
    ),
    CheckConstraint("attempt_generation >= 1", name="ck_progressive_attempt_generation_f6a"),
    CheckConstraint(
        "attempt_state IN ('OPEN', 'SETTLED', 'UNKNOWN')",
        name="ck_progressive_attempt_state_f6a",
    ),
)


progressive_presentation_frame_transport = Table(
    "progressive_presentation_frame_transport",
    metadata,
    Column("presentation_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_session_id", Uuid(as_uuid=True), primary_key=True),
    Column("frame_ordinal", Integer, primary_key=True),
    Column("frame_digest", String(64), nullable=False),
    Column("sink_acceptance_state", String(32), nullable=False),
    Column("acceptance_ref", String(256)),
    Column("dispatched_at", DateTime(timezone=True), nullable=False),
    Column("accepted_at", DateTime(timezone=True)),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id"],
        [
            "progressive_presentation_attempt.presentation_attempt_id",
            "progressive_presentation_attempt.presentation_session_id",
        ],
        name="fk_progressive_transport_attempt_session_f6a",
    ),
    ForeignKeyConstraint(
        ["presentation_session_id", "frame_ordinal"],
        [
            "progressive_presentation_frame.presentation_session_id",
            "progressive_presentation_frame.frame_ordinal",
        ],
        name="fk_progressive_transport_frame_f6a",
    ),
    CheckConstraint(
        "sink_acceptance_state IN ('UNKNOWN', 'ACCEPTED', 'NOT_ACCEPTED')",
        name="ck_progressive_transport_acceptance_f6a",
    ),
)


progressive_presentation_frame_evidence = Table(
    "progressive_presentation_frame_evidence",
    metadata,
    Column("presentation_evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_session_id", Uuid(as_uuid=True), nullable=False),
    Column("frame_ordinal", Integer, nullable=False),
    Column("presentation_key", String(128), nullable=False),
    Column("frame_digest", String(64), nullable=False),
    Column("presentation_receipt_ref", String(256), nullable=False),
    Column("presentation_receipt_contract_version", String(128), nullable=False),
    Column("presented_at", DateTime(timezone=True), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id", "frame_ordinal"],
        [
            "progressive_presentation_frame_transport.presentation_attempt_id",
            "progressive_presentation_frame_transport.presentation_session_id",
            "progressive_presentation_frame_transport.frame_ordinal",
        ],
        name="fk_progressive_evidence_transport_f6a",
    ),
    UniqueConstraint(
        "presentation_session_id",
        "frame_ordinal",
        name="uq_progressive_presented_frame_f6a",
    ),
    UniqueConstraint(
        "presentation_key",
        "presentation_receipt_ref",
        name="uq_progressive_presentation_receipt_f6a",
    ),
)
