from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from alsoul.adapters import HttpTransport, JsonHttpTransport
from alsoul.domain.types import Clock, SystemClock
from alsoul.host.config import FoundationHostConfig
from alsoul.host.readiness import HostReadiness, require_host_readiness
from alsoul.services import (
    ConfiguredFoundationRuntime,
    F4CounterpartMemoryAdmission,
    FirstPartyIngress,
    FoundationServices,
    RuntimeSecrets,
    TrustedCounterpartInputEnvelope,
)
from alsoul.storage import create_sqlite_engine, schema
from alsoul.surface.store import LocalSurfacePresentationTransport, LocalSurfaceStore


@dataclass(frozen=True, slots=True)
class LocalSurfaceIdentity:
    identity_namespace: str
    external_subject: str
    surface_namespace: str = "alsoul.first_party"
    surface_ref: str = "primary-text-surface"
    channel_namespace: str = "alsoul.first_party"
    channel_ref: str = "primary-text-channel"

    def __post_init__(self) -> None:
        for field_name in (
            "identity_namespace",
            "external_subject",
            "surface_namespace",
            "surface_ref",
            "channel_namespace",
            "channel_ref",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class LocalSurfaceInteractionResult:
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    input_event_id: UUID
    presented_event_id: UUID
    companion_output_id: UUID
    content_text: str
    transport_event_id: str
    idempotent_input_replay: bool
    memory_disposition: str = "NO_CANDIDATE"
    memory_claim_id: UUID | None = None
    memory_corrected_claim_id: UUID | None = None


class LocalFirstPartySurfaceApplication:
    """Local first-party UI composition over the existing trusted F4 boundaries.

    The surface owns only local interaction routing and operational presentation
    acceptance state. Canonical identity, Timeline, evidence, memory admission,
    cognition, adoption, and presentation history remain owned by semantic services.
    """

    def __init__(
        self,
        *,
        config: FoundationHostConfig,
        identity: LocalSurfaceIdentity,
        surface_state_path: str | Path,
        secrets: RuntimeSecrets | None = None,
        clock: Clock | None = None,
        world_transport: HttpTransport | None = None,
        model_transport: JsonHttpTransport | None = None,
    ) -> None:
        self.config = config
        self.identity = identity
        self.clock = clock or SystemClock()
        self.readiness: HostReadiness = require_host_readiness(config)
        self.engine = create_sqlite_engine(config.database_path)
        self.services = FoundationServices(self.engine, clock=self.clock)
        self.ingress = FirstPartyIngress(self.services)
        self.memory_admission = F4CounterpartMemoryAdmission(self.services)
        self.surface_store = LocalSurfaceStore(surface_state_path)
        self._transport_events_seen_this_process: set[str] = set()
        self.runtime = ConfiguredFoundationRuntime(
            self.services,
            config=config.runtime,
            secrets=secrets or RuntimeSecrets(),
            clock=self.clock,
            world_transport=world_transport,
            model_transport=model_transport,
            presentation_transport=LocalSurfacePresentationTransport(self.surface_store),
        )

    def interact(
        self,
        content_text: str,
        *,
        transport_event_id: str | None = None,
        conversation_id: str | None = "local-first-party",
    ) -> LocalSurfaceInteractionResult:
        if not isinstance(content_text, str) or not content_text.strip():
            raise ValueError("content_text must be a non-empty string")
        event_key = transport_event_id.strip() if transport_event_id is not None else str(uuid4())
        if not event_key:
            raise ValueError("transport_event_id must be non-empty when supplied")

        reservation = self.surface_store.reserve_input(
            transport_event_id=event_key,
            identity_namespace=self.identity.identity_namespace,
            external_subject=self.identity.external_subject,
            surface_namespace=self.identity.surface_namespace,
            surface_ref=self.identity.surface_ref,
            channel_namespace=self.identity.channel_namespace,
            channel_ref=self.identity.channel_ref,
            content_text=content_text,
            conversation_id=conversation_id,
            occurred_at=self.clock.now(),
        )
        replay_from_prior_process = (
            reservation.existing
            and event_key not in self._transport_events_seen_this_process
        )
        self._transport_events_seen_this_process.add(event_key)

        envelope = TrustedCounterpartInputEnvelope(
            identity_namespace=self.identity.identity_namespace,
            external_subject=self.identity.external_subject,
            surface_namespace=self.identity.surface_namespace,
            surface_ref=self.identity.surface_ref,
            channel_namespace=self.identity.channel_namespace,
            channel_ref=self.identity.channel_ref,
            transport_event_id=event_key,
            content_text=content_text,
            occurred_at=reservation.occurred_at,
            conversation_id=conversation_id,
        )
        admitted = self.ingress.admit(envelope)

        # Memory admission is a distinct governed boundary after canonical input
        # persistence and before ContextProjection. A statement can therefore become
        # usable in the same response only after Claim/Evidence admission commits.
        memory = self.memory_admission.consider_event(admitted.event_id)

        response = self.runtime.respond(
            relationship_id=admitted.relationship_id,
            current_input_event_id=admitted.event_id,
            surface_binding_id=admitted.surface_binding_id,
            channel_binding_id=admitted.channel_binding_id,
            after_process_loss=replay_from_prior_process,
        )

        presentation = self.surface_store.get_by_companion_output_id(
            response.companion_output_id
        )
        if presentation is not None:
            content = presentation.content_text
        else:
            with self.engine.connect() as conn:
                row = conn.execute(
                    select(schema.companion_output.c.content_text).where(
                        schema.companion_output.c.companion_output_id
                        == response.companion_output_id
                    )
                ).one_or_none()
            if row is None:
                raise RuntimeError("presented CompanionOutput could not be recovered")
            content = str(row[0])

        return LocalSurfaceInteractionResult(
            companion_person_id=admitted.companion_person_id,
            counterpart_id=admitted.counterpart_id,
            relationship_id=admitted.relationship_id,
            input_event_id=admitted.event_id,
            presented_event_id=response.presented_event_id,
            companion_output_id=response.companion_output_id,
            content_text=content,
            transport_event_id=event_key,
            idempotent_input_replay=admitted.idempotent_replay,
            memory_disposition=memory.disposition,
            memory_claim_id=memory.claim_id,
            memory_corrected_claim_id=memory.corrected_claim_id,
        )

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> "LocalFirstPartySurfaceApplication":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()


__all__ = [
    "LocalFirstPartySurfaceApplication",
    "LocalSurfaceIdentity",
    "LocalSurfaceInteractionResult",
]
