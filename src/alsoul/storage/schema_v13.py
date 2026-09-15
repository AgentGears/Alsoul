from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Uuid,
)

from . import schema_v12 as _schema_v12


metadata = MetaData()
for _table in _schema_v12.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v12).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_create_effect = Table(
    "personal_calendar_create_effect",
    metadata,
    Column("effect_id", Uuid(as_uuid=True), primary_key=True),
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
    Column("capability_semantic_operation", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("effect_schema_version", String(128), nullable=False),
    Column("admitted_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "capability_semantic_operation = 'calendar.event.create'",
        name="ck_calendar_create_effect_capability_f5b",
    ),
    CheckConstraint(
        "status = 'CONFIRMED_EFFECT'",
        name="ck_calendar_create_effect_status_f5b",
    ),
    CheckConstraint(
        "effect_schema_version = 'CALENDAR_CREATE_EFFECT_V1'",
        name="ck_calendar_create_effect_schema_f5b",
    ),
)


personal_calendar_create_effect_support = Table(
    "personal_calendar_create_effect_support",
    metadata,
    Column(
        "effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect.effect_id"),
        primary_key=True,
    ),
    Column(
        "effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect_evidence.effect_evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("support_kind", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "support_kind = 'SUPPORTS'",
        name="ck_calendar_create_effect_support_kind_f5b",
    ),
)
