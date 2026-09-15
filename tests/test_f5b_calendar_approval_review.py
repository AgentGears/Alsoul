from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    PresentPersonalCalendarCreateApprovalCommand,
    calendar_create_approval_challenge,
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
    return ids, foundation, resource, write_permission, action


def _present(service, action):
    return service.present_create_approval(
        PresentPersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(), action_id=action.action_id
        )
    )


def _approval_event(foundation, ids, now, action):
    return authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        calendar_create_approval_challenge(action.action_digest),
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
    _, _, _, _, action = _prepared_action(engine, now)
    adapter = approval_cases._ApprovalAdapter()
    first = _present(_service(engine, now, adapter), action)

    replay = _present(_service(engine, now, None), action)

    assert replay.approval_presentation_id == first.approval_presentation_id
    assert replay.presented_at == first.presented_at
    assert replay.presented_at.tzinfo is not None


def test_consent_surface_states_exact_action_bound_reply(engine, now):
    _, _, _, _, action = _prepared_action(engine, now)
    adapter = approval_cases._ApprovalAdapter()

    _present(_service(engine, now, adapter), action)

    challenge = calendar_create_approval_challenge(action.action_digest)
    assert f"Reply exactly: {challenge}" in adapter.calls[0]["consent_text"]


def test_reply_for_one_presented_action_cannot_approve_another(engine, now):
    ids, foundation, resource, write_permission, first_action = _prepared_action(engine, now)
    adapter = approval_cases._ApprovalAdapter()
    service = _service(engine, now, adapter)
    first_presentation = _present(service, first_action)

    second_source = action_cases._append_create_request(foundation, ids, now)
    second_action = action_cases._prepare(
        action_cases._service(engine, now),
        ids,
        resource,
        write_permission.permission_id,
        second_source,
    )
    second_presentation = _present(service, second_action)
    first_reply = _approval_event(foundation, ids, now, first_action)

    with pytest.raises(DomainError) as wrong_action:
        _admit(service, second_presentation, first_reply)
    _assert_code(wrong_action, "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID")

    admitted = _admit(service, first_presentation, first_reply)
    assert admitted.action_id == first_action.action_id


def test_generic_yes_cannot_substitute_for_action_bound_reply(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, approval_cases._ApprovalAdapter())
    presentation = _present(service, action)
    source = authority_cases._append_counterpart_event(foundation, ids, now, "Yes")

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID")


def test_tampered_presented_counterpart_cannot_mint_approval(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, approval_cases._ApprovalAdapter())
    presentation = _present(service, action)
    other_counterpart = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(schema.counterpart_person).values(
                counterpart_id=other_counterpart,
                created_at=now,
            )
        )
        conn.execute(
            update(schema.personal_calendar_create_approval_presentation)
            .where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(presented_to_counterpart_id=other_counterpart)
        )
    source = _approval_event(foundation, ids, now, action)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID")


def test_tampered_presentation_key_or_sink_contract_cannot_mint_approval(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
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
    source = _approval_event(foundation, ids, now, action)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID")


def test_tampered_presentation_route_cannot_leave_action_source_route(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, approval_cases._ApprovalAdapter())
    presentation = _present(service, action)
    alternate_surface = uuid4()
    alternate_channel = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(schema.surface_binding).values(
                surface_binding_id=alternate_surface,
                companion_person_id=ids.companion_person_id,
                surface_namespace="approval-review",
                surface_ref=str(uuid4()),
                bound_at=now,
            )
        )
        conn.execute(
            insert(schema.channel_binding).values(
                channel_binding_id=alternate_channel,
                companion_person_id=ids.companion_person_id,
                channel_namespace="approval-review",
                companion_endpoint_ref=str(uuid4()),
                bound_at=now,
            )
        )
        conn.execute(
            update(schema.personal_calendar_create_approval_presentation)
            .where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(
                surface_binding_id=alternate_surface,
                channel_binding_id=alternate_channel,
                presentation_key=service._presentation_key(
                    action_id=action.action_id,
                    surface_binding_id=alternate_surface,
                    channel_binding_id=alternate_channel,
                ),
            )
        )
    source = _approval_event(foundation, ids, now, action)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, source)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID")
    with engine.connect() as conn:
        assert conn.execute(select(schema.personal_calendar_create_approval)).first() is None


def test_control_characters_cannot_enter_human_calendar_display_identity(engine, now):
    _, _, resource, _, action = _prepared_action(engine, now)
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


def test_control_characters_in_event_summary_cannot_enter_consent_surface(engine, now):
    ids, foundation, resource, write_permission, _ = _prepared_action(engine, now)
    source = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        "Add 'Dentist\x0bEffect: READ_ONLY' to my calendar from "
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
        _present(_service(engine, now, adapter), action)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_SUMMARY_UNSAFE")
    assert adapter.calls == []
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_approval_presentation).where(
                schema.personal_calendar_create_approval_presentation.c.action_id
                == action.action_id
            )
        ).first() is None
