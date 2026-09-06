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

metadata = MetaData()

companion_person = Table(
    "companion_person",
    metadata,
    Column("person_id", Uuid(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

self_revision = Table(
    "self_revision",
    metadata,
    Column("person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("role", String(64), nullable=False),
    Column("preferred_name", String(128), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["person_id", "parent_revision"],
        ["self_revision.person_id", "self_revision.revision"],
        name="fk_self_revision_parent",
    ),
)

self_head = Table(
    "self_head",
    metadata,
    Column("person_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["person_id", "current_revision"],
        ["self_revision.person_id", "self_revision.revision"],
        name="fk_self_head_current",
    ),
)

counterpart_person = Table(
    "counterpart_person",
    metadata,
    Column("counterpart_id", Uuid(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

counterpart_identity_binding = Table(
    "counterpart_identity_binding",
    metadata,
    Column("binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("identity_namespace", String(128), nullable=False),
    Column("external_subject", String(256), nullable=False),
    Column("bound_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("identity_namespace", "external_subject", name="uq_counterpart_external_identity"),
)

relationship_identity = Table(
    "relationship_identity",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("companion_person_id", "counterpart_id", name="uq_relationship_pair"),
)

relationship_revision = Table(
    "relationship_revision",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), primary_key=True),
    Column("revision", BigInteger, primary_key=True),
    Column("parent_revision", BigInteger),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "parent_revision"],
        ["relationship_revision.relationship_id", "relationship_revision.revision"],
        name="fk_relationship_revision_parent",
    ),
)

relationship_head = Table(
    "relationship_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), primary_key=True),
    Column("current_revision", BigInteger, nullable=False),
    ForeignKeyConstraint(
        ["relationship_id", "current_revision"],
        ["relationship_revision.relationship_id", "relationship_revision.revision"],
        name="fk_relationship_head_current",
    ),
)

surface_binding = Table(
    "surface_binding",
    metadata,
    Column("surface_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("surface_namespace", String(128), nullable=False),
    Column("surface_ref", String(256), nullable=False),
    Column("bound_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("surface_namespace", "surface_ref", name="uq_surface_ref"),
)

channel_binding = Table(
    "channel_binding",
    metadata,
    Column("channel_binding_id", Uuid(as_uuid=True), primary_key=True),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("channel_namespace", String(128), nullable=False),
    Column("companion_endpoint_ref", String(256), nullable=False),
    Column("bound_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("channel_namespace", "companion_endpoint_ref", name="uq_channel_endpoint"),
)

relationship_timeline_head = Table(
    "relationship_timeline_head",
    metadata,
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), primary_key=True),
    Column("last_timeline_seq", BigInteger, nullable=False),
)

interaction_event = Table(
    "interaction_event",
    metadata,
    Column("event_id", Uuid(as_uuid=True), primary_key=True),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("timeline_seq", BigInteger, nullable=False),
    Column("actor_kind", String(32), nullable=False),
    Column("actor_ref", Uuid(as_uuid=True), nullable=False),
    Column("event_kind", String(64), nullable=False),
    Column("content_text", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("conversation_id", String(256)),
    Column("surface_binding_id", Uuid(as_uuid=True), ForeignKey("surface_binding.surface_binding_id")),
    Column("channel_binding_id", Uuid(as_uuid=True), ForeignKey("channel_binding.channel_binding_id")),
    Column("companion_output_id", Uuid(as_uuid=True)),
    Column("reply_to_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id")),
    Column("ingress_idempotency_key", String(256)),
    UniqueConstraint("relationship_id", "timeline_seq", name="uq_relationship_timeline_seq"),
    UniqueConstraint("relationship_id", "ingress_idempotency_key", name="uq_relationship_ingress_key"),
    CheckConstraint("event_kind IN ('COUNTERPART_INPUT', 'COMPANION_PRESENTED_OUTPUT')", name="ck_event_kind_f4"),
    CheckConstraint("actor_kind IN ('COMPANION', 'COUNTERPART')", name="ck_actor_kind_f4"),
)

content_blob = Table(
    "content_blob",
    metadata,
    Column("content_digest", String(64), primary_key=True),
    Column("content_text", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)

evidence_item = Table(
    "evidence_item",
    metadata,
    Column("evidence_id", Uuid(as_uuid=True), primary_key=True),
    Column("origin_kind", String(64), nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("source_id", Uuid(as_uuid=True), nullable=False),
    Column("source_locator", Text),
    Column("source_actor_ref", Uuid(as_uuid=True)),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("origin_kind IN ('COUNTERPART_STATEMENT', 'SEARCH_RESULT')", name="ck_evidence_origin_f4"),
)

claim = Table(
    "claim",
    metadata,
    Column("claim_id", Uuid(as_uuid=True), primary_key=True),
    Column("holder_companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("subject_counterpart_id", Uuid(as_uuid=True), ForeignKey("counterpart_person.counterpart_id"), nullable=False),
    Column("memory_scope_kind", String(32), nullable=False),
    Column("memory_scope_ref", Uuid(as_uuid=True), nullable=False),
    Column("claim_domain", String(32), nullable=False),
    Column("claim_kind", String(32), nullable=False),
    Column("predicate", String(256), nullable=False),
    Column("value_json", JSON, nullable=False),
    Column("valid_from", DateTime(timezone=True)),
    Column("admitted_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("memory_scope_kind = 'RELATIONSHIP'", name="ck_claim_scope_f4"),
    CheckConstraint("claim_domain = 'PERSON'", name="ck_claim_domain_f4"),
    CheckConstraint("claim_kind = 'FACTUAL'", name="ck_claim_kind_f4"),
)

claim_evidence = Table(
    "claim_evidence",
    metadata,
    Column("claim_id", Uuid(as_uuid=True), ForeignKey("claim.claim_id"), primary_key=True),
    Column("evidence_id", Uuid(as_uuid=True), ForeignKey("evidence_item.evidence_id"), primary_key=True),
    Column("relation", String(32), primary_key=True),
    CheckConstraint("relation IN ('SUPPORTS', 'CONTRADICTS')", name="ck_claim_evidence_relation"),
)

claim_supersession = Table(
    "claim_supersession",
    metadata,
    Column("newer_claim_id", Uuid(as_uuid=True), ForeignKey("claim.claim_id"), primary_key=True),
    Column("older_claim_id", Uuid(as_uuid=True), ForeignKey("claim.claim_id"), primary_key=True),
    Column("relation", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("relation IN ('TEMPORALLY_SUCCEEDS', 'CORRECTS')", name="ck_claim_supersession_relation"),
)

investigation = Table(
    "investigation",
    metadata,
    Column("investigation_id", Uuid(as_uuid=True), primary_key=True),
    Column("initiated_by_companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id")),
    Column("conversation_id", String(256)),
    Column("objective", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    CheckConstraint("status IN ('OPEN', 'SUCCEEDED', 'FAILED')", name="ck_investigation_status_f4"),
)

observation = Table(
    "observation",
    metadata,
    Column("observation_id", Uuid(as_uuid=True), primary_key=True),
    Column("investigation_id", Uuid(as_uuid=True), ForeignKey("investigation.investigation_id"), nullable=False),
    Column("acquisition_kind", String(64), nullable=False),
    Column("request_descriptor_json", JSON, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    CheckConstraint("status IN ('STARTED', 'SUCCEEDED', 'FAILED')", name="ck_observation_status_f4"),
)

world_source_capture = Table(
    "world_source_capture",
    metadata,
    Column("source_capture_id", Uuid(as_uuid=True), primary_key=True),
    Column("observation_id", Uuid(as_uuid=True), ForeignKey("observation.observation_id"), nullable=False, unique=True),
    Column("capture_kind", String(64), nullable=False),
    Column("source_identity", Text, nullable=False),
    Column("requested_locator", Text),
    Column("resolved_locator", Text),
    Column("source_version", String(256)),
    Column("source_published_at", DateTime(timezone=True)),
    Column("source_modified_at", DateTime(timezone=True)),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("content_ref", String(256), nullable=False),
    Column("content_digest", String(64), nullable=False),
)

world_result = Table(
    "world_result",
    metadata,
    Column("world_result_id", Uuid(as_uuid=True), primary_key=True),
    Column("investigation_id", Uuid(as_uuid=True), ForeignKey("investigation.investigation_id"), nullable=False),
    Column("result_kind", String(64), nullable=False),
    Column("predicate", String(256), nullable=False),
    Column("value_json", JSON, nullable=False),
    Column("valid_as_of", DateTime(timezone=True)),
    Column("derived_at", DateTime(timezone=True), nullable=False),
)

world_result_evidence = Table(
    "world_result_evidence",
    metadata,
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("world_result.world_result_id"), primary_key=True),
    Column("evidence_id", Uuid(as_uuid=True), ForeignKey("evidence_item.evidence_id"), primary_key=True),
    Column("relation", String(32), primary_key=True),
    CheckConstraint("relation IN ('SUPPORTS', 'CONTRADICTS')", name="ck_world_result_evidence_relation"),
)

context_projection = Table(
    "context_projection",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), primary_key=True),
    Column("projection_schema_version", Integer, nullable=False),
    Column("purpose", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id")),
    Column("current_input_event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id")),
    Column("source_self_revision", BigInteger, nullable=False),
    Column("source_relationship_revision", BigInteger),
    Column("source_timeline_frontier", BigInteger),
    Column("manifest_digest", String(64), nullable=False),
    ForeignKeyConstraint(
        ["companion_person_id", "source_self_revision"],
        ["self_revision.person_id", "self_revision.revision"],
        name="fk_projection_self_revision",
    ),
    ForeignKeyConstraint(
        ["relationship_id", "source_relationship_revision"],
        ["relationship_revision.relationship_id", "relationship_revision.revision"],
        name="fk_projection_relationship_revision",
    ),
)

context_projection_event = Table(
    "context_projection_event",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("context_projection.projection_id"), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("event_id", Uuid(as_uuid=True), ForeignKey("interaction_event.event_id"), nullable=False),
    UniqueConstraint("projection_id", "event_id", name="uq_projection_event"),
)

context_projection_personal_item = Table(
    "context_projection_personal_item",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("context_projection.projection_id"), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("claim_id", Uuid(as_uuid=True), ForeignKey("claim.claim_id"), nullable=False),
    Column("epistemic_basis", String(64), nullable=False),
    UniqueConstraint("projection_id", "claim_id", name="uq_projection_claim"),
)

context_projection_personal_support = Table(
    "context_projection_personal_support",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), primary_key=True),
    Column("personal_ordinal", Integer, primary_key=True),
    Column("evidence_id", Uuid(as_uuid=True), ForeignKey("evidence_item.evidence_id"), primary_key=True),
    ForeignKeyConstraint(
        ["projection_id", "personal_ordinal"],
        ["context_projection_personal_item.projection_id", "context_projection_personal_item.ordinal"],
        name="fk_projection_personal_support_item",
    ),
)

context_projection_world_item = Table(
    "context_projection_world_item",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), ForeignKey("context_projection.projection_id"), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("world_result_id", Uuid(as_uuid=True), ForeignKey("world_result.world_result_id"), nullable=False),
    Column("investigation_id", Uuid(as_uuid=True), ForeignKey("investigation.investigation_id"), nullable=False),
    Column("epistemic_mode", String(64), nullable=False),
    UniqueConstraint("projection_id", "world_result_id", name="uq_projection_world_result"),
)

context_projection_world_support = Table(
    "context_projection_world_support",
    metadata,
    Column("projection_id", Uuid(as_uuid=True), primary_key=True),
    Column("world_ordinal", Integer, primary_key=True),
    Column("evidence_id", Uuid(as_uuid=True), ForeignKey("evidence_item.evidence_id"), primary_key=True),
    ForeignKeyConstraint(
        ["projection_id", "world_ordinal"],
        ["context_projection_world_item.projection_id", "context_projection_world_item.ordinal"],
        name="fk_projection_world_support_item",
    ),
)

model_invocation = Table(
    "model_invocation",
    metadata,
    Column("model_invocation_id", Uuid(as_uuid=True), primary_key=True),
    Column("context_projection_id", Uuid(as_uuid=True), ForeignKey("context_projection.projection_id"), nullable=False),
    Column("provider_binding_ref", String(256), nullable=False),
    Column("model_ref", String(256), nullable=False),
    Column("renderer_version", String(128), nullable=False),
    Column("provider_request_digest", String(64), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("outcome", String(32), nullable=False),
    CheckConstraint("outcome IN ('IN_PROGRESS', 'SUCCEEDED', 'FAILED', 'UNKNOWN')", name="ck_model_invocation_outcome_f4"),
)

generated_output = Table(
    "generated_output",
    metadata,
    Column("generated_output_id", Uuid(as_uuid=True), primary_key=True),
    Column("model_invocation_id", Uuid(as_uuid=True), ForeignKey("model_invocation.model_invocation_id"), nullable=False, unique=True),
    Column("content_text", Text, nullable=False),
    Column("content_digest", String(64), nullable=False),
    Column("semantic_payload_json", JSON, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
)

output_target = Table(
    "output_target",
    metadata,
    Column("output_target_id", Uuid(as_uuid=True), primary_key=True),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("target_kind", String(64), nullable=False),
    Column("target_ref", Uuid(as_uuid=True), nullable=False),
    Column("purpose", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("relationship_id", "target_kind", "target_ref", "purpose", name="uq_output_target_semantic_slot"),
)

companion_output = Table(
    "companion_output",
    metadata,
    Column("companion_output_id", Uuid(as_uuid=True), primary_key=True),
    Column("companion_person_id", Uuid(as_uuid=True), ForeignKey("companion_person.person_id"), nullable=False),
    Column("relationship_id", Uuid(as_uuid=True), ForeignKey("relationship_identity.relationship_id"), nullable=False),
    Column("output_target_id", Uuid(as_uuid=True), ForeignKey("output_target.output_target_id"), nullable=False, unique=True),
    Column("origin_kind", String(64), nullable=False),
    Column("origin_ref", Uuid(as_uuid=True), nullable=False),
    Column("source_generated_output_id", Uuid(as_uuid=True), ForeignKey("generated_output.generated_output_id"), nullable=False),
    Column("content_text", Text, nullable=False),
    Column("content_digest", String(64), nullable=False),
    Column("semantic_payload_json", JSON, nullable=False),
    Column("adopted_at", DateTime(timezone=True), nullable=False),
)

operation_receipt = Table(
    "operation_receipt",
    metadata,
    Column("operation_scope", String(128), primary_key=True),
    Column("operation_id", Uuid(as_uuid=True), primary_key=True),
    Column("request_digest", String(64), nullable=False),
    Column("result_kind", String(128), nullable=False),
    Column("result_ref", Uuid(as_uuid=True), nullable=False),
    Column("result_json", JSON, nullable=False),
    Column("committed_at", DateTime(timezone=True), nullable=False),
)

Index(
    "ix_interaction_relationship_seq",
    interaction_event.c.relationship_id,
    interaction_event.c.timeline_seq,
)
Index(
    "ix_claim_subject_predicate",
    claim.c.holder_companion_person_id,
    claim.c.subject_counterpart_id,
    claim.c.predicate,
)
Index("ix_claim_evidence_claim", claim_evidence.c.claim_id)
Index("ix_claim_supersession_older", claim_supersession.c.older_claim_id)
Index("ix_observation_investigation", observation.c.investigation_id)
Index("ix_world_result_investigation_predicate", world_result.c.investigation_id, world_result.c.predicate)
Index("ix_model_invocation_projection", model_invocation.c.context_projection_id)
Index(
    "ux_presented_companion_output",
    interaction_event.c.companion_output_id,
    unique=True,
    sqlite_where=interaction_event.c.companion_output_id.is_not(None),
    postgresql_where=interaction_event.c.companion_output_id.is_not(None),
)
