from __future__ import annotations

from dataclasses import dataclass

from alsoul.domain.errors import fail
from alsoul.services.configured_runtime import (
    ConfiguredFoundationRuntime as ConfiguredFoundationRuntimeV1,
    FoundationRuntimeConfig,
    ModelContractProbeResult,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    RuntimeSecrets,
    WorldRuntimeConfig,
)
from alsoul.services.conversation_open_loop import (
    F4ConversationOpenLoopResult,
    F4ConversationOpenLoopService,
)
from alsoul.services.conversational_runtime import FoundationConversationalResponseRunResult
from alsoul.services.interaction_routing import F4InteractionPurpose
from alsoul.services.memory_admission import F4MemoryAdmissionResult
from alsoul.services.runtime import FoundationResponseRunResult, RuntimeCheckpoint


@dataclass(frozen=True, slots=True)
class FoundationInteractionRunResult:
    """Outcome of the current bounded interaction-purpose gate."""

    interaction_purpose: F4InteractionPurpose
    memory_admission: F4MemoryAdmissionResult | None = None
    open_loop_transition: F4ConversationOpenLoopResult | None = None
    response: (
        FoundationResponseRunResult
        | FoundationConversationalResponseRunResult
        | None
    ) = None


class ConfiguredFoundationRuntime(ConfiguredFoundationRuntimeV1):
    """Current runtime with governed ConversationOpenLoop admission/closure."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.open_loop_service = F4ConversationOpenLoopService(self.services)

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
        if classification.purpose == "MEMORY_STATEMENT":
            memory = self.memory_admission.consider_event(current_input_event_id)
            return FoundationInteractionRunResult(
                interaction_purpose=classification.purpose,
                memory_admission=memory,
            )
        if classification.purpose == "CONVERSATIONAL_RESPONSE":
            open_loop = self.open_loop_service.consider_event(current_input_event_id)
            response = self.conversational_coordinator.respond(
                relationship_id=relationship_id,
                current_input_event_id=current_input_event_id,
                surface_binding_id=surface_binding_id,
                channel_binding_id=channel_binding_id,
                model_adapter=self.model_adapter,
                presentation_adapter=self.presentation_adapter,
                after_process_loss=after_process_loss,
                checkpoint=checkpoint,
            )
            return FoundationInteractionRunResult(
                interaction_purpose=classification.purpose,
                open_loop_transition=open_loop,
                response=response,
            )
        if classification.purpose == "WORLD_QUESTION":
            response = self.respond(
                relationship_id=relationship_id,
                current_input_event_id=current_input_event_id,
                surface_binding_id=surface_binding_id,
                channel_binding_id=channel_binding_id,
                after_process_loss=after_process_loss,
                checkpoint=checkpoint,
            )
            return FoundationInteractionRunResult(
                interaction_purpose=classification.purpose,
                response=response,
            )
        fail(
            "INTERACTION_PURPOSE_UNSUPPORTED",
            "input is outside the bounded F4 interaction-purpose contract",
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
