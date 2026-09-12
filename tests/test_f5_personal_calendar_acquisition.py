from __future__ import annotations

from dataclasses import fields, replace
from datetime import date, datetime, timedelta
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
    GrantCalendarReadPermissionCommand,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    SetCalendarReadPolicyCommand,
    SetPermissionStatusCommand,
)
from alsoul.domain.personal_calendar_acquisition import (
    AcquirePersonalCalendarObservationCommand,
    CalendarReadCapabilityContract,
    NormalizedCalendarEvent,
    PersonalCalendarReadPage,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.services.personal_calendar import (
    CALENDAR_READ_PERMISSION_GRANT_TEXT,
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
)
from alsoul.services.personal_calendar_acquisition import PersonalCalendarAcquisitionServices
from alsoul.storage import schema

_RULES_VERSION = "test-tzdb-v1"
_CAPABILITY_VERSION = "calendar.events.read.v1"
_GRANT_POLICY_VERSION = "first-party-grant-v1"
_PROVIDER_SCOPE = "calendar.read"


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _append_counterpart_event(foundation, ids, now, content_text: str):
    return foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=content_text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )


def _bootstrap_calendar(engine, now):
    ids = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).bootstrap(
        identity_namespace="f5-calendar-acquisition-test",
        external_subject=str(uuid4()),
    )
    foundation = FoundationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    external_system_ref = f"calendar.test.{uuid4()}"
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
            external_system_ref=external_system_ref,
            external_resource_ref="primary",
            calendar_timezone="UTC",
            timezone_rules_version=_RULES_VERSION,
        )
    )
    credential = calendar.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref=external_system_ref,
            external_principal_ref="counterpart-account",
            secret_ref="secret://calendar/test",
            provider_scopes=(_PROVIDER_SCOPE,),
        )
    )
    grant_event = _append_counterpart_event(
        foundation,
        ids,
        now,
        CALENDAR_READ_PERMISSION_GRANT_TEXT,
    )
    permission = calendar.grant_read_permission(
        GrantCalendarReadPermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            capability_contract_version=_CAPABILITY_VERSION,
            grant_policy_version=_GRANT_POLICY_VERSION,
            source_interaction_event_id=grant_event.event_id,
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
    source_event = _append_counterpart_event(
        foundation,
        ids,
        now,
        "What's on my calendar on 2026-09-12?",
    )
    investigation = foundation.start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            objective="Acquire one bounded coherent personal calendar schedule.",
            conversation_id="f5-calendar-acquisition-test",
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
        )
    )
    return {
        "ids": ids,
        "foundation": foundation,
        "calendar": calendar,
        "resource": resource,
        "credential": credential,
        "permission": permission,
        "source_event": source_event,
        "investigation": investigation,
        "observation": observation,
        "prepared": prepared,
    }


def _contract() -> CalendarReadCapabilityContract:
    return CalendarReadCapabilityContract(
        contract_version=_CAPABILITY_VERSION,
        pagination_contract_version="calendar.cursor.v1",
        snapshot_contract_version="calendar.snapshot.v1",
        normalization_schema_version="calendar.normalized-event.v1",
        field_minimization_contract_version="calendar.minimized-event.v1",
        freshness_policy_version="calendar-freshness-v1",
        max_pages=4,
        max_events=20,
        max_events_per_page=10,
    )


class _FakeCalendarAdapter:
    adapter_binding_ref = "calendar.test/read"
    adapter_version = "calendar-test-adapter-v1"

    def __init__(self, pages, *, after_read=None):
        self.pages = list(pages)
        self.requests = []
        self.after_read = after_read

    def read_page(self, request):
        self.requests.append(request)
        if not self.pages:
            raise AssertionError("adapter received more page requests than configured")
        page = self.pages.pop(0)
        if self.after_read is not None:
            self.after_read(len(self.requests), request, page)
        return page


def _acquisition(engine, adapter, *, contract=None, clock=None):
    return PersonalCalendarAcquisitionServices(
        engine,
        capability_contract=contract or _contract(),
        adapter=adapter,
        time_resolver=ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION),
        clock=clock,
        ids=UUIDGenerator(),
    )


def _command(ctx):
    return AcquirePersonalCalendarObservationCommand(
        operation_id=uuid4(),
        observation_id=ctx["observation"].observation_id,
        permission_id=ctx["permission"].permission_id,
        credential_binding_id=ctx["credential"].credential_binding_id,
    )


def test_coherent_two_page_acquisition_admits_only_minimized_schedule_truth(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    snapshot_as_of = now + timedelta(minutes=2)
    page1 = PersonalCalendarReadPage(
        events=(
            NormalizedCalendarEvent(
                occurrence_ref="ends-at-start",
                title="Previous day",
                start_at=window.window_start - timedelta(hours=1),
                end_at=window.window_start,
                all_day=False,
            ),
            NormalizedCalendarEvent(
                occurrence_ref="meeting-1",
                title="Project review",
                start_at=window.window_start + timedelta(hours=9),
                end_at=window.window_start + timedelta(hours=10),
                all_day=False,
            ),
            NormalizedCalendarEvent(
                occurrence_ref="cancelled-1",
                title="Cancelled",
                start_at=window.window_start + timedelta(hours=11),
                end_at=window.window_start + timedelta(hours=12),
                all_day=False,
                occurrence_status="CANCELLED",
            ),
        ),
        snapshot_ref="snapshot-1",
        snapshot_as_of=snapshot_as_of,
        next_page_token="cursor-2",
        terminal=False,
    )
    page2 = PersonalCalendarReadPage(
        events=(
            NormalizedCalendarEvent(
                occurrence_ref="all-day-1",
                title="All day",
                start_at=window.window_start,
                end_at=window.window_end,
                all_day=True,
                all_day_start_date=date(2026, 9, 12),
                all_day_end_date_exclusive=date(2026, 9, 13),
            ),
            NormalizedCalendarEvent(
                occurrence_ref="starts-at-end",
                title="Next day",
                start_at=window.window_end,
                end_at=window.window_end + timedelta(hours=1),
                all_day=False,
            ),
        ),
        snapshot_ref="snapshot-1",
        snapshot_as_of=snapshot_as_of,
        next_page_token=None,
        terminal=True,
    )
    adapter = _FakeCalendarAdapter([page1, page2])
    command = _command(ctx)
    acquisition = _acquisition(engine, adapter, clock=FixedClock(now + timedelta(minutes=8)))
    result = acquisition.acquire(command)
    replay = acquisition.acquire(command)

    assert replay == result
    assert result.page_count == 2
    assert result.event_count == 2
    assert result.snapshot_ref == "snapshot-1"
    assert result.freshness_anchor_at == snapshot_as_of
    assert result.freshness_anchor_basis == "PROVIDER_SNAPSHOT_AS_OF"
    assert len(adapter.requests) == 2
    assert adapter.requests[0].page_token is None
    assert adapter.requests[1].page_token == "cursor-2"
    assert adapter.requests[1].expected_snapshot_ref == "snapshot-1"
    assert adapter.requests[0].window_start == adapter.requests[1].window_start == window.window_start
    assert adapter.requests[0].window_end == adapter.requests[1].window_end == window.window_end
    assert adapter.requests[0].external_resource_ref == adapter.requests[1].external_resource_ref == "primary"

    with engine.connect() as conn:
        fences = conn.execute(
            select(schema.personal_calendar_read_authority_fence).where(
                schema.personal_calendar_read_authority_fence.c.observation_id
                == ctx["observation"].observation_id
            )
        ).mappings().all()
        pages = conn.execute(
            select(schema.personal_calendar_acquisition_page).where(
                schema.personal_calendar_acquisition_page.c.acquisition_attempt_id
                == select(schema.personal_calendar_source_capture.c.acquisition_attempt_id)
                .where(
                    schema.personal_calendar_source_capture.c.source_capture_id
                    == result.source_capture_id
                )
                .scalar_subquery()
            )
        ).mappings().all()
        capture = conn.execute(
            select(schema.personal_calendar_source_capture).where(
                schema.personal_calendar_source_capture.c.source_capture_id
                == result.source_capture_id
            )
        ).mappings().one()
        generic_capture = conn.execute(
            select(schema.world_source_capture).where(
                schema.world_source_capture.c.source_capture_id == result.source_capture_id
            )
        ).mappings().one()
        blob = conn.execute(
            select(schema.content_blob).where(
                schema.content_blob.c.content_digest == generic_capture["content_digest"]
            )
        ).mappings().one()
        world_result = conn.execute(
            select(schema.world_result).where(
                schema.world_result.c.world_result_id == result.world_result_id
            )
        ).mappings().one()
        claims = conn.execute(select(schema.claim)).mappings().all()
        observations = conn.execute(
            select(schema.observation).where(
                schema.observation.c.investigation_id
                == ctx["investigation"].investigation_id
            )
        ).mappings().all()

    assert len(fences) == 2
    assert len(pages) == 2
    assert capture["freshness_anchor_basis"] == "PROVIDER_SNAPSHOT_AS_OF"
    assert capture["page_count"] == 2
    assert capture["event_count"] == 2
    assert generic_capture["capture_kind"] == "PERSONAL_CALENDAR_SCHEDULE"
    assert world_result["predicate"] == "personal_calendar.events_on_local_date"
    assert [item["occurrence_ref"] for item in world_result["value_json"]["events"]] == [
        "all-day-1",
        "meeting-1",
    ]
    assert "Project review" in blob["content_text"]
    for forbidden in (
        "description",
        "attendee",
        "organizer",
        "conference",
        "attachment",
        "reminder",
        "private_note",
        "location",
        "secret://calendar/test",
        "cursor-2",
    ):
        assert forbidden not in blob["content_text"].lower()
    assert claims == []
    assert len(observations) == 1
    assert observations[0]["status"] == "SUCCEEDED"


def test_permission_revocation_between_pages_blocks_next_transport_and_partial_admission(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    page1 = PersonalCalendarReadPage(
        events=(
            NormalizedCalendarEvent(
                occurrence_ref="meeting-1",
                title="First page",
                start_at=window.window_start + timedelta(hours=9),
                end_at=window.window_start + timedelta(hours=10),
                all_day=False,
            ),
        ),
        snapshot_ref="snapshot-1",
        snapshot_as_of=now,
        next_page_token="cursor-2",
        terminal=False,
    )
    page2 = PersonalCalendarReadPage(
        events=(),
        snapshot_ref="snapshot-1",
        snapshot_as_of=now,
        next_page_token=None,
        terminal=True,
    )

    def revoke_after_first_page(read_count, _request, _page):
        if read_count == 1:
            ctx["calendar"].set_permission_status(
                SetPermissionStatusCommand(
                    operation_id=uuid4(),
                    permission_id=ctx["permission"].permission_id,
                )
            )

    adapter = _FakeCalendarAdapter([page1, page2], after_read=revoke_after_first_page)
    with pytest.raises(DomainError) as revoked:
        _acquisition(engine, adapter, clock=FixedClock(now)).acquire(_command(ctx))
    _assert_code(revoked, "CALENDAR_READ_PERMISSION_REVOKED")
    assert len(adapter.requests) == 1

    with engine.connect() as conn:
        captures = conn.execute(
            select(schema.world_source_capture).where(
                schema.world_source_capture.c.observation_id
                == ctx["observation"].observation_id
            )
        ).mappings().all()
        results = conn.execute(
            select(schema.personal_calendar_world_result).where(
                schema.personal_calendar_world_result.c.observation_id
                == ctx["observation"].observation_id
            )
        ).mappings().all()
        observation = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == ctx["observation"].observation_id
            )
        ).mappings().one()
        attempt = conn.execute(
            select(schema.personal_calendar_acquisition_attempt).where(
                schema.personal_calendar_acquisition_attempt.c.observation_id
                == ctx["observation"].observation_id
            )
        ).mappings().one()
    assert captures == []
    assert results == []
    assert observation["status"] == "FAILED"
    assert attempt["status"] == "FAILED"


def test_snapshot_change_fails_closed_without_world_result(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    adapter = _FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(),
                snapshot_ref="snapshot-1",
                snapshot_as_of=now,
                next_page_token="cursor-2",
                terminal=False,
            ),
            PersonalCalendarReadPage(
                events=(),
                snapshot_ref="snapshot-2",
                snapshot_as_of=now,
                next_page_token=None,
                terminal=True,
            ),
        ]
    )
    with pytest.raises(DomainError) as changed:
        _acquisition(engine, adapter, clock=FixedClock(now)).acquire(_command(ctx))
    _assert_code(changed, "CALENDAR_SNAPSHOT_CHANGED_DURING_PAGINATION")
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.world_source_capture.c.source_capture_id).where(
                schema.world_source_capture.c.observation_id
                == ctx["observation"].observation_id
            )
        ).scalar_one_or_none() is None


def test_pagination_cycle_and_provider_cap_fail_closed(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    cyclic = _FakeCalendarAdapter(
        [
            PersonalCalendarReadPage((), "snapshot-1", now, "cursor-2", False),
            PersonalCalendarReadPage((), "snapshot-1", now, "cursor-2", False),
        ]
    )
    with pytest.raises(DomainError) as cycle:
        _acquisition(engine, cyclic, clock=FixedClock(now)).acquire(_command(ctx))
    _assert_code(cycle, "CALENDAR_PAGINATION_TOKEN_CYCLE")

    ctx2 = _bootstrap_calendar(engine, now + timedelta(seconds=1))
    capped = _FakeCalendarAdapter(
        [PersonalCalendarReadPage((), "snapshot-1", now, None, True, result_cap_hit=True)]
    )
    with pytest.raises(DomainError) as cap:
        _acquisition(engine, capped, clock=FixedClock(now)).acquire(_command(ctx2))
    _assert_code(cap, "CALENDAR_PROVIDER_RESULT_CAP_REACHED")


def test_duplicate_occurrence_and_untrusted_snapshot_time_fail_closed(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    repeated = NormalizedCalendarEvent(
        occurrence_ref="same-occurrence",
        title="One occurrence",
        start_at=window.window_start + timedelta(hours=9),
        end_at=window.window_start + timedelta(hours=10),
        all_day=False,
    )
    duplicate = _FakeCalendarAdapter(
        [
            PersonalCalendarReadPage((repeated,), "snapshot-1", now, "cursor-2", False),
            PersonalCalendarReadPage((repeated,), "snapshot-1", now, None, True),
        ]
    )
    with pytest.raises(DomainError) as dup:
        _acquisition(engine, duplicate, clock=FixedClock(now)).acquire(_command(ctx))
    _assert_code(dup, "CALENDAR_OCCURRENCE_DUPLICATED")

    ctx2 = _bootstrap_calendar(engine, now + timedelta(seconds=1))
    naive = _FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                (),
                "snapshot-1",
                datetime(2026, 9, 6, 12, 0),
                None,
                True,
            )
        ]
    )
    with pytest.raises(DomainError) as untrusted:
        _acquisition(engine, naive, clock=FixedClock(now)).acquire(_command(ctx2))
    _assert_code(untrusted, "CALENDAR_SNAPSHOT_TIME_UNTRUSTED")


def test_all_day_normalization_and_adapter_qualification_fail_before_canonical_capture(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    wrong_all_day = _FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                (
                    NormalizedCalendarEvent(
                        occurrence_ref="all-day-wrong",
                        title="All day",
                        start_at=window.window_start + timedelta(hours=1),
                        end_at=window.window_end,
                        all_day=True,
                        all_day_start_date=date(2026, 9, 12),
                        all_day_end_date_exclusive=date(2026, 9, 13),
                    ),
                ),
                "snapshot-1",
                now,
                None,
                True,
            )
        ]
    )
    with pytest.raises(DomainError) as mismatch:
        _acquisition(engine, wrong_all_day, clock=FixedClock(now)).acquire(_command(ctx))
    _assert_code(mismatch, "CALENDAR_ALL_DAY_TIME_MISMATCH")

    ctx2 = _bootstrap_calendar(engine, now + timedelta(seconds=1))
    adapter = _FakeCalendarAdapter([])
    untrusted_contract = replace(
        _contract(), raw_response_minimization_mode="RAW_PERSISTED"
    )
    with pytest.raises(DomainError) as untrusted:
        _acquisition(
            engine,
            adapter,
            contract=untrusted_contract,
            clock=FixedClock(now),
        ).acquire(_command(ctx2))
    _assert_code(untrusted, "CALENDAR_MINIMIZATION_CONTRACT_UNTRUSTED")
    assert adapter.requests == []


def test_freshness_falls_back_to_acquisition_start_not_capture_commit(engine, now):
    ctx = _bootstrap_calendar(engine, now)
    later = now + timedelta(hours=3)
    adapter = _FakeCalendarAdapter(
        [PersonalCalendarReadPage((), "snapshot-1", None, None, True)]
    )
    result = _acquisition(engine, adapter, clock=FixedClock(later)).acquire(_command(ctx))
    assert result.freshness_anchor_basis == "ACQUISITION_STARTED_AT"
    assert result.freshness_anchor_at == now
    assert result.freshness_anchor_at != later


def test_normalized_adapter_contract_has_no_disallowed_personal_fields():
    names = {field.name for field in fields(NormalizedCalendarEvent)}
    for forbidden in {
        "description",
        "body",
        "attendees",
        "organizer",
        "conference",
        "attachments",
        "reminders",
        "private_notes",
        "location",
    }:
        assert forbidden not in names
