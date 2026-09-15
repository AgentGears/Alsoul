from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION = "CALENDAR_MUTATION_RESULT_PLAN_V1"
CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION = "CALENDAR_CREATE_RESULT_V1"
CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION = "CALENDAR_MUTATION_COMPLETION_CONTEXT_V1"
CALENDAR_MUTATION_RESULT_KIND_CREATED = "CREATED"


@dataclass(frozen=True, slots=True)
class BuildPersonalCalendarMutationCompletionProjectionCommand:
    operation_id: UUID
    effect_id: UUID


@dataclass(frozen=True, slots=True)
class GeneratePersonalCalendarMutationResultPlanCommand:
    operation_id: UUID
    projection_id: UUID
    route_binding_id: UUID


@dataclass(frozen=True, slots=True)
class AdoptPersonalCalendarMutationOutputCommand:
    operation_id: UUID
    generated_output_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarMutationCompletionProjectionResult:
    projection_id: UUID
    mutation_completion_ref: UUID
    action_id: UUID
    effect_id: UUID
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class PersonalCalendarMutationGenerationResult:
    model_invocation_id: UUID
    generated_output_id: UUID
    projection_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarMutationAdoptionResult:
    companion_output_id: UUID
    output_target_id: UUID
    action_id: UUID
    effect_id: UUID


@runtime_checkable
class PersonalCalendarMutationCompletionModelAdapter(Protocol):
    provider_binding_ref: str
    model_ref: str

    def generate_plan(self, provider_context: dict[str, Any]) -> dict[str, Any]:
        ...


__all__ = [
    "AdoptPersonalCalendarMutationOutputCommand",
    "BuildPersonalCalendarMutationCompletionProjectionCommand",
    "CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION",
    "CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION",
    "CALENDAR_MUTATION_RESULT_KIND_CREATED",
    "CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION",
    "GeneratePersonalCalendarMutationResultPlanCommand",
    "PersonalCalendarMutationAdoptionResult",
    "PersonalCalendarMutationCompletionModelAdapter",
    "PersonalCalendarMutationCompletionProjectionResult",
    "PersonalCalendarMutationGenerationResult",
]
