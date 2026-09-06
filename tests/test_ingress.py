from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.errors import DomainError
from alsoul.services import FirstPartyIngress, TrustedCounterpartInputEnvelope
from alsoul.storage import schema


def _envelope(now, *, external_subject: str = "counterpart-1", transport_event_id: str = "evt-1"):
    return TrustedCounterpartInputEnvelope(
        identity_namespace="first-party-test",
        external_subject=external_subject,
        surface_namespace="alsoul.first_party",
        surface_ref="primary-text-surface",
        channel_namespace="alsoul.first_party",
        channel_ref="primary-text-channel",
        transport_event_id=transport_event_id,
        content_text="Would the current software run on my machine?",
        occurred_at=now,
        conversation_id="thread-a",
    )


def test_first_party_ingress_resolves_existing_identity_relationship_and_presence(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="first-party-test",
        external_subject="counterpart-1",
    )
    ingress = FirstPartyIngress(services)

    admitted = ingress.admit(_envelope(now))

    assert admitted.companion_person_id == ids.companion_person_id
    assert admitted.counterpart_id == ids.counterpart_id
    assert admitted.relationship_id == ids.relationship_id
    assert admitted.surface_binding_id == ids.surface_binding_id
    assert admitted.channel_binding_id == ids.channel_binding_id
    assert admitted.timeline_seq == 1
    assert admitted.idempotent_replay is False

    with services.engine.connect() as conn:
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == admitted.event_id
            )
        ).mappings().one()
    assert event["event_kind"] == "COUNTERPART_INPUT"
    assert event["relationship_id"] == ids.relationship_id
    assert event["surface_binding_id"] == ids.surface_binding_id
    assert event["channel_binding_id"] == ids.channel_binding_id


def test_duplicate_transport_event_is_one_logical_interaction_event(
    services, bootstrapper, now
):
    bootstrapper.bootstrap(
        identity_namespace="first-party-test",
        external_subject="counterpart-1",
    )
    ingress = FirstPartyIngress(services)
    envelope = _envelope(now)

    first = ingress.admit(envelope)
    second = ingress.admit(envelope)

    assert second.event_id == first.event_id
    assert second.timeline_seq == first.timeline_seq
    assert second.idempotent_replay is True
    with services.engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(schema.interaction_event)
        ).scalar_one()
    assert count == 1


def test_same_transport_event_identity_cannot_change_semantic_request(
    services, bootstrapper, now
):
    bootstrapper.bootstrap(
        identity_namespace="first-party-test",
        external_subject="counterpart-1",
    )
    ingress = FirstPartyIngress(services)
    envelope = _envelope(now)
    ingress.admit(envelope)

    with pytest.raises(DomainError) as excinfo:
        ingress.admit(replace(envelope, content_text="Different content"))

    assert excinfo.value.code == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"


def test_unknown_external_identity_fails_closed_without_creating_identity_or_relationship(
    services, bootstrapper, now
):
    bootstrapper.bootstrap(
        identity_namespace="first-party-test",
        external_subject="counterpart-1",
    )
    ingress = FirstPartyIngress(services)

    with pytest.raises(DomainError) as excinfo:
        ingress.admit(_envelope(now, external_subject="unknown-counterpart"))

    assert excinfo.value.code == "INGRESS_IDENTITY_BINDING_NOT_FOUND"
    with services.engine.connect() as conn:
        counterpart_count = conn.execute(
            select(func.count()).select_from(schema.counterpart_person)
        ).scalar_one()
        relationship_count = conn.execute(
            select(func.count()).select_from(schema.relationship_identity)
        ).scalar_one()
        event_count = conn.execute(
            select(func.count()).select_from(schema.interaction_event)
        ).scalar_one()
    assert counterpart_count == 1
    assert relationship_count == 1
    assert event_count == 0


def test_new_conversation_ref_keeps_same_relationship(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="first-party-test",
        external_subject="counterpart-1",
    )
    ingress = FirstPartyIngress(services)

    first = ingress.admit(_envelope(now, transport_event_id="evt-a"))
    second = ingress.admit(
        replace(
            _envelope(now, transport_event_id="evt-b"),
            conversation_id="thread-b",
        )
    )

    assert first.relationship_id == ids.relationship_id
    assert second.relationship_id == ids.relationship_id
    assert second.timeline_seq == 2
