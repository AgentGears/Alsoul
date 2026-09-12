from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION = "PERSONAL_CALENDAR_PRESENTATION_V1"
PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION = (
    "PERSONAL_CALENDAR_PRESENTATION_STATUS_V1"
)


@dataclass(frozen=True, slots=True)
class SetPersonalCalendarDisclosurePolicyCommand:
    operation_id: UUID
    relationship_id: UUID
    policy_version: str
    surface_binding_id: UUID
    channel_binding_id: UUID
    presentation_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
    status: str = "ALLOW"


@dataclass(frozen=True, slots=True)
class PresentPersonalCalendarOutputCommand:
    operation_id: UUID
    companion_output_id: UUID
    permission_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class RecoverPersonalCalendarPresentationCommand:
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarDisclosurePolicyResult:
    relationship_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarPresentationDispatchResult:
    presentation_key: str
    presentation_attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    state: str
    receipt_ref: str | None = None
    terminal_proof_kind: str | None = None
    settled_through_ref: str | None = None
    accepted_at: datetime | None = None
    proved_at: datetime | None = None
    status_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PersonalCalendarPresentationStatusResult:
    presentation_key: str
    presentation_attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    state: str
    receipt_ref: str | None = None
    terminal_proof_kind: str | None = None
    settled_through_ref: str | None = None
    accepted_at: datetime | None = None
    proved_at: datetime | None = None
    status_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PersonalCalendarPresentationResult:
    companion_output_id: UUID
    presentation_attempt_id: UUID
    presentation_attempt_generation: int
    presentation_key: str
    state: str
    interaction_event_id: UUID | None = None


@runtime_checkable
class PersonalCalendarPresentationAdapter(Protocol):
    sink_binding_ref: str
    presentation_contract_version: str
    status_contract_version: str

    def present_personal(
        self,
        *,
        presentation_key: str,
        presentation_attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        content_text: str,
        content_digest: str,
    ) -> PersonalCalendarPresentationDispatchResult:
        ...

    def lookup_personal_status(
        self,
        *,
        presentation_key: str,
        presentation_attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
    ) -> PersonalCalendarPresentationStatusResult:
        ...


__all__ = [
    "PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION",
    "PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION",
    "PersonalCalendarDisclosurePolicyResult",
    "PersonalCalendarPresentationAdapter",
    "PersonalCalendarPresentationDispatchResult",
    "PersonalCalendarPresentationResult",
    "PersonalCalendarPresentationStatusResult",
    "PresentPersonalCalendarOutputCommand",
    "RecoverPersonalCalendarPresentationCommand",
    "SetPersonalCalendarDisclosurePolicyCommand",
]
