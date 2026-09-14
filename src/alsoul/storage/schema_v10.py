from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
)

from . import schema_v9 as _schema_v9


metadata = MetaData()
for _table in _schema_v9.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v9).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_approval_presentation = Table(
    "personal_calendar_create_approval_presentation",
    metadata,
    Column("approval_presentation_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
        unique=True,
    ),
    Column("action_digest", String(64), nullable=False),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("effect_class", String(32), nullable=False),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column("target_calendar_display_identity", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("start_text", String(64), nullable=False),
    Column("end_text", String(64), nullable=False),
    Column("normalized_start_at", DateTime(timezone=True), nullable=False),
    Column("normalized_end_at", DateTime(timezone=True), nullable=False),
    Column("consent_rendering_version", String(128), nullable=False),
    Column("consent_payload_digest", String(64), nullable=False),
    Column(
        "presented_to_counterpart_id",
        Uuid(as_uuid=True),
        ForeignKey("counterpart_person.counterpart_id"),
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
    Column("presentation_timeline_frontier", BigInteger, nullable=False),
    Column("presentation_key", String(256), nullable=False, unique=True),
    Column("sink_binding_ref", String(128), nullable=False),
    Column("presentation_contract_version", String(128), nullable=False),
    Column("presentation_acceptance_ref", String(256), nullable=False),
    Column("presented_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_approval_presentation_capability_f5b",
    ),
    CheckConstraint(
        "effect_class = 'WRITE'",
        name="ck_calendar_create_approval_presentation_effect_f5b",
    ),
    CheckConstraint(
        "consent_rendering_version = 'CALENDAR_CREATE_CONSENT_V1'",
        name="ck_calendar_create_approval_rendering_f5b",
    ),
)


personal_calendar_create_approval = Table(
    "personal_calendar_create_approval",
    metadata,
    Column("approval_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "approval_presentation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_approval_presentation.approval_presentation_id"),
        nullable=False,
        unique=True,
    ),
    Column("action_digest", String(64), nullable=False),
    Column("consent_payload_digest", String(64), nullable=False),
    Column(
        "authorized_approver_ref",
        Uuid(as_uuid=True),
        ForeignKey("counterpart_person.counterpart_id"),
        nullable=False,
    ),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("effect_class", String(32), nullable=False),
    Column("approval_ceremony_source", String(128), nullable=False),
    Column("approval_policy_revision", BigInteger, nullable=False),
    Column("approval_policy_version", String(128), nullable=False),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column("write_permission_id", Uuid(as_uuid=True), nullable=False),
    Column("write_permission_state_revision", BigInteger, nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    ForeignKeyConstraint(
        ["relationship_id", "approval_policy_revision"],
        [
            "personal_calendar_create_policy_revision.relationship_id",
            "personal_calendar_create_policy_revision.revision",
        ],
        name="fk_calendar_create_approval_policy",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_calendar_create_approval_relationship_state",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_calendar_create_approval_resource_state",
    ),
    ForeignKeyConstraint(
        ["write_permission_id", "write_permission_state_revision"],
        [
            "personal_calendar_write_permission_state.permission_id",
            "personal_calendar_write_permission_state.revision",
        ],
        name="fk_calendar_create_approval_permission_state",
    ),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_approval_capability_f5b",
    ),
    CheckConstraint(
        "effect_class = 'WRITE'",
        name="ck_calendar_create_approval_effect_f5b",
    ),
    CheckConstraint(
        "approval_ceremony_source = 'FIRST_PARTY_COUNTERPART_APPROVAL_V1'",
        name="ck_calendar_create_approval_ceremony_f5b",
    ),
)

Index(
    "ix_calendar_create_approval_relationship",
    personal_calendar_create_approval.c.relationship_id,
    personal_calendar_create_approval.c.personal_resource_binding_id,
)

personal_calendar_create_approval_state = Table(
    "personal_calendar_create_approval_state",
    metadata,
    Column(
        "approval_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_approval.approval_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["approval_id", "parent_revision"],
        [
            "personal_calendar_create_approval_state.approval_id",
            "personal_calendar_create_approval_state.revision",
        ],
        name="fk_calendar_create_approval_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'REVOKED')",
        name="ck_calendar_create_approval_state_f5b",
    ),
)

personal_calendar_create_approval_head = Table(
    "personal_calendar_create_approval_head",
    metadata,
    Column("approval_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["approval_id", "current_revision"],
        [
            "personal_calendar_create_approval_state.approval_id",
            "personal_calendar_create_approval_state.revision",
        ],
        name="fk_calendar_create_approval_head_current",
    ),
)
