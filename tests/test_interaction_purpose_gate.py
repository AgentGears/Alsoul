from __future__ import annotations

from uuid import uuid4

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.services import F4InteractionPurposeGate, classify_f4_interaction_text


def test_f4_interaction_text_classification_is_bounded_and_deterministic():
    assert classify_f4_interaction_text("My machine has 16 GB RAM.") == "MEMORY_STATEMENT"
    assert (
        classify_f4_interaction_text("Actually, my machine has 32 GB RAM.")
        == "MEMORY_STATEMENT"
    )
    assert (
        classify_f4_interaction_text("Would the current software run on my machine?")
        == "WORLD_QUESTION"
    )
    assert (
        classify_f4_interaction_text(
            "Does my computer meet the current software memory requirements?"
        )
        == "WORLD_QUESTION"
    )

    assert classify_f4_interaction_text("Tell me a joke.") == "UNSUPPORTED"
    assert classify_f4_interaction_text("What is the weather?") == "UNSUPPORTED"
    assert classify_f4_interaction_text("My machine has 16 GB RAM; would it run?") == "UNSUPPORTED"


def test_f4_interaction_gate_classifies_from_canonical_timeline_event(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="purpose-gate",
        external_subject="u1",
    )
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="purpose-world-question",
            content_text="Would the current software run on my machine?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="purpose-gate",
        )
    )

    classification = F4InteractionPurposeGate(services).classify_event(event.event_id)

    assert classification.source_event_id == event.event_id
    assert classification.purpose == "WORLD_QUESTION"
