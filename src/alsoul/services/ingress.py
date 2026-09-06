from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import fail
from alsoul.services.common import request_digest
from alsoul.services.foundation import FoundationServices
from alsoul.storage import schema

_INGRESS_NAMESPACE = UUID("64d89465-0866-4aec-9bb5-9c032bce50c7")


@dataclass(frozen=True, slots=True)
class TrustedCounterpartInputEnvelope:
    """Authenticated first-party transport assertion presented to Alsoul ingress.

    Authentication of `external_subject` is a host/transport responsibility before
    this envelope reaches the semantic ingress boundary. Alsoul resolves only
    pre-existing identity, relationship, surface, and channel bindings and never
    infers or creates them from message content.
    """

    identity_namespace: str
    external_subject: str
    surface_namespace: str
    surface_ref: str
    channel_namespace: str
    channel_ref: str
    transport_event_id: str
    content_text: str
    occurred_at: datetime
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "identity_namespace",
            "external_subject",
            "surface_namespace",
            "surface_ref",
            "channel_namespace",
            "channel_ref",
            "transport_event_id",
            "content_text",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.conversation_id is not None and not self.conversation_id.strip():
            raise ValueError("conversation_id must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class AdmitTrustedCounterpartInputResult:
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID
    event_id: UUID
    timeline_seq: int
    idempotent_replay: bool


class FirstPartyIngress:
    """Resolve trusted transport identity into existing Alsoul relationship state."""

    def __init__(self, services: FoundationServices) -> None:
        self.services = services

    def admit(
        self, envelope: TrustedCounterpartInputEnvelope
    ) -> AdmitTrustedCounterpartInputResult:
        with self.services.engine.connect() as conn:
            channel = conn.execute(
                select(schema.channel_binding).where(
                    schema.channel_binding.c.channel_namespace
                    == envelope.channel_namespace,
                    schema.channel_binding.c.companion_endpoint_ref
                    == envelope.channel_ref,
                )
            ).mappings().one_or_none()
            if channel is None:
                fail(
                    "INGRESS_CHANNEL_BINDING_NOT_FOUND",
                    "trusted ingress channel binding does not exist",
                )

            surface = conn.execute(
                select(schema.surface_binding).where(
                    schema.surface_binding.c.surface_namespace
                    == envelope.surface_namespace,
                    schema.surface_binding.c.surface_ref == envelope.surface_ref,
                )
            ).mappings().one_or_none()
            if surface is None:
                fail(
                    "INGRESS_SURFACE_BINDING_NOT_FOUND",
                    "trusted ingress surface binding does not exist",
                )
            if surface["companion_person_id"] != channel["companion_person_id"]:
                fail(
                    "INGRESS_PRESENCE_BINDING_MISMATCH",
                    "surface and channel bindings belong to different CompanionPersons",
                )

            identity = conn.execute(
                select(schema.counterpart_identity_binding).where(
                    schema.counterpart_identity_binding.c.identity_namespace
                    == envelope.identity_namespace,
                    schema.counterpart_identity_binding.c.external_subject
                    == envelope.external_subject,
                )
            ).mappings().one_or_none()
            if identity is None:
                fail(
                    "INGRESS_IDENTITY_BINDING_NOT_FOUND",
                    "trusted counterpart identity binding does not exist",
                )

            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.companion_person_id
                    == channel["companion_person_id"],
                    schema.relationship_identity.c.counterpart_id
                    == identity["counterpart_id"],
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail(
                    "INGRESS_RELATIONSHIP_NOT_FOUND",
                    "existing relationship could not be resolved for trusted ingress",
                )

        semantic_identity = {
            "channel_binding_id": channel["channel_binding_id"],
            "identity_namespace": envelope.identity_namespace,
            "external_subject": envelope.external_subject,
            "transport_event_id": envelope.transport_event_id,
        }
        semantic_digest = request_digest(semantic_identity)
        operation_id = uuid5(_INGRESS_NAMESPACE, f"first-party:{semantic_digest}")
        ingress_key = f"first-party-v1:{semantic_digest}"

        admitted = self.services.append_counterpart_input(
            AppendCounterpartInputCommand(
                operation_id=operation_id,
                companion_person_id=channel["companion_person_id"],
                counterpart_id=identity["counterpart_id"],
                relationship_id=relationship["relationship_id"],
                ingress_idempotency_key=ingress_key,
                content_text=envelope.content_text,
                occurred_at=envelope.occurred_at,
                surface_binding_id=surface["surface_binding_id"],
                channel_binding_id=channel["channel_binding_id"],
                conversation_id=envelope.conversation_id,
            )
        )
        return AdmitTrustedCounterpartInputResult(
            companion_person_id=channel["companion_person_id"],
            counterpart_id=identity["counterpart_id"],
            relationship_id=relationship["relationship_id"],
            surface_binding_id=surface["surface_binding_id"],
            channel_binding_id=channel["channel_binding_id"],
            event_id=admitted.event_id,
            timeline_seq=admitted.timeline_seq,
            idempotent_replay=admitted.idempotent_replay,
        )


__all__ = [
    "AdmitTrustedCounterpartInputResult",
    "FirstPartyIngress",
    "TrustedCounterpartInputEnvelope",
]
