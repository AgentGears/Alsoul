from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.adapters.contracts import FirstPartyPresentationAdapter, ModelProviderAdapter
from alsoul.domain.commands import (
    AdoptCompanionOutputCommand,
    BuildContextProjectionCommand,
    PresentCompanionOutputCommand,
    ResolveOutputTargetCommand,
)
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.models import (
    AdoptCompanionOutputResult,
    FoundationResponseDraft,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.foundation import FoundationServices
from alsoul.services.provider_integration import ModelGenerationRunner
from alsoul.services.provider_recovery import ProviderRecoveryCoordinator
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.services.runtime import RuntimeCheckpoint
from alsoul.services.runtime_identity import (
    presentation_idempotency_key,
    response_operation_id,
)
from alsoul.storage import schema


@dataclass(frozen=True, slots=True)
class FoundationConversationalResponseRunResult:
    presented_event_id: UUID
    companion_output_id: UUID
    generated_output_id: UUID
    context_projection_id: UUID


@dataclass(frozen=True, slots=True)
class _ConversationContext:
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    current_input_event_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


class F4ConversationalOutputAdoption:
    """Adopt one source-free conversational GeneratedOutput for a semantic response target.

    The ordinary checked-response adoption service deliberately requires projected
    personal and world provenance. This bounded service handles the distinct case in
    which the ContextProjection contains only canonical Self/Relationship/current-input
    state and the model returns one unsourced Companion-owned expression.
    """

    def __init__(self, services: FoundationServices) -> None:
        self.services = services

    def adopt(
        self, command: AdoptCompanionOutputCommand
    ) -> AdoptCompanionOutputResult:
        scope = "AdoptCompanionOutput"
        req = request_digest(asdict(command))
        with self.services.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return AdoptCompanionOutputResult(UUID(replay["companion_output_id"]))

            target = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.output_target_id == command.output_target_id
                )
            ).mappings().one_or_none()
            if target is None:
                fail("OUTPUT_TARGET_NOT_FOUND", "OutputTarget does not exist")
            if (
                target["relationship_id"] != command.relationship_id
                or target["target_ref"] != command.origin_ref
                or target["purpose"] != "FINAL_RESPONSE"
            ):
                fail(
                    "OUTPUT_ORIGIN_INVALID",
                    "conversational output origin does not match its final-response target",
                )

            generated = conn.execute(
                select(schema.generated_output).where(
                    schema.generated_output.c.generated_output_id
                    == command.generated_output_id
                )
            ).mappings().one_or_none()
            if generated is None:
                fail("GENERATED_OUTPUT_NOT_FOUND", "GeneratedOutput does not exist")
            invocation = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.model_invocation_id
                    == generated["model_invocation_id"]
                )
            ).mappings().one_or_none()
            if invocation is None:
                fail("MODEL_INVOCATION_NOT_FOUND", "ModelInvocation does not exist")
            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id
                    == invocation["context_projection_id"]
                )
            ).mappings().one_or_none()
            if projection is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            if (
                projection["companion_person_id"] != command.companion_person_id
                or projection["relationship_id"] != command.relationship_id
                or projection["current_input_event_id"] != command.origin_ref
                or projection["purpose"] != "RESPOND_TO_INTERACTION"
            ):
                fail(
                    "GENERATED_OUTPUT_NOT_ELIGIBLE",
                    "GeneratedOutput was produced from a different conversational response context",
                )

            self._require_source_free_projection(conn, projection["projection_id"])
            draft = self._validate_payload(generated["semantic_payload_json"])
            if generated["content_text"] != draft.render_text():
                fail(
                    "OUTPUT_CONTENT_POLICY_REJECTED",
                    "generated text does not match the canonical conversational payload",
                )

            existing = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.output_target_id
                    == command.output_target_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                fail(
                    "OUTPUT_TARGET_ALREADY_FILLED",
                    "OutputTarget already has an adopted CompanionOutput",
                )

            companion_output_id = self.services.ids.new()
            now = self.services.clock.now()
            conn.execute(
                insert(schema.companion_output).values(
                    companion_output_id=companion_output_id,
                    companion_person_id=command.companion_person_id,
                    relationship_id=command.relationship_id,
                    output_target_id=command.output_target_id,
                    origin_kind=command.origin_kind,
                    origin_ref=command.origin_ref,
                    source_generated_output_id=command.generated_output_id,
                    content_text=generated["content_text"],
                    content_digest=generated["content_digest"],
                    semantic_payload_json=generated["semantic_payload_json"],
                    adopted_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="CompanionOutput",
                result_ref=companion_output_id,
                result_json={"companion_output_id": str(companion_output_id)},
                committed_at=now,
            )
            return AdoptCompanionOutputResult(companion_output_id)

    @staticmethod
    def _require_source_free_projection(conn, projection_id: UUID) -> None:
        personal = conn.execute(
            select(schema.context_projection_personal_item.c.claim_id).where(
                schema.context_projection_personal_item.c.projection_id == projection_id
            )
        ).scalars().all()
        world = conn.execute(
            select(schema.context_projection_world_item.c.world_result_id).where(
                schema.context_projection_world_item.c.projection_id == projection_id
            )
        ).scalars().all()
        if personal or world:
            fail(
                "CONVERSATIONAL_PROJECTION_INVALID",
                "bounded conversational response projection must not contain personal or world propositions",
            )

    @staticmethod
    def _validate_payload(payload: dict) -> FoundationResponseDraft:
        try:
            draft = FoundationResponseDraft.from_payload(payload)
        except Exception as exc:
            raise DomainError(
                "OUTPUT_CONTENT_POLICY_REJECTED",
                "generated conversational semantic payload is invalid",
            ) from exc
        if (
            len(draft.segments) != 1
            or draft.segments[0].epistemic_kind != "COMPANION_EXPRESSION"
            or draft.segments[0].source_ref is not None
            or not draft.segments[0].text.strip()
        ):
            fail(
                "OUTPUT_CONTENT_POLICY_REJECTED",
                "conversational response requires one non-empty unsourced Companion expression",
            )
        return draft


class FoundationConversationalResponseCoordinator:
    """Resume one bounded conversational response without starting world work.

    The current F4 conversational path projects canonical Self, Relationship, and the
    current counterpart input only. It performs no Investigation, Observation,
    WorldResult admission, or memory admission. Model output remains a candidate until
    the explicit conversational adoption boundary accepts one source-free expression.
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
        self.adoption = F4ConversationalOutputAdoption(services)

    def respond(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        model_adapter: ModelProviderAdapter,
        presentation_adapter: FirstPartyPresentationAdapter,
        after_process_loss: bool = False,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> FoundationConversationalResponseRunResult:
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

        context = self._load_context(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )

        if assessment.stage == "ADOPTED":
            assert assessment.adopted_output_id is not None
            return self._accept_and_commit_presentation(
                context=context,
                companion_output_id=assessment.adopted_output_id,
                presentation_adapter=presentation_adapter,
                checkpoint=emit,
            )

        if assessment.stage == "MODEL_ATTEMPT_UNRESOLVED":
            fail(
                "MODEL_ATTEMPT_UNRESOLVED",
                "provider attempt must be explicitly reconciled after known process loss before retry",
            )

        generated_output_id: UUID | None = None
        if assessment.stage == "INPUT_ADMITTED":
            self._require_input_frontier(context)
            emit("INPUT_ADMITTED")
            projection = self.services.build_context_projection(
                BuildContextProjectionCommand(
                    operation_id=self.ids.new(),
                    companion_person_id=context.companion_person_id,
                    relationship_id=context.relationship_id,
                    current_input_event_id=context.current_input_event_id,
                    required_personal_predicates=(),
                    required_world_result_ids=(),
                )
            )
            projection_id = projection.projection_id
            emit("CONTEXT_PROJECTION_BUILT")
        elif assessment.stage == "PROJECTION_READY":
            assert assessment.reusable_projection_id is not None
            projection_id = assessment.reusable_projection_id
            self._require_conversational_projection(projection_id)
        elif assessment.stage == "GENERATED":
            assert assessment.reusable_projection_id is not None
            assert assessment.reusable_generated_output_id is not None
            projection_id = assessment.reusable_projection_id
            self._require_conversational_projection(projection_id)
            generated_output_id = assessment.reusable_generated_output_id
        else:
            fail(
                "RUNTIME_RECOVERY_STAGE_UNSUPPORTED",
                f"unsupported conversational recovery stage {assessment.stage}",
            )

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

        adopted = self.adoption.adopt(
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

        return self._accept_and_commit_presentation(
            context=context,
            companion_output_id=adopted.companion_output_id,
            presentation_adapter=presentation_adapter,
            checkpoint=emit,
        )

    def _load_context(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> _ConversationContext:
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
            event["surface_binding_id"] != surface_binding_id
            or event["channel_binding_id"] != channel_binding_id
        ):
            fail(
                "INTERACTION_PURPOSE_ROUTE_MISMATCH",
                "conversational response route does not match the canonical input route",
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

        return _ConversationContext(
            companion_person_id=relationship["companion_person_id"],
            counterpart_id=relationship["counterpart_id"],
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )

    def _require_input_frontier(self, context: _ConversationContext) -> None:
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
                "conversational response may start only from the current relationship Timeline frontier",
            )

    def _require_conversational_projection(self, projection_id: UUID) -> None:
        with self.services.engine.connect() as conn:
            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id == projection_id
                )
            ).mappings().one_or_none()
            if projection is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            F4ConversationalOutputAdoption._require_source_free_projection(
                conn, projection_id
            )

    def _accept_and_commit_presentation(
        self,
        *,
        context: _ConversationContext,
        companion_output_id: UUID,
        presentation_adapter: FirstPartyPresentationAdapter,
        checkpoint: RuntimeCheckpoint,
    ) -> FoundationConversationalResponseRunResult:
        with self.services.engine.connect() as conn:
            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == companion_output_id
                )
            ).mappings().one_or_none()
        if output is None:
            fail("COMPANION_OUTPUT_NOT_FOUND", "adopted CompanionOutput does not exist")
        if (
            output["companion_person_id"] != context.companion_person_id
            or output["relationship_id"] != context.relationship_id
        ):
            fail(
                "PRESENTATION_ROUTE_INVALID",
                "CompanionOutput does not belong to the conversational relationship",
            )

        key = presentation_idempotency_key(
            companion_output_id,
            context.surface_binding_id,
            context.channel_binding_id,
        )
        acceptance = presentation_adapter.present(
            presentation_key=key,
            companion_output_id=companion_output_id,
            surface_binding_id=context.surface_binding_id,
            channel_binding_id=context.channel_binding_id,
            content_text=output["content_text"],
            content_digest=output["content_digest"],
        )
        if (
            acceptance.presentation_key != key
            or acceptance.content_digest != output["content_digest"]
            or not acceptance.receipt_ref.strip()
        ):
            fail(
                "PRESENTATION_ACCEPTANCE_INVALID",
                "first-party sink did not acknowledge the exact adopted output",
            )
        checkpoint("PRESENTATION_ACCEPTED")

        presented = self.services.present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=response_operation_id(
                    context.current_input_event_id,
                    "presentation-commit",
                ),
                companion_output_id=companion_output_id,
                surface_binding_id=context.surface_binding_id,
                channel_binding_id=context.channel_binding_id,
                presented_at=self.clock.now(),
            )
        )
        checkpoint("PRESENTED")
        return self._load_final_result(presented.interaction_event_id)

    def _load_final_result(
        self, presented_event_id: UUID | None
    ) -> FoundationConversationalResponseRunResult:
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
            self._require_conversational_projection(
                invocation["context_projection_id"]
            )
        return FoundationConversationalResponseRunResult(
            presented_event_id=presented_event_id,
            companion_output_id=output["companion_output_id"],
            generated_output_id=generated["generated_output_id"],
            context_projection_id=invocation["context_projection_id"],
        )


__all__ = [
    "F4ConversationalOutputAdoption",
    "FoundationConversationalResponseCoordinator",
    "FoundationConversationalResponseRunResult",
]
