from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from alsoul.domain.commands import (
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    ResolveOutputTargetCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    FenceProgressivePresentationAttemptCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    ProgressivePresentationFrameTransportResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services import F4ConversationalOutputAdoption, ProgressivePresentationServices
from alsoul.services.common import canonical_json, sha256_text
from alsoul.storage import schema


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _adopt_output(services, bootstrapper, now, content_text: str):
    ids = bootstrapper.bootstrap(
        identity_namespace="f6a-progressive-presentation-test",
        external_subject=str(uuid4()),
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text="Give me one bounded conversational response.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="f6a-progressive-presentation-test",
        )
    )
    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            required_personal_predicates=(),
            required_world_result_ids=(),
        )
    )
    provider_context = services.render_provider_context(projection.projection_id)
    invocation = services.start_model_invocation(
        StartModelInvocationCommand(
            operation_id=uuid4(),
            context_projection_id=projection.projection_id,
            provider_binding_ref="f6a-test-provider",
            model_ref="f6a-test-model-v1",
            renderer_version="f6a-test-renderer-v1",
            provider_request_digest=sha256_text(canonical_json(provider_context)),
        )
    )
    draft = FoundationResponseDraft(
        segments=(
            FoundationResponseSegment(
                epistemic_kind="COMPANION_EXPRESSION",
                text=content_text,
                source_ref=None,
            ),
        )
    )
    generated = services.complete_model_invocation(
        CompleteModelInvocationCommand(
            operation_id=uuid4(),
            model_invocation_id=invocation.model_invocation_id,
            content_text=draft.render_text(),
            content_digest=sha256_text(draft.render_text()),
            semantic_payload=draft.to_payload(),
            received_at=now,
        )
    )
    target = services.resolve_output_target(
        ResolveOutputTargetCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            target_kind="INTERACTION_EVENT",
            target_ref=current.event_id,
            purpose="FINAL_RESPONSE",
        )
    )
    adopted = F4ConversationalOutputAdoption(services).adopt(
        AdoptCompanionOutputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            output_target_id=target.output_target_id,
            origin_kind="RESPONSE_TO_EVENT",
            origin_ref=current.event_id,
            generated_output_id=generated.generated_output_id,
        )
    )
    return {
        "ids": ids,
        "current": current,
        "projection": projection,
        "generated": generated,
        "adopted": adopted,
        "content_text": content_text,
    }


class _AcceptingAdapter:
    presentation_contract_version = PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    frame_contract_version = PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    transport_contract_version = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION

    def __init__(self, now):
        self.now = now
        self.calls: list[dict] = []

    def dispatch_frame(self, **kwargs):
        self.calls.append(dict(kwargs))
        return ProgressivePresentationFrameTransportResult(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            frame_ordinal=kwargs["frame_ordinal"],
            frame_digest=kwargs["frame_digest"],
            acceptance_state="ACCEPTED",
            acceptance_ref=f"accepted-{kwargs['frame_ordinal']}",
            accepted_at=self.now,
        )


class _BadDigestAdapter(_AcceptingAdapter):
    def dispatch_frame(self, **kwargs):
        self.calls.append(dict(kwargs))
        return ProgressivePresentationFrameTransportResult(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            frame_ordinal=kwargs["frame_ordinal"],
            frame_digest="0" * 64,
            acceptance_state="ACCEPTED",
            acceptance_ref="invalid-digest-acceptance",
            accepted_at=self.now,
        )


def _open_session(service, ctx):
    return service.open_session(
        OpenProgressivePresentationCommand(
            operation_id=uuid4(),
            companion_output_id=ctx["adopted"].companion_output_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )


def _fence_attempt(service, session):
    return service.fence_attempt(
        FenceProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_session_id=session.presentation_session_id,
        )
    )


def _frame(engine, session_id, frame_ordinal):
    with engine.connect() as conn:
        return conn.execute(
            select(schema.progressive_presentation_frame).where(
                schema.progressive_presentation_frame.c.presentation_session_id
                == session_id,
                schema.progressive_presentation_frame.c.frame_ordinal == frame_ordinal,
            )
        ).mappings().one()


def _receipt_command(session, attempt, frame, now, **overrides):
    values = {
        "operation_id": uuid4(),
        "presentation_session_id": session.presentation_session_id,
        "presentation_attempt_id": attempt.presentation_attempt_id,
        "presentation_key": session.presentation_key,
        "attempt_generation": attempt.attempt_generation,
        "presentation_transport_fence_scope_id": attempt.presentation_transport_fence_scope_id,
        "frame_ordinal": int(frame["frame_ordinal"]),
        "frame_digest": frame["content_digest"],
        "presentation_receipt_ref": f"presented-{frame['frame_ordinal']}",
        "presented_at": now,
        "presentation_receipt_contract_version": PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    }
    values.update(overrides)
    return RecordProgressivePresentationReceiptCommand(**values)


def test_session_identity_and_frames_are_durable_deterministic(
    services, bootstrapper, engine, now
):
    content = "0123456789" * 60
    ctx = _adopt_output(services, bootstrapper, now, content)
    service = ProgressivePresentationServices(engine, clock=services.clock, ids=services.ids)

    first = _open_session(service, ctx)
    replay = _open_session(service, ctx)

    assert replay.presentation_session_id == first.presentation_session_id
    assert replay.presentation_key == first.presentation_key
    assert first.presentation_session_id != ctx["adopted"].companion_output_id
    assert first.presentation_key != str(first.presentation_session_id)
    assert first.presentation_contract_version == PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    assert first.frame_contract_version == PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    assert first.frame_count == 3

    with engine.connect() as conn:
        session_row = conn.execute(
            select(schema.progressive_presentation_session).where(
                schema.progressive_presentation_session.c.presentation_session_id
                == first.presentation_session_id
            )
        ).mappings().one()
        frames = conn.execute(
            select(schema.progressive_presentation_frame)
            .where(
                schema.progressive_presentation_frame.c.presentation_session_id
                == first.presentation_session_id
            )
            .order_by(schema.progressive_presentation_frame.c.frame_ordinal)
        ).mappings().all()

    assert session_row["companion_output_id"] == ctx["adopted"].companion_output_id
    assert session_row["relationship_id"] == ctx["ids"].relationship_id
    assert session_row["surface_binding_id"] == ctx["ids"].surface_binding_id
    assert session_row["channel_binding_id"] == ctx["ids"].channel_binding_id
    assert session_row["source_content_digest"] == sha256_text(content)
    assert [int(row["frame_ordinal"]) for row in frames] == [1, 2, 3]
    assert [(int(row["source_start"]), int(row["source_end"])) for row in frames] == [
        (0, PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT),
        (
            PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT,
            PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT * 2,
        ),
        (PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT * 2, len(content)),
    ]
    assert "".join(row["content_text"] for row in frames) == content
    assert all(
        row["content_digest"] == sha256_text(row["content_text"]) for row in frames
    )

    attempt = _fence_attempt(service, first)
    assert attempt.presentation_session_id == first.presentation_session_id
    assert attempt.presentation_attempt_id != first.presentation_session_id
    assert attempt.presentation_transport_fence_scope_id not in {
        first.presentation_session_id,
        attempt.presentation_attempt_id,
    }
    assert attempt.attempt_generation == 1
    assert attempt.state == "OPEN"


def test_frame_transport_requires_fence_and_prior_authoritative_presentation(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "x" * 600)
    adapter = _AcceptingAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=uuid4(),
                frame_ordinal=1,
            )
        )
    _assert_code(exc, "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_FOUND")
    assert adapter.calls == []

    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)
    frame1 = _frame(engine, session.presentation_session_id, 1)

    dispatched1 = service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    assert dispatched1.acceptance_state == "ACCEPTED"
    assert len(adapter.calls) == 1

    with engine.connect() as conn:
        evidence_count = conn.execute(
            select(func.count()).select_from(schema.progressive_presentation_frame_evidence)
        ).scalar_one()
        presented_event_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one()
    assert evidence_count == 0
    assert presented_event_count == 0

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=2,
            )
        )
    _assert_code(exc, "PROGRESSIVE_PRESENTATION_FRAME_ORDER_INVALID")
    assert len(adapter.calls) == 1

    service.record_presentation_receipt(
        _receipt_command(session, attempt, frame1, now)
    )
    dispatched2 = service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=2,
        )
    )
    assert dispatched2.acceptance_state == "ACCEPTED"
    assert len(adapter.calls) == 2


def test_later_frame_receipt_cannot_fill_an_unproved_gap(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "y" * 600)
    adapter = _AcceptingAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)
    frame1 = _frame(engine, session.presentation_session_id, 1)
    frame2 = _frame(engine, session.presentation_session_id, 2)

    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    with engine.begin() as conn:
        conn.execute(
            insert(schema.progressive_presentation_frame_transport).values(
                presentation_attempt_id=attempt.presentation_attempt_id,
                presentation_session_id=session.presentation_session_id,
                frame_ordinal=2,
                frame_digest=frame2["content_digest"],
                sink_acceptance_state="ACCEPTED",
                acceptance_ref="accepted-frame-2-before-evidence-gap-check",
                dispatched_at=now,
                accepted_at=now,
            )
        )

    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(
            _receipt_command(session, attempt, frame2, now)
        )
    _assert_code(exc, "PROGRESSIVE_PRESENTATION_RECEIPT_GAP")

    first = service.record_presentation_receipt(
        _receipt_command(session, attempt, frame1, now)
    )
    second = service.record_presentation_receipt(
        _receipt_command(session, attempt, frame2, now)
    )
    assert first.presented_through_frame == 1
    assert second.presented_through_frame == 2


def test_presentation_receipts_are_exact_idempotent_and_fail_closed(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "z" * 300)
    adapter = _AcceptingAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)
    frame1 = _frame(engine, session.presentation_session_id, 1)
    service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )

    first = service.record_presentation_receipt(
        _receipt_command(
            session,
            attempt,
            frame1,
            now,
            presentation_receipt_ref="receipt-exact-1",
        )
    )
    duplicate = service.record_presentation_receipt(
        _receipt_command(
            session,
            attempt,
            frame1,
            now,
            presentation_receipt_ref="receipt-exact-1",
        )
    )
    assert duplicate.presentation_evidence_id == first.presentation_evidence_id

    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(
            _receipt_command(
                session,
                attempt,
                frame1,
                now,
                presentation_receipt_ref="receipt-conflicts-with-existing-evidence",
            )
        )
    _assert_code(exc, "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT")

    invalid_cases = (
        {"presentation_key": f"{session.presentation_key}-wrong"},
        {"attempt_generation": attempt.attempt_generation + 1},
        {"presentation_transport_fence_scope_id": uuid4()},
        {"frame_digest": "f" * 64},
    )
    for overrides in invalid_cases:
        with pytest.raises(DomainError) as exc:
            service.record_presentation_receipt(
                _receipt_command(session, attempt, frame1, now, **overrides)
            )
        _assert_code(exc, "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID")


def test_invalid_transport_status_preserves_unknown_without_presentation_truth(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "transport-status-test")
    adapter = _BadDigestAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    attempt = _fence_attempt(service, session)

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=1,
            )
        )
    _assert_code(exc, "PROGRESSIVE_PRESENTATION_TRANSPORT_STATUS_INVALID")

    with engine.connect() as conn:
        transport = conn.execute(
            select(schema.progressive_presentation_frame_transport).where(
                schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                == attempt.presentation_attempt_id,
                schema.progressive_presentation_frame_transport.c.frame_ordinal == 1,
            )
        ).mappings().one()
        evidence_count = conn.execute(
            select(func.count()).select_from(schema.progressive_presentation_frame_evidence)
        ).scalar_one()
        presented_event_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one()

    assert transport["sink_acceptance_state"] == "UNKNOWN"
    assert transport["acceptance_ref"] is None
    assert evidence_count == 0
    assert presented_event_count == 0
