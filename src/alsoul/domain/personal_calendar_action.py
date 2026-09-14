from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


CALENDAR_EVENT_CREATE = "calendar.event.create"
CALENDAR_CREATE_EFFECT_CLASS = "WRITE"
CALENDAR_CREATE_ACTION_SCHEMA_VERSION = "PERSONAL_CALENDAR_CREATE_ACTION_V1"


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
    allowed_resource_binding_ids: tuple[UUID, ...]
    status: Literal["ALLOW", "DENY"] = "ALLOW"


@dataclass(frozen=True, slots=True)
class GrantCalendarCreatePermissionCommand:
    operation_id: UUID
    holder_companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    personal_resource_binding_id: UUID
    capability_contract_version: str
    grant_policy_version: str
    source_interaction_event_id: UUID


@dataclass(frozen=True, slots=True)
class SetCalendarCreatePermissionStatusCommand:
    operation_id: UUID
    permission_id: UUID


@dataclass(frozen=True, slots=True)
class PreparePersonalCalendarCreateActionCommand:
    operation_id: UUID
    relationship_id: UUID
    personal_resource_binding_id: UUID
    permission_id: UUID
    source_interaction_event_id: UUID
    capability_contract_version: str


@dataclass(frozen=True, slots=True)
class CalendarCreatePolicyResult:
    relationship_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class GrantCalendarCreatePermissionResult:
    permission_id: UUID


@dataclass(frozen=True, slots=True)
class CalendarCreatePermissionStateResult:
    permission_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateActionResult:
    action_id: UUID
    personal_resource_binding_id: UUID
    summary: str
    start_text: str
    end_text: str
    normalized_start_at: datetime
    normalized_end_at: datetime
    action_digest: str


__all__ = [
    "CALENDAR_CREATE_ACTION_SCHEMA_VERSION",
    "CALENDAR_CREATE_EFFECT_CLASS",
    "CALENDAR_EVENT_CREATE",
    "CalendarCreatePermissionStateResult",
    "CalendarCreatePolicyResult",
    "GrantCalendarCreatePermissionCommand",
    "GrantCalendarCreatePermissionResult",
    "PersonalCalendarCreateActionResult",
    "PreparePersonalCalendarCreateActionCommand",
    "SetCalendarCreatePermissionStatusCommand",
    "SetCalendarCreatePolicyCommand",
]
