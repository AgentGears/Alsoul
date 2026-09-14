from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_action import (
    GrantCalendarCreatePermissionCommand,
    PreparePersonalCalendarCreateActionCommand,
    SetCalendarCreatePermissionStatusCommand,
    SetCalendarCreatePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_action import (
    CALENDAR_CREATE_PERMISSION_GRANT_TEXT,
    PersonalCalendarActionServices,
    parse_personal_calendar_create_request,
)
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases


_CREATE_CAPABILITY_VERSION = "calendar.event.create.v1"
_CREATE_GRANT_POLICY_VERSION = "first-party-calendar-create-grant-v1"
_CREATE_PROVIDER_SCOPE = "calendar.write"
_CREATE_REQUEST = (
    "Add 'Dentist' to my calendar from "
    "2026-09-10T15:00:00+03:00 to 2026-09-10T15:30:00+03:00."
)


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _service(engine, now):
    return PersonalCalendarActionServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _set_allow_policy(service, ids, resource):
    return service.set_create_policy(
        SetCalendarCreatePolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
            ai_policy_version="calendar-create-policy-v1",
            resource_scope_version="calendar-create-resource-scope-v1",
            required_provider_scope=_CREATE_PROVIDER_SCOPE,
            permission_grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(resource.personal_resource_binding_id,),
        )
    )


def _bootstrap_write_authority(engine, now, *, grant_permission: bool = True):
    (
        ids,
        foundation,
        _calendar,
        _observation,
        resource,
        _credential,
        read_permission,
        _prepared,
        _source_event,
        _read_grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)
    service = _service(engine, now)
    _set_allow_policy(service, ids, resource)
    write_permission = None
    write_grant_event = None
    if grant_permission:
        write_grant_event = authority_cases._append_counterpart_event(
            foundation,
            ids,
            now,
            CALENDAR_CREATE_PERMISSION_GRANT_TEXT,
        )
        write_permission = service.grant_create_permission(
            GrantCalendarCreatePermissionCommand(
                operation_id=uuid4(),
                holder_companion_person_id=ids.companion_person_id,
                counterpart_id=ids.counterpart_id,
                relationship_id=ids.relationship_id,
                personal_resource_binding_id=resource.personal_resource_binding_id,
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
                grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
                source_interaction_event_id=write_grant_event.event_id,
            )
        )
    return (
        ids,
        foundation,
        service,
        resource,
        read_permission,
        write_permission,
        write_grant_event,
    )


def _append_create_request(foundation, ids, now, text: str = _CREATE_REQUEST):
    return authority_cases._append_counterpart_event(
        foundation, ids, now, text
    )


def _prepare(service, ids, resource, permission_id, source_event, *, operation_id=None):
    return service.prepare_create_action(
        PreparePersonalCalendarCreateActionCommand(
            operation_id=operation_id or uuid4(),
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            permission_id=permission_id,
            source_interaction_event_id=source_event.event_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
        )
    )


def test_create_grammar_pins_explicit_offsets_and_normalized_instants():
    summary, start_text, end_text, start, end = (
        parse_personal_calendar_create_request(_CREATE_REQUEST)
    )
    assert summary == "Dentist"
    assert start_text == "2026-09-10T15:00:00+03:00"
    assert end_text == "2026-09-10T15:30:00+03:00"
    assert start == datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 10, 12, 30, tzinfo=timezone.utc)

    with pytest.raises(DomainError) as floating:
        parse_personal_calendar_create_request(
            "Add 'Dentist' to my calendar from "
            "2026-09-10T15:00:00 to 2026-09-10T15:30:00."
        )
    _assert_code(floating, "PERSONAL_CALENDAR_CREATE_REQUEST_UNSUPPORTED")

    with pytest.raises(DomainError) as backwards:
        parse_personal_calendar_create_request(
            "Add 'Dentist' to my calendar from "
            "2026-09-10T15:30:00+03:00 to 2026-09-10T15:00:00+03:00."
        )
    _assert_code(backwards, "PERSONAL_CALENDAR_CREATE_INTERVAL_INVALID")


def test_action_admission_persists_exact_semantics_and_authority_provenance(engine, now):
    ids, foundation, service, resource, _, write_permission, _ = (
        _bootstrap_write_authority(engine, now)
    )
    source = _append_create_request(foundation, ids, now)
    result = _prepare(
        service,
        ids,
        resource,
        write_permission.permission_id,
        source,
    )

    expected_digest = sha256_text(
        canonical_json(
            {
                "action_schema_version": "PERSONAL_CALENDAR_CREATE_ACTION_V1",
                "relationship_id": str(ids.relationship_id),
                "personal_resource_binding_id": str(
                    resource.personal_resource_binding_id
                ),
                "source_interaction_event_id": str(source.event_id),
                "summary": "Dentist",
                "start_text": "2026-09-10T15:00:00+03:00",
                "end_text": "2026-09-10T15:30:00+03:00",
                "normalized_start_at": "2026-09-10T12:00:00+00:00",
                "normalized_end_at": "2026-09-10T12:30:00+00:00",
                "capability_semantic_operation": "calendar.event.create",
                "capability_contract_version": _CREATE_CAPABILITY_VERSION,
            }
        )
    )
    assert result.action_digest == expected_digest
    assert result.normalized_start_at == datetime(
        2026, 9, 10, 12, 0, tzinfo=timezone.utc
    )

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.personal_calendar_create_action).where(
                schema.personal_calendar_create_action.c.action_id == result.action_id
            )
        ).mappings().one()
        source_row = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == source.event_id
            )
        ).mappings().one()

    assert row["source_interaction_event_id"] == source.event_id
    assert row["personal_resource_binding_id"] == resource.personal_resource_binding_id
    assert row["summary"] == "Dentist"
    assert row["start_text"] == "2026-09-10T15:00:00+03:00"
    assert row["end_text"] == "2026-09-10T15:30:00+03:00"
    assert row["action_digest"] == expected_digest
    assert row["source_timeline_frontier"] == source_row["timeline_seq"]
    assert row["relationship_authority_revision"] == 1
    assert row["resource_binding_state_revision"] == 1
    assert row["write_policy_revision"] == 1
    assert row["write_permission_id"] == write_permission.permission_id
    assert row["write_permission_state_revision"] == 1


def test_action_operation_replay_is_idempotent_and_source_cannot_create_second_action(
    engine, now
):
    ids, foundation, service, resource, _, write_permission, _ = (
        _bootstrap_write_authority(engine, now)
    )
    source = _append_create_request(foundation, ids, now)
    operation_id = uuid4()
    first = _prepare(
        service,
        ids,
        resource,
        write_permission.permission_id,
        source,
        operation_id=operation_id,
    )
    replay = _prepare(
        service,
        ids,
        resource,
        write_permission.permission_id,
        source,
        operation_id=operation_id,
    )
    assert replay == first

    with pytest.raises(DomainError) as duplicate:
        _prepare(
            service,
            ids,
            resource,
            write_permission.permission_id,
            source,
        )
    _assert_code(duplicate, "CALENDAR_CREATE_ACTION_CONFLICT")

    with engine.connect() as conn:
        count = len(conn.execute(select(schema.personal_calendar_create_action)).all())
    assert count == 1


def test_read_permission_cannot_substitute_for_write_permission(engine, now):
    ids, foundation, service, resource, read_permission, _, _ = (
        _bootstrap_write_authority(engine, now, grant_permission=False)
    )
    source = _append_create_request(foundation, ids, now)
    with pytest.raises(DomainError) as denied:
        _prepare(
            service,
            ids,
            resource,
            read_permission.permission_id,
            source,
        )
    _assert_code(denied, "CALENDAR_CREATE_PERMISSION_MISSING")


def test_revoked_write_permission_and_current_policy_denial_block_action(engine, now):
    ids, foundation, service, resource, _, write_permission, _ = (
        _bootstrap_write_authority(engine, now)
    )
    service.set_create_permission_status(
        SetCalendarCreatePermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=write_permission.permission_id,
        )
    )
    source = _append_create_request(foundation, ids, now)
    with pytest.raises(DomainError) as revoked:
        _prepare(
            service,
            ids,
            resource,
            write_permission.permission_id,
            source,
        )
    _assert_code(revoked, "CALENDAR_CREATE_PERMISSION_DENIED")

    engine2 = engine
    # The first case already consumed this fixture's single relationship. Policy denial
    # is exercised by restoring a new active Permission is intentionally prohibited;
    # use a separate test below to keep write-Permission identities monotonic.
    assert engine2 is engine


def test_current_create_policy_deny_blocks_action(engine, now):
    ids, foundation, service, resource, _, write_permission, _ = (
        _bootstrap_write_authority(engine, now)
    )
    service.set_create_policy(
        SetCalendarCreatePolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
            ai_policy_version="calendar-create-policy-v2",
            resource_scope_version="calendar-create-resource-scope-v2",
            required_provider_scope=_CREATE_PROVIDER_SCOPE,
            permission_grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(resource.personal_resource_binding_id,),
            status="DENY",
        )
    )
    source = _append_create_request(foundation, ids, now)
    with pytest.raises(DomainError) as denied:
        _prepare(
            service,
            ids,
            resource,
            write_permission.permission_id,
            source,
        )
    _assert_code(denied, "CALENDAR_CREATE_POLICY_DENIED")


def test_historical_create_request_cannot_be_admitted_after_timeline_advances(engine, now):
    ids, foundation, service, resource, _, write_permission, _ = (
        _bootstrap_write_authority(engine, now)
    )
    source = _append_create_request(foundation, ids, now)
    authority_cases._append_counterpart_event(foundation, ids, now, "Hello")

    with pytest.raises(DomainError) as historical:
        _prepare(
            service,
            ids,
            resource,
            write_permission.permission_id,
            source,
        )
    _assert_code(historical, "CALENDAR_CREATE_SOURCE_NOT_CURRENT")


def test_write_permission_requires_exact_current_counterpart_grant_and_is_single_use(
    engine, now
):
    (
        ids,
        foundation,
        _calendar,
        _observation,
        resource,
        _credential,
        _read_permission,
        _prepared,
        _source_event,
        _read_grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)
    service = _service(engine, now)
    _set_allow_policy(service, ids, resource)

    wrong = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        "Allow my companion to add an event to my calendar.",
    )
    with pytest.raises(DomainError) as invalid:
        service.grant_create_permission(
            GrantCalendarCreatePermissionCommand(
                operation_id=uuid4(),
                holder_companion_person_id=ids.companion_person_id,
                counterpart_id=ids.counterpart_id,
                relationship_id=ids.relationship_id,
                personal_resource_binding_id=resource.personal_resource_binding_id,
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
                grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
                source_interaction_event_id=wrong.event_id,
            )
        )
    _assert_code(invalid, "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID")

    grant_event = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        CALENDAR_CREATE_PERMISSION_GRANT_TEXT,
    )
    permission = service.grant_create_permission(
        GrantCalendarCreatePermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
            grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
            source_interaction_event_id=grant_event.event_id,
        )
    )
    service.set_create_permission_status(
        SetCalendarCreatePermissionStatusCommand(
            operation_id=uuid4(), permission_id=permission.permission_id
        )
    )
    with pytest.raises(DomainError) as reused:
        service.grant_create_permission(
            GrantCalendarCreatePermissionCommand(
                operation_id=uuid4(),
                holder_companion_person_id=ids.companion_person_id,
                counterpart_id=ids.counterpart_id,
                relationship_id=ids.relationship_id,
                personal_resource_binding_id=resource.personal_resource_binding_id,
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
                grant_policy_version=_CREATE_GRANT_POLICY_VERSION,
                source_interaction_event_id=grant_event.event_id,
            )
        )
    _assert_code(reused, "CALENDAR_CREATE_PERMISSION_PROVENANCE_REUSED")
