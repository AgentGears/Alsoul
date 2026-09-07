from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from alsoul.adapters import (
    AdapterRejected,
    F4JsonMemoryRequirementExtractor,
    HttpTransport,
    HttpWorldAdapter,
    JsonFirstPartyPresentationAdapter,
    JsonHttpTransport,
    JsonModelProviderAdapter,
    UrllibHttpTransport,
    UrllibJsonTransport,
    https_origin,
)
from alsoul.domain.errors import fail
from alsoul.domain.models import FoundationResponseDraft
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.diagnostics import (
    FoundationRuntimeDiagnostic,
    FoundationRuntimeDiagnostics,
)
from alsoul.services.foundation import (
    FoundationServices,
    WORLD_MEMORY_REQUIREMENT_PREDICATE,
)
from alsoul.services.interaction_routing import (
    F4InteractionPurpose,
    F4InteractionPurposeGate,
)
from alsoul.services.memory_admission import (
    F4CounterpartMemoryAdmission,
    F4MemoryAdmissionResult,
)
from alsoul.services.runtime import (
    FoundationResponseCoordinator,
    FoundationResponseRunResult,
    RuntimeCheckpoint,
)

_PROBE_PERSON_ID = UUID("00000000-0000-0000-0000-000000000101")
_PROBE_RELATIONSHIP_ID = UUID("00000000-0000-0000-0000-000000000102")
_PROBE_CLAIM_ID = UUID("00000000-0000-0000-0000-000000000103")
_PROBE_WORLD_RESULT_ID = UUID("00000000-0000-0000-0000-000000000104")


@dataclass(frozen=True, slots=True)
class WorldRuntimeConfig:
    """Non-secret configuration for the F4 world acquisition route."""

    locator: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.locator)
        https_origin(self.locator)
        if parsed.fragment:
            raise ValueError("world locator must not contain a URL fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("world timeout_seconds must be positive")

    @property
    def expected_origin(self) -> str:
        return https_origin(self.locator)


@dataclass(frozen=True, slots=True)
class ModelRuntimeConfig:
    """Non-secret configuration for one model-provider route."""

    endpoint: str
    provider_binding_ref: str
    model_ref: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _validate_https_endpoint(self.endpoint, label="model")
        if self.timeout_seconds <= 0:
            raise ValueError("model timeout_seconds must be positive")
        if not self.provider_binding_ref.strip():
            raise ValueError("provider_binding_ref is required")
        if not self.model_ref.strip():
            raise ValueError("model_ref is required")


@dataclass(frozen=True, slots=True)
class PresentationRuntimeConfig:
    """Non-secret route to the idempotent first-party presentation sink."""

    endpoint: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        _validate_https_endpoint(self.endpoint, label="presentation")
        if self.timeout_seconds <= 0:
            raise ValueError("presentation timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class FoundationRuntimeConfig:
    world: WorldRuntimeConfig
    model: ModelRuntimeConfig
    presentation: PresentationRuntimeConfig

    def public_snapshot(self) -> dict[str, Any]:
        """Return only non-secret runtime configuration suitable for diagnostics."""

        return {
            "world": {
                "locator": self.world.locator,
                "expected_origin": self.world.expected_origin,
                "timeout_seconds": self.world.timeout_seconds,
            },
            "model": {
                "endpoint": self.model.endpoint,
                "provider_binding_ref": self.model.provider_binding_ref,
                "model_ref": self.model.model_ref,
                "timeout_seconds": self.model.timeout_seconds,
            },
            "presentation": {
                "endpoint": self.presentation.endpoint,
                "timeout_seconds": self.presentation.timeout_seconds,
            },
        }


@dataclass(frozen=True, slots=True)
class RuntimeSecrets:
    """Ephemeral transport credentials. This object is never persisted by Alsoul."""

    model_authorization_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ModelContractProbeResult:
    provider_binding_ref: str
    model_ref: str
    provider_request_digest: str
    epistemic_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FoundationInteractionRunResult:
    """Outcome of the bounded F4 interaction-purpose gate."""

    interaction_purpose: F4InteractionPurpose
    memory_admission: F4MemoryAdmissionResult | None = None
    response: FoundationResponseRunResult | None = None


class ConfiguredFoundationRuntime:
    """Configured F4 runtime using controlled network adapters.

    Configuration and credentials remain outside canonical companion state. The
    runtime first applies a provider-independent interaction-purpose gate. A bounded
    memory statement can terminate after evidence-grounded memory admission, while a
    bounded world question enters the existing recovery-safe reactive response path.
    """

    def __init__(
        self,
        services: FoundationServices,
        *,
        config: FoundationRuntimeConfig,
        secrets: RuntimeSecrets | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        world_transport: HttpTransport | None = None,
        model_transport: JsonHttpTransport | None = None,
        presentation_transport: JsonHttpTransport | None = None,
    ) -> None:
        self.services = services
        self.config = config
        self.secrets = secrets or RuntimeSecrets()
        self.clock = clock or services.clock or SystemClock()
        self.ids = ids or UUIDGenerator()

        self.world_adapter = HttpWorldAdapter(
            locator=config.world.locator,
            timeout_seconds=config.world.timeout_seconds,
            transport=world_transport or UrllibHttpTransport(),
        )
        self.world_extractor = F4JsonMemoryRequirementExtractor(
            expected_https_origin=config.world.expected_origin,
            predicate=WORLD_MEMORY_REQUIREMENT_PREDICATE,
        )
        self.model_adapter = JsonModelProviderAdapter(
            endpoint=config.model.endpoint,
            provider_binding_ref=config.model.provider_binding_ref,
            model_ref=config.model.model_ref,
            authorization_token=self.secrets.model_authorization_token,
            timeout_seconds=config.model.timeout_seconds,
            transport=model_transport or UrllibJsonTransport(),
        )
        self.presentation_adapter = JsonFirstPartyPresentationAdapter(
            endpoint=config.presentation.endpoint,
            timeout_seconds=config.presentation.timeout_seconds,
            transport=presentation_transport or UrllibJsonTransport(),
        )
        self.interaction_gate = F4InteractionPurposeGate(services)
        self.memory_admission = F4CounterpartMemoryAdmission(services)
        self.coordinator = FoundationResponseCoordinator(
            services,
            clock=self.clock,
            ids=self.ids,
        )
        self.diagnostics = FoundationRuntimeDiagnostics(services.engine)

    def interact(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        after_process_loss: bool = False,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> FoundationInteractionRunResult:
        """Run the bounded F4 purpose gate over one already-admitted input."""

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

    def respond(
        self,
        *,
        relationship_id: UUID,
        current_input_event_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        after_process_loss: bool = False,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> FoundationResponseRunResult:
        return self.coordinator.respond(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
            world_adapter=self.world_adapter,
            world_extractor=self.world_extractor,
            model_adapter=self.model_adapter,
            presentation_adapter=self.presentation_adapter,
            after_process_loss=after_process_loss,
            checkpoint=checkpoint,
        )

    def diagnose(
        self, *, relationship_id: UUID, current_input_event_id: UUID
    ) -> FoundationRuntimeDiagnostic:
        return self.diagnostics.assess(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )

    def probe_model_contract(self) -> ModelContractProbeResult:
        """Perform an operator-only provider contract probe with synthetic context.

        This is not CompanionPerson cognition and writes no ModelInvocation,
        GeneratedOutput, memory, or Timeline state. It verifies only that the
        configured endpoint can satisfy the current F4 wire contract.
        """

        context = _synthetic_provider_context()
        digest = self.model_adapter.provider_request_digest(context)
        draft = self.model_adapter.generate(context)
        _validate_probe_sources(draft)
        return ModelContractProbeResult(
            provider_binding_ref=self.model_adapter.provider_binding_ref,
            model_ref=self.model_adapter.model_ref,
            provider_request_digest=digest,
            epistemic_kinds=tuple(
                segment.epistemic_kind for segment in draft.segments
            ),
        )


def _validate_https_endpoint(value: str, *, label: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            f"{label} endpoint must be an absolute HTTPS URL without embedded credentials"
        )
    if parsed.fragment:
        raise ValueError(f"{label} endpoint must not contain a URL fragment")


def _synthetic_provider_context() -> dict[str, Any]:
    return {
        "person": {
            "person_id": str(_PROBE_PERSON_ID),
            "role": "PERSONAL_COMPANION",
            "preferred_name": "Alsoul",
            "self_revision": 1,
        },
        "relationship_id": str(_PROBE_RELATIONSHIP_ID),
        "current_input": "Operational contract probe. Produce only the requested structured response.",
        "personal_context": [
            {
                "claim_id": str(_PROBE_CLAIM_ID),
                "predicate": "primary_machine.memory_gb",
                "value": 16,
                "epistemic_basis": "COUNTERPART_STATED_MEMORY",
            }
        ],
        "world_context": [
            {
                "world_result_id": str(_PROBE_WORLD_RESULT_ID),
                "predicate": WORLD_MEMORY_REQUIREMENT_PREDICATE,
                "value": 24,
                "epistemic_mode": "CURRENT_CHECKED",
            }
        ],
    }


def _validate_probe_sources(draft: FoundationResponseDraft) -> None:
    if (
        len(draft.segments) != 3
        or draft.segments[0].source_ref != _PROBE_CLAIM_ID
        or draft.segments[1].source_ref != _PROBE_WORLD_RESULT_ID
        or draft.segments[2].source_ref is not None
    ):
        raise AdapterRejected(
            "configured model endpoint did not preserve the synthetic F4 source-attribution contract"
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
