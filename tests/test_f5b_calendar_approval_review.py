from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    CALENDAR_CREATE_APPROVAL_TEXT,
    PresentPersonalCalendarCreateApprovalCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_approval_v2 import PersonalCalendarApprovalServices
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_approval_authority as approval_cases


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _service(engine, now, adapter=None):
    return PersonalCalendarApprovalServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        approval_adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _prepared_action(engine, now):
    ids, foundation, _, resource, _, write_permission, _ = (
        action_cases._bootstrap_write_authority(engine, now)
    )
    source = action_cases._append_create_request(foundation, ids, now)
    action = action_cases._prepare(
        action_cases._service(engine, now),
        ids,
        resource,
        write_permission.permission_id,
        source,
    )
    return ids, foundation, resource, action


def _present(service, action):
    return service.present_create_approval(
        PresentPersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(), action_id=action.action_id
        )
    )


def _approval_event(foundation, ids, now):
    return authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )


def _admit(service, presentation, source):
    return service.admit_create_approval(
        AdmitPersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            approval_presentation_id=presentation.approval_presentation_id,
            source_interaction_event_id=source.event_id,
        )
    )


def test_hardened_replay_preserves_offset_aware_presentation_time(engine, now):
    _, _, _, action = _prepared_action(engine, now)
    adapter = approval_cases._ApprovalAdapter()
    first = _present(_service(engine, now, adapter), action)

    replay = _present(_service(engine, now, None), action)

    assert replay.approval_presentation_id == first.approval_presentation_id
    assert replay.presented_at == first.presented_at
    assert replay.presented_at.tzinfo is not None


def test_tampered_presented_counterpart_cannot_mint_approval(engine, now):
    ids, foundation, _, action = _prepared_action(engine, now)
    service = _service(engine, now, approval_cases._ApprovalAdapter())
    presentation = _present(service, action)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_approval_presentation)
            .where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(presented_to_counterpart_id=uuid4())
        )
    source = _approval_event(foundation, ids, now)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID")


def test_tampered_presentation_key_or_sink_contract_cannot_mint_approval(engine, now):
    ids, foundation, _, action = _prepared_action(engine, now)
    service = _service(engine, now, approval_cases._ApprovalAdapter())
    presentation = _present(service, action)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_approval_presentation)
            .where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(presentation_key="calendar-create-approval:" + "0" * 64)
        )
    source = _approval_event(foundation, ids, now)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID")


def test_control_characters_cannot_enter_human_calendar_display_identity(engine, now):
    _, _, resource, action = _prepared_action(engine, now)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_resource_binding)
            .where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == resource.personal_resource_binding_id
            )
            .values(external_resource_ref="primary\nEffect: READ_ONLY")
        )

    with pytest.raises(DomainError) as invalid:
        _present(_service(engine, now, approval_cases._ApprovalAdapter()), action)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_DISPLAY_IDENTITY_INVALID")

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_approval_presentation)
        ).first() is None
