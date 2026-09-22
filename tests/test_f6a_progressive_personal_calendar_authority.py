from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import SetPermissionStatusCommand
from alsoul.domain.personal_calendar_presentation import (
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.progressive_personal_calendar import (
    DispatchPersonalCalendarProgressiveFrameCommand,
    OpenPersonalCalendarProgressivePresentationCommand,
)
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    FenceProgressivePresentationAttemptCommand,
    OpenProgressivePresentationCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    PersonalCalendarPresentationServices,
    ProgressivePresentationServices,
)
from alsoul.services.common import sha256_text
from alsoul.storage import schema
from test_f5_personal_calendar_presentation import _adopted_calendar_output
from test_f6a_progressive_presentation_core import _frame, _receipt_command
from test_f6a_progressive_presentation_reconciliation import _ReconciliationAdapter


class _PersonalProgressiveAdapter(_ReconciliationAdapter):
    def __init__(self, now, *, acceptance_state="ACCEPTED"):
        super().__init__(now, acceptance_state=acceptance_state)
        self.payload_calls: list[dict] = []

    def dispatch_frame(self, **kwargs):
        self.payload_calls.append(dict(kwargs))
        return super().dispatch_frame(**kwargs)


def _make_multiframe_output(engine, ctx):
    content = (
        "Personal calendar schedule. "
        + ("A" * 250)
        + " Next calendar portion. "
        + ("B" * 120)
    )
    digest = sha256_text(content)
    with engine.begin() as conn:
        conn.execute(
            update(schema.companion_output)
            .where(
                schema.companion_output.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
            .values(content_text=content, content_digest=digest)
        )
        conn.execute(
            update(schema.personal_calendar_companion_output)
            .where(
                schema.personal_calendar_companion_output.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
            .values(deterministic_render_digest=digest)
        )
    return content


def _set_disclosure_policy(engine, now, ctx, *, status="ALLOW", version="v1"):
    PersonalCalendarPresentationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version=f"calendar-progressive-disclosure-{version}",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
            status=status,
        )
    )


def _open(service, ctx):
    return service.open_personal_calendar_session(
        OpenPersonalCalendarProgressivePresentationCommand(
            operation_id=uuid4(),
            companion_output_id=ctx["adopted"].companion_output_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )


def _fence(service, session):
    return service.fence_attempt(
        FenceProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_session_id=session.presentation_session_id,
        )
    )


def _dispatch_command(ctx, attempt, ordinal, operation_id=None):
    return DispatchPersonalCalendarProgressiveFrameCommand(
        operation_id=operation_id or uuid4(),
        presentation_attempt_id=attempt.presentation_attempt_id,
        frame_ordinal=ordinal,
        permission_id=ctx["permission"].permission_id,
    )


def test_personal_calendar_requires_specialized_open_and_per_frame_authority(
    engine, now
):
    ctx = _adopted_calendar_output(engine, now)
    _make_multiframe_output(engine, ctx)
    _set_disclosure_policy(engine, now, ctx)
    adapter = _PersonalProgressiveAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(DomainError) as generic_open:
        service.open_session(
            OpenProgressivePresentationCommand(
                operation_id=uuid4(),
                companion_output_id=ctx["adopted"].companion_output_id,
                surface_binding_id=ctx["ids"].surface_binding_id,
                channel_binding_id=ctx["ids"].channel_binding_id,
            )
        )
    assert (
        generic_open.value.code
        == "PROGRESSIVE_PRESENTATION_SPECIALIZED_AUTHORITY_REQUIRED"
    )

    session = _open(service, ctx)
    attempt = _fence(service, session)

    with pytest.raises(DomainError) as generic_dispatch:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=1,
            )
        )
    assert (
        generic_dispatch.value.code
        == "PROGRESSIVE_PRESENTATION_SPECIALIZED_AUTHORITY_REQUIRED"
    )
    assert adapter.payload_calls == []

    result = service.dispatch_personal_calendar_frame(
        _dispatch_command(ctx, attempt, 1)
    )
    assert result.acceptance_state == "ACCEPTED"
    assert len(adapter.payload_calls) == 1

    with engine.connect() as conn:
        authority = conn.execute(
            select(schema.progressive_personal_calendar_frame_authority)
        ).mappings().one()
        freshness_count = conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_presentation_freshness_decision
            )
        ).scalar_one()
        disclosure_count = conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_disclosure_decision
            )
        ).scalar_one()

    assert authority["presentation_attempt_id"] == attempt.presentation_attempt_id
    assert authority["frame_ordinal"] == 1
    assert authority["permission_id"] == ctx["permission"].permission_id
    assert int(freshness_count) == 1
    assert int(disclosure_count) == 1


def test_permission_revocation_between_frames_blocks_next_payload_before_transport(
    engine, now
):
    ctx = _adopted_calendar_output(engine, now)
    _make_multiframe_output(engine, ctx)
    _set_disclosure_policy(engine, now, ctx)
    adapter = _PersonalProgressiveAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    session = _open(service, ctx)
    attempt = _fence(service, session)
    frame1 = _frame(engine, session.presentation_session_id, 1)

    first_command = _dispatch_command(ctx, attempt, 1)
    service.dispatch_personal_calendar_frame(first_command)
    service.record_presentation_receipt(
        _receipt_command(session, attempt, frame1, now)
    )
    ctx["calendar"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=ctx["permission"].permission_id,
        )
    )

    replay = service.dispatch_personal_calendar_frame(first_command)
    assert replay.acceptance_state == "ACCEPTED"
    assert len(adapter.payload_calls) == 1

    with pytest.raises(DomainError) as denied:
        service.dispatch_personal_calendar_frame(
            _dispatch_command(ctx, attempt, 2)
        )
    assert denied.value.code == "CALENDAR_DISCLOSURE_DENIED"
    assert len(adapter.payload_calls) == 1

    with engine.connect() as conn:
        authority_count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_personal_calendar_frame_authority
            )
        ).scalar_one()
        frame1_evidence = conn.execute(
            select(func.count())
            .select_from(schema.progressive_presentation_frame_evidence)
            .where(
                schema.progressive_presentation_frame_evidence.c.presentation_session_id
                == session.presentation_session_id,
                schema.progressive_presentation_frame_evidence.c.frame_ordinal == 1,
            )
        ).scalar_one()
        frame2_transport = conn.execute(
            select(func.count())
            .select_from(schema.progressive_presentation_frame_transport)
            .where(
                schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                == attempt.presentation_attempt_id,
                schema.progressive_presentation_frame_transport.c.frame_ordinal == 2,
            )
        ).scalar_one()

    assert int(authority_count) == 1
    assert int(frame1_evidence) == 1
    assert int(frame2_transport) == 0


def test_freshness_and_disclosure_are_re_evaluated_for_each_frame(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    _make_multiframe_output(engine, ctx)
    _set_disclosure_policy(engine, now, ctx)
    adapter = _PersonalProgressiveAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    session = _open(service, ctx)
    attempt = _fence(service, session)
    frame1 = _frame(engine, session.presentation_session_id, 1)

    service.dispatch_personal_calendar_frame(_dispatch_command(ctx, attempt, 1))
    service.record_presentation_receipt(
        _receipt_command(session, attempt, frame1, now)
    )

    stale = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now + timedelta(hours=2)),
        ids=UUIDGenerator(),
    )
    with pytest.raises(DomainError) as expired:
        stale.dispatch_personal_calendar_frame(_dispatch_command(ctx, attempt, 2))
    assert expired.value.code == "CALENDAR_RESULT_STALE"
    assert len(adapter.payload_calls) == 1

    _set_disclosure_policy(engine, now, ctx, status="DENY", version="deny-v2")
    fresh = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    with pytest.raises(DomainError) as denied:
        fresh.dispatch_personal_calendar_frame(_dispatch_command(ctx, attempt, 2))
    assert denied.value.code == "CALENDAR_DISCLOSURE_DENIED"
    assert len(adapter.payload_calls) == 1

    with engine.connect() as conn:
        authority_count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_personal_calendar_frame_authority
            )
        ).scalar_one()
        freshness_count = conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_presentation_freshness_decision
            )
        ).scalar_one()

    assert int(authority_count) == 1
    assert int(freshness_count) == 1


def test_personal_progressive_session_cannot_switch_to_another_first_party_route(
    engine, now
):
    ctx = _adopted_calendar_output(engine, now)
    _set_disclosure_policy(engine, now, ctx)
    adapter = _PersonalProgressiveAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    other_surface = uuid4()
    other_channel = uuid4()
    with engine.begin() as conn:
        conn.execute(
            schema.surface_binding.insert().values(
                surface_binding_id=other_surface,
                companion_person_id=ctx["ids"].companion_person_id,
                surface_namespace="alsoul.first_party",
                surface_ref=f"alternate-{uuid4()}",
                bound_at=now,
            )
        )
        conn.execute(
            schema.channel_binding.insert().values(
                channel_binding_id=other_channel,
                companion_person_id=ctx["ids"].companion_person_id,
                channel_namespace="alsoul.first_party",
                companion_endpoint_ref=f"alternate-{uuid4()}",
                bound_at=now,
            )
        )

    with pytest.raises(DomainError) as wrong_route:
        service.open_personal_calendar_session(
            OpenPersonalCalendarProgressivePresentationCommand(
                operation_id=uuid4(),
                companion_output_id=ctx["adopted"].companion_output_id,
                surface_binding_id=other_surface,
                channel_binding_id=other_channel,
            )
        )
    assert wrong_route.value.code == "PROGRESSIVE_PRESENTATION_ROUTE_INVALID"
    assert adapter.payload_calls == []
