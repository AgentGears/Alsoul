from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    CommitProgressivePresentationHistoryCommand,
    DispatchProgressivePresentationFrameCommand,
)
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
    assert lineage["terminal_status_evidence_id"] == terminal.presentation_status_evidence_id
    assert lineage["interrupting_event_id"] == canonical.event_id


def test_input_admitted_after_terminal_observation_cannot_be_retroactive_interruption(
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
        suffix="already-terminal",
    )
    canonical = _append_interrupt(services, ctx, now)

    with engine.begin() as conn:
        conn.execute(
            update(schema.interaction_event)
            .where(schema.interaction_event.c.event_id == canonical.event_id)
            .values(recorded_at=now + timedelta(seconds=1))
        )

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
        status = conn.execute(
            select(schema.progressive_presentation_status_evidence).where(
                schema.progressive_presentation_status_evidence.c.presentation_status_evidence_id
                == terminal.presentation_status_evidence_id
            )
        ).mappings().one()
    assert int(interruption_count) == 0
    assert status["settlement_state"] == "TERMINAL"
