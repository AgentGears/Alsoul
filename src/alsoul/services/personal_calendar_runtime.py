from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.commands import StartInvestigationCommand, StartObservationCommand
from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar import (
    CALENDAR_EVENTS_READ,
    PreparePersonalCalendarObservationCommand,
)
from alsoul.domain.personal_calendar_acquisition import (
    AcquirePersonalCalendarObservationCommand,
)
from alsoul.domain.personal_calendar_cognition import (
    AdoptPersonalCalendarScheduleOutputCommand,
    BuildPersonalCalendarProjectionCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.calendar_runtime_recovery import (
    generate_or_recover,
    operation_id,
    present_or_recover,
)
from alsoul.services.calendar_runtime_selector import CalendarRuntimeSelector
from alsoul.services.personal_calendar import PersonalCalendarReadServices
from alsoul.services.personal_calendar_acquisition_v2 import PersonalCalendarAcquisitionServices
from alsoul.services.personal_calendar_cognition_v2 import PersonalCalendarCognitionServices
from alsoul.services.personal_calendar_presentation_v4 import PersonalCalendarPresentationServices
from alsoul.storage import schema


@dataclass(frozen=True, slots=True)
class PersonalCalendarResponseRunResult:
    investigation_id: UUID
    observation_id: UUID
    source_capture_id: UUID
    world_result_id: UUID
    projection_id: UUID
    model_invocation_id: UUID
    generated_output_id: UUID
    companion_output_id: UUID
    presentation_attempt_id: UUID
    presentation_state: str
    presented_event_id: UUID | None


class PersonalCalendarResponseCoordinator:
    """Compose the hardened F5.A stages for one canonical interaction."""

    def __init__(
        self,
        services,
        *,
        capability_contract,
        read_adapter,
        time_resolver,
        model_adapter,
        presentation_adapter,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.services = services
        self.engine = services.engine
        self.clock = clock or services.clock or SystemClock()
        self.ids = ids or UUIDGenerator()
        self.read_services = PersonalCalendarReadServices(
            self.engine, time_resolver=time_resolver, clock=self.clock, ids=self.ids
        )
        self.acquisition = PersonalCalendarAcquisitionServices(
            self.engine,
            capability_contract=capability_contract,
            adapter=read_adapter,
            time_resolver=time_resolver,
            clock=self.clock,
            ids=self.ids,
        )
        self.cognition = PersonalCalendarCognitionServices(
            self.engine, adapter=model_adapter, clock=self.clock, ids=self.ids
        )
        self.presentation = PersonalCalendarPresentationServices(
            self.engine, adapter=presentation_adapter, clock=self.clock, ids=self.ids
        )
        self.selector = CalendarRuntimeSelector(
            self.engine,
            capability_contract=capability_contract,
            model_adapter=model_adapter,
            clock=self.clock,
        )

    def respond(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        after_process_loss: bool = False,
    ) -> PersonalCalendarResponseRunResult:
        source = self._source(
            relationship_id,
            current_input_event_id,
            surface_binding_id,
            channel_binding_id,
        )
        investigation = self.services.start_investigation(
            StartInvestigationCommand(
                operation_id=operation_id(current_input_event_id, "investigation"),
                initiated_by_companion_person_id=source["companion_person_id"],
                relationship_id=relationship_id,
                objective="Answer one bounded personal calendar question.",
                conversation_id=source["conversation_id"],
            )
        )
        observation = self.services.start_observation(
            StartObservationCommand(
                operation_id=operation_id(current_input_event_id, "observation"),
                investigation_id=investigation.investigation_id,
                acquisition_kind="PERSONAL_CALENDAR_READ",
                request_descriptor={"purpose": CALENDAR_EVENTS_READ},
            )
        )
        prepared = self.read_services.prepare_observation(
            PreparePersonalCalendarObservationCommand(
                operation_id=operation_id(current_input_event_id, "prepare"),
                observation_id=observation.observation_id,
                source_interaction_event_id=current_input_event_id,
            )
        )
        permission_id, credential_id = self.selector.select_read_bindings(
            relationship_id=relationship_id,
            companion_person_id=source["companion_person_id"],
            counterpart_id=source["counterpart_id"],
            resource_id=prepared.personal_resource_binding_id,
        )
        acquired = self.acquisition.acquire(
            AcquirePersonalCalendarObservationCommand(
                operation_id=operation_id(current_input_event_id, "acquire"),
                observation_id=observation.observation_id,
                permission_id=permission_id,
                credential_binding_id=credential_id,
            )
        )
        projection = self.cognition.build_projection(
            BuildPersonalCalendarProjectionCommand(
                operation_id=operation_id(current_input_event_id, "projection"),
                world_result_id=acquired.world_result_id,
                current_input_event_id=current_input_event_id,
            )
        )
        generated = generate_or_recover(
            self.engine,
            self.cognition,
            source_event_id=current_input_event_id,
            projection_id=projection.projection_id,
            permission_id=permission_id,
            route_binding_id=self.selector.select_model_route(relationship_id),
        )
        adopted = self.cognition.adopt_schedule_output(
            AdoptPersonalCalendarScheduleOutputCommand(
                operation_id=operation_id(current_input_event_id, "adopt"),
                generated_output_id=generated.generated_output_id,
            )
        )
        presented = present_or_recover(
            self.engine,
            self.presentation,
            source_event_id=current_input_event_id,
            companion_output_id=adopted.companion_output_id,
            permission_id=permission_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        return PersonalCalendarResponseRunResult(
            investigation.investigation_id,
            observation.observation_id,
            acquired.source_capture_id,
            acquired.world_result_id,
            projection.projection_id,
            generated.model_invocation_id,
            generated.generated_output_id,
            adopted.companion_output_id,
            presented.presentation_attempt_id,
            presented.state,
            presented.interaction_event_id,
        )

    def _source(self, relationship_id, event_id, surface_id, channel_id):
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
            fail("PERSONAL_CALENDAR_RUNTIME_SOURCE_INVALID", "calendar runtime source does not match the trusted relationship route")
        return {
            "companion_person_id": relationship["companion_person_id"],
            "counterpart_id": relationship["counterpart_id"],
            "conversation_id": event["conversation_id"],
        }


__all__ = ["PersonalCalendarResponseCoordinator", "PersonalCalendarResponseRunResult"]
