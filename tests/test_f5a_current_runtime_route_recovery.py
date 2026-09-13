from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from alsoul.domain.personal_calendar_cognition import (
    SetPersonalCalendarModelRouteStatusCommand,
)
from alsoul.storage import schema

import test_f5a_current_runtime_calendar as runtime_cases


def test_completed_calendar_cognition_recovers_after_model_route_revocation(engine, now):
    ids, source, runtime, read_adapter, plan_adapter, sink = runtime_cases._configured_runtime(
        engine, now
    )
    first = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )
    with engine.connect() as conn:
        route_id = conn.execute(
            select(schema.personal_calendar_model_invocation.c.route_binding_id).where(
                schema.personal_calendar_model_invocation.c.model_invocation_id
                == first.response.model_invocation_id
            )
        ).scalar_one()
    runtime.personal_calendar_coordinator.cognition.set_model_route_status(
        SetPersonalCalendarModelRouteStatusCommand(
            operation_id=uuid4(),
            route_binding_id=route_id,
            status="REVOKED",
        )
    )

    replay = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        after_process_loss=True,
    )

    assert replay.response == first.response
    assert len(read_adapter.requests) == 1
    assert len(plan_adapter.requests) == 1
    assert len(sink.payload_calls) == 1
