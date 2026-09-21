from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v18 as _schema_v18


metadata = MetaData()
for _table in _schema_v18.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v18).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


progressive_presentation_reception_evidence = Table(
    "progressive_presentation_reception_evidence",
    metadata,
    Column("reception_evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_session_id", Uuid(as_uuid=True), nullable=False),
    Column("attempt_generation", Integer, nullable=False),
    Column("presentation_transport_fence_scope_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_key", String(128), nullable=False),
    Column("received_through_frame", Integer, nullable=False),
    Column("reception_kind", String(64), nullable=False),
    Column("reception_receipt_ref", String(256), nullable=False),
    Column("reception_contract_version", String(128), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id"],
        [
            "progressive_presentation_attempt.presentation_attempt_id",
            "progressive_presentation_attempt.presentation_session_id",
        ],
        name="fk_progressive_reception_attempt_session_f6a",
    ),
    ForeignKeyConstraint(
        ["presentation_session_id", "received_through_frame"],
        [
            "progressive_presentation_frame.presentation_session_id",
            "progressive_presentation_frame.frame_ordinal",
        ],
        name="fk_progressive_reception_frame_extent_f6a",
    ),
    UniqueConstraint(
        "presentation_key",
        "reception_receipt_ref",
        name="uq_progressive_reception_receipt_f6a",
    ),
    CheckConstraint(
        "received_through_frame >= 1",
        name="ck_progressive_reception_frame_f6a",
    ),
    CheckConstraint(
        "attempt_generation >= 1",
        name="ck_progressive_reception_generation_f6a",
    ),
    CheckConstraint(
        "reception_kind = 'PLAYBACK_CONFIRMED_THROUGH_FRAME'",
        name="ck_progressive_reception_kind_f6a",
    ),
)


progressive_presentation_status_evidence = Table(
    "progressive_presentation_status_evidence",
    metadata,
    Column("presentation_status_evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_session_id", Uuid(as_uuid=True), nullable=False),
    Column("attempt_generation", Integer, nullable=False),
    Column("presentation_transport_fence_scope_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_key", String(128), nullable=False),
    Column("settlement_state", String(64), nullable=False),
    Column("status_ref", String(256), nullable=False),
    Column("last_authoritatively_presented_frame", Integer, nullable=False),
    Column("last_authoritatively_received_frame", Integer, nullable=False),
    Column("settled_through_ref", String(256)),
    Column("status_contract_version", String(128), nullable=False),
    Column("settled_at", DateTime(timezone=True)),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id"],
        [
            "progressive_presentation_attempt.presentation_attempt_id",
            "progressive_presentation_attempt.presentation_session_id",
        ],
        name="fk_progressive_status_attempt_session_f6a",
    ),
    UniqueConstraint(
        "presentation_key",
        "status_ref",
        name="uq_progressive_status_ref_f6a",
    ),
    CheckConstraint(
        "attempt_generation >= 1",
        name="ck_progressive_status_generation_f6a",
    ),
    CheckConstraint(
        "last_authoritatively_presented_frame >= 0",
        name="ck_progressive_status_presented_frame_f6a",
    ),
    CheckConstraint(
        "last_authoritatively_received_frame >= 0",
        name="ck_progressive_status_received_frame_f6a",
    ),
    CheckConstraint(
        "last_authoritatively_received_frame <= last_authoritatively_presented_frame",
        name="ck_progressive_status_received_le_presented_f6a",
    ),
    CheckConstraint(
        "settlement_state IN ('TERMINAL', 'UNKNOWN_PRESENTATION_EXTENT')",
        name="ck_progressive_status_state_f6a",
    ),
    CheckConstraint(
        "(settlement_state = 'TERMINAL' AND settled_through_ref IS NOT NULL AND settled_at IS NOT NULL) OR "
        "(settlement_state = 'UNKNOWN_PRESENTATION_EXTENT' AND settled_through_ref IS NULL AND settled_at IS NULL)",
        name="ck_progressive_status_terminal_proof_f6a",
    ),
)
