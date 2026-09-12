from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


CALENDAR_ANSWER_PLAN_SCHEMA_VERSION = "CALENDAR_ANSWER_PLAN_V1"
CALENDAR_DAY_RENDERING_CONTRACT_VERSION = "DAY_SCHEDULE_V1"


@dataclass(frozen=True, slots=True)
class SetPersonalCalendarFreshnessPolicyCommand:
    operation_id: UUID
    relationship_id: UUID
    policy_version: str
    max_age_seconds: int
    status: str = "ALLOW"


@dataclass(frozen=True, slots=True)
class RegisterPersonalCalendarModelRouteCommand:
    operation_id: UUID
    provider_binding_ref: str
    model_ref: str
    route_contract_version: str
    data_handling_contract_version: str
    retention_class: str
    residency_class: str


@dataclass(frozen=True, slots=True)
class SetPersonalCalendarModelRouteStatusCommand:
    operation_id: UUID
    route_binding_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class SetPersonalCalendarModelEgressPolicyCommand:
    operation_id: UUID
    relationship_id: UUID
    policy_version: str
    allowed_route_binding_ids: tuple[UUID, ...]
    required_retention_class: str
    required_residency_class: str
    status: str = "ALLOW"


@dataclass(frozen=True, slots=True)
class BuildPersonalCalendarProjectionCommand:
    operation_id: UUID
    world_result_id: UUID
    current_input_event_id: UUID


@dataclass(frozen=True, slots=True)
class GeneratePersonalCalendarAnswerPlanCommand:
    operation_id: UUID
    projection_id: UUID
    permission_id: UUID
    route_binding_id: UUID


@dataclass(frozen=True, slots=True)
class AdoptPersonalCalendarScheduleOutputCommand:
    operation_id: UUID
    generated_output_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarPolicyRevisionResult:
    relationship_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarModelRouteResult:
    route_binding_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class PersonalCalendarProjectionResult:
    projection_id: UUID
    freshness_decision_id: UUID
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class PersonalCalendarGenerationResult:
    model_invocation_id: UUID
    generated_output_id: UUID
    egress_decision_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarAdoptionResult:
    companion_output_id: UUID
    output_target_id: UUID


@runtime_checkable
class PersonalCalendarModelAdapter(Protocol):
    provider_binding_ref: str
    model_ref: str

    def generate_plan(self, provider_context: dict[str, Any]) -> dict[str, Any]:
        ...
