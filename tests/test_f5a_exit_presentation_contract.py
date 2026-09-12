from __future__ import annotations

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_presentation as presentation_cases
from alsoul.adapters import JsonPersonalCalendarPresentationAdapter
from alsoul.domain.errors import DomainError
from alsoul.storage import schema


class _DelayedAcceptanceSink(presentation_cases._PresentationAdapter):
    sink_binding_ref = "presentation.test/delayed-acceptance"
    terminal_negative_semantics = "POINT_IN_TIME_NEGATIVE_V1"


def test_exit_sink_without_terminal_generation_guarantee_is_ineligible_before_payload(
    engine, now
):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    sink = _DelayedAcceptanceSink(now)
    service = presentation_cases._presentation_service(engine, now, ctx, sink)

    with pytest.raises(DomainError) as ineligible:
        service.present_output(presentation_cases._present_command(ctx))
    assert ineligible.value.code == "CALENDAR_PRESENTATION_ADAPTER_INELIGIBLE"
    assert sink.payload_calls == []
    assert sink.status_calls == []
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_presentation_attempt)
        ).scalar_one() == 0


def test_exit_qualified_sink_terminal_semantics_are_immutable_and_identity_bound():
    sink = JsonPersonalCalendarPresentationAdapter(
        endpoint="https://presentation.test/send",
        status_endpoint="https://presentation.test/status",
    )
    original_ref = sink.sink_binding_ref
    with pytest.raises((AttributeError, TypeError)):
        sink.terminal_negative_semantics = "POINT_IN_TIME_NEGATIVE_V1"
    assert sink.sink_binding_ref == original_ref

    with pytest.raises(ValueError):
        JsonPersonalCalendarPresentationAdapter(
            endpoint="https://presentation.test/send",
            status_endpoint="https://presentation.test/status",
            terminal_negative_semantics="POINT_IN_TIME_NEGATIVE_V1",
        )
