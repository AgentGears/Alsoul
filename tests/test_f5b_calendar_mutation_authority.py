from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

import test_f5_personal_calendar_authority as authority_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_APPROVAL_TEXT,
    CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT,
    CalendarCreateApprovalPresentationAcceptance,
    CreateCalendarActionCommand,
    GrantCalendarCreateApprovalCommand,
    GrantCalendarCreatePermissionCommand,
    PresentCalendarCreateApprovalCommand,
    RevokeCalendarCreateApprovalCommand,
    RevokeCalendarCreatePermissionCommand,
    SetCalendarCreatePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarMutationAuthorityServices
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.storage import schema

_CREATE_CAPABILITY_VERSION = "calendar.event.create.v1"
_WRITE_GRANT_POLICY_VERSION = "calendar-write-grant-v1"
_APPROVAL_POLICY_VERSION = "calendar-create-approval-v1"
_WRITE_SCOPE = "calendar.write"


class _ApprovalPresenter:
    presenter_binding_ref = "first-party.test/calendar-create-consent"
    presentation_contract_version = "CALENDAR_CREATE_APPROVAL_PRESENTATION_V1"

    def __init__(self):
        self.calls = []

    def present_approval(self, **kwargs):
        self.calls.append(dict(kwargs))
        return CalendarCreateApprovalPresentationAcceptance(
            presentation_acceptance_ref=f"accepted-{kwargs['approval_presentation_id']}"
        )


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _service(engine, now, presenter=None):
    return PersonalCalendarMutationAuthorityServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        approval_presenter=presenter,
    )


def _bootstrap_mutation(engine, now):
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
        _grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)
    presenter = _ApprovalPresenter()
    service = _service(engine, now, presenter)

    grant_event = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT,
    )
    write_permission = service.grant_write_permission(
        GrantCalendarCreatePermissionCommand(
            operation_id=uuid4(),
            source_interaction_event_id=grant_event.event_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
            grant_policy_version=_WRITE_GRANT_POLICY_VERSION,
        )
    )
    service.set_write_policy(
        SetCalendarCreatePolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
            ai_policy_version="calendar-create-policy-v1",
            resource_scope_version="calendar-create-scope-v1",
            required_provider_scope=_WRITE_SCOPE,
            permission_grant_policy_version=_WRITE_GRANT_POLICY_VERSION,
            approval_policy_version=_APPROVAL_POLICY_VERSION,
            allowed_resource_binding_ids=(resource.personal_resource_binding_id,),
        )
    )
    action_event = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        "Add 'Dentist' to my calendar from 2026-09-10T15:00:00+03:00 to 2026-09-10T15:30:00+03:00.",
    )
    action = service.create_action(
        CreateCalendarActionCommand(
            operation_id=uuid4(),
            source_interaction_event_id=action_event.event_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
        )
    )
    return {
        "ids": ids,
        "foundation": foundation,
        "resource": resource,
        "read_permission": read_permission,
        "write_permission": write_permission,
        "presenter": presenter,
        "service": service,
        "action_event": action_event,
        "action": action,
    }


def test_calendar_create_action_permission_and_approval_are_exact_and_separate(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    action = ctx["action"]
    service = ctx["service"]

    presentation = service.present_action_for_approval(
        PresentCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=action.action_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    assert len(ctx["presenter"].calls) == 1
    payload = ctx["presenter"].calls[0]["consent_payload_text"]
    assert "Dentist" in payload
    assert "2026-09-10T15:00:00+03:00" in payload
    assert "calendar.event.create" in payload

    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"],
        ctx["ids"],
        now,
        CALENDAR_CREATE_APPROVAL_TEXT,
    )
    approval = service.grant_approval(
        GrantCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=action.action_id,
            approval_presentation_id=presentation.approval_presentation_id,
            source_interaction_event_id=approval_event.event_id,
            approval_policy_version=_APPROVAL_POLICY_VERSION,
        )
    )

    with engine.connect() as conn:
        action_row = conn.execute(
            select(schema.personal_calendar_action).where(
                schema.personal_calendar_action.c.action_id == action.action_id
            )
        ).mappings().one()
        permission_row = conn.execute(
            select(schema.personal_calendar_write_permission_grant).where(
                schema.personal_calendar_write_permission_grant.c.permission_id
                == ctx["write_permission"].permission_id
            )
        ).mappings().one()
        approval_row = conn.execute(
            select(schema.personal_calendar_approval).where(
                schema.personal_calendar_approval.c.approval_id == approval.approval_id
            )
        ).mappings().one()

    assert action_row["title"] == "Dentist"
    assert action_row["start_timestamp_text"] == "2026-09-10T15:00:00+03:00"
    assert action_row["end_timestamp_text"] == "2026-09-10T15:30:00+03:00"
    assert action_row["normalized_start_at"].replace(tzinfo=timezone.utc) == datetime(
        2026, 9, 10, 12, 0, tzinfo=timezone.utc
    )
    assert action_row["normalized_end_at"].replace(tzinfo=timezone.utc) == datetime(
        2026, 9, 10, 12, 30, tzinfo=timezone.utc
    )
    assert permission_row["operation_class"] == "WRITE"
    assert permission_row["capability_semantic_operation"] == "calendar.event.create"
    assert ctx["write_permission"].permission_id != ctx["read_permission"].permission_id
    assert approval_row["action_digest"] == action.action_digest
    assert approval_row["consent_payload_digest"] == presentation.consent_payload_digest


def test_calendar_create_requires_explicit_offsets_and_current_request(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    floating = authority_cases._append_counterpart_event(
        ctx["foundation"],
        ctx["ids"],
        now,
        "Add 'Floating' to my calendar from 2026-09-10T15:00:00 to 2026-09-10T15:30:00.",
    )
    with pytest.raises(DomainError) as offset:
        ctx["service"].create_action(
            CreateCalendarActionCommand(
                operation_id=uuid4(),
                source_interaction_event_id=floating.event_id,
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
            )
        )
    _assert_code(offset, "CALENDAR_CREATE_TIME_OFFSET_REQUIRED")

    newer = authority_cases._append_counterpart_event(
        ctx["foundation"], ctx["ids"], now, "Hello"
    )
    assert newer.timeline_seq > floating.timeline_seq
    with pytest.raises(DomainError) as stale:
        ctx["service"].create_action(
            CreateCalendarActionCommand(
                operation_id=uuid4(),
                source_interaction_event_id=floating.event_id,
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
            )
        )
    _assert_code(stale, "CALENDAR_CREATE_SOURCE_EVENT_NOT_CURRENT")


def test_write_permission_has_trusted_distinct_grant_provenance(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    with engine.connect() as conn:
        write = conn.execute(
            select(schema.personal_calendar_write_permission_grant).where(
                schema.personal_calendar_write_permission_grant.c.permission_id
                == ctx["write_permission"].permission_id
            )
        ).mappings().one()
        read = conn.execute(
            select(schema.permission_grant).where(
                schema.permission_grant.c.permission_id == ctx["read_permission"].permission_id
            )
        ).mappings().one()
    assert write["grantor_ref"] == ctx["ids"].counterpart_id
    assert write["grant_source"] == "FIRST_PARTY_COUNTERPART"
    assert write["operation_class"] == "WRITE"
    assert read["operation_class"] == "READ"
    assert write["permission_id"] != read["permission_id"]

    with pytest.raises(DomainError) as reused:
        ctx["service"].grant_write_permission(
            GrantCalendarCreatePermissionCommand(
                operation_id=uuid4(),
                source_interaction_event_id=write["source_interaction_event_id"],
                capability_contract_version=_CREATE_CAPABILITY_VERSION,
                grant_policy_version=_WRITE_GRANT_POLICY_VERSION,
            )
        )
    _assert_code(reused, "CALENDAR_CREATE_SOURCE_EVENT_NOT_CURRENT")


def test_approval_requires_exact_trusted_presentation_and_rejects_tampering(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    presentation = ctx["service"].present_action_for_approval(
        PresentCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=ctx["action"].action_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"], ctx["ids"], now, CALENDAR_CREATE_APPROVAL_TEXT
    )

    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_approval_presentation)
            .where(
                schema.personal_calendar_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(title="Tampered title")
        )
    with pytest.raises(DomainError) as tampered:
        ctx["service"].grant_approval(
            GrantCalendarCreateApprovalCommand(
                operation_id=uuid4(),
                action_id=ctx["action"].action_id,
                approval_presentation_id=presentation.approval_presentation_id,
                source_interaction_event_id=approval_event.event_id,
                approval_policy_version=_APPROVAL_POLICY_VERSION,
            )
        )
    _assert_code(tampered, "CALENDAR_CREATE_APPROVAL_SEMANTICS_MISMATCH")


def test_materially_new_action_cannot_reuse_prior_consent(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    old_presentation = ctx["service"].present_action_for_approval(
        PresentCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=ctx["action"].action_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    new_event = authority_cases._append_counterpart_event(
        ctx["foundation"],
        ctx["ids"],
        now,
        "Add 'Dentist moved' to my calendar from 2026-09-10T16:00:00+03:00 to 2026-09-10T16:30:00+03:00.",
    )
    new_action = ctx["service"].create_action(
        CreateCalendarActionCommand(
            operation_id=uuid4(),
            source_interaction_event_id=new_event.event_id,
            capability_contract_version=_CREATE_CAPABILITY_VERSION,
        )
    )
    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"], ctx["ids"], now, CALENDAR_CREATE_APPROVAL_TEXT
    )
    with pytest.raises(DomainError) as mismatch:
        ctx["service"].grant_approval(
            GrantCalendarCreateApprovalCommand(
                operation_id=uuid4(),
                action_id=new_action.action_id,
                approval_presentation_id=old_presentation.approval_presentation_id,
                source_interaction_event_id=approval_event.event_id,
                approval_policy_version=_APPROVAL_POLICY_VERSION,
            )
        )
    _assert_code(mismatch, "CALENDAR_CREATE_APPROVAL_SEMANTICS_MISMATCH")


def test_write_permission_and_approval_revocation_are_append_only(engine, now):
    ctx = _bootstrap_mutation(engine, now)
    presentation = ctx["service"].present_action_for_approval(
        PresentCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=ctx["action"].action_id,
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"], ctx["ids"], now, CALENDAR_CREATE_APPROVAL_TEXT
    )
    approval = ctx["service"].grant_approval(
        GrantCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            action_id=ctx["action"].action_id,
            approval_presentation_id=presentation.approval_presentation_id,
            source_interaction_event_id=approval_event.event_id,
            approval_policy_version=_APPROVAL_POLICY_VERSION,
        )
    )
    permission_state = ctx["service"].revoke_write_permission(
        RevokeCalendarCreatePermissionCommand(
            operation_id=uuid4(), permission_id=ctx["write_permission"].permission_id
        )
    )
    approval_state = ctx["service"].revoke_approval(
        RevokeCalendarCreateApprovalCommand(
            operation_id=uuid4(), approval_id=approval.approval_id
        )
    )
    assert permission_state.revision == 2
    assert approval_state.revision == 2
    with engine.connect() as conn:
        permission_rows = conn.execute(
            select(schema.personal_calendar_write_permission_state).where(
                schema.personal_calendar_write_permission_state.c.permission_id
                == ctx["write_permission"].permission_id
            )
        ).mappings().all()
        approval_rows = conn.execute(
            select(schema.personal_calendar_approval_state).where(
                schema.personal_calendar_approval_state.c.approval_id
                == approval.approval_id
            )
        ).mappings().all()
    assert [(row["revision"], row["status"]) for row in permission_rows] == [
        (1, "ACTIVE"), (2, "REVOKED")
    ]
    assert [(row["revision"], row["status"]) for row in approval_rows] == [
        (1, "ACTIVE"), (2, "REVOKED")
    ]
