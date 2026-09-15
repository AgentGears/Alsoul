from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v10 as _schema_v10


metadata = MetaData()
for _table in _schema_v10.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v10).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_execution_attempt = Table(
    "personal_calendar_create_execution_attempt",
    metadata,
    Column("execution_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column("attempt_generation", BigInteger, nullable=False),
    Column(
        "approval_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_approval.approval_id"),
        nullable=False,
    ),
    Column(
        "credential_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("credential_binding.credential_binding_id"),
        nullable=False,
    ),
    Column("correlation_key", String(256), nullable=False),
    Column("correlation_contract_version", String(128), nullable=False),
    Column("prepared_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "action_id",
        "attempt_generation",
        name="uq_calendar_create_execution_attempt_generation_f5b",
    ),
    CheckConstraint(
        "attempt_generation >= 1",
        name="ck_calendar_create_execution_attempt_generation_f5b",
    ),
    CheckConstraint(
        "correlation_contract_version = 'CALENDAR_CREATE_ACTION_CORRELATION_V1'",
        name="ck_calendar_create_execution_attempt_correlation_f5b",
    ),
)

Index(
    "ix_calendar_create_execution_attempt_action",
    personal_calendar_create_execution_attempt.c.action_id,
    personal_calendar_create_execution_attempt.c.attempt_generation,
)


personal_calendar_create_execution_attempt_state = Table(
    "personal_calendar_create_execution_attempt_state",
    metadata,
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["execution_attempt_id", "parent_revision"],
        [
            "personal_calendar_create_execution_attempt_state.execution_attempt_id",
            "personal_calendar_create_execution_attempt_state.revision",
        ],
        name="fk_calendar_create_execution_attempt_state_parent",
    ),
    CheckConstraint(
        "status IN ('PREPARED', 'ABANDONED', 'DISPATCH_FENCED', 'UNKNOWN_EFFECT', 'CONFIRMED_EFFECT', 'CONFIRMED_NO_EFFECT')",
        name="ck_calendar_create_execution_attempt_state_f5b",
    ),
)


personal_calendar_create_execution_attempt_head = Table(
    "personal_calendar_create_execution_attempt_head",
    metadata,
    Column("execution_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["execution_attempt_id", "current_revision"],
        [
            "personal_calendar_create_execution_attempt_state.execution_attempt_id",
            "personal_calendar_create_execution_attempt_state.revision",
        ],
        name="fk_calendar_create_execution_attempt_head_current",
    ),
)


personal_calendar_create_execution_fence = Table(
    "personal_calendar_create_execution_fence",
    metadata,
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        primary_key=True,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column("attempt_generation", BigInteger, nullable=False),
    Column("correlation_key", String(256), nullable=False),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column("write_policy_revision", BigInteger, nullable=False),
    Column("write_permission_id", Uuid(as_uuid=True), nullable=False),
    Column("write_permission_state_revision", BigInteger, nullable=False),
    Column("approval_id", Uuid(as_uuid=True), nullable=False),
    Column("approval_state_revision", BigInteger, nullable=False),
    Column(
        "approval_presentation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_approval_presentation.approval_presentation_id"),
        nullable=False,
    ),
    Column("consent_payload_digest", String(64), nullable=False),
    Column("authorized_approver_ref", Uuid(as_uuid=True), nullable=False),
    Column("approver_eligibility_version", String(128), nullable=False),
    Column("credential_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("credential_binding_state_revision", BigInteger, nullable=False),
    Column("provider_scope_snapshot_json", JSON, nullable=False),
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("ai_policy_version", String(128), nullable=False),
    Column("resource_scope_version", String(128), nullable=False),
    Column("action_constraint_version", String(128), nullable=False),
    Column("adapter_binding_ref", String(128), nullable=False),
    Column("adapter_contract_version", String(128), nullable=False),
    Column("executor_contract_version", String(128), nullable=False),
    Column("correlation_contract_version", String(128), nullable=False),
    Column("negative_confirmation_contract_version", String(128), nullable=False),
    Column("authority_evaluated_at", DateTime(timezone=True), nullable=False),
    Column("dispatch_fenced_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["action_id", "relationship_authority_revision"],
        [
            "personal_calendar_create_action.action_id",
            "personal_calendar_create_action.relationship_authority_revision",
        ],
        name="fk_calendar_create_execution_fence_action_relationship_snapshot",
        use_alter=True,
    ),
    ForeignKeyConstraint(
        ["write_permission_id", "write_permission_state_revision"],
        [
            "personal_calendar_write_permission_state.permission_id",
            "personal_calendar_write_permission_state.revision",
        ],
        name="fk_calendar_create_execution_fence_permission_state",
    ),
    ForeignKeyConstraint(
        ["approval_id", "approval_state_revision"],
        [
            "personal_calendar_create_approval_state.approval_id",
            "personal_calendar_create_approval_state.revision",
        ],
        name="fk_calendar_create_execution_fence_approval_state",
    ),
    ForeignKeyConstraint(
        ["credential_binding_id", "credential_binding_state_revision"],
        [
            "credential_binding_state.credential_binding_id",
            "credential_binding_state.revision",
        ],
        name="fk_calendar_create_execution_fence_credential_state",
    ),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_execution_fence_capability_f5b",
    ),
    CheckConstraint(
        "approver_eligibility_version = 'FIRST_PARTY_COUNTERPART_APPROVER_V1'",
        name="ck_calendar_create_execution_fence_approver_f5b",
    ),
    CheckConstraint(
        "action_constraint_version = 'CALENDAR_CREATE_ACTION_CONSTRAINTS_V1'",
        name="ck_calendar_create_execution_fence_constraints_f5b",
    ),
    CheckConstraint(
        "correlation_contract_version = 'CALENDAR_CREATE_ACTION_CORRELATION_V1'",
        name="ck_calendar_create_execution_fence_correlation_f5b",
    ),
)


personal_calendar_create_action_dispatch_state = Table(
    "personal_calendar_create_action_dispatch_state",
    metadata,
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        primary_key=True,
    ),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
    ),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["action_id", "parent_revision"],
        [
            "personal_calendar_create_action_dispatch_state.action_id",
            "personal_calendar_create_action_dispatch_state.revision",
        ],
        name="fk_calendar_create_action_dispatch_state_parent",
    ),
    CheckConstraint(
        "status IN ('AVAILABLE', 'PREPARED', 'DISPATCH_FENCED', 'UNKNOWN_EFFECT', 'CONFIRMED_EFFECT', 'CONFIRMED_NO_EFFECT')",
        name="ck_calendar_create_action_dispatch_state_f5b",
    ),
)


personal_calendar_create_action_dispatch_head = Table(
    "personal_calendar_create_action_dispatch_head",
    metadata,
    Column("action_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["action_id", "current_revision"],
        [
            "personal_calendar_create_action_dispatch_state.action_id",
            "personal_calendar_create_action_dispatch_state.revision",
        ],
        name="fk_calendar_create_action_dispatch_head_current",
    ),
)
