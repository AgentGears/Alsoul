from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID


CALENDAR_EVENT_CREATE = "calendar.event.create"
CALENDAR_CREATE_EFFECT_CLASS = "WRITE"
CALENDAR_CREATE_CONSENT_RENDERING_VERSION = "CALENDAR_CREATE_CONSENT_V1"
CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT = (
    "Allow my companion to create calendar events."
)
CALENDAR_CREATE_APPROVAL_TEXT = "Approve the presented calendar event."


@dataclass(frozen=True, slots=True)
class CalendarCreateApprovalPresentationAcceptance:
    presentation_acceptance_ref: str


@runtime_checkable
class CalendarCreateApprovalPresenter(Protocol):
    presenter_binding_ref: str
    presentation_contract_version: str

    def present_approval(
        self,
        *,
        approval_presentation_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        consent_payload_text: str,
        consent_payload_digest: str,
    ) -> CalendarCreateApprovalPresentationAcceptance:
        ...


@dataclass(frozen=True, slots=True)
class CalendarCreateActionResult:
    action_id: UUID
    personal_resource_binding_id: UUID
    action_digest: str


@dataclass(frozen=True, slots=True)
class CalendarCreateWritePermissionResult:
    permission_id: UUID


@dataclass(frozen=True, slots=True)
class CalendarCreateWritePolicyResult:
    relationship_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class CalendarCreateApprovalPresentationResult:
    approval_presentation_id: UUID
    action_id: UUID
    consent_payload_digest: str
    presentation_acceptance_ref: str


@dataclass(frozen=True, slots=True)
class CalendarCreateApprovalResult:
    approval_id: UUID
    action_id: UUID


@dataclass(frozen=True, slots=True)
class CalendarCreateAuthorityStateResult:
    entity_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class CreateCalendarActionCommand:
    operation_id: UUID
    source_interaction_event_id: UUID
    capability_contract_version: str


@dataclass(frozen=True, slots=True)
class GrantCalendarCreatePermissionCommand:
    operation_id: UUID
    source_interaction_event_id: UUID
    capability_contract_version: str
    grant_policy_version: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SetCalendarCreatePolicyCommand:
    operation_id: UUID
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    capability_contract_version: str
    ai_policy_version: str
    resource_scope_version: str
    required_provider_scope: str
    permission_grant_policy_version: str
    approval_policy_version: str
    allowed_resource_binding_ids: tuple[UUID, ...]
    status: Literal["ALLOW", "DENY"] = "ALLOW"


@dataclass(frozen=True, slots=True)
class PresentCalendarCreateApprovalCommand:
    operation_id: UUID
    action_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID
    consent_rendering_version: str = CALENDAR_CREATE_CONSENT_RENDERING_VERSION


@dataclass(frozen=True, slots=True)
class GrantCalendarCreateApprovalCommand:
    operation_id: UUID
    action_id: UUID
    approval_presentation_id: UUID
    source_interaction_event_id: UUID
    approval_policy_version: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RevokeCalendarCreatePermissionCommand:
    operation_id: UUID
    permission_id: UUID


@dataclass(frozen=True, slots=True)
class RevokeCalendarCreateApprovalCommand:
    operation_id: UUID
    approval_id: UUID


__all__ = [
    "CALENDAR_CREATE_APPROVAL_TEXT",
    "CALENDAR_CREATE_CONSENT_RENDERING_VERSION",
    "CALENDAR_CREATE_EFFECT_CLASS",
    "CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT",
    "CALENDAR_EVENT_CREATE",
    "CalendarCreateActionResult",
    "CalendarCreateApprovalPresentationAcceptance",
    "CalendarCreateApprovalPresenter",
    "CalendarCreateApprovalPresentationResult",
    "CalendarCreateApprovalResult",
    "CalendarCreateAuthorityStateResult",
    "CalendarCreateWritePermissionResult",
    "CalendarCreateWritePolicyResult",
    "CreateCalendarActionCommand",
    "GrantCalendarCreateApprovalCommand",
    "GrantCalendarCreatePermissionCommand",
    "PresentCalendarCreateApprovalCommand",
    "RevokeCalendarCreateApprovalCommand",
    "RevokeCalendarCreatePermissionCommand",
    "SetCalendarCreatePolicyCommand",
]
