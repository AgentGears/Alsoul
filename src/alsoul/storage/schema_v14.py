from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v13 as _schema_v13


metadata = MetaData()
for _table in _schema_v13.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v13).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_reconciliation_probe = Table(
    "personal_calendar_create_reconciliation_probe",
    metadata,
    Column("reconciliation_probe_id", Uuid(as_uuid=True), primary_key=True),
    Column("authority_fence_id", Uuid(as_uuid=True), nullable=False, unique=True),
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        nullable=False,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column("generation", BigInteger, nullable=False),
    Column("correlation_key", String(256), nullable=False),
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
    Column("read_policy_revision", BigInteger, nullable=False),
    Column("read_capability_contract_version", String(128), nullable=False),
    Column("ai_policy_version", String(128), nullable=False),
    Column("resource_scope_version", String(128), nullable=False),
    Column("adapter_binding_ref", String(128), nullable=False),
    Column("adapter_version", String(128), nullable=False),
    Column("correlation_contract_version", String(128), nullable=False),
    Column("reconciliation_contract_version", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column(
        "effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect_evidence.effect_evidence_id"),
        unique=True,
    ),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    UniqueConstraint(
        "execution_attempt_id",
        "generation",
        name="uq_calendar_create_reconciliation_generation_f5b",
    ),
    CheckConstraint(
        "generation >= 1",
        name="ck_calendar_create_reconciliation_generation_f5b",
    ),
    CheckConstraint(
        "status IN ('STARTED', 'MATCHED_EFFECT_EVIDENCE', 'DIVERGENT_EFFECT_EVIDENCE', 'NOT_FOUND', 'UNKNOWN')",
        name="ck_calendar_create_reconciliation_status_f5b",
    ),
    CheckConstraint(
        "((status = 'STARTED' AND completed_at IS NULL AND effect_evidence_id IS NULL) OR "
        "(status IN ('NOT_FOUND', 'UNKNOWN') AND completed_at IS NOT NULL AND effect_evidence_id IS NULL) OR "
        "(status IN ('MATCHED_EFFECT_EVIDENCE', 'DIVERGENT_EFFECT_EVIDENCE') AND completed_at IS NOT NULL AND effect_evidence_id IS NOT NULL))",
        name="ck_calendar_create_reconciliation_completion_f5b",
    ),
    CheckConstraint(
        "reconciliation_contract_version = 'CALENDAR_CREATE_RECONCILIATION_V1'",
        name="ck_calendar_create_reconciliation_contract_f5b",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_calendar_create_reconciliation_relationship_state",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_calendar_create_reconciliation_resource_state",
    ),
    ForeignKeyConstraint(
        ["permission_id", "permission_state_revision"],
        ["permission_state.permission_id", "permission_state.revision"],
        name="fk_calendar_create_reconciliation_permission_state",
    ),
    ForeignKeyConstraint(
        ["credential_binding_id", "credential_state_revision"],
        [
            "credential_binding_state.credential_binding_id",
            "credential_binding_state.revision",
        ],
        name="fk_calendar_create_reconciliation_credential_state",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "read_policy_revision"],
        [
            "personal_calendar_read_policy_revision.relationship_id",
            "personal_calendar_read_policy_revision.revision",
        ],
        name="fk_calendar_create_reconciliation_read_policy",
    ),
)
