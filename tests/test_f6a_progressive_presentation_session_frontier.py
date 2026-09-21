from __future__ import annotations

from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import func, select

from alsoul.domain.commands import AppendCounterpartInputCommand, PresentCompanionOutputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import OpenProgressivePresentationCommand
from alsoul.services import ProgressivePresentationServices
from alsoul.services.progressive_presentation_v10 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV10,
)
from alsoul.storage import schema
from test_f6a_progressive_presentation_core import _adopt_output


def _open_command(ctx):
    return OpenProgressivePresentationCommand(
        operation_id=uuid4(),
        companion_output_id=ctx["adopted"].companion_output_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )


def test_session_open_operation_receipt_replays_uuid_typed_session_reference(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(
        services,
        bootstrapper,
        now,
        "exact progressive session operation replay",
    )
    service = ProgressivePresentationServices(
        engine,
        clock=services.clock,
        ids=services.ids,
    )
    command = _open_command(ctx)

    first = service.open_session(command)
    replay = service.open_session(command)

    assert replay.presentation_session_id == first.presentation_session_id
    assert replay.presentation_key == first.presentation_key
    assert replay.frame_count == first.frame_count


def test_v10_inner_open_replay_uses_uuid_typed_session_reference(
    services, bootstrapper, engine, now
):
    ctx = _adopt_output(
        services,
        bootstrapper,
        now,
        "exact v10 inner replay typing",
    )
    service = ProgressivePresentationServicesV10(
        engine,
        clock=services.clock,
        ids=services.ids,
    )
    command = _open_command(ctx)

    first = service.open_session(command)
    replay = service.open_session(command)

    assert replay.presentation_session_id == first.presentation_session_id
    assert replay.presentation_key == first.presentation_key


def test_session_open_frontier_serializes_concurrent_canonical_input(
    services, bootstrapper, engine, now, monkeypatch
):
    ctx = _adopt_output(
        services,
        bootstrapper,
        now,
        "serialize session-open frontier against canonical input",
    )
    service = ProgressivePresentationServices(
        engine,
        clock=services.clock,
        ids=services.ids,
    )
    command = _open_command(ctx)

    render_entered = Event()
    release_render = Event()
    input_started = Event()
    input_done = Event()
    errors: list[BaseException] = []
    results: dict[str, object] = {}
    original_render = service._render_frames

    def blocking_render(content_text):
        render_entered.set()
        if not release_render.wait(timeout=5):
            raise AssertionError("timed out waiting to release session-open render")
        return original_render(content_text)

    monkeypatch.setattr(service, "_render_frames", blocking_render)

    def open_worker():
        try:
            results["session"] = service.open_session(command)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    def input_worker():
        input_started.set()
        try:
            results["input"] = services.append_counterpart_input(
                AppendCounterpartInputCommand(
                    operation_id=uuid4(),
                    companion_person_id=ctx["ids"].companion_person_id,
                    counterpart_id=ctx["ids"].counterpart_id,
                    relationship_id=ctx["ids"].relationship_id,
                    ingress_idempotency_key=str(uuid4()),
                    content_text="Interrupt after presentation is active.",
                    occurred_at=now,
                    surface_binding_id=ctx["ids"].surface_binding_id,
                    channel_binding_id=ctx["ids"].channel_binding_id,
                    conversation_id="f6a-frontier-race",
                )
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            input_done.set()

    opener = Thread(target=open_worker)
    opener.start()
    assert render_entered.wait(timeout=5)

    ingress = Thread(target=input_worker)
    ingress.start()
    assert input_started.wait(timeout=5)
    assert not input_done.wait(timeout=0.2)

    release_render.set()
    opener.join(timeout=5)
    ingress.join(timeout=5)
    assert not opener.is_alive()
    assert not ingress.is_alive()
    assert errors == []

    session = results["session"]
    canonical = results["input"]
    with engine.connect() as conn:
        frontier = conn.execute(
            select(schema.progressive_presentation_session_frontier).where(
                schema.progressive_presentation_session_frontier.c.presentation_session_id
                == session.presentation_session_id
            )
        ).mappings().one()
    assert canonical.timeline_seq > int(frontier["open_timeline_frontier"])


def test_progressive_open_fences_concurrent_generic_full_presentation(
    services, bootstrapper, engine, now, monkeypatch
):
    ctx = _adopt_output(
        services,
        bootstrapper,
        now,
        "serialize progressive ownership against generic presentation",
    )
    service = ProgressivePresentationServices(
        engine,
        clock=services.clock,
        ids=services.ids,
    )
    command = _open_command(ctx)

    render_entered = Event()
    release_render = Event()
    generic_started = Event()
    generic_done = Event()
    errors: list[BaseException] = []
    generic_error: list[BaseException] = []
    original_render = service._render_frames

    def blocking_render(content_text):
        render_entered.set()
        if not release_render.wait(timeout=5):
            raise AssertionError("timed out waiting to release progressive open")
        return original_render(content_text)

    monkeypatch.setattr(service, "_render_frames", blocking_render)

    def open_worker():
        try:
            service.open_session(command)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    def generic_worker():
        generic_started.set()
        try:
            services.present_companion_output(
                PresentCompanionOutputCommand(
                    operation_id=uuid4(),
                    companion_output_id=ctx["adopted"].companion_output_id,
                    surface_binding_id=ctx["ids"].surface_binding_id,
                    channel_binding_id=ctx["ids"].channel_binding_id,
                    presented_at=now,
                )
            )
        except BaseException as exc:
            generic_error.append(exc)
        finally:
            generic_done.set()

    opener = Thread(target=open_worker)
    opener.start()
    assert render_entered.wait(timeout=5)

    generic = Thread(target=generic_worker)
    generic.start()
    assert generic_started.wait(timeout=5)
    assert not generic_done.wait(timeout=0.2)

    release_render.set()
    opener.join(timeout=5)
    generic.join(timeout=5)
    assert not opener.is_alive()
    assert not generic.is_alive()
    assert errors == []
    assert len(generic_error) == 1
    assert isinstance(generic_error[0], DomainError)
    assert (
        generic_error[0].code
        == "PROGRESSIVE_PRESENTATION_HISTORY_COMMIT_REQUIRED"
    )

    with engine.connect() as conn:
        count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id,
                schema.interaction_event.c.event_kind
                == "COMPANION_PRESENTED_OUTPUT",
            )
        ).scalar_one()
    assert int(count) == 0
