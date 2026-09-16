from __future__ import annotations

from dataclasses import dataclass

from alsoul.domain.errors import fail
from alsoul.services.configured_runtime import (
    FoundationRuntimeConfig,
    ModelContractProbeResult,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    RuntimeSecrets,
    WorldRuntimeConfig,
)
from alsoul.services.configured_runtime_v2 import (
    ConfiguredFoundationRuntime as ConfiguredFoundationRuntimeV2,
    FoundationInteractionRunResult as FoundationInteractionRunResultV2,
)
from alsoul.services.conversation_open_loop import F4ConversationOpenLoopResult
from alsoul.services.conversational_runtime import FoundationConversationalResponseRunResult
from alsoul.services.interaction_routing_current_v2 import (
    CurrentInteractionPurpose,
    CurrentInteractionPurposeGate,
)
from alsoul.services.memory_admission import F4MemoryAdmissionResult
from alsoul.services.personal_calendar_mutation_runtime import (
    PersonalCalendarMutationRunResult,
)
from alsoul.services.personal_calendar_runtime import PersonalCalendarResponseRunResult
from alsoul.services.runtime import FoundationResponseRunResult, RuntimeCheckpoint


@dataclass(frozen=True, slots=True)
class FoundationInteractionRunResult:
    """Outcome of the current bounded interaction-purpose gate."""

    interaction_purpose: CurrentInteractionPurpose
    memory_admission: F4MemoryAdmissionResult | None = None
    open_loop_transition: F4ConversationOpenLoopResult | None = None
    response: (
        FoundationResponseRunResult
        | FoundationConversationalResponseRunResult
        | PersonalCalendarResponseRunResult
        | PersonalCalendarMutationRunResult
        | None
    ) = None


class ConfiguredFoundationRuntime(ConfiguredFoundationRuntimeV2):
    """Current runtime with bounded F5.A reads and two-turn F5.B mutation routing."""

    def __init__(
        self,
        *args,
        personal_calendar_mutation_coordinator=None,
        **kwargs,
    ) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.interaction_gate = CurrentInteractionPurposeGate(self.services)
        self.personal_calendar_mutation_coordinator = personal_calendar_mutation_coordinator

    def interact(
        self,
        *,
        relationship_id,
        current_input_event_id,
        surface_binding_id,
        channel_binding_id,
        after_process_loss: bool = False,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> FoundationInteractionRunResult:
        classification = self.interaction_gate.classify_event(
            current_input_event_id,
            expected_relationship_id=relationship_id,
            expected_surface_binding_id=surface_binding_id,
            expected_channel_binding_id=channel_binding_id,
        )
        if classification.purpose in {
            "PERSONAL_CALENDAR_CREATE_REQUEST",
            "PERSONAL_CALENDAR_CREATE_APPROVAL",
        }:
            coordinator = self.personal_calendar_mutation_coordinator
            if coordinator is None:
                fail(
                    "PERSONAL_CALENDAR_MUTATION_RUNTIME_UNCONFIGURED",
                    "calendar-create interaction requires the specialized F5.B runtime",
                )
            kwargs = {
                "relationship_id": relationship_id,
                "current_input_event_id": current_input_event_id,
                "surface_binding_id": surface_binding_id,
                "channel_binding_id": channel_binding_id,
            }
            if classification.purpose == "PERSONAL_CALENDAR_CREATE_REQUEST":
                response = coordinator.start_create(**kwargs)
            else:
                response = coordinator.approve_and_execute(**kwargs)
            return FoundationInteractionRunResult(
                interaction_purpose=classification.purpose,
                response=response,
            )

        prior: FoundationInteractionRunResultV2 = super().interact(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
            after_process_loss=after_process_loss,
            checkpoint=checkpoint,
        )
        return FoundationInteractionRunResult(
            interaction_purpose=prior.interaction_purpose,
            memory_admission=prior.memory_admission,
            open_loop_transition=prior.open_loop_transition,
            response=prior.response,
        )


__all__ = [
    "ConfiguredFoundationRuntime",
    "FoundationInteractionRunResult",
    "FoundationRuntimeConfig",
    "ModelContractProbeResult",
    "ModelRuntimeConfig",
    "PresentationRuntimeConfig",
    "RuntimeSecrets",
    "WorldRuntimeConfig",
]
