from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal
from uuid import UUID, uuid5

from sqlalchemy import select

from alsoul.adapters.contracts import ModelProviderAdapter, WorldAcquisitionAdapter
from alsoul.domain.commands import (
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    BuildContextProjectionCommand,
    PresentCompanionOutputCommand,
    ResolveOutputTargetCommand,
    StartInvestigationCommand,
)
from alsoul.domain.errors import fail
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.foundation import (
    FoundationServices,
    RAM_PREDICATE,
    WORLD_MEMORY_REQUIREMENT_PREDICATE,
)
from alsoul.services.provider_integration import (
    ModelGenerationRunner,
    WorldAcquisitionRunner,
)
from alsoul.services.provider_recovery import ProviderRecoveryCoordinator
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.storage import schema

_RUNTIME_NAMESPACE = UUID("a7d54b3d-29f4-4f3f-8fa4-70a697078b42")
_WORLD_OBJECTIVE = "Determine the current minimum memory requirement for the software."
_WORLD_REQUEST = {"resource": "current software requirements"}

RuntimeCheckpointName = Literal[
    "INPUT_ADMITTED",
    "INVESTIGATION_STARTED",
    "OBSERVATION_STARTED",
    "WORLD_CAPTURED",
    "WORLD_RESULT_ADMITTED",
    "CONTEXT_PROJECTION_BUILT",
    "MODEL_INVOCATION_STARTED",
    "GENERATED_OUTPUT_COMMITTED",
    "OUTPUT_TARGET_RESOLVED",
    "COMPANION_OUTPUT_ADOPTED",
    "PRESENTED",
]
RuntimeCheckpoint = Callable[[RuntimeCheckpointName], None]


@dataclass(frozen=True, slots=True)
class FoundationResponseRunResult:
    presented_event_id: UUID
    companion_output_id: UUID
    generated_output_id: UUID
    context_projection_id: UUID
    world_result_id: UUID


@dataclass(frozen=True, slots=True)
class _ResponseContext:
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    current_input_event_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID
    conversation_id: str | None


class FoundationResponseCoordinator:
    """Resume one F4 reactive response from the furthest durable semantic stage.

    The coordinator persists no mutable turn-status aggregate. It composes the
    existing semantic services, provider runners, and recovery assessment.
    """

    def __init__(
        self,
        services: FoundationServices,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.services = services
        self.clock = clock or services.clock or SystemClock()
        self.ids = ids or UUIDGenerator()
        self.recovery = RecoveryCoordinator(services.engine)
        self.provider_recovery = ProviderRecoveryCoordinator(services)

    def respond(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        world_adapter: WorldAcquisitionAdapter,
        model_adapter: ModelProviderAdapter,
        after_process_loss: bool = False,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> FoundationResponseRunResult:
        emit = checkpoint or (lambda _stage: None)

        if after_process_loss:
            assessment = self.provider_recovery.reconcile_response_after_process_loss(
                relationship_id=relationship_id,
                current_input_event_id=current_input_event_id,
            )
        else:
            assessment = self.recovery.assess_response(
                relationship_id=relationship_id,
                current_input_event_id=current_input_event_id,
            )

        if assessment.stage == "PRESENTED":
            return self._load_final_result(assessment.presented_event_id)

        context = self._load_response_context(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )

        if assessment.stage == "ADOPTED":
            assert assessment.adopted_output_id is not None
            presented = self.services.present_companion_output(
                PresentCompanionOutputCommand(
                    operation_id=self.ids.new(),
                    companion_output_id=assessment.adopted_output_id,
                    surface_binding_id=surface_binding_id,
                    channel_binding_id=channel_binding_id,
                    presented_at=self.clock.now(),
                )
            )
            emit("PRESENTED")
            return self._load_final_result(presented.interaction_event_id)

        if assessment.stage == "MODEL_ATTEMPT_UNRESOLVED":
            fail(
                "MODEL_ATTEMPT_UNRESOLVED",
                "provider attempt must be explicitly reconciled after known process loss before retry",
            )

        if assessment.stage == "INPUT_ADMITTED":
            self._require_input_frontier(context)
            emit("INPUT_ADMITTED")
            world_result_id = self._ensure_world_result(
                context=context,
                world_adapter=world_adapter,
                after_process_loss=after_process_loss,
                checkpoint=emit,
            )
            projection = self.services.build_context_projection(
                BuildContextProjectionCommand(
                    operation_id=self.ids.new(),
                    companion_person_id=context.companion_person_id,
                    relationship_id=context.relationship_id,
                    current_input_event_id=context.current_input_event_id,
                    required_personal_predicates=(RAM_PREDICATE,),
                    required_world_result_ids=(world_result_id,),
                )
            )
            projection_id = projection.projection_id
            emit("CONTEXT_PROJECTION_BUILT")
            generated_output_id = None
        elif assessment.stage == "PROJECTION_READY":
            assert assessment.reusable_projection_id is not None
            projection_id = assessment.reusable_projection_id
            world_result_id = self._world_result_for_projection(projection_id)
            generated_output_id = None
        elif assessment.stage == "GENERATED":
            assert assessment.reusable_projection_id is not None
            assert assessment.reusable_generated_output_id is not None
            projection_id = assessment.reusable_projection_id
            generated_output_id = assessment.reusable_generated_output_id
            world_result_id = self._world_result_for_projection(projection_id)
        else:
            fail("RUNTIME_RECOVERY_STAGE_UNSUPPORTED", f"unsupported recovery stage {assessment.stage}")

        if generated_output_id is None:
            generated = ModelGenerationRunner(
                self.services,
                clock=self.clock,
                ids=self.ids,
            ).run(
                context_projection_id=projection_id,
                adapter=model_adapter,
                after_invocation_started=lambda _invocation_id: emit(
                    "MODEL_INVOCATION_STARTED"
                ),
            )
            generated_output_id = generated.generated_output_id
            emit("GENERATED_OUTPUT_COMMITTED")

        target = self.services.resolve_output_target(
            ResolveOutputTargetCommand(
                operation_id=self.ids.new(),
                relationship_id=context.relationship_id,
                target_kind="INTERACTION_EVENT",
                target_ref=context.current_input_event_id,
                purpose="FINAL_RESPONSE",
            )
        )
        emit("OUTPUT_TARGET_RESOLVED")

        adopted = self.services.adopt_companion_output(
            AdoptCompanionOutputCommand(
                operation_id=self.ids.new(),
                companion_person_id=context.companion_person_id,
                relationship_id=context.relationship_id,
                output_target_id=target.output_target_id,
                origin_kind="RESPONSE_TO_EVENT",
                origin_ref=context.current_input_event_id,
                generated_output_id=generated_output_id,
            )
        )
        emit("COMPANION_OUTPUT_ADOPTED")

        presented = self.services.present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=self.ids.new(),
                companion_output_id=adopted.companion_output_id,
                surface_binding_id=context.surface_binding_id,
                channel_binding_id=context.channel_binding_id,
                presented_at=self.clock.now(),
            )
        )
        emit("PRESENTED")
        return self._load_final_result(presented.interaction_event_id)

    def _load_response_context(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> _ResponseContext:
        with self.services.engine.connect() as conn:
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id == relationship_id
                )
            ).mappings().one_or_none()
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == current_input_event_id
                )
            ).mappings().one_or_none()
            surface = conn.execute(
                select(schema.surface_binding).where(
                    schema.surface_binding.c.surface_binding_id == surface_binding_id
                )
            ).mappings().one_or_none()
            channel = conn.execute(
                select(schema.channel_binding).where(
                    schema.channel_binding.c.channel_binding_id == channel_binding_id
                )
            ).mappings().one_or_none()

        if relationship is None:
            fail("RELATIONSHIP_NOT_FOUND", "Relationship does not exist")
        if (
            event is None
            or event["relationship_id"] != relationship_id
            or event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "RUNTIME_CURRENT_INPUT_INVALID",
                "current input is not a counterpart input in the supplied relationship",
            )
        if (
            surface is None
            or surface["companion_person_id"] != relationship["companion_person_id"]
            or channel is None
            or channel["companion_person_id"] != relationship["companion_person_id"]
        ):
            fail(
                "PRESENTATION_ROUTE_INVALID",
                "surface/channel route does not belong to the CompanionPerson",
            )

        return _ResponseContext(
            companion_person_id=relationship["companion_person_id"],
            counterpart_id=relationship["counterpart_id"],
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
            conversation_id=event["conversation_id"],
        )

    def _require_input_frontier(self, context: _ResponseContext) -> None:
        with self.services.engine.connect() as conn:
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == context.current_input_event_id
                )
            ).mappings().one()
            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == context.relationship_id
                )
            ).mappings().one()
        if event["timeline_seq"] != timeline["last_timeline_seq"]:
            fail(
                "RUNTIME_CURRENT_INPUT_NOT_FRONTIER",
                "reactive response may start only from the current relationship Timeline frontier",
            )

    def _ensure_world_result(
        self,
        *,
        context: _ResponseContext,
        world_adapter: WorldAcquisitionAdapter,
        after_process_loss: bool,
        checkpoint: RuntimeCheckpoint,
    ) -> UUID:
        investigation = self.services.start_investigation(
            StartInvestigationCommand(
                operation_id=self._singleton_operation_id(
                    context.current_input_event_id, "investigation"
                ),
                initiated_by_companion_person_id=context.companion_person_id,
                relationship_id=context.relationship_id,
                objective=_WORLD_OBJECTIVE,
                conversation_id=context.conversation_id,
            )
        )
        checkpoint("INVESTIGATION_STARTED")

        existing_result = self._world_result_in_investigation(
            investigation.investigation_id
        )
        if existing_result is not None:
            return existing_result

        evidence_id = self._successful_world_evidence(
            investigation.investigation_id
        )
        if evidence_id is None:
            if (
                self._has_started_observation(investigation.investigation_id)
                and not after_process_loss
            ):
                fail(
                    "WORLD_ACQUISITION_UNRESOLVED",
                    "an Observation is still STARTED; retry requires a known process-loss boundary",
                )
            acquired = WorldAcquisitionRunner(
                self.services,
                clock=self.clock,
                ids=self.ids,
            ).run(
                investigation_id=investigation.investigation_id,
                adapter=world_adapter,
                acquisition_kind="FETCH",
                request_descriptor=dict(_WORLD_REQUEST),
                after_observation_started=lambda _observation_id: checkpoint(
                    "OBSERVATION_STARTED"
                ),
            )
            evidence_id = acquired.evidence_id
            checkpoint("WORLD_CAPTURED")

        value, captured_at = self._extract_world_requirement(evidence_id)
        result = self.services.admit_world_result(
            AdmitWorldResultCommand(
                operation_id=self._singleton_operation_id(
                    context.current_input_event_id, "world-result"
                ),
                investigation_id=investigation.investigation_id,
                result_kind="REQUIREMENT",
                predicate=WORLD_MEMORY_REQUIREMENT_PREDICATE,
                value=value,
                support_evidence_ids=(evidence_id,),
                valid_as_of=captured_at,
            )
        )
        checkpoint("WORLD_RESULT_ADMITTED")
        return result.world_result_id

    def _world_result_in_investigation(self, investigation_id: UUID) -> UUID | None:
        with self.services.engine.connect() as conn:
            rows = conn.execute(
                select(schema.world_result.c.world_result_id).where(
                    schema.world_result.c.investigation_id == investigation_id,
                    schema.world_result.c.predicate
                    == WORLD_MEMORY_REQUIREMENT_PREDICATE,
                )
            ).scalars().all()
        if len(rows) > 1:
            fail(
                "RUNTIME_WORLD_RESULT_AMBIGUOUS",
                "foundation Investigation has multiple admitted results for the required predicate",
            )
        return rows[0] if rows else None

    def _successful_world_evidence(self, investigation_id: UUID) -> UUID | None:
        with self.services.engine.connect() as conn:
            rows = conn.execute(
                select(schema.evidence_item.c.evidence_id)
                .select_from(
                    schema.evidence_item.join(
                        schema.world_source_capture,
                        schema.evidence_item.c.source_id
                        == schema.world_source_capture.c.source_capture_id,
                    ).join(
                        schema.observation,
                        schema.world_source_capture.c.observation_id
                        == schema.observation.c.observation_id,
                    )
                )
                .where(
                    schema.evidence_item.c.origin_kind == "SEARCH_RESULT",
                    schema.evidence_item.c.source_type == "WORLD_SOURCE_CAPTURE",
                    schema.observation.c.investigation_id == investigation_id,
                    schema.observation.c.status == "SUCCEEDED",
                )
            ).scalars().all()
        if len(rows) > 1:
            fail(
                "RUNTIME_WORLD_CAPTURE_AMBIGUOUS",
                "foundation Investigation has multiple successful captures before WorldResult admission",
            )
        return rows[0] if rows else None

    def _has_started_observation(self, investigation_id: UUID) -> bool:
        with self.services.engine.connect() as conn:
            return (
                conn.execute(
                    select(schema.observation.c.observation_id)
                    .where(
                        schema.observation.c.investigation_id == investigation_id,
                        schema.observation.c.status == "STARTED",
                    )
                    .limit(1)
                ).scalar_one_or_none()
                is not None
            )

    def _extract_world_requirement(self, evidence_id: UUID) -> tuple[int, datetime]:
        with self.services.engine.connect() as conn:
            evidence = conn.execute(
                select(schema.evidence_item).where(
                    schema.evidence_item.c.evidence_id == evidence_id
                )
            ).mappings().one_or_none()
            if (
                evidence is None
                or evidence["source_type"] != "WORLD_SOURCE_CAPTURE"
                or evidence["origin_kind"] != "SEARCH_RESULT"
            ):
                fail(
                    "WORLD_RESULT_SUPPORT_INVALID",
                    "runtime world evidence is not a source-capture EvidenceItem",
                )
            capture = conn.execute(
                select(schema.world_source_capture).where(
                    schema.world_source_capture.c.source_capture_id
                    == evidence["source_id"]
                )
            ).mappings().one_or_none()
            if capture is None:
                fail("CAPTURE_CONTENT_UNAVAILABLE", "WorldSourceCapture is missing")
            blob = conn.execute(
                select(schema.content_blob).where(
                    schema.content_blob.c.content_digest == capture["content_digest"]
                )
            ).mappings().one_or_none()
        if blob is None:
            fail("CAPTURE_CONTENT_UNAVAILABLE", "captured source content is unavailable")
        try:
            payload = json.loads(blob["content_text"])
        except json.JSONDecodeError:
            fail(
                "WORLD_RESULT_SUPPORT_INVALID",
                "captured world source is not valid JSON",
            )
        value = payload.get("minimum_memory_gb")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            fail(
                "WORLD_RESULT_SUPPORT_INVALID",
                "captured world source does not contain a valid minimum_memory_gb",
            )
        return value, capture["captured_at"]

    def _world_result_for_projection(self, projection_id: UUID) -> UUID:
        with self.services.engine.connect() as conn:
            rows = conn.execute(
                select(schema.context_projection_world_item.c.world_result_id).where(
                    schema.context_projection_world_item.c.projection_id == projection_id
                )
            ).scalars().all()
        if len(rows) != 1:
            fail(
                "RUNTIME_PROJECTION_WORLD_RESULT_INVALID",
                "foundation projection must contain exactly one WorldResult",
            )
        return rows[0]

    def _load_final_result(self, presented_event_id: UUID | None) -> FoundationResponseRunResult:
        if presented_event_id is None:
            fail("PRESENTATION_NOT_FOUND", "presented event is missing")
        with self.services.engine.connect() as conn:
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == presented_event_id
                )
            ).mappings().one_or_none()
            if event is None or event["companion_output_id"] is None:
                fail("PRESENTATION_NOT_FOUND", "presented Timeline event is missing")
            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == event["companion_output_id"]
                )
            ).mappings().one()
            generated = conn.execute(
                select(schema.generated_output).where(
                    schema.generated_output.c.generated_output_id
                    == output["source_generated_output_id"]
                )
            ).mappings().one()
            invocation = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.model_invocation_id
                    == generated["model_invocation_id"]
                )
            ).mappings().one()
            world_result_id = self._world_result_for_projection(
                invocation["context_projection_id"]
            )
        return FoundationResponseRunResult(
            presented_event_id=presented_event_id,
            companion_output_id=output["companion_output_id"],
            generated_output_id=generated["generated_output_id"],
            context_projection_id=invocation["context_projection_id"],
            world_result_id=world_result_id,
        )

    @staticmethod
    def _singleton_operation_id(current_input_event_id: UUID, stage: str) -> UUID:
        return uuid5(
            _RUNTIME_NAMESPACE,
            f"{current_input_event_id}:{stage}:f4-runtime-v1",
        )


__all__ = [
    "FoundationResponseCoordinator",
    "FoundationResponseRunResult",
    "RuntimeCheckpoint",
    "RuntimeCheckpointName",
]
