from __future__ import annotations

from uuid import uuid4

from alsoul.domain.progressive_presentation import OpenProgressivePresentationCommand
from alsoul.services import ProgressivePresentationServices
from test_f6a_progressive_presentation_core import _adopt_output


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
    command = OpenProgressivePresentationCommand(
        operation_id=uuid4(),
        companion_output_id=ctx["adopted"].companion_output_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )

    first = service.open_session(command)
    replay = service.open_session(command)

    assert replay.presentation_session_id == first.presentation_session_id
    assert replay.presentation_key == first.presentation_key
    assert replay.frame_count == first.frame_count
