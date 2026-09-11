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
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from . import schema_v4 as _schema_v4

# Compose the current runtime metadata from a clone of frozen schema v4.
metadata = MetaData()
for _table in _schema_v4.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v4).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_world_relationship_state = Table(
    "personal_world_relationship_state",
    metadata,
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "parent_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_personal_world_relationship_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'ENDED')",
        name="ck_personal_world_relationship_state_status_f5",
    ),
)

personal_world_relationship_head = Table(
    "personal_world_relationship_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_personal_world_relationship_head_current",
    ),
)


personal_resource_binding = Table(
    "personal_resource_binding",
    metadata,
    Column("personal_resource_binding_id", Uuid(as_uuid=True), primary_key=True),
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
    Column("resource_kind", String(64), nullable=False),
    Column("external_system_ref", Text, nullable=False),
    Column("external_resource_ref", Text, nullable=False),
    Column("calendar_timezone", String(128), nullable=False),
    Column("timezone_rules_version", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "external_system_ref",
        "external_resource_ref",
        name="uq_personal_resource_external_target",
    ),
    CheckConstraint(
        "resource_kind = 'CALENDAR'",
        name="ck_personal_resource_binding_kind_f5",
    ),
)

Index(
    "ix_personal_resource_binding_relationship",
    personal_resource_binding.c.relationship_id,
    personal_resource_binding.c.resource_kind,
)

personal_resource_binding_state = Table(
    "personal_resource_binding_state",
    metadata,
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "parent_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_personal_resource_binding_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'INACTIVE', 'REVOKED')",
        name="ck_personal_resource_binding_state_status_f5",
    ),
)

personal_resource_binding_head = Table(
    "personal_resource_binding_head",
    metadata,
    Column("personal_resource_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "current_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_personal_resource_binding_head_current",
    ),
)


credential_binding = Table(
    "credential_binding",
    metadata,
    Column("credential_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("external_system_ref", Text, nullable=False),
    Column("external_principal_ref", Text, nullable=False),
    Column("secret_ref", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

credential_binding_state = Table(
    "credential_binding_state",
    metadata,
    Column(
        "credential_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("credential_binding.credential_binding_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("provider_scopes_json", JSON, nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["credential_binding_id", "parent_revision"],
        [
            "credential_binding_state.credential_binding_id",
            "credential_binding_state.revision",
        ],
        name="fk_credential_binding_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'REVOKED')",
        name="ck_credential_binding_state_status_f5",
    ),
)

credential_binding_head = Table(
    "credential_binding_head",
    metadata,
    Column("credential_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["credential_binding_id", "current_revision"],
        [
            "credential_binding_state.credential_binding_id",
            "credential_binding_state.revision",
        ],
        name="fk_credential_binding_head_current",
    ),
)


permission_grant = Table(
    "permission_grant",
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
        "capability_semantic_operation = 'calendar.events.read'",
        name="ck_permission_grant_capability_f5",
    ),
    CheckConstraint(
        "operation_class = 'READ'",
        name="ck_permission_grant_operation_class_f5",
    ),
    CheckConstraint(
        "grant_source = 'FIRST_PARTY_COUNTERPART'",
        name="ck_permission_grant_source_f5",
    ),
)

Index(
    "ix_permission_grant_calendar_lookup",
    permission_grant.c.holder_companion_person_id,
    permission_grant.c.relationship_id,
    permission_grant.c.personal_resource_binding_id,
    permission_grant.c.capability_semantic_operation,
)

permission_state = Table(
    "permission_state",
    metadata,
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permission_grant.permission_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["permission_id", "parent_revision"],
        ["permission_state.permission_id", "permission_state.revision"],
        name="fk_permission_state_parent",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'REVOKED')",
        name="ck_permission_state_status_f5",
    ),
)

permission_head = Table(
    "permission_head",
    metadata,
    Column("permission_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["permission_id", "current_revision"],
        ["permission_state.permission_id", "permission_state.revision"],
        name="fk_permission_head_current",
    ),
)


personal_calendar_read_policy_revision = Table(
    "personal_calendar_read_policy_revision",
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
            "personal_calendar_read_policy_revision.relationship_id",
            "personal_calendar_read_policy_revision.revision",
        ],
        name="fk_personal_calendar_read_policy_parent",
    ),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.events.read'",
        name="ck_personal_calendar_read_policy_capability_f5",
    ),
    CheckConstraint(
        "capability_effect_class = 'READ_ONLY'",
        name="ck_personal_calendar_read_policy_effect_f5",
    ),
    CheckConstraint(
        "status IN ('ALLOW', 'DENY')",
        name="ck_personal_calendar_read_policy_status_f5",
    ),
)

personal_calendar_read_policy_head = Table(
    "personal_calendar_read_policy_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        [
            "personal_calendar_read_policy_revision.relationship_id",
            "personal_calendar_read_policy_revision.revision",
        ],
        name="fk_personal_calendar_read_policy_head_current",
    ),
)


personal_calendar_observation_scope = Table(
    "personal_calendar_observation_scope",
    metadata,
    Column(
        "observation_id",
        Uuid(as_uuid=True),
        ForeignKey("observation.observation_id"),
        primary_key=True,
    ),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column("requested_local_date", String(10), nullable=False),
    Column("calendar_timezone", String(128), nullable=False),
    Column("timezone_rules_version", String(128), nullable=False),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("window_end", DateTime(timezone=True), nullable=False),
    Column("acquisition_started_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


personal_calendar_read_authority_fence = Table(
    "personal_calendar_read_authority_fence",
    metadata,
    Column("authority_fence_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "observation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_observation_scope.observation_id"),
        nullable=False,
    ),
    Column("page_ordinal", Integer, nullable=False),
    Column(
        "relationship_id",
        Uuid(as_uuid=True),
        ForeignKey("relationship_identity.relationship_id"),
        nullable=False,
    ),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permission_grant.permission_id"),
        nullable=False,
    ),
    Column("permission_state_revision", BigInteger, nullable=False),
    Column(
        "credential_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("credential_binding.credential_binding_id"),
        nullable=False,
    ),
    Column("credential_state_revision", BigInteger, nullable=False),
    Column("policy_revision", BigInteger, nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("ai_policy_version", String(128), nullable=False),
    Column("resource_scope_version", String(128), nullable=False),
    Column("authorized_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "observation_id",
        "page_ordinal",
        name="uq_personal_calendar_read_authority_page",
    ),
    CheckConstraint(
        "page_ordinal >= 0",
        name="ck_personal_calendar_read_page_ordinal_f5",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_calendar_fence_relationship_authority",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_calendar_fence_resource_state",
    ),
    ForeignKeyConstraint(
        ["permission_id", "permission_state_revision"],
        ["permission_state.permission_id", "permission_state.revision"],
        name="fk_calendar_fence_permission_state",
    ),
    ForeignKeyConstraint(
        ["credential_binding_id", "credential_state_revision"],
        [
            "credential_binding_state.credential_binding_id",
            "credential_binding_state.revision",
        ],
        name="fk_calendar_fence_credential_state",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "policy_revision"],
        [
            "personal_calendar_read_policy_revision.relationship_id",
            "personal_calendar_read_policy_revision.revision",
        ],
        name="fk_calendar_fence_policy_revision",
    ),
)

Index(
    "ix_personal_calendar_read_authority_observation",
    personal_calendar_read_authority_fence.c.observation_id,
    personal_calendar_read_authority_fence.c.page_ordinal,
)
