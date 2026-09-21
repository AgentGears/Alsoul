from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    ReconcileProgressivePresentationAttemptCommand,
)
from alsoul.services import ProgressivePresentationServices
from test_f6a_progressive_presentation_core import (
    _adopt_output,
    _fence_attempt,
    _frame,
    _open_session,
    _receipt_command,
)
from test_f6a_progressive_presentation_reconciliation import _ReconciliationAdapter


def test_exact_durable_receipt_remains_replayable_after_terminal_settlement(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "terminal replay")
    adapter = _ReconciliationAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)
    frame = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    receipt = _receipt_command(
        session,
        attempt,
        frame,
        now,
        presentation_receipt_ref="durable-before-terminal",
    )
    first = service.record_presentation_receipt(receipt)

    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-after-durable-receipt"
    adapter.presented_extent = 1
    adapter.received_extent = 0
    adapter.settled_through_ref = "settled-after-durable-receipt"
    service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    replay = service.record_presentation_receipt(
        replace(receipt, operation_id=uuid4())
    )

    assert replay.presentation_evidence_id == first.presentation_evidence_id
    assert replay.presented_through_frame == 1
    assert len(adapter.receipt_calls) == 1
