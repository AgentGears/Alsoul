from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID


CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION = (
    "CALENDAR_CREATE_MUTATION_REQUEST_V1"
)
CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION = (
    "CALENDAR_CREATE_EFFECT_EVIDENCE_V1"
)


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateMutationRequest:
    """Exact minimized provider-bound request for one fenced calendar Action.

    The trusted adapter may translate these semantic fields to provider syntax and
    resolve ``credential_secret_ref`` ephemerally. No Approval, Permission,
    conversation, model, or unrelated personal-world state belongs in this request.
    """

    execution_attempt_id: UUID
    action_id: UUID
    external_system_ref: str
    external_resource_ref: str
    summary: str
    normalized_start_at: datetime
    normalized_end_at: datetime
    correlation_key: str
    credential_secret_ref: str
    capability_contract_version: str
    adapter_contract_version: str
    request_contract_version: str = CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateMutationResponse:
    """Normalized allowlisted positive provider response material.

    A response is not itself an Effect. The host still validates Action correlation
    and semantic equivalence before the material can support later Effect admission.
    Provider responses that cannot be normalized into this bounded shape are not
    durable mutation evidence.
    """

    correlation_key: str
    external_effect_ref: str
    external_system_ref: str
    external_resource_ref: str
    summary: str
    normalized_start_at: datetime
    normalized_end_at: datetime
    receipt_ref: str
    observed_at: datetime
    provider_status: Literal["CREATED"] = "CREATED"
    evidence_schema_version: str = CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION


@runtime_checkable
class PersonalCalendarCreateMutationAdapter(Protocol):
    """Trusted F5.B provider mutation boundary for one calendar-create attempt.

    The adapter is eligible only when its stable binding/contract identity matches
    the exact execution semantics already pinned by ``DISPATCH_FENCED``. It must
    enforce request/response minimization before non-canonical persistence or
    telemetry and must not implement an internal blind mutation retry.
    """

    adapter_binding_ref: str
    adapter_contract_version: str
    capability_contract_version: str
    external_system_ref: str

    def create_event(
        self, request: PersonalCalendarCreateMutationRequest
    ) -> PersonalCalendarCreateMutationResponse:
        ...


@dataclass(frozen=True, slots=True)
class DispatchPersonalCalendarCreateMutationCommand:
    operation_id: UUID
    execution_attempt_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateMutationTransportResult:
    execution_attempt_id: UUID
    action_id: UUID
    status: Literal[
        "MATCHED_EFFECT_EVIDENCE",
        "DIVERGENT_EFFECT_EVIDENCE",
        "UNKNOWN_EFFECT",
    ]
    effect_evidence_id: UUID | None


__all__ = [
    "CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION",
    "CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION",
    "DispatchPersonalCalendarCreateMutationCommand",
    "PersonalCalendarCreateMutationAdapter",
    "PersonalCalendarCreateMutationRequest",
    "PersonalCalendarCreateMutationResponse",
    "PersonalCalendarCreateMutationTransportResult",
]
