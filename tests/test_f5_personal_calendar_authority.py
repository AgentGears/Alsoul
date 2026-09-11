from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.commands import (
    AppendCounterpartInputCommand,
    StartInvestigationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    FencePersonalCalendarReadPageCommand,
    GrantCalendarReadPermissionCommand,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    SetCalendarReadPolicyCommand,
    SetPermissionStatusCommand,
    SetPersonalResourceBindingStatusCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.services.personal_calendar import (
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
    all_day_event_interval,
    parse_personal_calendar_question,
    timed_event_overlaps_day,
)
from alsoul.storage import schema

_RULES_VERSION = "test-tzdb-v1"
_CAPABILITY_VERSION = "calendar.events.read.v1"
_GRANT_POLICY_VERSION = "first-party-grant-v1"
_PROVIDER_SCOPE = "calendar.read"


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _bootstrap_calendar(engine, now):
    ids = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).bootstrap(
        identity_namespace="f5-calendar-test",
        external_subject=str(uuid4()),
    )
    foundation = FoundationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    question = "What's on my calendar on 2026-09-12?"
    source_event = foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=question,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    investigation = foundation.start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            objective="Answer one bounded personal calendar question.",
            conversation_id="f5-calendar-test",
        )
    )
    observation = foundation.start_observation(
        StartObservationCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            acquisition_kind="PERSONAL_CALENDAR_READ",
            request_descriptor={"purpose": "calendar.events.read"},
        )
    )
    calendar = PersonalCalendarReadServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    resource = calendar.register_calendar_resource(
        RegisterPersonalCalendarResourceCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            external_system_ref="calendar.test",
            external_resource_ref="primary",
            calendar_timezone="UTC",
            timezone_rules_version=_RULES_VERSION,
        )
    )
    credential = calendar.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-account",
            secret_ref="secret://calendar/test",
            provider_scopes=(_PROVIDER_SCOPE,),
        )
    )
    permission = calendar.grant_read_permission(
        GrantCalendarReadPermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            capability_contract_version=_CAPABILITY_VERSION,
            grantor_ref=ids.counterpart_id,
            grant_policy_version=_GRANT_POLICY_VERSION,
        )
    )
    calendar.set_read_policy(
        SetCalendarReadPolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CAPABILITY_VERSION,
            ai_policy_version="personal-calendar-read-v1",
            resource_scope_version="calendar-scope-v1",
            required_provider_scope=_PROVIDER_SCOPE,
            permission_grant_policy_version=_GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(resource.personal_resource_binding_id,),
        )
    )
    prepared = calendar.prepare_observation(
        PreparePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            source_interaction_event_id=source_event.event_id,
            question_text=question,
        )
    )
    return ids, foundation, calendar, observation, resource, credential, permission, prepared


def test_absolute_date_parser_and_half_open_calendar_membership():
    assert parse_personal_calendar_question("What's on my calendar on 2026-09-12?") == date(2026, 9, 12)
    assert parse_personal_calendar_question("What do I have on my calendar on 2026-09-12?") == date(2026, 9, 12)
    with pytest.raises(DomainError) as unsupported:
        parse_personal_calendar_question("What's on my calendar tomorrow?")
    _assert_code(unsupported, "PERSONAL_CALENDAR_QUESTION_UNSUPPORTED")

    resolver = ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION)
    window = resolver.resolve_day(zone_name="UTC", local_date=date(2026, 9, 12))
    assert window.window_start == datetime(2026, 9, 12, tzinfo=timezone.utc)
    assert window.window_end == datetime(2026, 9, 13, tzinfo=timezone.utc)

    assert timed_event_overlaps_day(
        window=window,
        event_start=window.window_start - timedelta(minutes=30),
        event_end=window.window_start + timedelta(minutes=30),
    )
    assert not timed_event_overlaps_day(
        window=window,
        event_start=window.window_start - timedelta(hours=1),
        event_end=window.window_start,
    )
    assert not timed_event_overlaps_day(
        window=window,
        event_start=window.window_end,
        event_end=window.window_end + timedelta(hours=1),
    )

    all_day_start, all_day_end = all_day_event_interval(
        resolver=resolver,
        zone_name="UTC",
        start_date=date(2026, 9, 12),
        end_date_exclusive=date(2026, 9, 13),
    )
    assert all_day_start == window.window_start
    assert all_day_end == window.window_end


def test_calendar_page_fence_pins_current_authority_and_revocation_blocks_later_page(engine, now):
    ids, _, calendar, observation, resource, credential, permission, prepared = _bootstrap_calendar(engine, now)

    first = calendar.fence_read_page(
        FencePersonalCalendarReadPageCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            page_ordinal=0,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )
    assert first.personal_resource_binding_id == resource.personal_resource_binding_id
    assert first.relationship_authority_revision == 1
    assert first.resource_binding_state_revision == 1
    assert first.permission_state_revision == 1
    assert first.credential_state_revision == 1
    assert first.policy_revision == 1
    assert prepared.window.local_date == date(2026, 9, 12)

    calendar.set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=permission.permission_id,
            status="REVOKED",
        )
    )
    with pytest.raises(DomainError) as revoked:
        calendar.fence_read_page(
            FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=1,
                permission_id=permission.permission_id,
                credential_binding_id=credential.credential_binding_id,
            )
        )
    _assert_code(revoked, "CALENDAR_READ_PERMISSION_REVOKED")

    with engine.connect() as conn:
        fences = conn.execute(
            select(schema.personal_calendar_read_authority_fence).where(
                schema.personal_calendar_read_authority_fence.c.observation_id == observation.observation_id
            )
        ).mappings().all()
    assert len(fences) == 1
    assert fences[0]["permission_state_revision"] == 1
    assert fences[0]["relationship_id"] == ids.relationship_id


def test_replacement_calendar_does_not_inherit_old_permission(engine, now):
    ids, foundation, calendar, _, old_resource, credential, old_permission, _ = _bootstrap_calendar(engine, now)

    calendar.set_resource_status(
        SetPersonalResourceBindingStatusCommand(
            operation_id=uuid4(),
            personal_resource_binding_id=old_resource.personal_resource_binding_id,
            status="INACTIVE",
        )
    )
    replacement = calendar.register_calendar_resource(
        RegisterPersonalCalendarResourceCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            external_system_ref="calendar.test",
            external_resource_ref="replacement",
            calendar_timezone="UTC",
            timezone_rules_version=_RULES_VERSION,
        )
    )
    calendar.set_read_policy(
        SetCalendarReadPolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CAPABILITY_VERSION,
            ai_policy_version="personal-calendar-read-v1",
            resource_scope_version="calendar-scope-v2",
            required_provider_scope=_PROVIDER_SCOPE,
            permission_grant_policy_version=_GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(replacement.personal_resource_binding_id,),
        )
    )

    question = "What do I have on my calendar on 2026-09-12?"
    source_event = foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=question,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    investigation = foundation.start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            objective="Read replacement calendar.",
        )
    )
    observation = foundation.start_observation(
        StartObservationCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            acquisition_kind="PERSONAL_CALENDAR_READ",
            request_descriptor={"purpose": "calendar.events.read"},
        )
    )
    prepared = calendar.prepare_observation(
        PreparePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            source_interaction_event_id=source_event.event_id,
            question_text=question,
        )
    )
    assert prepared.personal_resource_binding_id == replacement.personal_resource_binding_id

    with pytest.raises(DomainError) as inherited:
        calendar.fence_read_page(
            FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=old_permission.permission_id,
                credential_binding_id=credential.credential_binding_id,
            )
        )
    _assert_code(inherited, "CALENDAR_READ_PERMISSION_MISMATCH")
