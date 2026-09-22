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

from . import schema_v20 as _schema_v20


metadata = MetaData()
for _table in _schema_v20.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v20).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


progressive_personal_calendar_frame_authority = Table(
    "progressive_personal_calendar_frame_authority",
    metadata,
    Column("presentation_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column("presentation_session_id", Uuid(as_uuid=True), primary_key=True),
    Column("frame_ordinal", Integer, primary_key=True),
    Column("attempt_generation", Integer, nullable=False),
    Column(
        "presentation_transport_fence_scope_id",
        Uuid(as_uuid=True),
        nullable=False,
    ),
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_companion_output.companion_output_id"),
        nullable=False,
    ),
    Column("permission_id", Uuid(as_uuid=True), nullable=False),
    Column(
        "freshness_decision_id",
        Uuid(as_uuid=True),
        ForeignKey(
            "personal_calendar_presentation_freshness_decision.freshness_decision_id"
        ),
        nullable=False,
    ),
    Column(
        "disclosure_decision_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_disclosure_decision.disclosure_decision_id"),
        nullable=False,
    ),
    Column("frame_digest", String(64), nullable=False),
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
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["presentation_attempt_id", "presentation_session_id", "frame_ordinal"],
        [
            "progressive_presentation_frame_transport.presentation_attempt_id",
            "progressive_presentation_frame_transport.presentation_session_id",
            "progressive_presentation_frame_transport.frame_ordinal",
        ],
        name="fk_progressive_calendar_authority_transport_f6a",
    ),
    UniqueConstraint(
        "freshness_decision_id",
        name="uq_progressive_calendar_authority_freshness_f6a",
    ),
    UniqueConstraint(
        "disclosure_decision_id",
        name="uq_progressive_calendar_authority_disclosure_f6a",
    ),
    CheckConstraint(
        "frame_ordinal >= 1",
        name="ck_progressive_calendar_authority_frame_f6a",
    ),
    CheckConstraint(
        "attempt_generation >= 1",
        name="ck_progressive_calendar_authority_generation_f6a",
    ),
)
