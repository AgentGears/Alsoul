from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_action import (
    PreparePersonalCalendarCreateActionCommand,
)
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    PresentPersonalCalendarCreateApprovalCommand,
    calendar_create_approval_challenge,
)
from alsoul.domain.personal_calendar_effect import (
    AdmitPersonalCalendarCreateConfirmedEffectCommand,
)
from alsoul.domain.personal_calendar_execution import (
    PreparePersonalCalendarCreateExecutionAttemptCommand,
)
from alsoul.domain.personal_calendar_mutation_completion import (
    AdoptPersonalCalendarMutationOutputCommand,
    BuildPersonalCalendarMutationCompletionProjectionCommand,
    GeneratePersonalCalendarMutationResultPlanCommand,
)
from alsoul.domain.personal_calendar_mutation_presentation import (
    PresentPersonalCalendarMutationOutputCommand,
    RecoverPersonalCalendarMutationPresentationCommand,
)
from alsoul.domain.personal_calendar_transport import (
    DispatchPersonalCalendarCreateMutationCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.calendar_runtime_mutation_selection import (
    select_create_credential,
    select_create_resource,
    select_mutation_model_route,
    select_write_permission,
)
from alsoul.services.calendar_runtime_recovery import operation_id
from alsoul.services.personal_calendar_action_v2 import PersonalCalendarActionServices
from alsoul.services.personal_calendar_approval_v2 import PersonalCalendarApprovalServices
from alsoul.services.personal_calendar_effect import PersonalCalendarEffectServices
from alsoul.services.personal_calendar_execution_v4 import PersonalCalendarExecutionServices
from alsoul.services.personal_calendar_mutation_completion_v2 import (
    PersonalCalendarMutationCompletionServices,
)
from alsoul.services.personal_calendar_mutation_presentation_v2 import (
    PersonalCalendarMutationPresentationServices,
)
from alsoul.services.personal_calendar_transport_v3 import (
    PersonalCalendarMutationTransportServices,
)
from alsoul.storage import schema


MutationRuntimeStatus = Literal[
    "AWAITING_APPROVAL",
    "UNKNOWN_EFFECT",
    "PRESENTED",
]


@dataclass(frozen=True, slots=True)
class PersonalCalendarMutationRunResult:
    status: MutationRuntimeStatus
    action_id: UUID
    approval_presentation_id: UUID | None = None
    approval_challenge: str | None = None
    approval_id: UUID | None = None
    execution_attempt_id: UUID | None = None
    effect_id: UUID | None = None
    companion_output_id: UUID | None = None
    presentation_attempt_id: UUID | None = None
    presentation_state: str | None = None
    presented_event_id: UUID | None = None


class PersonalCalendarMutationCoordinator:
    """Compose the bounded F5.B create flow without collapsing authority stages.

    A create request may only prepare an immutable Action and present its exact
    approval challenge. A later trusted counterpart input carrying that exact
    Action-bound challenge may admit Approval and attempt execution. Uncertain or
    divergent mutation transport never enters Effect admission or completion output.
    """

    def __init__(
        self,
        services,
        *,
        capability_contract_version: str,
        time_resolver,
        execution_binding,
        approval_adapter,
        mutation_adapter,
        completion_model_adapter,
        presentation_adapter,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.services = services
        self.engine = services.engine
        self.clock = clock or services.clock or SystemClock()
        self.ids = ids or UUIDGenerator()
        self.capability_contract_version = capability_contract_version
        self.completion_model_adapter = completion_model_adapter
        common = {
            "time_resolver": time_resolver,
            "clock": self.clock,
            "ids": self.ids,
        }
        self.action = PersonalCalendarActionServices(self.engine, **common)
        self.approval = PersonalCalendarApprovalServices(
            self.engine,
            approval_adapter=approval_adapter,
            **common,
        )
        self.execution = PersonalCalendarExecutionServices(
            self.engine,
            execution_binding=execution_binding,
            approval_adapter=approval_adapter,
            **common,
        )
        self.transport = PersonalCalendarMutationTransportServices(
            self.engine,
            mutation_adapter=mutation_adapter,
            execution_binding=execution_binding,
            approval_adapter=approval_adapter,
            **common,
        )
        self.effect = PersonalCalendarEffectServices(
            self.engine,
            execution_binding=execution_binding,
            approval_adapter=approval_adapter,
            **common,
        )
        self.completion = PersonalCalendarMutationCompletionServices(
            self.engine,
            adapter=completion_model_adapter,
            clock=self.clock,
            ids=self.ids,
        )
        self.presentation = PersonalCalendarMutationPresentationServices(
            self.engine,
            adapter=presentation_adapter,
            clock=self.clock,
            ids=self.ids,
        )

    def start_create(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> PersonalCalendarMutationRunResult:
        source = self._source(
            relationship_id,
            current_input_event_id,
            surface_binding_id,
            channel_binding_id,
        )
        resource_id = select_create_resource(
            self.engine,
            relationship_id=relationship_id,
            counterpart_id=source["counterpart_id"],
            capability_contract_version=self.capability_contract_version,
        )
        permission_id = select_write_permission(
            self.engine,
            relationship_id=relationship_id,
            companion_person_id=source["companion_person_id"],
            counterpart_id=source["counterpart_id"],
            resource_id=resource_id,
            capability_contract_version=self.capability_contract_version,
            clock=self.clock,
        )
        action = self.action.prepare_create_action(
            PreparePersonalCalendarCreateActionCommand(
                operation_id=operation_id(current_input_event_id, "mutation:action"),
                relationship_id=relationship_id,
                personal_resource_binding_id=resource_id,
                permission_id=permission_id,
                source_interaction_event_id=current_input_event_id,
                capability_contract_version=self.capability_contract_version,
            )
        )
        presentation = self.approval.present_create_approval(
            PresentPersonalCalendarCreateApprovalCommand(
                operation_id=operation_id(current_input_event_id, "mutation:approval-present"),
                action_id=action.action_id,
            )
        )
        return PersonalCalendarMutationRunResult(
            status="AWAITING_APPROVAL",
            action_id=action.action_id,
            approval_presentation_id=presentation.approval_presentation_id,
            approval_challenge=calendar_create_approval_challenge(action.action_digest),
        )

    def approve_and_execute(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> PersonalCalendarMutationRunResult:
        source = self._source(
            relationship_id,
            current_input_event_id,
            surface_binding_id,
            channel_binding_id,
        )
        presentation = self._approval_presentation_for_input(
            relationship_id=relationship_id,
            event_id=current_input_event_id,
            counterpart_id=source["counterpart_id"],
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        approval = self.approval.admit_create_approval(
            AdmitPersonalCalendarCreateApprovalCommand(
                operation_id=operation_id(current_input_event_id, "mutation:approval-admit"),
                approval_presentation_id=presentation["approval_presentation_id"],
                source_interaction_event_id=current_input_event_id,
            )
        )
        credential_id = select_create_credential(
            self.engine,
            relationship_id=relationship_id,
            resource_id=presentation["personal_resource_binding_id"],
            capability_contract_version=self.capability_contract_version,
        )
        attempt = self.execution.prepare_execution_attempt(
            PreparePersonalCalendarCreateExecutionAttemptCommand(
                operation_id=operation_id(current_input_event_id, "mutation:attempt"),
                action_id=approval.action_id,
                approval_id=approval.approval_id,
                credential_binding_id=credential_id,
            )
        )
        transport = self.transport.dispatch_create_mutation(
            DispatchPersonalCalendarCreateMutationCommand(
                operation_id=operation_id(current_input_event_id, "mutation:dispatch"),
                execution_attempt_id=attempt.execution_attempt_id,
            )
        )
        if transport.status != "MATCHED_EFFECT_EVIDENCE":
            return PersonalCalendarMutationRunResult(
                status="UNKNOWN_EFFECT",
                action_id=approval.action_id,
                approval_presentation_id=presentation["approval_presentation_id"],
                approval_id=approval.approval_id,
                execution_attempt_id=attempt.execution_attempt_id,
            )
        if transport.effect_evidence_id is None:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_EVIDENCE_MISSING",
                "matched mutation transport must expose its durable evidence identity",
            )

        effect = self.effect.admit_confirmed_effect(
            AdmitPersonalCalendarCreateConfirmedEffectCommand(
                operation_id=operation_id(current_input_event_id, "mutation:effect"),
                execution_attempt_id=attempt.execution_attempt_id,
                effect_evidence_id=transport.effect_evidence_id,
            )
        )
        projection = self.completion.build_completion_projection(
            BuildPersonalCalendarMutationCompletionProjectionCommand(
                operation_id=operation_id(current_input_event_id, "mutation:projection"),
                effect_id=effect.effect_id,
            )
        )
        route_id = select_mutation_model_route(
            self.engine,
            relationship_id=relationship_id,
            model_adapter=self.completion_model_adapter,
        )
        generated = self.completion.generate_result_plan(
            GeneratePersonalCalendarMutationResultPlanCommand(
                operation_id=operation_id(current_input_event_id, "mutation:generate"),
                projection_id=projection.projection_id,
                route_binding_id=route_id,
            )
        )
        adopted = self.completion.adopt_mutation_output(
            AdoptPersonalCalendarMutationOutputCommand(
                operation_id=operation_id(current_input_event_id, "mutation:adopt"),
                generated_output_id=generated.generated_output_id,
            )
        )
        presented = self._present_or_recover(
            source_event_id=current_input_event_id,
            companion_output_id=adopted.companion_output_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        return PersonalCalendarMutationRunResult(
            status="PRESENTED",
            action_id=approval.action_id,
            approval_presentation_id=presentation["approval_presentation_id"],
            approval_id=approval.approval_id,
            execution_attempt_id=attempt.execution_attempt_id,
            effect_id=effect.effect_id,
            companion_output_id=adopted.companion_output_id,
            presentation_attempt_id=presented.presentation_attempt_id,
            presentation_state=presented.state,
            presented_event_id=presented.interaction_event_id,
        )

    def _present_or_recover(
        self,
        *,
        source_event_id: UUID,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ):
        recover = RecoverPersonalCalendarMutationPresentationCommand(
            companion_output_id=companion_output_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        with self.engine.connect() as conn:
            latest = conn.execute(
                select(schema.personal_calendar_mutation_presentation_attempt)
                .where(
                    schema.personal_calendar_mutation_presentation_attempt.c.companion_output_id
                    == companion_output_id
                )
                .order_by(
                    schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_generation.desc()
                )
                .limit(1)
            ).mappings().one_or_none()
        if latest is not None and latest["sink_acceptance_state"] in {"UNKNOWN", "ACCEPTED"}:
            settled = self.presentation.recover_presentation(recover)
            if settled.state != "NOT_ACCEPTED":
                return settled
            generation = settled.presentation_attempt_generation + 1
        elif latest is not None:
            generation = int(latest["presentation_attempt_generation"]) + 1
        else:
            generation = 1
        try:
            return self.presentation.present_output(
                PresentPersonalCalendarMutationOutputCommand(
                    operation_id=operation_id(
                        source_event_id, f"mutation:present:{generation}"
                    ),
                    companion_output_id=companion_output_id,
                    surface_binding_id=surface_binding_id,
                    channel_binding_id=channel_binding_id,
                )
            )
        except DomainError as exc:
            if exc.code != "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN":
                raise
            return self.presentation.recover_presentation(recover)

    def _approval_presentation_for_input(
        self,
        *,
        relationship_id: UUID,
        event_id: UUID,
        counterpart_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ):
        with self.engine.connect() as conn:
            text = conn.execute(
                select(schema.interaction_event.c.content_text).where(
                    schema.interaction_event.c.event_id == event_id
                )
            ).scalar_one()
            rows = conn.execute(
                select(schema.personal_calendar_create_approval_presentation)
                .join(
                    schema.personal_calendar_create_action,
                    schema.personal_calendar_create_action.c.action_id
                    == schema.personal_calendar_create_approval_presentation.c.action_id,
                )
                .where(
                    schema.personal_calendar_create_action.c.relationship_id
                    == relationship_id,
                    schema.personal_calendar_create_approval_presentation.c.presented_to_counterpart_id
                    == counterpart_id,
                    schema.personal_calendar_create_approval_presentation.c.surface_binding_id
                    == surface_binding_id,
                    schema.personal_calendar_create_approval_presentation.c.channel_binding_id
                    == channel_binding_id,
                )
            ).mappings().all()
        matches = [
            row
            for row in rows
            if text == calendar_create_approval_challenge(row["action_digest"])
        ]
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_APPROVAL_AMBIGUOUS",
                "approval input must resolve to exactly one trusted Action presentation on this route",
            )
        return matches[0]

    def _source(
        self,
        relationship_id: UUID,
        event_id: UUID,
        surface_id: UUID,
        channel_id: UUID,
    ):
        with self.engine.connect() as conn:
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id == relationship_id
                )
            ).mappings().one_or_none()
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == event_id
                )
            ).mappings().one_or_none()
        if relationship is None or event is None or (
            event["relationship_id"] != relationship_id
            or event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
            or event["surface_binding_id"] != surface_id
            or event["channel_binding_id"] != channel_id
        ):
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_SOURCE_INVALID",
                "calendar mutation source does not match the trusted relationship route",
            )
        return {
            "companion_person_id": relationship["companion_person_id"],
            "counterpart_id": relationship["counterpart_id"],
        }


__all__ = [
    "MutationRuntimeStatus",
    "PersonalCalendarMutationCoordinator",
    "PersonalCalendarMutationRunResult",
]
