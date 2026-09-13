from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from alsoul.domain.personal_calendar import (
    SetCredentialBindingStatusCommand,
    SetPermissionStatusCommand,
)
from alsoul.storage import schema

import test_f5a_current_runtime_calendar as runtime_cases


def test_accepted_runtime_recovery_does_not_require_current_read_or_credential(engine, now):
    ids, source, runtime, read_adapter, plan_adapter, sink = runtime_cases._configured_runtime(
        engine, now
    )
    first = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )
    with engine.connect() as conn:
        disclosure = conn.execute(
            select(schema.personal_calendar_disclosure_decision).where(
                schema.personal_calendar_disclosure_decision.c.companion_output_id
                == first.response.companion_output_id
            )
        ).mappings().one()
        fence = conn.execute(
            select(schema.personal_calendar_read_authority_fence).where(
                schema.personal_calendar_read_authority_fence.c.observation_id
                == first.response.observation_id
            )
        ).mappings().one()

    read_services = runtime.personal_calendar_coordinator.read_services
    read_services.set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(), permission_id=disclosure["permission_id"]
        )
    )
    read_services.set_credential_status(
        SetCredentialBindingStatusCommand(
            operation_id=uuid4(),
            credential_binding_id=fence["credential_binding_id"],
        )
    )

    replay = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        after_process_loss=True,
    )

    assert replay.response == first.response
    assert len(read_adapter.requests) == 1
    assert len(plan_adapter.requests) == 1
    assert len(sink.payload_calls) == 1
    assert sink.status_calls == []
