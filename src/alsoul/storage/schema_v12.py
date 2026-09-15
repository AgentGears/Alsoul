from __future__ import annotations

from sqlalchemy import (
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

from . import schema_v11 as _schema_v11


metadata = MetaData()
for _table in _schema_v11.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v11).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_mutation_dispatch = Table(
    "personal_calendar_create_mutation_dispatch",
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
    Column("request_contract_version", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "request_contract_version = 'CALENDAR_CREATE_MUTATION_REQUEST_V1'",
        name="ck_calendar_create_mutation_dispatch_request_f5b",
    ),
)


personal_calendar_create_effect_evidence = Table(
    "personal_calendar_create_effect_evidence",
    metadata,
    Column("effect_evidence_id", Uuid(as_uuid=True), primary_key=True),
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
    Column("validation_kind", String(32), nullable=False),
    Column("correlation_key", String(256), nullable=False),
    Column("external_effect_ref", Text, nullable=False),
    Column("external_system_ref", Text, nullable=False),
    Column("external_resource_ref", Text, nullable=False),
    Column("normalized_summary", Text, nullable=False),
    Column("normalized_start_at", DateTime(timezone=True), nullable=False),
    Column("normalized_end_at", DateTime(timezone=True), nullable=False),
    Column("provider_status", String(32), nullable=False),
    Column("receipt_ref", Text, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("evidence_schema_version", String(128), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "validation_kind IN ('SEMANTIC_MATCH', 'SEMANTIC_DIVERGENCE')",
        name="ck_calendar_create_effect_evidence_validation_f5b",
    ),
    CheckConstraint(
        "provider_status = 'CREATED'",
        name="ck_calendar_create_effect_evidence_status_f5b",
    ),
    CheckConstraint(
        "evidence_schema_version = 'CALENDAR_CREATE_EFFECT_EVIDENCE_V1'",
        name="ck_calendar_create_effect_evidence_schema_f5b",
    ),
)
