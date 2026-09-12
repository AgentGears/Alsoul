from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_presentation as presentation_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_presentation import (
    PersonalCalendarPresentationStatusResult,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarPresentationServices
from alsoul.storage import schema


def test_accepted_receipt_replay_repairs_missing_timeline_commit(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    adapter = presentation_cases._PresentationAdapter(
        now, dispatch_state="UNKNOWN", lookup_state="UNKNOWN"
    )
    adapter.sink_binding_ref = "presentation.test/replay-repair"
    service = presentation_cases._presentation_service(engine, now, ctx, adapter)
    operation_id = uuid4()
    command = presentation_cases._present_command(ctx, operation_id)

    with pytest.raises(DomainError) as uncertain:
        service.present_output(command)
    assert uncertain.value.code == "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN"

    with engine.connect() as conn:
        attempt = conn.execute(
            select(schema.personal_calendar_presentation_attempt)
        ).mappings().one()
        assert attempt["sink_acceptance_state"] == "UNKNOWN"
        assert conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one() == 0

    service._settle_attempt(
        attempt["presentation_attempt_id"],
        PersonalCalendarPresentationStatusResult(
            presentation_key=attempt["presentation_key"],
            presentation_attempt_generation=int(
                attempt["presentation_attempt_generation"]
            ),
            presentation_transport_fence_scope_id=attempt[
                "presentation_transport_fence_scope_id"
            ],
            state="ACCEPTED",
            receipt_ref="receipt-before-process-loss",
            accepted_at=now,
        ),
    )

    # Simulate process loss after durable ACCEPTED settlement and before the canonical
    # Timeline append. Replaying the exact presentation operation must repair history
    # without sending the personal payload again.
    replay = service.present_output(command)
    assert replay.state == "ACCEPTED"
    assert replay.interaction_event_id is not None
    assert len(adapter.payload_calls) == 1
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one() == 1


def test_unknown_attempt_cannot_reconcile_against_different_sink_binding(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    original = presentation_cases._PresentationAdapter(
        now, dispatch_state="UNKNOWN", lookup_state="UNKNOWN"
    )
    original.sink_binding_ref = "presentation.test/original-sink"
    service = presentation_cases._presentation_service(engine, now, ctx, original)

    with pytest.raises(DomainError) as uncertain:
        service.present_output(presentation_cases._present_command(ctx))
    assert uncertain.value.code == "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN"
    assert len(original.payload_calls) == 1

    replacement = presentation_cases._PresentationAdapter(
        now, dispatch_state="ACCEPTED", lookup_state="NOT_ACCEPTED"
    )
    replacement.sink_binding_ref = "presentation.test/replacement-sink"
    recovered = PersonalCalendarPresentationServices(
        engine,
        adapter=replacement,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(DomainError) as mismatch:
        recovered.recover_presentation(presentation_cases._recover_command(ctx))
    assert mismatch.value.code == "CALENDAR_PRESENTATION_SINK_MISMATCH"
    assert replacement.status_calls == []

    with engine.connect() as conn:
        attempt = conn.execute(
            select(schema.personal_calendar_presentation_attempt)
        ).mappings().one()
        assert attempt["sink_binding_ref"] == "presentation.test/original-sink"
        assert attempt["sink_acceptance_state"] == "UNKNOWN"
        assert conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one() == 0
