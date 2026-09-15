from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID


CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION = "CALENDAR_CREATE_CONSENT_V1"
CALENDAR_CREATE_APPROVAL_CEREMONY = "FIRST_PARTY_COUNTERPART_APPROVAL_V1"
CALENDAR_CREATE_APPROVAL_REPLY_PREFIX = "APPROVE CALENDAR ACTION "
_ACTION_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def calendar_create_approval_challenge(action_digest: str) -> str:
    """Return the exact first-party reply bound to one immutable Action digest."""

    if not isinstance(action_digest, str) or _ACTION_DIGEST.fullmatch(action_digest) is None:
        raise ValueError("calendar-create approval challenge requires a lowercase SHA-256 Action digest")
    return f"{CALENDAR_CREATE_APPROVAL_REPLY_PREFIX}{action_digest}"


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
    "CALENDAR_CREATE_APPROVAL_REPLY_PREFIX",
    "PersonalCalendarCreateApprovalPresentationResult",
    "PersonalCalendarCreateApprovalResult",
    "PersonalCalendarCreateApprovalStateResult",
    "PresentPersonalCalendarCreateApprovalCommand",
    "RevokePersonalCalendarCreateApprovalCommand",
    "calendar_create_approval_challenge",
]
