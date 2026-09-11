from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID


CALENDAR_EVENTS_READ = "calendar.events.read"


@dataclass(frozen=True, slots=True)
class CalendarDayWindow:
    local_date: date
    calendar_timezone: str
    timezone_rules_version: str
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True, slots=True)
class RegisterPersonalCalendarResourceResult:
    personal_resource_binding_id: UUID


@dataclass(frozen=True, slots=True)
class BindCalendarCredentialResult:
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class GrantCalendarReadPermissionResult:
    permission_id: UUID


@dataclass(frozen=True, slots=True)
class AuthorityStateRevisionResult:
    entity_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class SetCalendarReadPolicyResult:
    relationship_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PrepareCalendarObservationResult:
    observation_id: UUID
    personal_resource_binding_id: UUID
    window: CalendarDayWindow


@dataclass(frozen=True, slots=True)
class CalendarReadPageFenceResult:
    authority_fence_id: UUID
    observation_id: UUID
    page_ordinal: int
    personal_resource_binding_id: UUID
    relationship_authority_revision: int
    resource_binding_state_revision: int
    permission_state_revision: int
    credential_state_revision: int
    policy_revision: int


@dataclass(frozen=True, slots=True)
class RegisterPersonalCalendarResourceCommand:
    operation_id: UUID
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    external_system_ref: str
    external_resource_ref: str
    calendar_timezone: str
    timezone_rules_version: str


@dataclass(frozen=True, slots=True)
class BindCalendarCredentialCommand:
    operation_id: UUID
    external_system_ref: str
    external_principal_ref: str
    secret_ref: str
    provider_scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GrantCalendarReadPermissionCommand:
    operation_id: UUID
    holder_companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    personal_resource_binding_id: UUID
    capability_contract_version: str
    grant_policy_version: str
    source_interaction_event_id: UUID


@dataclass(frozen=True, slots=True)
class SetCalendarReadPolicyCommand:
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
class SetPersonalWorldRelationshipStatusCommand:
    operation_id: UUID
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    status: Literal["ACTIVE", "ENDED"]


@dataclass(frozen=True, slots=True)
class SetPersonalResourceBindingStatusCommand:
    operation_id: UUID
    personal_resource_binding_id: UUID
    status: Literal["ACTIVE", "INACTIVE", "REVOKED"]


@dataclass(frozen=True, slots=True)
class SetCredentialBindingStatusCommand:
    operation_id: UUID
    credential_binding_id: UUID
    status: Literal["ACTIVE", "REVOKED"]
    provider_scopes: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SetPermissionStatusCommand:
    operation_id: UUID
    permission_id: UUID
    status: Literal["ACTIVE", "REVOKED"]


@dataclass(frozen=True, slots=True)
class PreparePersonalCalendarObservationCommand:
    operation_id: UUID
    observation_id: UUID
    source_interaction_event_id: UUID


@dataclass(frozen=True, slots=True)
class FencePersonalCalendarReadPageCommand:
    operation_id: UUID
    observation_id: UUID
    page_ordinal: int
    permission_id: UUID
    credential_binding_id: UUID
