from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from alsoul.services.recovery import RecoveryCoordinator
from alsoul.services.runtime_identity import response_operation_id
from alsoul.storage import schema

RuntimeNextAction = Literal[
    "NONE",
    "START_INVESTIGATION",
    "START_WORLD_ACQUISITION",
    "RECONCILE_WORLD_ACQUISITION",
    "INTERPRET_WORLD_CAPTURE",
    "BUILD_CONTEXT_PROJECTION",
    "START_MODEL_INVOCATION",
    "RECONCILE_MODEL_ATTEMPT",
    "ADOPT_GENERATED_OUTPUT",
    "PRESENT_ADOPTED_OUTPUT",
]


@dataclass(frozen=True, slots=True)
class ObservationDiagnostic:
    observation_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class ModelAttemptDiagnostic:
    model_invocation_id: UUID
    outcome: str
    provider_binding_ref: str
    model_ref: str


@dataclass(frozen=True, slots=True)
class FoundationRuntimeDiagnostic:
    """Derived operator-facing runtime state with no message/source contents."""

    recovery_stage: str
    next_action: RuntimeNextAction
    current_input_event_id: UUID
    investigation_id: UUID | None = None
    observation_states: tuple[ObservationDiagnostic, ...] = ()
    world_result_ids: tuple[UUID, ...] = ()
    model_attempts: tuple[ModelAttemptDiagnostic, ...] = ()
    reusable_projection_id: UUID | None = None
    reusable_generated_output_id: UUID | None = None
    adopted_output_id: UUID | None = None
    presented_event_id: UUID | None = None
    blockers: tuple[str, ...] = ()


class FoundationRuntimeDiagnostics:
    """Derive a recovery-safe operator view from canonical F4 rows.

    Diagnostics are intentionally content-free and non-authoritative. They expose
    semantic stage, attempt identities, and the next safe operation without
    leaking provider credentials, source bodies, user messages, or generated text.
    """

    def __init__(self, engine) -> None:
        self.engine = engine
        self.recovery = RecoveryCoordinator(engine)

    def assess(
        self, *, relationship_id: UUID, current_input_event_id: UUID
    ) -> FoundationRuntimeDiagnostic:
        assessment = self.recovery.assess_response(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )
        blockers: list[str] = []
        if assessment.projection_reuse_blocker:
            blockers.append(assessment.projection_reuse_blocker)
        if assessment.stage == "MODEL_ATTEMPT_UNRESOLVED":
            blockers.append(
                f"model_attempt:{assessment.unresolved_model_invocation_outcome or 'UNKNOWN'}"
            )

        with self.engine.connect() as conn:
            investigation_id = self._investigation_id(conn, current_input_event_id)
            observations: tuple[ObservationDiagnostic, ...] = ()
            world_result_ids: tuple[UUID, ...] = ()
            if investigation_id is not None:
                observation_rows = conn.execute(
                    select(
                        schema.observation.c.observation_id,
                        schema.observation.c.status,
                    )
                    .where(
                        schema.observation.c.investigation_id == investigation_id
                    )
                    .order_by(schema.observation.c.observed_at)
                ).all()
                observations = tuple(
                    ObservationDiagnostic(row.observation_id, row.status)
                    for row in observation_rows
                )
                world_result_ids = tuple(
                    conn.execute(
                        select(schema.world_result.c.world_result_id).where(
                            schema.world_result.c.investigation_id == investigation_id
                        )
                    ).scalars().all()
                )

            attempt_rows = conn.execute(
                select(
                    schema.model_invocation.c.model_invocation_id,
                    schema.model_invocation.c.outcome,
                    schema.model_invocation.c.provider_binding_ref,
                    schema.model_invocation.c.model_ref,
                )
                .select_from(
                    schema.model_invocation.join(
                        schema.context_projection,
                        schema.model_invocation.c.context_projection_id
                        == schema.context_projection.c.projection_id,
                    )
                )
                .where(
                    schema.context_projection.c.relationship_id == relationship_id,
                    schema.context_projection.c.current_input_event_id
                    == current_input_event_id,
                )
                .order_by(schema.model_invocation.c.started_at)
            ).all()
            attempts = tuple(
                ModelAttemptDiagnostic(
                    row.model_invocation_id,
                    row.outcome,
                    row.provider_binding_ref,
                    row.model_ref,
                )
                for row in attempt_rows
            )

        next_action = self._next_action(
            assessment.stage,
            investigation_id=investigation_id,
            observations=observations,
            world_result_ids=world_result_ids,
        )
        return FoundationRuntimeDiagnostic(
            recovery_stage=assessment.stage,
            next_action=next_action,
            current_input_event_id=current_input_event_id,
            investigation_id=investigation_id,
            observation_states=observations,
            world_result_ids=world_result_ids,
            model_attempts=attempts,
            reusable_projection_id=assessment.reusable_projection_id,
            reusable_generated_output_id=assessment.reusable_generated_output_id,
            adopted_output_id=assessment.adopted_output_id,
            presented_event_id=assessment.presented_event_id,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _investigation_id(conn, current_input_event_id: UUID) -> UUID | None:
        operation_id = response_operation_id(current_input_event_id, "investigation")
        receipt = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope == "StartInvestigation",
                schema.operation_receipt.c.operation_id == operation_id,
            )
        ).mappings().one_or_none()
        if receipt is None:
            return None
        result_json = receipt["result_json"]
        raw = result_json.get("investigation_id") if isinstance(result_json, dict) else None
        return UUID(raw) if raw else receipt["result_ref"]

    @staticmethod
    def _next_action(
        stage: str,
        *,
        investigation_id: UUID | None,
        observations: tuple[ObservationDiagnostic, ...],
        world_result_ids: tuple[UUID, ...],
    ) -> RuntimeNextAction:
        if stage == "PRESENTED":
            return "NONE"
        if stage == "ADOPTED":
            return "PRESENT_ADOPTED_OUTPUT"
        if stage == "GENERATED":
            return "ADOPT_GENERATED_OUTPUT"
        if stage == "MODEL_ATTEMPT_UNRESOLVED":
            return "RECONCILE_MODEL_ATTEMPT"
        if stage == "PROJECTION_READY":
            return "START_MODEL_INVOCATION"

        if investigation_id is None:
            return "START_INVESTIGATION"
        if world_result_ids:
            return "BUILD_CONTEXT_PROJECTION"
        if any(item.status == "SUCCEEDED" for item in observations):
            return "INTERPRET_WORLD_CAPTURE"
        if any(item.status == "STARTED" for item in observations):
            return "RECONCILE_WORLD_ACQUISITION"
        return "START_WORLD_ACQUISITION"


__all__ = [
    "FoundationRuntimeDiagnostic",
    "FoundationRuntimeDiagnostics",
    "ModelAttemptDiagnostic",
    "ObservationDiagnostic",
    "RuntimeNextAction",
]
