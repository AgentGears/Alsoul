from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION = "CALENDAR_CREATE_ACTION_CORRELATION_V1"
CALENDAR_CREATE_ACTION_CONSTRAINT_VERSION = "CALENDAR_CREATE_ACTION_CONSTRAINTS_V1"
CALENDAR_CREATE_APPROVER_ELIGIBILITY_VERSION = "FIRST_PARTY_COUNTERPART_APPROVER_V1"
CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION = (
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_V1"
)


@dataclass(frozen=True, slots=True)
class CalendarCreateExecutionBinding:
    """Trusted non-secret execution semantics selected by the host composition.

    The binding is configuration, not authority. The execution service revalidates all
    mutable Action authority independently and persists these exact semantics only when
    the dispatch fence commits.
    """

    adapter_binding_ref: str
    adapter_contract_version: str
    executor_contract_version: str
    correlation_contract_version: str
    negative_confirmation_contract_version: str
    capability_contract_version: str
    external_system_ref: str


@dataclass(frozen=True, slots=True)
class PreparePersonalCalendarCreateExecutionAttemptCommand:
    operation_id: UUID
    action_id: UUID
    approval_id: UUID
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class FencePersonalCalendarCreateExecutionAttemptCommand:
    operation_id: UUID
    execution_attempt_id: UUID


@dataclass(frozen=True, slots=True)
class AbandonPersonalCalendarCreateExecutionAttemptCommand:
    operation_id: UUID
    execution_attempt_id: UUID


@dataclass(frozen=True, slots=True)
class RecoverPersonalCalendarCreateFencedAttemptCommand:
    operation_id: UUID
    execution_attempt_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateExecutionAttemptResult:
    execution_attempt_id: UUID
    action_id: UUID
    attempt_generation: int
    correlation_key: str
    status: Literal["PREPARED", "ABANDONED"]
    guard_revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateExecutionFenceResult:
    execution_attempt_id: UUID
    action_id: UUID
    attempt_generation: int
    correlation_key: str
    status: Literal["DISPATCH_FENCED", "UNKNOWN_EFFECT"]
    guard_revision: int
    adapter_binding_ref: str
    adapter_contract_version: str
    executor_contract_version: str
    correlation_contract_version: str
    negative_confirmation_contract_version: str
    dispatch_fenced_at: datetime


__all__ = [
    "AbandonPersonalCalendarCreateExecutionAttemptCommand",
    "CALENDAR_CREATE_ACTION_CONSTRAINT_VERSION",
    "CALENDAR_CREATE_APPROVER_ELIGIBILITY_VERSION",
    "CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION",
    "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION",
    "CalendarCreateExecutionBinding",
    "FencePersonalCalendarCreateExecutionAttemptCommand",
    "PersonalCalendarCreateExecutionAttemptResult",
    "PersonalCalendarCreateExecutionFenceResult",
    "PreparePersonalCalendarCreateExecutionAttemptCommand",
    "RecoverPersonalCalendarCreateFencedAttemptCommand",
]
