from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEPTION_KIND,
    PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    ProgressivePresentationFrameTransportResult,
    ProgressivePresentationReconciliationStatus,
    ReconcileProgressivePresentationAttemptCommand,
    RecordProgressivePresentationReceptionCommand,
)
from alsoul.services import ProgressivePresentationServices
from alsoul.storage import schema
from test_f6a_progressive_presentation_core import (
    _adopt_output,
    _fence_attempt,
    _frame,
    _open_session,
    _receipt_command,
)


class _ReconciliationAdapter:
    presentation_contract_version = PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    frame_contract_version = PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    transport_contract_version = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION
    receipt_contract_version = PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
    reception_contract_version = PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION
    status_contract_version = PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION

    def __init__(self, now, *, acceptance_state="ACCEPTED"):
        self.now = now
        self.acceptance_state = acceptance_state
        self.receipt_calls: list[dict] = []
        self.reception_calls: list[dict] = []
        self.status_calls: list[dict] = []
        self.reception_valid = True
        self.settlement_state = "UNKNOWN_PRESENTATION_EXTENT"
        self.status_ref = "status-1"
        self.presented_extent = 0
        self.received_extent = 0
        self.settled_through_ref: str | None = None

    def dispatch_frame(self, **kwargs):
        return ProgressivePresentationFrameTransportResult(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            frame_ordinal=kwargs["frame_ordinal"],
            frame_digest=kwargs["frame_digest"],
            acceptance_state=self.acceptance_state,
            acceptance_ref="transport-1",
            accepted_at=self.now if self.acceptance_state == "ACCEPTED" else None,
        )

    def validate_presentation_receipt(self, **kwargs):
        self.receipt_calls.append(dict(kwargs))
        return True

    def validate_reception_receipt(self, **kwargs):
        self.reception_calls.append(dict(kwargs))
        return self.reception_valid

    def reconcile_presentation_status(self, **kwargs):
        self.status_calls.append(dict(kwargs))
        terminal = self.settlement_state == "TERMINAL"
        return ProgressivePresentationReconciliationStatus(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            presentation_attempt_id=kwargs["presentation_attempt_id"],
            presentation_session_id=kwargs["presentation_session_id"],
            settlement_state=self.settlement_state,
            status_ref=self.status_ref,
            last_authoritatively_presented_frame=self.presented_extent,
            last_authoritatively_received_frame=self.received_extent,
            settled_through_ref=self.settled_through_ref if terminal else None,
            settled_at=self.now if terminal else None,
        )


def _setup_one_frame(services, bootstrapper, engine, now):
    ctx = _adopt_output(services, bootstrapper, now, "one bounded presentation frame")
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
    return service, adapter, session, attempt, frame


def _reception_command(session, attempt, now, **overrides):
    values = {
        "operation_id": uuid4(),
        "presentation_session_id": session.presentation_session_id,
        "presentation_attempt_id": attempt.presentation_attempt_id,
        "presentation_key": session.presentation_key,
        "attempt_generation": attempt.attempt_generation,
        "presentation_transport_fence_scope_id": attempt.presentation_transport_fence_scope_id,
        "received_through_frame": 1,
        "reception_receipt_ref": "reception-1",
        "received_at": now,
        "reception_kind": PROGRESSIVE_PRESENTATION_RECEPTION_KIND,
        "reception_contract_version": PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION,
    }
    values.update(overrides)
    return RecordProgressivePresentationReceptionCommand(**values)


def test_reception_requires_authoritative_presented_extent_and_is_idempotent(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    command = _reception_command(session, attempt, now)

    with pytest.raises(DomainError) as exc:
        service.record_reception_receipt(command)
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_RECEPTION_EXCEEDS_PRESENTED_EXTENT"
    assert adapter.reception_calls == []

    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    first = service.record_reception_receipt(command)
    replay = service.record_reception_receipt(
        replace(command, operation_id=uuid4())
    )

    assert first.reception_evidence_id == replay.reception_evidence_id
    assert first.received_through_frame == 1
    assert len(adapter.reception_calls) == 1

    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_presentation_reception_evidence
            )
        ).scalar_one()
    assert int(count) == 1


def test_untrusted_reception_receipt_fails_closed(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    adapter.reception_valid = False

    with pytest.raises(DomainError) as exc:
        service.record_reception_receipt(_reception_command(session, attempt, now))

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_RECEPTION_UNTRUSTED"
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_presentation_reception_evidence
            )
        ).scalar_one()
    assert int(count) == 0


def test_terminal_reconciliation_is_content_free_and_settles_exact_known_extent(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    service.record_reception_receipt(_reception_command(session, attempt, now))

    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-status-1"
    adapter.presented_extent = 1
    adapter.received_extent = 1
    adapter.settled_through_ref = "settled-through-1"
    command = ReconcileProgressivePresentationAttemptCommand(
        operation_id=uuid4(),
        presentation_attempt_id=attempt.presentation_attempt_id,
    )

    first = service.reconcile_attempt(command)
    replay = service.reconcile_attempt(command)

    assert first.presentation_status_evidence_id == replay.presentation_status_evidence_id
    assert first.state == "TERMINAL"
    assert first.last_authoritatively_presented_frame == 1
    assert first.last_authoritatively_received_frame == 1
    assert len(adapter.status_calls) == 1
    assert set(adapter.status_calls[0]) == {
        "presentation_key",
        "attempt_generation",
        "presentation_transport_fence_scope_id",
        "presentation_session_id",
        "presentation_attempt_id",
    }

    with engine.connect() as conn:
        attempt_row = conn.execute(
            select(schema.progressive_presentation_attempt).where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt.presentation_attempt_id
            )
        ).mappings().one()
        status_row = conn.execute(
            select(schema.progressive_presentation_status_evidence).where(
                schema.progressive_presentation_status_evidence.c.presentation_status_evidence_id
                == first.presentation_status_evidence_id
            )
        ).mappings().one()
    assert attempt_row["attempt_state"] == "SETTLED"
    assert status_row["settled_through_ref"] == "settled-through-1"


def test_unknown_reconciliation_blocks_retry_until_later_terminal_proof(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, _frame_row = _setup_one_frame(
        services, bootstrapper, engine, now
    )

    unknown = service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )
    assert unknown.state == "UNKNOWN_PRESENTATION_EXTENT"

    with pytest.raises(DomainError) as exc:
        _fence_attempt(service, session)
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLEMENT_REQUIRED"

    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-after-unknown"
    adapter.settled_through_ref = "settled-after-unknown"
    terminal = service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )
    assert terminal.state == "TERMINAL"

    next_attempt = _fence_attempt(service, session)
    assert next_attempt.attempt_generation == 2
    assert next_attempt.presentation_attempt_id != attempt.presentation_attempt_id


def test_status_lookup_cannot_manufacture_missing_presented_evidence(
    services, bootstrapper, engine, now
):
    service, adapter, _session, attempt, _frame_row = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "fabricated-presented-prefix"
    adapter.presented_extent = 1
    adapter.received_extent = 0
    adapter.settled_through_ref = "fabricated-proof"

    with pytest.raises(DomainError) as exc:
        service.reconcile_attempt(
            ReconcileProgressivePresentationAttemptCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_STATUS_EVIDENCE_INCOMPLETE"

    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_presentation_status_evidence
            )
        ).scalar_one()
        attempt_state = conn.execute(
            select(schema.progressive_presentation_attempt.c.attempt_state).where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt.presentation_attempt_id
            )
        ).scalar_one()
    assert int(count) == 0
    assert attempt_state == "OPEN"


def test_terminal_settlement_rejects_new_late_presentation_receipt(
    services, bootstrapper, engine, now
):
    service, adapter, _session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = "terminal-no-presentation"
    adapter.settled_through_ref = "settled-no-presentation"

    service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    session_row = None
    with engine.connect() as conn:
        session_row = conn.execute(
            select(schema.progressive_presentation_session).where(
                schema.progressive_presentation_session.c.presentation_session_id
                == attempt.presentation_session_id
            )
        ).mappings().one()

    from alsoul.domain.progressive_presentation import RecordProgressivePresentationReceiptCommand

    late = RecordProgressivePresentationReceiptCommand(
        operation_id=uuid4(),
        presentation_session_id=attempt.presentation_session_id,
        presentation_attempt_id=attempt.presentation_attempt_id,
        presentation_key=session_row["presentation_key"],
        attempt_generation=attempt.attempt_generation,
        presentation_transport_fence_scope_id=attempt.presentation_transport_fence_scope_id,
        frame_ordinal=1,
        frame_digest=frame["content_digest"],
        presentation_receipt_ref="late-after-terminal",
        presented_at=now,
    )
    calls_before = len(adapter.receipt_calls)
    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(late)

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED"
    assert len(adapter.receipt_calls) == calls_before
