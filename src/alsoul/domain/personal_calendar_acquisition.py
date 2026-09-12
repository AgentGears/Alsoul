from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID


PERSONAL_CALENDAR_DAY_EVENTS_PREDICATE = "personal_calendar.events_on_local_date"
PERSONAL_CALENDAR_SCHEDULE_RESULT_KIND = "PERSONAL_CALENDAR_SCHEDULE"
PERSONAL_CALENDAR_CAPTURE_SCHEMA_VERSION = "PERSONAL_CALENDAR_CAPTURE_V1"
PERSONAL_CALENDAR_RESULT_SCHEMA_VERSION = "PERSONAL_CALENDAR_WORLD_RESULT_V1"


@dataclass(frozen=True, slots=True)
class CalendarReadCapabilityContract:
    contract_version: str
    pagination_contract_version: str
    snapshot_contract_version: str
    normalization_schema_version: str
    field_minimization_contract_version: str
    freshness_policy_version: str
    max_pages: int
    max_events: int
    max_events_per_page: int
    max_title_chars: int = 1024
    semantic_operation: str = "calendar.events.read"
    effect_class: str = "READ_ONLY"
    resource_kind: str = "CALENDAR"
    pagination_mode: str = "OPAQUE_CURSOR"
    coherent_snapshot_mode: str = "STABLE_SNAPSHOT_REF"
    recurrence_expansion_mode: str = "CONCRETE_OCCURRENCES"
    query_interval_semantics: str = "OVERLAP_COMPLETE_HALF_OPEN_WINDOW"
    history_compensation_mode: str = "PROHIBITED"
    raw_response_minimization_mode: str = "EPHEMERAL_TO_ALLOWLIST"


@dataclass(frozen=True, slots=True)
class NormalizedCalendarEvent:
    occurrence_ref: str
    title: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    series_ref: str | None = None
    exception_ref: str | None = None
    all_day_start_date: date | None = None
    all_day_end_date_exclusive: date | None = None
    occurrence_status: Literal["ACTIVE", "CANCELLED"] = "ACTIVE"
    record_kind: Literal["OCCURRENCE"] = "OCCURRENCE"


@dataclass(frozen=True, slots=True)
class PersonalCalendarReadPageRequest:
    authority_fence_id: UUID
    observation_id: UUID
    traversal_page_ordinal: int
    external_system_ref: str
    external_resource_ref: str
    window_start: datetime
    window_end: datetime
    page_token: str | None
    expected_snapshot_ref: str | None
    credential_secret_ref: str
    normalization_schema_version: str
    field_minimization_contract_version: str
    max_events_per_page: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarReadPage:
    events: tuple[NormalizedCalendarEvent, ...]
    snapshot_ref: str
    snapshot_as_of: datetime | None
    next_page_token: str | None
    terminal: bool
    result_cap_hit: bool = False


@runtime_checkable
class PersonalCalendarReadAdapter(Protocol):
    adapter_binding_ref: str
    adapter_version: str
    capability_contract_version: str

    def read_page(self, request: PersonalCalendarReadPageRequest) -> PersonalCalendarReadPage:
        ...


@dataclass(frozen=True, slots=True)
class AcquirePersonalCalendarObservationCommand:
    operation_id: UUID
    observation_id: UUID
    permission_id: UUID
    credential_binding_id: UUID


@dataclass(frozen=True, slots=True)
class AcquirePersonalCalendarObservationResult:
    source_capture_id: UUID
    evidence_id: UUID
    world_result_id: UUID
    page_count: int
    event_count: int
    snapshot_ref: str
    freshness_anchor_at: datetime
    freshness_anchor_basis: Literal[
        "PROVIDER_SNAPSHOT_AS_OF", "ACQUISITION_STARTED_AT"
    ]
