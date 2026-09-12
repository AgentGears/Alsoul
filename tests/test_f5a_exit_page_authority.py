from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_acquisition as acquisition_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    SetPersonalResourceBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.domain.personal_calendar_acquisition import PersonalCalendarReadPage
from alsoul.domain.types import FixedClock
from alsoul.storage import schema


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("relationship", "RELATIONSHIP_NOT_ACTIVE"),
        ("resource", "PERSONAL_RESOURCE_BINDING_NOT_CURRENT"),
    ],
)
def test_exit_relationship_or_resource_change_between_pages_blocks_next_transport(
    engine, now, mutation, expected_code
):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    first = PersonalCalendarReadPage(
        events=(),
        snapshot_ref="snapshot-authority-change",
        snapshot_as_of=now,
        next_page_token="cursor-2",
        terminal=False,
    )
    second = PersonalCalendarReadPage(
        events=(),
        snapshot_ref="snapshot-authority-change",
        snapshot_as_of=now,
        next_page_token=None,
        terminal=True,
    )

    def mutate_after_first(read_count, _request, _page):
        if read_count != 1:
            return
        if mutation == "relationship":
            ctx["calendar"].set_relationship_status(
                SetPersonalWorldRelationshipStatusCommand(
                    operation_id=uuid4(),
                    companion_person_id=ctx["ids"].companion_person_id,
                    counterpart_id=ctx["ids"].counterpart_id,
                    relationship_id=ctx["ids"].relationship_id,
                )
            )
        else:
            ctx["calendar"].set_resource_status(
                SetPersonalResourceBindingStatusCommand(
                    operation_id=uuid4(),
                    personal_resource_binding_id=ctx[
                        "resource"
                    ].personal_resource_binding_id,
                    status="INACTIVE",
                )
            )

    adapter = acquisition_cases._FakeCalendarAdapter(
        [first, second], after_read=mutate_after_first
    )
    with pytest.raises(DomainError) as blocked:
        acquisition_cases._acquisition(
            engine, adapter, clock=FixedClock(now)
        ).acquire(acquisition_cases._command(ctx))
    assert blocked.value.code == expected_code
    assert len(adapter.requests) == 1

    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_world_result)
        ).scalar_one() == 0
        attempt = conn.execute(
            select(schema.personal_calendar_acquisition_attempt)
        ).mappings().one()
        fences = conn.execute(
            select(schema.personal_calendar_read_authority_fence)
        ).mappings().all()
    assert attempt["status"] == "FAILED"
    assert len(fences) == 1
    assert int(fences[0]["relationship_authority_revision"]) == 1
    assert int(fences[0]["resource_binding_state_revision"]) == 1
