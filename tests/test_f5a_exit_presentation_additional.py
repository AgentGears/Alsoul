from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_presentation as presentation_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    SetPermissionStatusCommand,
    SetPersonalResourceBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.domain.personal_calendar_presentation import (
    PersonalCalendarPresentationStatusResult,
)
from alsoul.storage import schema


@pytest.mark.parametrize("mutation", ["permission", "resource", "relationship"])
def test_exit_current_authority_change_before_first_payload_blocks_delivery(
    engine, now, mutation
):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    adapter = presentation_cases._PresentationAdapter(now)
    adapter.sink_binding_ref = f"presentation.test/pre-dispatch-{mutation}"
    service = presentation_cases._presentation_service(engine, now, ctx, adapter)

    if mutation == "permission":
        ctx["calendar"].set_permission_status(
            SetPermissionStatusCommand(
                operation_id=uuid4(),
                permission_id=ctx["permission"].permission_id,
            )
        )
    elif mutation == "resource":
        ctx["calendar"].set_resource_status(
            SetPersonalResourceBindingStatusCommand(
                operation_id=uuid4(),
                personal_resource_binding_id=ctx[
                    "resource"
                ].personal_resource_binding_id,
                status="INACTIVE",
            )
        )
    else:
        ctx["calendar"].set_relationship_status(
            SetPersonalWorldRelationshipStatusCommand(
                operation_id=uuid4(),
                companion_person_id=ctx["ids"].companion_person_id,
                counterpart_id=ctx["ids"].counterpart_id,
                relationship_id=ctx["ids"].relationship_id,
            )
        )

    with pytest.raises(DomainError) as denied:
        service.present_output(presentation_cases._present_command(ctx))
    assert denied.value.code == "CALENDAR_DISCLOSURE_DENIED"
    assert adapter.payload_calls == []

    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_presentation_attempt)
        ).scalar_one() == 0
        assert conn.execute(
            select(func.count())
            .select_from(schema.personal_calendar_companion_output)
            .where(
                schema.personal_calendar_companion_output.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one() == 1


def test_exit_terminal_negative_recovery_after_revocation_never_resends_or_presents(
    engine, now
):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    adapter = presentation_cases._PresentationAdapter(
        now, dispatch_state="UNKNOWN", lookup_state="NOT_ACCEPTED"
    )
    adapter.sink_binding_ref = "presentation.test/recovered-terminal-negative"
    service = presentation_cases._presentation_service(engine, now, ctx, adapter)

    with pytest.raises(DomainError) as uncertain:
        service.present_output(presentation_cases._present_command(ctx))
    assert uncertain.value.code == "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN"
    assert len(adapter.payload_calls) == 1

    ctx["calendar"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=ctx["permission"].permission_id,
        )
    )
    recovered = service.recover_presentation(presentation_cases._recover_command(ctx))
    assert recovered.state == "NOT_ACCEPTED"
    assert recovered.interaction_event_id is None
    assert len(adapter.payload_calls) == 1
    assert len(adapter.status_calls) == 1

    with engine.connect() as conn:
        assert conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one() == 0


def test_exit_old_terminal_generation_cannot_be_reclassified_as_accepted(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    adapter = presentation_cases._PresentationAdapter(now, dispatch_state="NOT_ACCEPTED")
    adapter.sink_binding_ref = "presentation.test/terminal-generation"
    service = presentation_cases._presentation_service(engine, now, ctx, adapter)
    first = service.present_output(presentation_cases._present_command(ctx))
    assert first.state == "NOT_ACCEPTED"

    with engine.connect() as conn:
        attempt = conn.execute(
            select(schema.personal_calendar_presentation_attempt).where(
                schema.personal_calendar_presentation_attempt.c.presentation_attempt_id
                == first.presentation_attempt_id
            )
        ).mappings().one()

    with pytest.raises(DomainError) as conflict:
        service._settle_attempt(
            first.presentation_attempt_id,
            PersonalCalendarPresentationStatusResult(
                presentation_key=first.presentation_key,
                presentation_attempt_generation=first.presentation_attempt_generation,
                presentation_transport_fence_scope_id=attempt[
                    "presentation_transport_fence_scope_id"
                ],
                state="ACCEPTED",
                receipt_ref="late-old-generation-acceptance",
                accepted_at=now,
            ),
        )
    assert conflict.value.code == "CALENDAR_PRESENTATION_SETTLEMENT_CONFLICT"

    with engine.connect() as conn:
        settled = conn.execute(
            select(schema.personal_calendar_presentation_attempt).where(
                schema.personal_calendar_presentation_attempt.c.presentation_attempt_id
                == first.presentation_attempt_id
            )
        ).mappings().one()
    assert settled["sink_acceptance_state"] == "NOT_ACCEPTED"
