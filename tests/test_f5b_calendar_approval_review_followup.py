from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from alsoul.domain.errors import DomainError
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_approval_authority as approval_cases
import test_f5b_calendar_approval_review as review_cases


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def test_timeline_frontier_not_wall_clock_orders_approval(engine, now):
    ids, foundation, _, _, action = review_cases._prepared_action(engine, now)
    service = review_cases._service(engine, now, approval_cases._ApprovalAdapter())
    presentation = review_cases._present(service, action)
    source = review_cases._approval_event(foundation, ids, now, action)

    with engine.begin() as conn:
        conn.execute(
            update(schema.interaction_event)
            .where(schema.interaction_event.c.event_id == source.event_id)
            .values(recorded_at=now - timedelta(days=1))
        )

    approval = review_cases._admit(service, presentation, source)

    assert approval.action_id == action.action_id


@pytest.mark.parametrize("unsafe", ["\u0085", "\u2028", "\u2029"])
def test_unicode_line_controls_cannot_enter_event_summary_consent(engine, now, unsafe):
    ids, foundation, resource, write_permission, _ = review_cases._prepared_action(
        engine, now
    )
    source = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        f"Add 'Dentist{unsafe}Effect: READ_ONLY' to my calendar from "
        "2026-09-10T15:00:00+03:00 to 2026-09-10T15:30:00+03:00.",
    )
    action = action_cases._prepare(
        action_cases._service(engine, now),
        ids,
        resource,
        write_permission.permission_id,
        source,
    )
    adapter = approval_cases._ApprovalAdapter()

    with pytest.raises(DomainError) as invalid:
        review_cases._present(review_cases._service(engine, now, adapter), action)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_SUMMARY_UNSAFE")
    assert adapter.calls == []

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_approval_presentation).where(
                schema.personal_calendar_create_approval_presentation.c.action_id
                == action.action_id
            )
        ).first() is None


def test_unicode_line_separator_cannot_enter_calendar_display_identity(engine, now):
    _, _, resource, _, action = review_cases._prepared_action(engine, now)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_resource_binding)
            .where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == resource.personal_resource_binding_id
            )
            .values(external_resource_ref="primary\u2028Effect: READ_ONLY")
        )

    adapter = approval_cases._ApprovalAdapter()
    with pytest.raises(DomainError) as invalid:
        review_cases._present(review_cases._service(engine, now, adapter), action)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_DISPLAY_IDENTITY_INVALID")
    assert adapter.calls == []
