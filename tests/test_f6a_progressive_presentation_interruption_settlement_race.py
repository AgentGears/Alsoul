from __future__ import annotations

from threading import Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    CommitProgressivePresentationHistoryCommand,
    DispatchProgressivePresentationFrameCommand,
)
from alsoul.services import ProgressivePresentationServices
from alsoul.storage import schema
from test_f6a_progressive_presentation_core import _frame, _receipt_command
from test_f6a_progressive_presentation_interruption_history import (
    _append_interrupt,
    _interrupt,
    _setup,
    _settle_terminal,
)


def _present_first_frame(service, engine, session, attempt, now):
    frame = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    service.record_presentation_receipt(
        _receipt_command(session, attempt, frame, now)
    )
    return frame


def test_input_admitted_before_terminal_observation_survives_settlement_race(
    services, bootstrapper, engine, now
):
    content = "A" * 256 + "B" * 44
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    _present_first_frame(service, engine, session, attempt, now)

    canonical = _append_interrupt(services, ctx, now)
    terminal = _settle_terminal(
        service,
        adapter,
        attempt,
        presented=1,
        received=0,
        suffix="race-before-terminal-observation",
    )

    result = _interrupt(service, attempt, canonical.event_id)

    assert result.cancellation_request_state == "NOT_REQUIRED_TERMINAL"
    assert adapter.cancellation_calls == []

    history = service.commit_presentation_history(
        CommitProgressivePresentationHistoryCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )
    assert history.last_presented_frame == 1
    assert history.interaction_event_id is not None

    with engine.connect() as conn:
        lineage = conn.execute(
            select(schema.progressive_presentation_timeline_lineage).where(
                schema.progressive_presentation_timeline_lineage.c.interaction_event_id
                == history.interaction_event_id
            )
        ).mappings().one()
        frontier = conn.execute(
            select(schema.progressive_presentation_terminal_timeline_frontier).where(
                schema.progressive_presentation_terminal_timeline_frontier.c.presentation_status_evidence_id
                == terminal.presentation_status_evidence_id
            )
        ).mappings().one()
    assert lineage["terminal_status_evidence_id"] == terminal.presentation_status_evidence_id
    assert lineage["interrupting_event_id"] == canonical.event_id
    assert canonical.timeline_seq <= int(frontier["observed_timeline_frontier"])


def test_input_admitted_after_terminal_observation_is_rejected_even_when_timestamps_tie(
    services, bootstrapper, engine, now
):
    content = "A" * 256 + "B" * 44
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    _present_first_frame(service, engine, session, attempt, now)
    terminal = _settle_terminal(
        service,
        adapter,
        attempt,
        presented=1,
        received=0,
        suffix="already-terminal-same-clock-tick",
    )
    canonical = _append_interrupt(services, ctx, now)

    with engine.connect() as conn:
        status = conn.execute(
            select(schema.progressive_presentation_status_evidence).where(
                schema.progressive_presentation_status_evidence.c.presentation_status_evidence_id
                == terminal.presentation_status_evidence_id
            )
        ).mappings().one()
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == canonical.event_id
            )
        ).mappings().one()
        frontier = conn.execute(
            select(schema.progressive_presentation_terminal_timeline_frontier).where(
                schema.progressive_presentation_terminal_timeline_frontier.c.presentation_status_evidence_id
                == terminal.presentation_status_evidence_id
            )
        ).mappings().one()

    # FixedClock intentionally gives both durable writes the same wall-clock value.
    # Ordering must therefore come from the serialized Timeline frontier, not timestamps.
    assert event["recorded_at"] == status["observed_at"]
    assert canonical.timeline_seq > int(frontier["observed_timeline_frontier"])

    with pytest.raises(DomainError) as exc:
        _interrupt(service, attempt, canonical.event_id)
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE"

    with engine.connect() as conn:
        interruption_count = conn.execute(
            select(func.count())
            .select_from(schema.progressive_presentation_interruption)
            .where(
                schema.progressive_presentation_interruption.c.presentation_attempt_id
                == attempt.presentation_attempt_id
            )
        ).scalar_one()
    assert int(interruption_count) == 0
    assert status["settlement_state"] == "TERMINAL"


def test_interrupt_rechecks_terminal_state_under_shared_attempt_fence(
    services, bootstrapper, engine, now, monkeypatch
):
    content = "A" * 256 + "B" * 44
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    _present_first_frame(service, engine, session, attempt, now)
    canonical = _append_interrupt(services, ctx, now)

    about_to_lock = Event()
    release_lock = Event()
    worker_done = Event()
    result_box: dict[str, object] = {}
    errors: list[BaseException] = []
    original_locked_attempt = service._locked_attempt
    first_call = {"pending": True}

    def delayed_locked_attempt(conn, attempt_id):
        if first_call["pending"]:
            first_call["pending"] = False
            about_to_lock.set()
            if not release_lock.wait(timeout=5):
                raise AssertionError("timed out waiting to release attempt fence")
        return original_locked_attempt(conn, attempt_id)

    monkeypatch.setattr(service, "_locked_attempt", delayed_locked_attempt)

    def interrupt_worker():
        try:
            result_box["result"] = _interrupt(
                service, attempt, canonical.event_id
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            worker_done.set()

    worker = Thread(target=interrupt_worker)
    worker.start()
    assert about_to_lock.wait(timeout=5)

    settler = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    terminal = _settle_terminal(
        settler,
        adapter,
        attempt,
        presented=1,
        received=0,
        suffix="interleaved-terminal",
    )

    release_lock.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert worker_done.is_set()
    assert errors == []

    result = result_box["result"]
    assert result.cancellation_request_state == "NOT_REQUIRED_TERMINAL"
    assert adapter.cancellation_calls == []

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.progressive_presentation_interruption).where(
                schema.progressive_presentation_interruption.c.interruption_id
                == result.interruption_id
            )
        ).mappings().one()
    assert row["interrupting_event_id"] == canonical.event_id
    assert terminal.state == "TERMINAL"
