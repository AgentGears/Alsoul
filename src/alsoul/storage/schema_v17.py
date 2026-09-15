from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v16 as _schema_v16


metadata = MetaData()
for _table in _schema_v16.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v16).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_mutation_disclosure_decision = Table(
    "personal_calendar_mutation_disclosure_decision",
    metadata,
    Column("disclosure_decision_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_adoption.companion_output_id"),
        nullable=False,
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
    Column(
        "effect_evidence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_create_effect_evidence.effect_evidence_id"),
        nullable=False,
    ),
    Column("relationship_id", Uuid(as_uuid=True), nullable=False),
    Column("relationship_authority_revision", BigInteger, nullable=False),
    Column("personal_resource_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("resource_binding_state_revision", BigInteger, nullable=False),
    Column("disclosure_policy_revision", BigInteger, nullable=False),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column("source_timeline_frontier", BigInteger, nullable=False),
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
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "relationship_authority_revision"],
        [
            "personal_world_relationship_state.relationship_id",
            "personal_world_relationship_state.revision",
        ],
        name="fk_calendar_mutation_disclosure_relationship_state",
    ),
    ForeignKeyConstraint(
        ["personal_resource_binding_id", "resource_binding_state_revision"],
        [
            "personal_resource_binding_state.personal_resource_binding_id",
            "personal_resource_binding_state.revision",
        ],
        name="fk_calendar_mutation_disclosure_resource_state",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "disclosure_policy_revision"],
        [
            "personal_calendar_disclosure_policy_revision.relationship_id",
            "personal_calendar_disclosure_policy_revision.revision",
        ],
        name="fk_calendar_mutation_disclosure_policy",
    ),
)


personal_calendar_mutation_presentation_attempt = Table(
    "personal_calendar_mutation_presentation_attempt",
    metadata,
    Column("presentation_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "companion_output_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_adoption.companion_output_id"),
        nullable=False,
    ),
    Column("presentation_key", String(128), nullable=False),
    Column("sink_binding_ref", String(128), nullable=False),
    Column("presentation_attempt_generation", Integer, nullable=False),
    Column(
        "presentation_transport_fence_scope_id",
        Uuid(as_uuid=True),
        nullable=False,
        unique=True,
    ),
    Column(
        "disclosure_decision_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_disclosure_decision.disclosure_decision_id"),
        nullable=False,
        unique=True,
    ),
    Column("surface_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("channel_binding_id", Uuid(as_uuid=True), nullable=False),
    Column("presentation_contract_version", String(128), nullable=False),
    Column("status_contract_version", String(128), nullable=False),
    Column("payload_digest", String(64), nullable=False),
    Column("dispatch_fenced_at", DateTime(timezone=True), nullable=False),
    Column("sink_acceptance_state", String(32), nullable=False),
    Column("settled_at", DateTime(timezone=True)),
    UniqueConstraint(
        "companion_output_id",
        "presentation_attempt_generation",
        name="uq_calendar_mutation_presentation_output_generation",
    ),
    UniqueConstraint(
        "presentation_key",
        "presentation_attempt_generation",
        name="uq_calendar_mutation_presentation_key_generation",
    ),
    CheckConstraint(
        "presentation_attempt_generation >= 1",
        name="ck_calendar_mutation_presentation_generation_f5b",
    ),
    CheckConstraint(
        "sink_acceptance_state IN ('UNKNOWN', 'ACCEPTED', 'NOT_ACCEPTED')",
        name="ck_calendar_mutation_presentation_state_f5b",
    ),
)


personal_calendar_mutation_presentation_status_evidence = Table(
    "personal_calendar_mutation_presentation_status_evidence",
    metadata,
    Column("status_evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "presentation_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_mutation_presentation_attempt.presentation_attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column("state", String(32), nullable=False),
    Column("receipt_ref", String(256)),
    Column("terminal_proof_kind", String(128)),
    Column("settled_through_ref", String(256)),
    Column("status_contract_version", String(128), nullable=False),
    Column("accepted_at", DateTime(timezone=True)),
    Column("proved_at", DateTime(timezone=True)),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "state IN ('ACCEPTED', 'NOT_ACCEPTED')",
        name="ck_calendar_mutation_presentation_evidence_state_f5b",
    ),
    CheckConstraint(
        "(state = 'ACCEPTED' AND receipt_ref IS NOT NULL) OR "
        "(state = 'NOT_ACCEPTED' AND terminal_proof_kind IS NOT NULL AND settled_through_ref IS NOT NULL)",
        name="ck_calendar_mutation_presentation_evidence_shape_f5b",
    ),
)
