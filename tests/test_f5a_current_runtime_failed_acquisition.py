from __future__ import annotations

import pytest
from sqlalchemy import func, select

from alsoul.adapters.contracts import AdapterRejected
from alsoul.domain.errors import DomainError
from alsoul.storage import schema

import test_f5a_current_runtime_calendar as runtime_cases


def test_failed_acquisition_retries_with_fresh_bounded_observation(engine, now):
    ids, source, runtime, read_adapter, plan_adapter, sink = runtime_cases._configured_runtime(
        engine, now
    )
    successful_read = read_adapter.read_page

    def reject_once(request):
        read_adapter.requests.append(request)
        raise AdapterRejected("definite provider rejection")

    read_adapter.read_page = reject_once
    with pytest.raises(DomainError) as excinfo:
        runtime.interact(
            relationship_id=ids.relationship_id,
            current_input_event_id=source.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    assert excinfo.value.code == "CALENDAR_PROVIDER_REJECTED"

    read_adapter.read_page = successful_read
    completed = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        after_process_loss=True,
    )

    with engine.connect() as conn:
        scoped = conn.execute(
            select(func.count())
            .select_from(schema.personal_calendar_observation_scope)
            .where(
                schema.personal_calendar_observation_scope.c.source_interaction_event_id
                == source.event_id
            )
        ).scalar_one()
    assert scoped >= 2
    assert completed.response.presentation_state == "ACCEPTED"
    assert len(read_adapter.requests) == 2
    assert len(plan_adapter.requests) == 1
    assert len(sink.payload_calls) == 1
