from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from alsoul.adapters.contracts import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    ModelProviderAdapter,
    WorldAcquisitionAdapter,
)
from alsoul.domain.commands import (
    CompleteModelInvocationCommand,
    RecordObservationSuccessCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.domain.models import FoundationResponseDraft, WorldAcquisitionSuccess
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.foundation import FoundationServices


@dataclass(frozen=True, slots=True)
class WorldAcquisitionRunResult:
    observation_id: UUID
    source_capture_id: UUID
    evidence_id: UUID


@dataclass(frozen=True, slots=True)
class ModelGenerationRunResult:
    model_invocation_id: UUID
    generated_output_id: UUID


class WorldAcquisitionRunner:
    """Run one concrete read-only acquisition under an existing Investigation.

    The Observation is persisted before calling the adapter. Provider return data
    becomes canonical only through RecordObservationSuccess; this runner never
    creates a WorldResult.
    """

    def __init__(
        self,
        services: FoundationServices,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.services = services
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def run(
        self,
        *,
        investigation_id: UUID,
        adapter: WorldAcquisitionAdapter,
        acquisition_kind: str,
        request_descriptor: dict[str, Any],
    ) -> WorldAcquisitionRunResult:
        observation = self.services.start_observation(
            StartObservationCommand(
                operation_id=self.ids.new(),
                investigation_id=investigation_id,
                acquisition_kind=acquisition_kind,
                request_descriptor=request_descriptor,
            )
        )

        try:
            acquired = adapter.acquire(captured_at=self.clock.now())
            if not isinstance(acquired, WorldAcquisitionSuccess):
                raise TypeError("world adapter returned an invalid acquisition result")
            success_command = RecordObservationSuccessCommand(
                operation_id=self.ids.new(),
                observation_id=observation.observation_id,
                source_identity=acquired.source_identity,
                requested_locator=acquired.requested_locator,
                resolved_locator=acquired.resolved_locator,
                content_text=acquired.content,
                captured_at=acquired.captured_at,
                source_version=acquired.source_version,
                source_published_at=acquired.source_published_at,
                source_modified_at=acquired.source_modified_at,
            )
        except Exception:
            self._mark_observation_failed_best_effort(observation.observation_id)
            raise

        try:
            accepted = self.services.record_observation_success(success_command)
        except Exception:
            # If the success transaction definitely did not commit, FAILED is the
            # conservative recoverable state. If it did commit before transport
            # uncertainty, the terminal-state guard prevents rewriting SUCCEEDED.
            self._mark_observation_failed_best_effort(observation.observation_id)
            raise

        return WorldAcquisitionRunResult(
            observation_id=observation.observation_id,
            source_capture_id=accepted.source_capture_id,
            evidence_id=accepted.evidence_id,
        )

    def _mark_observation_failed_best_effort(self, observation_id: UUID) -> None:
        try:
            self.services.record_observation_failure(
                operation_id=self.ids.new(),
                observation_id=observation_id,
            )
        except Exception:
            # Preserve the primary failure. Recovery derives the durable state and
            # will not treat an orphan STARTED observation as successful evidence.
            pass


class ModelGenerationRunner:
    """Bind one replaceable provider attempt to an immutable ContextProjection.

    ModelInvocation is committed before dispatch. A successful provider return is
    persisted only as GeneratedOutput; adoption and presentation remain separate
    semantic boundaries.
    """

    def __init__(
        self,
        services: FoundationServices,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        renderer_version: str = "f4-renderer-v1",
    ) -> None:
        self.services = services
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()
        self.renderer_version = renderer_version

    def run(
        self,
        *,
        context_projection_id: UUID,
        adapter: ModelProviderAdapter,
    ) -> ModelGenerationRunResult:
        provider_context = self.services.render_provider_context(context_projection_id)
        request_digest = sha256_text(canonical_json(provider_context))
        invocation = self.services.start_model_invocation(
            StartModelInvocationCommand(
                operation_id=self.ids.new(),
                context_projection_id=context_projection_id,
                provider_binding_ref=adapter.provider_binding_ref,
                model_ref=adapter.model_ref,
                renderer_version=self.renderer_version,
                provider_request_digest=request_digest,
            )
        )

        try:
            draft = adapter.generate(provider_context)
            if not isinstance(draft, FoundationResponseDraft):
                raise AdapterRejected("model adapter returned an invalid draft type")
            content_text = draft.render_text()
            semantic_payload = draft.to_payload()
        except AdapterRejected:
            self.services.fail_model_invocation(invocation.model_invocation_id)
            raise
        except AdapterOutcomeUnknown:
            self.services.fail_model_invocation(
                invocation.model_invocation_id,
                unknown=True,
            )
            raise
        except Exception as exc:
            self.services.fail_model_invocation(
                invocation.model_invocation_id,
                unknown=True,
            )
            raise AdapterOutcomeUnknown(
                "model adapter outcome became unusable after invocation dispatch began"
            ) from exc

        completion = CompleteModelInvocationCommand(
            operation_id=self.ids.new(),
            model_invocation_id=invocation.model_invocation_id,
            content_text=content_text,
            content_digest=sha256_text(content_text),
            semantic_payload=semantic_payload,
            received_at=self.clock.now(),
        )
        try:
            generated = self.services.complete_model_invocation(completion)
        except Exception:
            self._mark_model_unknown_best_effort(invocation.model_invocation_id)
            raise

        return ModelGenerationRunResult(
            model_invocation_id=invocation.model_invocation_id,
            generated_output_id=generated.generated_output_id,
        )

    def _mark_model_unknown_best_effort(self, model_invocation_id: UUID) -> None:
        try:
            self.services.fail_model_invocation(model_invocation_id, unknown=True)
        except Exception:
            # Preserve the primary persistence failure. If completion committed,
            # SUCCEEDED stays terminal; otherwise recovery sees IN_PROGRESS/UNKNOWN.
            pass


__all__ = [
    "ModelGenerationRunResult",
    "ModelGenerationRunner",
    "WorldAcquisitionRunResult",
    "WorldAcquisitionRunner",
]
