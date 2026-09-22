from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import AppendCounterpartInputCommand, PresentCompanionOutputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    CommitProgressivePresentationHistoryCommand,
    DispatchProgressivePresentationFrameCommand,
    InterruptProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION,
    ReconcileProgressivePresentationAttemptCommand,
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
from test_f6a_progressive_presentation_reconciliation import _ReconciliationAdapter


class _InterruptAdapter(_ReconciliationAdapter):
    cancellation_contract_version = PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION

    def __init__(self, now):
        super().__init__(now)
        self.cancellation_calls: list[dict] = []
        self.cancellation_acknowledged = True
        self.raise_on_cancellation = False

    def request_presentation_cancellation(self, **kwargs):
        self.cancellation_calls.append(dict(kwargs))
        if self.raise_on_cancellation:
            raise RuntimeError("simulated cancellation transport uncertainty")
        return self.cancellation_acknowledged


def _setup(services, bootstrapper, engine, now, content_text):
    ctx = _adopt_output(services, bootstrapper, now, content_text)
    adapter = _InterruptAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)
    return ctx, adapter, service, session, attempt


def _append_interrupt(services, ctx, now, text="Stop there."):
    return services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ctx["ids"].companion_person_id,
            counterpart_id=ctx["ids"].counterpart_id,
            relationship_id=ctx["ids"].relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=text,
            occurred_at=now,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
            conversation_id="f6a-interruption-test",
        )
    )


def _interrupt(service, attempt, event_id):
    return service.interrupt_attempt(
        InterruptProgressivePresentationCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            interrupting_event_id=event_id,
        )
    )


def _settle_terminal(service, adapter, attempt, *, presented, received=0, suffix="1"):
    adapter.settlement_state = "TERMINAL"
    adapter.status_ref = f"terminal-interruption-{suffix}"
    adapter.presented_extent = presented
    adapter.received_extent = received
    adapter.settled_through_ref = f"settled-interruption-{suffix}"
    return service.reconcile_attempt(
        ReconcileProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )


def test_only_post_session_canonical_counterpart_input_can_interrupt(
    services, bootstrapper, engine, now
):
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, "A" * 300
    )

    with pytest.raises(DomainError) as exc:
        _interrupt(service, attempt, ctx["current"].event_id)
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_INTERRUPTION_EVENT_INVALID"
    assert adapter.cancellation_calls == []

    canonical = _append_interrupt(services, ctx, now)
    result = _interrupt(service, attempt, canonical.event_id)

    assert result.presentation_attempt_id == attempt.presentation_attempt_id
    assert result.presentation_session_id == session.presentation_session_id
    assert result.interrupting_event_id == canonical.event_id
    assert result.cancellation_request_state == "REQUESTED"
    assert len(adapter.cancellation_calls) == 1
    call = adapter.cancellation_calls[0]
    assert set(call) == {
        "presentation_key",
        "attempt_generation",
        "presentation_transport_fence_scope_id",
        "presentation_session_id",
        "presentation_attempt_id",
        "interruption_key",
        "interrupting_event_id",
    }
    assert call["presentation_attempt_id"] == attempt.presentation_attempt_id
    assert call["interrupting_event_id"] == canonical.event_id


def test_interruption_fences_new_frames_and_never_auto_resumes_remainder(
    services, bootstrapper, engine, now
):
    content = "A" * 256 + "B" * 44
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    frame1 = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame1, now))

    canonical = _append_interrupt(services, ctx, now)
    _interrupt(service, attempt, canonical.event_id)

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=2,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_INTERRUPTED"

    with pytest.raises(DomainError) as exc:
        _fence_attempt(service, session)
    assert (
        exc.value.code
        == "PROGRESSIVE_PRESENTATION_INTERRUPTED_REMAINDER_REQUIRES_NEW_OUTPUT"
    )


def test_cancellation_uncertainty_keeps_interrupt_fence_and_can_retry_content_free(
    services, bootstrapper, engine, now
):
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, "A" * 300
    )
    canonical = _append_interrupt(services, ctx, now)
    adapter.raise_on_cancellation = True

    first = _interrupt(service, attempt, canonical.event_id)
    assert first.cancellation_request_state == "UNKNOWN"

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=1,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_INTERRUPTED"

    adapter.raise_on_cancellation = False
    second = _interrupt(service, attempt, canonical.event_id)
    assert second.interruption_id == first.interruption_id
    assert second.cancellation_request_state == "REQUESTED"
    assert len(adapter.cancellation_calls) == 2
    assert all("content_text" not in call for call in adapter.cancellation_calls)


def test_interrupted_partial_history_commits_exact_presented_prefix_only(
    services, bootstrapper, engine, now
):
    content = "A" * 256 + "B" * 44
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    frame1 = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame1, now))

    with pytest.raises(DomainError) as exc:
        services.present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=uuid4(),
                companion_output_id=ctx["adopted"].companion_output_id,
                surface_binding_id=ctx["ids"].surface_binding_id,
                channel_binding_id=ctx["ids"].channel_binding_id,
                presented_at=now,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_HISTORY_COMMIT_REQUIRED"

    canonical = _append_interrupt(services, ctx, now)
    _interrupt(service, attempt, canonical.event_id)
    terminal = _settle_terminal(
        service, adapter, attempt, presented=1, received=0, suffix="partial"
    )

    command = CommitProgressivePresentationHistoryCommand(
        operation_id=uuid4(),
        presentation_attempt_id=attempt.presentation_attempt_id,
    )
    first = service.commit_presentation_history(command)
    replay = service.commit_presentation_history(
        CommitProgressivePresentationHistoryCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    assert first.interaction_event_id is not None
    assert first.last_presented_frame == 1
    assert replay.interaction_event_id == first.interaction_event_id
    assert replay.idempotent_replay is True

    with engine.connect() as conn:
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == first.interaction_event_id
            )
        ).mappings().one()
        lineage = conn.execute(
            select(schema.progressive_presentation_timeline_lineage).where(
                schema.progressive_presentation_timeline_lineage.c.interaction_event_id
                == first.interaction_event_id
            )
        ).mappings().one()
        count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id,
                schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT",
            )
        ).scalar_one()

    assert int(count) == 1
    assert event["content_text"] == frame1["content_text"]
    assert event["content_text"] == "A" * 256
    assert "B" not in event["content_text"]
    assert int(event["timeline_seq"]) > canonical.timeline_seq
    assert event["surface_binding_id"] == ctx["ids"].surface_binding_id
    assert event["channel_binding_id"] == ctx["ids"].channel_binding_id
    assert event["companion_output_id"] == ctx["adopted"].companion_output_id
    assert event["reply_to_event_id"] == ctx["current"].event_id
    assert lineage["terminal_presentation_attempt_id"] == attempt.presentation_attempt_id
    assert lineage["terminal_status_evidence_id"] == terminal.presentation_status_evidence_id
    assert lineage["interrupting_event_id"] == canonical.event_id
    assert int(lineage["first_presented_frame"]) == 1
    assert int(lineage["last_presented_frame"]) == 1

    compatibility = services.present_companion_output(
        PresentCompanionOutputCommand(
            operation_id=uuid4(),
            companion_output_id=ctx["adopted"].companion_output_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
            presented_at=now,
        )
    )
    assert compatibility.interaction_event_id == first.interaction_event_id
    assert compatibility.idempotent_replay is True


def test_interrupted_zero_extent_creates_no_companion_presented_timeline_event(
    services, bootstrapper, engine, now
):
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, "never presented"
    )
    canonical = _append_interrupt(services, ctx, now)
    _interrupt(service, attempt, canonical.event_id)
    _settle_terminal(service, adapter, attempt, presented=0, received=0, suffix="zero")

    result = service.commit_presentation_history(
        CommitProgressivePresentationHistoryCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )
    assert result.interaction_event_id is None
    assert result.timeline_seq is None
    assert result.last_presented_frame == 0
    assert result.presented_content_digest is None

    with engine.connect() as conn:
        count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id,
                schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT",
            )
        ).scalar_one()
    assert int(count) == 0


def test_full_terminal_history_is_backward_compatible_complete_output(
    services, bootstrapper, engine, now
):
    content = "complete progressive output"
    ctx, adapter, service, session, attempt = _setup(
        services, bootstrapper, engine, now, content
    )
    frame = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    _settle_terminal(service, adapter, attempt, presented=1, received=0, suffix="full")

    result = service.commit_presentation_history(
        CommitProgressivePresentationHistoryCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )

    with engine.connect() as conn:
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == result.interaction_event_id
            )
        ).mappings().one()
        lineage = conn.execute(
            select(schema.progressive_presentation_timeline_lineage).where(
                schema.progressive_presentation_timeline_lineage.c.interaction_event_id
                == result.interaction_event_id
            )
        ).mappings().one()

    assert event["event_kind"] == "COMPANION_PRESENTED_OUTPUT"
    assert event["actor_kind"] == "COMPANION"
    assert event["content_text"] == content
    assert event["companion_output_id"] == ctx["adopted"].companion_output_id
    assert event["reply_to_event_id"] == ctx["current"].event_id
    assert lineage["interrupting_event_id"] is None
    assert int(lineage["last_presented_frame"]) == 1

    with pytest.raises(DomainError) as exc:
        _fence_attempt(service, session)
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_HISTORY_ALREADY_COMMITTED"
