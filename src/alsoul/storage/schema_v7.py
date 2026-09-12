from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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

from . import schema_v6 as _schema_v6

metadata = MetaData()
for _table in _schema_v6.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v6).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_freshness_policy_revision = Table(
    "personal_calendar_freshness_policy_revision",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("policy_version", String(128), nullable=False),
    Column("max_age_seconds", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "parent_revision"],
        ["personal_calendar_freshness_policy_revision.relationship_id", "personal_calendar_freshness_policy_revision.revision"],
        name="fk_calendar_freshness_policy_parent",
    ),
    CheckConstraint("max_age_seconds >= 0", name="ck_calendar_freshness_policy_max_age_f5"),
    CheckConstraint("status IN ('ALLOW', 'DENY')", name="ck_calendar_freshness_policy_status_f5"),
)

personal_calendar_freshness_policy_head = Table(
    "personal_calendar_freshness_policy_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        ["personal_calendar_freshness_policy_revision.relationship_id", "personal_calendar_freshness_policy_revision.revision"],
        name="fk_calendar_freshness_policy_head_current",
    ),
)


personal_calendar_model_route_binding = Table(
    "personal_calendar_model_route_binding",
    metadata,
    Column("route_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("provider_binding_ref", String(256), nullable=False),
    Column("model_ref", String(256), nullable=False),
    Column("route_contract_version", String(128), nullable=False),
    Column("data_handling_contract_version", String(128), nullable=False),
    Column("retention_class", String(128), nullable=False),
    Column("residency_class", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "provider_binding_ref", "model_ref", "route_contract_version",
        name="uq_calendar_model_route_contract",
    ),
)

personal_calendar_model_route_state = Table(
    "personal_calendar_model_route_state",
    metadata,
    Column("route_binding_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_model_route_binding.route_binding_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["route_binding_id", "parent_revision"],
        ["personal_calendar_model_route_state.route_binding_id", "personal_calendar_model_route_state.revision"],
        name="fk_calendar_model_route_state_parent",
    ),
    CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_calendar_model_route_state_status_f5"),
)

personal_calendar_model_route_head = Table(
    "personal_calendar_model_route_head",
    metadata,
    Column("route_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["route_binding_id", "current_revision"],
        ["personal_calendar_model_route_state.route_binding_id", "personal_calendar_model_route_state.revision"],
        name="fk_calendar_model_route_head_current",
    ),
)


personal_calendar_model_egress_policy_revision = Table(
    "personal_calendar_model_egress_policy_revision",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("policy_version", String(128), nullable=False),
    Column("allowed_route_binding_ids_json", JSON, nullable=False),
    Column("required_retention_class", String(128), nullable=False),
    Column("required_residency_class", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "parent_revision"],
        ["personal_calendar_model_egress_policy_revision.relationship_id", "personal_calendar_model_egress_policy_revision.revision"],
        name="fk_calendar_model_egress_policy_parent",
    ),
    CheckConstraint("status IN ('ALLOW', 'DENY')", name="ck_calendar_model_egress_policy_status_f5"),
)

personal_calendar_model_egress_policy_head = Table(
    "personal_calendar_model_egress_policy_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        ["personal_calendar_model_egress_policy_revision.relationship_id", "personal_calendar_model_egress_policy_revision.revision"],
        name="fk_calendar_model_egress_policy_head_current",
    ),
)


personal_calendar_freshness_decision = Table(
    "personal_calendar_freshness_decision",
    metadata,
    Column("freshness_decision_id", Uuid(as_uuid=True), primary_key=True),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_world_result.world_result_id"), nullable=False),
    Column("decision_purpose", String(32), nullable=False),
    Column("policy_revision", BigInteger, nullable=False),
    Column("policy_version", String(128), nullable=False),
    Column("freshness_anchor_at", DateTime(timezone=True), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    Column("max_age_seconds", Integer, nullable=False),
    Column("age_seconds", Integer, nullable=False),
    Column("eligible", Boolean, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "policy_revision"],
        ["personal_calendar_freshness_policy_revision.relationship_id", "personal_calendar_freshness_policy_revision.revision"],
        name="fk_calendar_freshness_decision_policy",
    ),
    CheckConstraint("decision_purpose IN ('BUILD_PROJECTION', 'MODEL_EGRESS')", name="ck_calendar_freshness_decision_purpose_f5"),
    CheckConstraint("max_age_seconds >= 0 AND age_seconds >= 0", name="ck_calendar_freshness_decision_age_f5"),
)


personal_calendar_context_projection = Table(
    "personal_calendar_context_projection",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("context_projection.projection_id"), primary_key=True),
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_world_result.world_result_id"), nullable=False),
    Column("source_interaction_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id"), nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), ForeignKey("personal_resource_binding.personal_resource_binding_id"), nullable=False),
    Column("freshness_decision_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_freshness_decision.freshness_decision_id"), nullable=False),
    Column("requested_local_date", String(10), nullable=False),
    Column("calendar_timezone", String(128), nullable=False),
    Column("projection_contract_version", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index("ix_calendar_projection_world_result", personal_calendar_context_projection.c.world_result_id)

personal_calendar_projection_occurrence = Table(
    "personal_calendar_projection_occurrence",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_context_projection.projection_id"), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("occurrence_ref", String(64), nullable=False),
    Column("source_occurrence_ref", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("start_at", DateTime(timezone=True), nullable=False),
    Column("end_at", DateTime(timezone=True), nullable=False),
    Column("all_day", Boolean, nullable=False),
    Column("all_day_start_date", String(10)),
    Column("all_day_end_date_exclusive", String(10)),
    UniqueConstraint("projection_id", "occurrence_ref", name="uq_calendar_projection_occurrence_ref"),
    UniqueConstraint("projection_id", "source_occurrence_ref", name="uq_calendar_projection_source_occurrence_ref"),
    CheckConstraint("ordinal >= 0", name="ck_calendar_projection_occurrence_ordinal_f5"),
)


personal_calendar_model_egress_decision = Table(
    "personal_calendar_model_egress_decision",
    metadata,
    Column("egress_decision_id", Uuid(as_uuid=True), primary_key=True),
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_context_projection.projection_id"), nullable=False),
    Column("freshness_decision_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_freshness_decision.freshness_decision_id"), nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), nullable=False),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column("permission_id", Uuid(as_uuid=True), nullable=False),
    Column("permission_state_revision", BigInteger, nullable=False),
    Column("read_policy_revision", BigInteger, nullable=False),
    Column("egress_policy_revision", BigInteger, nullable=False),
    Column("route_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("route_state_revision", BigInteger, nullable=False),
    Column("route_contract_version", String(128), nullable=False),
    Column("data_handling_contract_version", String(128), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        ["personal_world_relationship_state.relationship_id", "personal_world_relationship_state.revision"],
        name="fk_calendar_egress_relationship_state",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        ["personal_resource_binding_state.personal_resource_binding_id", "personal_resource_binding_state.revision"],
        name="fk_calendar_egress_resource_state",
    ),
    ForeignKeyConstraint(
        ["permission_id", "permission_state_revision"],
        ["permission_state.permission_id", "permission_state.revision"],
        name="fk_calendar_egress_permission_state",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "read_policy_revision"],
        ["personal_calendar_read_policy_revision.relationship_id", "personal_calendar_read_policy_revision.revision"],
        name="fk_calendar_egress_read_policy",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "egress_policy_revision"],
        ["personal_calendar_model_egress_policy_revision.relationship_id", "personal_calendar_model_egress_policy_revision.revision"],
        name="fk_calendar_egress_policy",
    ),
    ForeignKeyConstraint(
        ["route_binding_id", "route_state_revision"],
        ["personal_calendar_model_route_state.route_binding_id", "personal_calendar_model_route_state.revision"],
        name="fk_calendar_egress_route_state",
    ),
)


personal_calendar_model_invocation = Table(
    "personal_calendar_model_invocation",
    metadata,
    Column("model_invocation_id", Uuid(as_uuid=True), ForeignKey("model_invocation.model_invocation_id"), primary_key=True),
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_context_projection.projection_id"), nullable=False),
    Column("egress_decision_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_model_egress_decision.egress_decision_id"), nullable=False, unique=True),
    Column("route_binding_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_model_route_binding.route_binding_id"), nullable=False),
    Column("plan_schema_version", String(128), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("dispatched_at", DateTime(timezone=True), nullable=False),
)

personal_calendar_generated_output = Table(
    "personal_calendar_generated_output",
    metadata,
    Column("generated_output_id", Uuid(as_uuid=True), ForeignKey("generated_output.generated_output_id"), primary_key=True),
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_context_projection.projection_id"), nullable=False),
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_world_result.world_result_id"), nullable=False),
    Column("plan_schema_version", String(128), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("validated_shape_at", DateTime(timezone=True), nullable=False),
)

personal_calendar_companion_output = Table(
    "personal_calendar_companion_output",
    metadata,
    Column("companion_output_id", Uuid(as_uuid=True), ForeignKey("companion_output.companion_output_id"), primary_key=True),
    Column("generated_output_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_generated_output.generated_output_id"), nullable=False, unique=True),
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_context_projection.projection_id"), nullable=False),
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("personal_calendar_world_result.world_result_id"), nullable=False),
    Column("rendering_contract_version", String(128), nullable=False),
    Column("deterministic_render_digest", String(64), nullable=False),
)
