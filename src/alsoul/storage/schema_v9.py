from __future__ import annotations

from sqlalchemy import (
    JSON,
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

from . import schema_v8 as _schema_v8


metadata = MetaData()
for _table in _schema_v8.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v8).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_policy_revision = Table(
    "personal_calendar_create_policy_revision",
    metadata,
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("capability_effect_class", String(32), nullable=False),
    Column("ai_policy_version", String(128), nullable=False),
    Column("resource_scope_version", String(128), nullable=False),
    Column("required_provider_scope", String(256), nullable=False),
    Column("permission_grant_policy_version", String(128), nullable=False),
    Column("allowed_resource_binding_ids_json", JSON, nullable=False),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "parent_revision"],
        [
            "personal_calendar_create_policy_revision.relationship_id",
            "personal_calendar_create_policy_revision.revision",
        ],
        name="fk_calendar_create_policy_parent",
    ),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_policy_capability_f5b",
    ),
    CheckConstraint(
        "capability_effect_class = 'WRITE'",
        name="ck_calendar_create_policy_effect_f5b",
    ),
    CheckConstraint(
        "status IN ('ALLOW', 'DENY')",
        name="ck_calendar_create_policy_status_f5b",
    ),
)

personal_calendar_create_policy_head = Table(
    "personal_calendar_create_policy_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        [
            "personal_calendar_create_policy_revision.relationship_id",
            "personal_calendar_create_policy_revision.revision",
        ],
        name="fk_calendar_create_policy_head_current",
    ),
)


personal_calendar_write_permission_grant = Table(
    "personal_calendar_write_permission_grant",
    metadata,
    Column("permission_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "holder_companion_person_id",
        Uuid(as_uuid=True),
        ForeignKey("companion_person.person_id"),
        nullable=False,
    ),
    Column(
        "counterpart_id",
        Uuid(as_uuid=True),
        ForeignKey("counterpart_person.counterpart_id"),
        nullable=False,
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
    Column("capability_contract_version", String(128), nullable=False),
    Column("operation_class", String(32), nullable=False),
    Column(
        "grantor_ref",
        Uuid(as_uuid=True),
        ForeignKey("counterpart_person.counterpart_id"),
        nullable=False,
    ),
    Column("grant_source", String(64), nullable=False),
    Column("grant_policy_version", String(128), nullable=False),
    Column("constraints_json", JSON, nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_write_permission_capability_f5b",
    ),
    CheckConstraint(
        "operation_class = 'WRITE'",
        name="ck_calendar_write_permission_operation_f5b",
    ),
    CheckConstraint(
        "grant_source = 'FIRST_PARTY_COUNTERPART'",
        name="ck_calendar_write_permission_source_f5b",
    ),
)

Index(
    "ix_calendar_write_permission_lookup",
    personal_calendar_write_permission_grant.c.holder_companion_person_id,
    personal_calendar_write_permission_grant.c.relationship_id,
    personal_calendar_write_permission_grant.c.personal_resource_binding_id,
)

personal_calendar_write_permission_state = Table(
    "personal_calendar_write_permission_state",
    metadata,
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_write_permission_grant.permission_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["permission_id", "parent_revision"],
        [
            "personal_calendar_write_permission_state.permission_id",
            "personal_calendar_write_permission_state.revision",
        ],
        name="fk_calendar_write_permission_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'REVOKED')",
        name="ck_calendar_write_permission_state_f5b",
    ),
)

personal_calendar_write_permission_head = Table(
    "personal_calendar_write_permission_head",
    metadata,
    Column("permission_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["permission_id", "current_revision"],
        [
            "personal_calendar_write_permission_state.permission_id",
            "personal_calendar_write_permission_state.revision",
        ],
        name="fk_calendar_write_permission_head_current",
    ),
)


personal_calendar_create_action = Table(
    "personal_calendar_create_action",
    metadata,
    Column("action_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column(
        "counterpart_id",
        Uuid(as_uuid=True),
        ForeignKey("counterpart_person.counterpart_id"),
        nullable=False,
    ),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
        unique=True,
    ),
    Column("summary", Text, nullable=False),
    Column("start_text", String(64), nullable=False),
    Column("end_text", String(64), nullable=False),
    Column("normalized_start_at", DateTime(timezone=True), nullable=False),
    Column("normalized_end_at", DateTime(timezone=True), nullable=False),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("action_schema_version", String(128), nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("source_timeline_frontier", BigInteger, nullable=False),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column("write_policy_revision", BigInteger, nullable=False),
    Column("write_permission_id", Uuid(as_uuid=True), nullable=False),
    Column("write_permission_state_revision", BigInteger, nullable=False),
    Column("prepared_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_calendar_create_action_relationship_state",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_calendar_create_action_resource_state",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "write_policy_revision"],
        [
            "personal_calendar_create_policy_revision.relationship_id",
            "personal_calendar_create_policy_revision.revision",
        ],
        name="fk_calendar_create_action_policy",
    ),
    ForeignKeyConstraint(
        ["write_permission_id", "write_permission_state_revision"],
        [
            "personal_calendar_write_permission_state.permission_id",
            "personal_calendar_write_permission_state.revision",
        ],
        name="fk_calendar_create_action_permission_state",
    ),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_action_capability_f5b",
    ),
    CheckConstraint(
        "action_schema_version = 'PERSONAL_CALENDAR_CREATE_ACTION_V1'",
        name="ck_calendar_create_action_schema_f5b",
    ),
)

Index(
    "ix_calendar_create_action_relationship",
    personal_calendar_create_action.c.relationship_id,
    personal_calendar_create_action.c.personal_resource_binding_id,
)
