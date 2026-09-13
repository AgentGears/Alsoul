from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, MetaData, String, Table, Uuid
from . import schema_v9_approval_presentation as _base

metadata = MetaData()
for _t in _base.metadata.sorted_tables:
    _t.to_metadata(metadata)
for _n, _v in vars(_base).items():
    if isinstance(_v, Table):
        globals()[_n] = metadata.tables[_v.name]

personal_calendar_approval = Table(
    "personal_calendar_approval", metadata,
    Column("approval_id", Uuid(as_uuid=True), primary_key=True),
    Column("action_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_action.action_id"), nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("approval_presentation_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_approval_presentation.approval_presentation_id"), nullable=False, unique=True),
    Column("consent_payload_digest", String(64), nullable=False),
    Column("approver_ref", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("grant_source", String(64), nullable=False),
    Column("approval_policy_version", String(128), nullable=False),
    Column("write_policy_revision", BigInteger, nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), ForeignKey("personal_resource_binding.personal_resource_binding_id"), nullable=False),
    Column("source_interaction_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id"), nullable=False, unique=True),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    ForeignKeyConstraint(["relationship_id", "write_policy_revision"], ["personal_calendar_write_policy_revision.relationship_id", "personal_calendar_write_policy_revision.revision"], name="fk_approval_write_policy"),
    CheckConstraint("grant_source = 'FIRST_PARTY_COUNTERPART'", name="ck_approval_source_f5b"),
)

personal_calendar_approval_state = Table(
    "personal_calendar_approval_state", metadata,
    Column("approval_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_approval.approval_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["approval_id", "parent_revision"], ["personal_calendar_approval_state.approval_id", "personal_calendar_approval_state.revision"], name="fk_approval_state_parent"),
    CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_approval_state_f5b"),
)

personal_calendar_approval_head = Table(
    "personal_calendar_approval_head", metadata,
    Column("approval_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(["approval_id", "current_revision"], ["personal_calendar_approval_state.approval_id", "personal_calendar_approval_state.revision"], name="fk_approval_head_current"),
)
