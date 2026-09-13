from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, MetaData, String, Table, Text, Uuid
from . import schema_v9_authority as _base

metadata = MetaData()
for _t in _base.metadata.sorted_tables:
    _t.to_metadata(metadata)
for _n, _v in vars(_base).items():
    if isinstance(_v, Table):
        globals()[_n] = metadata.tables[_v.name]

personal_calendar_action = Table(
    "personal_calendar_action", metadata,
    Column("action_id", Uuid(as_uuid=True), primary_key=True),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), ForeignKey("personal_resource_binding.personal_resource_binding_id"), nullable=False),
    Column("source_interaction_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id"), nullable=False, unique=True),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("effect_class", String(32), nullable=False),
    Column("title", Text, nullable=False),
    Column("start_timestamp_text", String(64), nullable=False),
    Column("end_timestamp_text", String(64), nullable=False),
    Column("normalized_start_at", DateTime(timezone=True), nullable=False),
    Column("normalized_end_at", DateTime(timezone=True), nullable=False),
    Column("action_digest", String(64), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("capability_semantic_operation = 'calendar.event.create' AND effect_class = 'WRITE'", name="ck_calendar_action_f5b"),
)
