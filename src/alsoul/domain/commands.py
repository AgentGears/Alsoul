from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AppendCounterpartInputCommand:
    operation_id: UUID
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    ingress_idempotency_key: str
    content_text: str
    occurred_at: datetime
    surface_binding_id: UUID
    channel_binding_id: UUID
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class AdmitPersonMemoryClaimCommand:
    operation_id: UUID
    holder_companion_person_id: UUID
    subject_counterpart_id: UUID
    relationship_id: UUID
    predicate: str
    value: Any
    source_event_id: UUID
    correction_of_claim_id: UUID | None = None
    valid_from: datetime | None = None


@dataclass(frozen=True, slots=True)
class StartInvestigationCommand:
    operation_id: UUID
    initiated_by_companion_person_id: UUID
    relationship_id: UUID | None
    objective: str
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartObservationCommand:
    operation_id: UUID
    investigation_id: UUID
    acquisition_kind: str
    request_descriptor: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RecordObservationSuccessCommand:
    operation_id: UUID
    observation_id: UUID
    source_identity: str
    requested_locator: str | None
    resolved_locator: str | None
    content_text: str
    captured_at: datetime
    source_version: str | None = None
    source_published_at: datetime | None = None
    source_modified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AdmitWorldResultCommand:
    operation_id: UUID
    investigation_id: UUID
    result_kind: str
    predicate: str
    value: Any
    support_evidence_ids: tuple[UUID, ...]
    contradiction_evidence_ids: tuple[UUID, ...] = ()
    valid_as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class BuildContextProjectionCommand:
    operation_id: UUID
    companion_person_id: UUID
    relationship_id: UUID
    current_input_event_id: UUID
    required_personal_predicates: tuple[str, ...]
    required_world_result_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class StartModelInvocationCommand:
    operation_id: UUID
    context_projection_id: UUID
    provider_binding_ref: str
    model_ref: str
    renderer_version: str
    provider_request_digest: str


@dataclass(frozen=True, slots=True)
class CompleteModelInvocationCommand:
    operation_id: UUID
    model_invocation_id: UUID
    content_text: str
    content_digest: str
    semantic_payload: dict[str, Any]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class ResolveOutputTargetCommand:
    operation_id: UUID
    relationship_id: UUID
    target_kind: str
    target_ref: UUID
    purpose: str


@dataclass(frozen=True, slots=True)
class AdoptCompanionOutputCommand:
    operation_id: UUID
    companion_person_id: UUID
    relationship_id: UUID
    output_target_id: UUID
    origin_kind: str
    origin_ref: UUID
    generated_output_id: UUID


@dataclass(frozen=True, slots=True)
class PresentCompanionOutputCommand:
    operation_id: UUID
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID
    presented_at: datetime
