from __future__ import annotations

from uuid import uuid4

import pytest

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    ConfiguredFoundationRuntime,
    FoundationBootstrapper,
    FoundationRuntimeConfig,
    FoundationServices,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
    classify_current_interaction_text,
)


def _append(foundation, ids, now, text):
    return foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )


def _runtime(engine, now, foundation):
    return ConfiguredFoundationRuntime(
        foundation,
        config=FoundationRuntimeConfig(
            world=WorldRuntimeConfig(locator="https://world.invalid/f4"),
            model=ModelRuntimeConfig(
                endpoint="https://model.invalid/generate",
                provider_binding_ref="model.test/f4",
                model_ref="f4-model",
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://presentation.invalid/accept"
            ),
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def test_current_gate_classifies_only_exact_calendar_question_grammar():
    assert (
        classify_current_interaction_text("What's on my calendar on 2026-09-12?")
        == "PERSONAL_CALENDAR_QUESTION"
    )
    assert (
        classify_current_interaction_text(
            "What do I have on my calendar on 2026-09-12?"
        )
        == "PERSONAL_CALENDAR_QUESTION"
    )
    assert classify_current_interaction_text("Show my calendar tomorrow") == "UNSUPPORTED"


def test_calendar_question_cannot_fall_through_generic_runtime_when_unconfigured(engine, now):
    ids = FoundationBootstrapper(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    ).bootstrap(identity_namespace="calendar-route-test", external_subject=str(uuid4()))
    foundation = FoundationServices(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    )
    source = _append(
        foundation, ids, now, "What's on my calendar on 2026-09-12?"
    )
    runtime = _runtime(engine, now, foundation)

    with pytest.raises(DomainError) as excinfo:
        runtime.interact(
            relationship_id=ids.relationship_id,
            current_input_event_id=source.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    assert excinfo.value.code == "PERSONAL_CALENDAR_RUNTIME_UNCONFIGURED"
