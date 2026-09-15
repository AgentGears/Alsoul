from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
)

from . import schema_v14 as _schema_v14


metadata = MetaData()
for _table in _schema_v14.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v14).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_no_effect_operation_claim = Table(
    "personal_calendar_create_no_effect_operation_claim",
    metadata,
    Column("operation_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        nullable=False,
    ),
    Column("request_digest", String(64), nullable=False),
    Column(
        "reconciliation_probe_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_reconciliation_probe.reconciliation_probe_id"),
        unique=True,
    ),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    CheckConstraint(
        "status IN ('STARTED', 'COMPLETED')",
        name="ck_calendar_create_no_effect_operation_claim_status_f5b",
    ),
    CheckConstraint(
        "((status = 'STARTED' AND completed_at IS NULL) OR "
        "(status = 'COMPLETED' AND completed_at IS NOT NULL AND reconciliation_probe_id IS NOT NULL))",
        name="ck_calendar_create_no_effect_operation_claim_completion_f5b",
    ),
)


personal_calendar_create_no_effect_evidence = Table(
    "personal_calendar_create_no_effect_evidence",
    metadata,
    Column("no_effect_evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "reconciliation_probe_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_reconciliation_probe.reconciliation_probe_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_mutation_dispatch.execution_attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column("correlation_key", String(256), nullable=False),
    Column("operation_status", String(64), nullable=False),
    Column("terminality_scope", String(64), nullable=False),
    Column("intended_effect_absent", Boolean, nullable=False),
    Column("terminal_non_application", Boolean, nullable=False),
    Column("terminality_proof_ref", Text, nullable=False),
    Column("absence_proof_ref", Text, nullable=False),
    Column("negative_confirmation_contract_version", String(128), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("evidence_schema_version", String(128), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "operation_status = 'TERMINAL_NOT_APPLIED'",
        name="ck_calendar_create_no_effect_operation_status_f5b",
    ),
    CheckConstraint(
        "terminality_scope = 'EXACT_EXECUTION_ATTEMPT'",
        name="ck_calendar_create_no_effect_scope_f5b",
    ),
    CheckConstraint(
        "intended_effect_absent AND terminal_non_application",
        name="ck_calendar_create_no_effect_terminal_predicate_f5b",
    ),
    CheckConstraint(
        "negative_confirmation_contract_version = 'CALENDAR_CREATE_NEGATIVE_CONFIRMATION_V1'",
        name="ck_calendar_create_no_effect_contract_f5b",
    ),
    CheckConstraint(
        "evidence_schema_version = 'CALENDAR_CREATE_NO_EFFECT_EVIDENCE_V1'",
        name="ck_calendar_create_no_effect_evidence_schema_f5b",
    ),
)


personal_calendar_create_no_effect = Table(
    "personal_calendar_create_no_effect",
    metadata,
    Column("no_effect_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column("status", String(32), nullable=False),
    Column("no_effect_schema_version", String(128), nullable=False),
    Column("admitted_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status = 'CONFIRMED_NO_EFFECT'",
        name="ck_calendar_create_no_effect_status_f5b",
    ),
    CheckConstraint(
        "no_effect_schema_version = 'CALENDAR_CREATE_NO_EFFECT_V1'",
        name="ck_calendar_create_no_effect_schema_f5b",
    ),
)


personal_calendar_create_no_effect_support = Table(
    "personal_calendar_create_no_effect_support",
    metadata,
    Column(
        "no_effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_no_effect.no_effect_id"),
        primary_key=True,
    ),
    Column(
        "no_effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_no_effect_evidence.no_effect_evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("support_kind", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "support_kind = 'SUPPORTS'",
        name="ck_calendar_create_no_effect_support_kind_f5b",
    ),
)


personal_calendar_create_retry_claim = Table(
    "personal_calendar_create_retry_claim",
    metadata,
    Column(
        "new_execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        primary_key=True,
    ),
    Column(
        "prior_execution_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_execution_attempt.execution_attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
    ),
    Column(
        "no_effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_no_effect.no_effect_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "no_effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_no_effect_evidence.no_effect_evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("retry_contract_version", String(128), nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "retry_contract_version = 'CALENDAR_CREATE_RETRY_V1'",
        name="ck_calendar_create_retry_contract_f5b",
    ),
)
