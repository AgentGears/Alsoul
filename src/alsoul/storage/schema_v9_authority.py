from __future__ import annotations

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, MetaData, String, Table, Uuid
from . import schema_v8 as _v8

metadata = MetaData()
for _t in _v8.metadata.sorted_tables:
    _t.to_metadata(metadata)
for _n, _v in vars(_v8).items():
    if isinstance(_v, Table):
        globals()[_n] = metadata.tables[_v.name]

personal_calendar_write_permission_grant = Table(
    "personal_calendar_write_permission_grant", metadata,
    Column("permission_id", Uuid(as_uuid=True), primary_key=True),
    Column("holder_companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), ForeignKey("personal_resource_binding.personal_resource_binding_id"), nullable=False),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("operation_class", String(32), nullable=False),
    Column("grantor_ref", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("grant_source", String(64), nullable=False),
    Column("grant_policy_version", String(128), nullable=False),
    Column("constraints_json", JSON, nullable=False),
    Column("source_interaction_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id"), nullable=False, unique=True),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    CheckConstraint("capability_semantic_operation = 'calendar.event.create' AND operation_class = 'WRITE' AND grant_source = 'FIRST_PARTY_COUNTERPART'", name="ck_write_permission_f5b"),
)

personal_calendar_write_permission_state = Table(
    "personal_calendar_write_permission_state", metadata,
    Column("permission_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_write_permission_grant.permission_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["permission_id", "parent_revision"], ["personal_calendar_write_permission_state.permission_id", "personal_calendar_write_permission_state.revision"], name="fk_write_permission_state_parent"),
    CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_write_permission_state_f5b"),
)

personal_calendar_write_permission_head = Table(
    "personal_calendar_write_permission_head", metadata,
    Column("permission_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(["permission_id", "current_revision"], ["personal_calendar_write_permission_state.permission_id", "personal_calendar_write_permission_state.revision"], name="fk_write_permission_head_current"),
)

personal_calendar_write_policy_revision = Table(
    "personal_calendar_write_policy_revision", metadata,
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("capability_effect_class", String(32), nullable=False),
    Column("ai_policy_version", String(128), nullable=False),
    Column("resource_scope_version", String(128), nullable=False),
    Column("required_provider_scope", String(256), nullable=False),
    Column("permission_grant_policy_version", String(128), nullable=False),
    Column("approval_policy_version", String(128), nullable=False),
    Column("allowed_resource_binding_ids_json", JSON, nullable=False),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["relationship_id", "parent_revision"], ["personal_calendar_write_policy_revision.relationship_id", "personal_calendar_write_policy_revision.revision"], name="fk_write_policy_parent"),
    CheckConstraint("capability_semantic_operation = 'calendar.event.create' AND capability_effect_class = 'WRITE' AND status IN ('ALLOW', 'DENY')", name="ck_write_policy_f5b"),
)

personal_calendar_write_policy_head = Table(
    "personal_calendar_write_policy_head", metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(["relationship_id", "current_revision"], ["personal_calendar_write_policy_revision.relationship_id", "personal_calendar_write_policy_revision.revision"], name="fk_write_policy_head_current"),
)
