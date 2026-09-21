from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import ReconcileProgressivePresentationAttemptCommand
from test_f6a_progressive_presentation_core import _receipt_command
from test_f6a_progressive_presentation_reconciliation import (
    _reception_command,
    _setup_one_frame,
)


def test_terminal_settlement_rejects_new_late_reception_evidence(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))

    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-before-reception"
    adapter.presented_extent = 1
    adapter.received_extent = 0
    adapter.settled_through_ref = "settled-before-reception"
    service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    calls_before = len(adapter.reception_calls)
    with pytest.raises(DomainError) as exc:
        service.record_reception_receipt(_reception_command(session, attempt, now))

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED"
    assert len(adapter.reception_calls) == calls_before + 1


def test_durable_reception_remains_replayable_after_terminal_settlement(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    command = _reception_command(session, attempt, now)
    first = service.record_reception_receipt(command)

    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-after-reception"
    adapter.presented_extent = 1
    adapter.received_extent = 1
    adapter.settled_through_ref = "settled-after-reception"
    service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    calls_before = len(adapter.reception_calls)
    replay = service.record_reception_receipt(
        replace(command, operation_id=uuid4())
    )

    assert replay.reception_evidence_id == first.reception_evidence_id
    assert replay.received_through_frame == 1
    assert len(adapter.reception_calls) == calls_before
