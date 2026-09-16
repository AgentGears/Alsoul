from __future__ import annotations

from alsoul.services import (
    ConfiguredFoundationRuntime,
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
)
from alsoul.domain.types import FixedClock, UUIDGenerator

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_mutation_runtime as runtime_cases


def _configured(ctx, now):
    return ConfiguredFoundationRuntime(
        ctx["foundation"],
        config=FoundationRuntimeConfig(
            world=WorldRuntimeConfig(locator="https://world.invalid/f5b"),
            model=ModelRuntimeConfig(
                endpoint="https://model.invalid/generate",
                provider_binding_ref="model.test/f4",
                model_ref="f4-model",
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://presentation.invalid/accept"
            ),
        ),
        personal_calendar_mutation_coordinator=ctx["coordinator"],
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def test_configured_runtime_routes_two_turn_mutation_and_process_replay_without_redispatch(
    engine, now
):
    ctx = runtime_cases._runtime(engine, now)
    runtime = _configured(ctx, now)
    request = action_cases._append_create_request(ctx["foundation"], ctx["ids"], now)

    started = runtime.interact(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=request.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    assert started.interaction_purpose == "PERSONAL_CALENDAR_CREATE_REQUEST"
    assert started.response.status == "AWAITING_APPROVAL"
    assert ctx["mutation_adapter"].calls == []

    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"],
        ctx["ids"],
        now,
        started.response.approval_challenge,
    )
    completed = runtime.interact(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    replay = runtime.interact(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
        after_process_loss=True,
    )

    assert completed.interaction_purpose == "PERSONAL_CALENDAR_CREATE_APPROVAL"
    assert completed.response.status == "PRESENTED"
    assert completed.response.presentation_state == "ACCEPTED"
    assert completed.response.presented_event_id is not None
    assert replay == completed
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["completion_adapter"].requests) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1
