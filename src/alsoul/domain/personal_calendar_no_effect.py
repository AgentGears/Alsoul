from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from alsoul.domain.personal_calendar_reconciliation import (
    PersonalCalendarCreateReconciliationRequest,
)


CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION = (
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_V1"
)
CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION = (
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_V1"
)
CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION = (
    "CALENDAR_CREATE_NO_EFFECT_EVIDENCE_V1"
)
CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION = "CALENDAR_CREATE_NO_EFFECT_V1"
CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND = "SUPPORTS"
CALENDAR_CREATE_RETRY_CONTRACT_VERSION = "CALENDAR_CREATE_RETRY_V1"


@dataclass(frozen=True, slots=True)
class CalendarCreateNegativeConfirmationContract:
    """Trusted terminal-negative semantics for one fenced create ExecutionAttempt."""

    read_capability_contract_version: str
    correlation_contract_version: str
    contract_version: str = CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
    response_schema_version: str = (
        CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION
    )
    semantic_operation: str = "calendar.events.read"
    effect_class: str = "READ_ONLY"
    lookup_mode: str = "ACTION_CORRELATION_TERMINAL_STATUS"
    terminal_operation_status: str = "TERMINAL_NOT_APPLIED"
    terminality_scope: str = "EXACT_EXECUTION_ATTEMPT"
    delayed_application_mode: str = "PROHIBITED_AFTER_TERMINAL"
    intended_effect_absence_mode: str = "ACTION_CORRELATION_AUTHORITATIVE"
    retry_correlation_mode: str = "REUSE_ACTION_CORRELATION_AFTER_TERMINAL"
    raw_response_minimization_mode: str = "EPHEMERAL_TO_ALLOWLIST"


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateNegativeConfirmationRequest:
    authority_fence_id: UUID
    reconciliation_probe_id: UUID
    execution_attempt_id: UUID
    action_id: UUID
    external_system_ref: str
    external_resource_ref: str
    correlation_key: str
    credential_secret_ref: str
    correlation_contract_version: str
    negative_confirmation_contract_version: str = (
        CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
    )

    @classmethod
    def from_reconciliation_request(
        cls, request: PersonalCalendarCreateReconciliationRequest
    ) -> "PersonalCalendarCreateNegativeConfirmationRequest":
        return cls(
            authority_fence_id=request.authority_fence_id,
            reconciliation_probe_id=request.reconciliation_probe_id,
            execution_attempt_id=request.execution_attempt_id,
            action_id=request.action_id,
            external_system_ref=request.external_system_ref,
            external_resource_ref=request.external_resource_ref,
            correlation_key=request.correlation_key,
            credential_secret_ref=request.credential_secret_ref,
            correlation_contract_version=request.correlation_contract_version,
        )


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateTerminalNoEffectObservation:
    status: Literal["TERMINAL_NO_EFFECT", "INCONCLUSIVE"]
    correlation_key: str
    observed_at: datetime
    intended_effect_absent: bool
    terminal_non_application: bool
    terminality_scope: str
    operation_status: str
    terminality_proof_ref: str | None = None
    absence_proof_ref: str | None = None
    response_schema_version: str = (
        CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION
    )


@runtime_checkable
class PersonalCalendarCreateNegativeConfirmationAdapter(Protocol):
    adapter_binding_ref: str
    adapter_version: str
    read_capability_contract_version: str
    correlation_contract_version: str
    negative_confirmation_contract_version: str
    external_system_ref: str

    def lookup_terminal_no_effect(
        self, request: PersonalCalendarCreateNegativeConfirmationRequest
    ) -> PersonalCalendarCreateTerminalNoEffectObservation:
        ...


@dataclass(frozen=True, slots=True)
class ReconcilePersonalCalendarCreateNoEffectCommand:
    operation_id: UUID
    execution_attempt_id: UUID
    permission_id: UUID
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateConfirmedNoEffectResult:
    no_effect_id: UUID
    no_effect_evidence_id: UUID
    reconciliation_probe_id: UUID
    execution_attempt_id: UUID
    action_id: UUID
    status: Literal["CONFIRMED_NO_EFFECT"] = "CONFIRMED_NO_EFFECT"


@dataclass(frozen=True, slots=True)
class PreparePersonalCalendarCreateRetryAttemptCommand:
    operation_id: UUID
    prior_execution_attempt_id: UUID
    approval_id: UUID
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateRetryAttemptResult:
    execution_attempt_id: UUID
    prior_execution_attempt_id: UUID
    action_id: UUID
    no_effect_id: UUID
    attempt_generation: int
    correlation_key: str
    status: Literal["PREPARED"]
    guard_revision: int
    retry_contract_version: str = CALENDAR_CREATE_RETRY_CONTRACT_VERSION


__all__ = [
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION",
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION",
    "CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION",
    "CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION",
    "CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND",
    "CALENDAR_CREATE_RETRY_CONTRACT_VERSION",
    "CalendarCreateNegativeConfirmationContract",
    "PersonalCalendarCreateConfirmedNoEffectResult",
    "PersonalCalendarCreateNegativeConfirmationAdapter",
    "PersonalCalendarCreateNegativeConfirmationRequest",
    "PersonalCalendarCreateRetryAttemptResult",
    "PersonalCalendarCreateTerminalNoEffectObservation",
    "PreparePersonalCalendarCreateRetryAttemptCommand",
    "ReconcilePersonalCalendarCreateNoEffectCommand",
]
