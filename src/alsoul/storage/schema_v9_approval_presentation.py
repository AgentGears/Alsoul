from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, MetaData, String, Table, Text, Uuid
from . import schema_v9_action as _base

metadata = MetaData()
for _t in _base.metadata.sorted_tables:
    _t.to_metadata(metadata)
for _n, _v in vars(_base).items():
    if isinstance(_v, Table):
        globals()[_n] = metadata.tables[_v.name]

personal_calendar_approval_presentation = Table(
    "personal_calendar_approval_presentation", metadata,
    Column("approval_presentation_id", Uuid(as_uuid=True), primary_key=True),
    Column("action_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_action.action_id"), nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("effect_class", String(32), nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), ForeignKey("personal_resource_binding.personal_resource_binding_id"), nullable=False),
    Column("target_calendar_display_identity", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("start_timestamp_text", String(64), nullable=False),
    Column("end_timestamp_text", String(64), nullable=False),
    Column("normalized_start_at", DateTime(timezone=True), nullable=False),
    Column("normalized_end_at", DateTime(timezone=True), nullable=False),
    Column("consent_rendering_version", String(128), nullable=False),
    Column("consent_payload_digest", String(64), nullable=False),
    Column("presented_to_counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("surface_binding_id", Uuid(as_uuid=True), ForeignKey("surface_binding.surface_binding_id"), nullable=False),
    Column("channel_binding_id", Uuid(as_uuid=True), ForeignKey("channel_binding.channel_binding_id"), nullable=False),
    Column("source_timeline_frontier", BigInteger, nullable=False),
    Column("presented_at", DateTime(timezone=True), nullable=False),
    Column("presentation_acceptance_ref", String(128), nullable=False, unique=True),
    CheckConstraint("capability_semantic_operation = 'calendar.event.create' AND effect_class = 'WRITE'", name="ck_approval_presentation_f5b"),
)
