from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    ProgressivePresentationFrameTransportResult,
)
from alsoul.services import ProgressivePresentationServices
from alsoul.services.progressive_presentation_v2 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV2,
)
from alsoul.storage import schema
from test_f6a_progressive_presentation_core import (
    _adopt_output,
    _fence_attempt,
    _frame,
    _open_session,
    _receipt_command,
)


class _TrustedAdapter:
    presentation_contract_version = PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    frame_contract_version = PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    transport_contract_version = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION
    receipt_contract_version = PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION

    def __init__(self, now):
        self.now = now

    def dispatch_frame(self, **kwargs):
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

    def validate_presentation_receipt(self, **_kwargs):
        return True


class _RejectingAdapter(_TrustedAdapter):
    def dispatch_frame(self, **kwargs):
        return ProgressivePresentationFrameTransportResult(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            frame_ordinal=kwargs["frame_ordinal"],
            frame_digest=kwargs["frame_digest"],
            acceptance_state="NOT_ACCEPTED",
        )


def test_progressive_session_rejects_noncanonical_same_companion_route(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "canonical route only")
    alternate_surface_id = uuid4()
    alternate_channel_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(schema.surface_binding).values(
                surface_binding_id=alternate_surface_id,
                companion_person_id=ctx["ids"].companion_person_id,
                surface_namespace="alsoul.first_party",
                surface_ref=f"alternate-surface-{uuid4()}",
                bound_at=now,
            )
        )
        conn.execute(
            insert(schema.channel_binding).values(
                channel_binding_id=alternate_channel_id,
                companion_person_id=ctx["ids"].companion_person_id,
                channel_namespace="alsoul.first_party",
                companion_endpoint_ref=f"alternate-channel-{uuid4()}",
                bound_at=now,
            )
        )

    service = ProgressivePresentationServices(
        engine,
        clock=services.clock,
        ids=services.ids,
    )
    output_id = ctx["adopted"].companion_output_id

    with pytest.raises(DomainError) as exc:
        service.open_session(
            OpenProgressivePresentationCommand(
                operation_id=uuid4(),
                companion_output_id=output_id,
                surface_binding_id=alternate_surface_id,
                channel_binding_id=alternate_channel_id,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ROUTE_INVALID"

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.progressive_presentation_session).where(
                schema.progressive_presentation_session.c.companion_output_id == output_id
            )
        ).mappings().one_or_none()
    assert row is None


def test_terminal_nonacceptance_settles_prior_attempt_and_allows_new_generation(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(services, bootstrapper, now, "safe retry after rejection")
    service = ProgressivePresentationServices(
        engine,
        adapter=_RejectingAdapter(now),
        clock=services.clock,
        ids=services.ids,
    )
    session = _open_session(service, ctx)
    first_attempt = _fence_attempt(service, session)

    rejected = service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=first_attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    assert rejected.acceptance_state == "NOT_ACCEPTED"

    second_attempt = _fence_attempt(service, session)
    assert second_attempt.attempt_generation == 2
    assert second_attempt.presentation_attempt_id != first_attempt.presentation_attempt_id
    assert (
        second_attempt.presentation_transport_fence_scope_id
        != first_attempt.presentation_transport_fence_scope_id
    )

    with engine.connect() as conn:
        first_state = conn.execute(
            select(schema.progressive_presentation_attempt.c.attempt_state).where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == first_attempt.presentation_attempt_id
            )
        ).scalar_one()
    assert first_state == "SETTLED"

    service.adapter = _TrustedAdapter(now)
    retried = service.dispatch_frame(
        DispatchProgressivePresentationFrameCommand(
            operation_id=uuid4(),
            presentation_attempt_id=second_attempt.presentation_attempt_id,
            frame_ordinal=1,
        )
    )
    assert retried.acceptance_state == "ACCEPTED"


def test_concurrent_exact_receipt_conflict_recovers_idempotently(
    services, bootstrapper, engine, now, monkeypatch
):
    ctx = _adopt_output(services, bootstrapper, now, "receipt race")
    service = ProgressivePresentationServices(
        engine,
        adapter=_TrustedAdapter(now),
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
    command = _receipt_command(
        session,
        attempt,
        frame,
        now,
        presentation_receipt_ref="same-sink-receipt",
    )

    original = ProgressivePresentationServicesV2.record_presentation_receipt
    calls = 0

    def concurrent_winner_then_delegate(self, losing_command):
        nonlocal calls
        calls += 1
        if calls == 1:
            original(self, replace(losing_command, operation_id=uuid4()))
            raise IntegrityError(
                "simulated concurrent unique conflict",
                {},
                Exception("duplicate frame evidence"),
            )
        return original(self, losing_command)

    monkeypatch.setattr(
        ProgressivePresentationServicesV2,
        "record_presentation_receipt",
        concurrent_winner_then_delegate,
    )

    result = service.record_presentation_receipt(command)
    assert result.presentation_session_id == session.presentation_session_id
    assert result.frame_ordinal == 1
    assert result.presented_through_frame == 1
    assert calls == 2
