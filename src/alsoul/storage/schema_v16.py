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

from . import schema_v15 as _schema_v15


metadata = MetaData()
for _table in _schema_v15.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v15).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_mutation_completion_projection = Table(
    "personal_calendar_mutation_completion_projection",
    metadata,
    Column(
        "projection_id",
        Uuid(as_uuid=True),
        ForeignKey("context_projection.projection_id"),
        primary_key=True,
    ),
    Column("mutation_completion_ref", Uuid(as_uuid=True), nullable=False, unique=True),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect.effect_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect_evidence.effect_evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("result_kind", String(32), nullable=False),
    Column("plan_schema_version", String(128), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("context_contract_version", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "result_kind = 'CREATED'",
        name="ck_calendar_mutation_completion_result_kind_f5b",
    ),
    CheckConstraint(
        "plan_schema_version = 'CALENDAR_MUTATION_RESULT_PLAN_V1'",
        name="ck_calendar_mutation_completion_plan_schema_f5b",
    ),
    CheckConstraint(
        "rendering_contract_version = 'CALENDAR_CREATE_RESULT_V1'",
        name="ck_calendar_mutation_completion_rendering_f5b",
    ),
    CheckConstraint(
        "context_contract_version = 'CALENDAR_MUTATION_COMPLETION_CONTEXT_V1'",
        name="ck_calendar_mutation_completion_context_f5b",
    ),
)


personal_calendar_mutation_model_invocation = Table(
    "personal_calendar_mutation_model_invocation",
    metadata,
    Column(
        "model_invocation_id",
        Uuid(as_uuid=True),
        ForeignKey("model_invocation.model_invocation_id"),
        primary_key=True,
    ),
    Column(
        "projection_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_completion_projection.projection_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "route_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_model_route_binding.route_binding_id"),
        nullable=False,
    ),
    Column("route_state_revision", BigInteger, nullable=False),
    Column("plan_schema_version", String(128), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("dispatched_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["route_binding_id", "route_state_revision"],
        [
            "personal_calendar_model_route_state.route_binding_id",
            "personal_calendar_model_route_state.revision",
        ],
        name="fk_calendar_mutation_invocation_route_state",
    ),
    CheckConstraint(
        "plan_schema_version = 'CALENDAR_MUTATION_RESULT_PLAN_V1'",
        name="ck_calendar_mutation_invocation_plan_schema_f5b",
    ),
    CheckConstraint(
        "rendering_contract_version = 'CALENDAR_CREATE_RESULT_V1'",
        name="ck_calendar_mutation_invocation_rendering_f5b",
    ),
)


personal_calendar_mutation_generated_output = Table(
    "personal_calendar_mutation_generated_output",
    metadata,
    Column(
        "generated_output_id",
        Uuid(as_uuid=True),
        ForeignKey("generated_output.generated_output_id"),
        primary_key=True,
    ),
    Column(
        "projection_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_completion_projection.projection_id"),
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
        "effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect.effect_id"),
        nullable=False,
    ),
    Column("plan_schema_version", String(128), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("validated_shape_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "action_id",
        "effect_id",
        name="uq_calendar_mutation_generated_action_effect_f5b",
    ),
    CheckConstraint(
        "plan_schema_version = 'CALENDAR_MUTATION_RESULT_PLAN_V1'",
        name="ck_calendar_mutation_generated_plan_schema_f5b",
    ),
    CheckConstraint(
        "rendering_contract_version = 'CALENDAR_CREATE_RESULT_V1'",
        name="ck_calendar_mutation_generated_rendering_f5b",
    ),
)


personal_calendar_mutation_adoption = Table(
    "personal_calendar_mutation_adoption",
    metadata,
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("companion_output.companion_output_id"),
        primary_key=True,
    ),
    Column(
        "generated_output_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_generated_output.generated_output_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "projection_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_completion_projection.projection_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "action_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_action.action_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "effect_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect.effect_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect_evidence.effect_evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("deterministic_render_digest", String(64), nullable=False),
    Column("validated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "rendering_contract_version = 'CALENDAR_CREATE_RESULT_V1'",
        name="ck_calendar_mutation_adoption_rendering_f5b",
    ),
)
