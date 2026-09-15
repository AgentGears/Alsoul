from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID


CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION = (
    "CALENDAR_CREATE_RECONCILIATION_V1"
)
CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION = (
    "CALENDAR_CREATE_RECONCILIATION_RESPONSE_V1"
)


@dataclass(frozen=True, slots=True)
class CalendarCreateReconciliationContract:
    read_capability_contract_version: str
    correlation_contract_version: str
    max_probes: int
    contract_version: str = CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION
    response_schema_version: str = (
        CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION
    )
    semantic_operation: str = "calendar.events.read"
    effect_class: str = "READ_ONLY"
    lookup_mode: str = "ACTION_CORRELATION"
    raw_response_minimization_mode: str = "EPHEMERAL_TO_ALLOWLIST"


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateReconciliationRequest:
    authority_fence_id: UUID
    reconciliation_probe_id: UUID
    execution_attempt_id: UUID
    action_id: UUID
    external_system_ref: str
    external_resource_ref: str
    correlation_key: str
    credential_secret_ref: str
    correlation_contract_version: str
    reconciliation_contract_version: str = (
        CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION
    )


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateReconciliationObservation:
    status: Literal["FOUND", "NOT_FOUND"]
    correlation_key: str
    observed_at: datetime
    external_effect_ref: str | None = None
    external_system_ref: str | None = None
    external_resource_ref: str | None = None
    summary: str | None = None
    normalized_start_at: datetime | None = None
    normalized_end_at: datetime | None = None
    provider_status: str | None = None
    receipt_ref: str | None = None
    response_schema_version: str = (
        CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION
    )


@runtime_checkable
class PersonalCalendarCreateReconciliationAdapter(Protocol):
    adapter_binding_ref: str
    adapter_version: str
    read_capability_contract_version: str
    correlation_contract_version: str
    external_system_ref: str

    def lookup_create_effect(
        self, request: PersonalCalendarCreateReconciliationRequest
    ) -> PersonalCalendarCreateReconciliationObservation:
        ...


@dataclass(frozen=True, slots=True)
class ReconcilePersonalCalendarCreateUnknownEffectCommand:
    operation_id: UUID
    execution_attempt_id: UUID
    permission_id: UUID
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateReconciliationResult:
    reconciliation_probe_id: UUID
    execution_attempt_id: UUID
    action_id: UUID
    status: Literal[
        "MATCHED_EFFECT_EVIDENCE",
        "DIVERGENT_EFFECT_EVIDENCE",
        "UNKNOWN_EFFECT",
    ]
    effect_evidence_id: UUID | None


__all__ = [
    "CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION",
    "CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION",
    "CalendarCreateReconciliationContract",
    "PersonalCalendarCreateReconciliationAdapter",
    "PersonalCalendarCreateReconciliationObservation",
    "PersonalCalendarCreateReconciliationRequest",
    "PersonalCalendarCreateReconciliationResult",
    "ReconcilePersonalCalendarCreateUnknownEffectCommand",
]
