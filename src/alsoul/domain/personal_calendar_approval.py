from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION = "CALENDAR_CREATE_CONSENT_V1"
CALENDAR_CREATE_APPROVAL_CEREMONY = "FIRST_PARTY_COUNTERPART_APPROVAL_V1"
CALENDAR_CREATE_APPROVAL_TEXT = "Approve this calendar event."


@dataclass(frozen=True, slots=True)
class PresentPersonalCalendarCreateApprovalCommand:
    operation_id: UUID
    action_id: UUID


@dataclass(frozen=True, slots=True)
class AdmitPersonalCalendarCreateApprovalCommand:
    operation_id: UUID
    approval_presentation_id: UUID
    source_interaction_event_id: UUID


@dataclass(frozen=True, slots=True)
class RevokePersonalCalendarCreateApprovalCommand:
    operation_id: UUID
    approval_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateApprovalPresentationResult:
    approval_presentation_id: UUID
    action_id: UUID
    action_digest: str
    consent_payload_digest: str
    presentation_key: str
    acceptance_ref: str
    presented_at: datetime


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateApprovalResult:
    approval_id: UUID
    action_id: UUID
    approval_presentation_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateApprovalStateResult:
    approval_id: UUID
    revision: int


__all__ = [
    "AdmitPersonalCalendarCreateApprovalCommand",
    "CALENDAR_CREATE_APPROVAL_CEREMONY",
    "CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION",
    "CALENDAR_CREATE_APPROVAL_TEXT",
    "PersonalCalendarCreateApprovalPresentationResult",
    "PersonalCalendarCreateApprovalResult",
    "PersonalCalendarCreateApprovalStateResult",
    "PresentPersonalCalendarCreateApprovalCommand",
    "RevokePersonalCalendarCreateApprovalCommand",
]
