from __future__ import annotations

from dataclasses import replace
from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_acquisition as acquisition_cases
from alsoul.domain.commands import StartInvestigationCommand, StartObservationCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import PreparePersonalCalendarObservationCommand
from alsoul.domain.personal_calendar_acquisition import (
    NormalizedCalendarEvent,
    PersonalCalendarReadPage,
)
from alsoul.domain.personal_calendar_cognition import (
    BuildPersonalCalendarProjectionCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarCognitionServices
from alsoul.storage import schema


def _code(exc: pytest.ExceptionInfo[DomainError]) -> str:
    return exc.value.code


def test_exit_moved_recurrence_exception_and_cancellation_are_normalized(engine, now):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    moved = NormalizedCalendarEvent(
        occurrence_ref="series-1-moved",
        title="Moved review",
        start_at=window.window_start + timedelta(hours=12),
        end_at=window.window_start + timedelta(hours=13),
        all_day=False,
        series_ref="series-1",
        exception_ref="series-1-original-slot",
    )
    cancelled_original = NormalizedCalendarEvent(
        occurrence_ref="series-1-original",
        title="Original slot",
        start_at=window.window_start + timedelta(hours=9),
        end_at=window.window_start + timedelta(hours=10),
        all_day=False,
        series_ref="series-1",
        occurrence_status="CANCELLED",
    )
    adapter = acquisition_cases._FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(cancelled_original, moved),
                snapshot_ref="snapshot-recurrence-moved",
                snapshot_as_of=now,
                next_page_token=None,
                terminal=True,
            )
        ]
    )
    result = acquisition_cases._acquisition(
        engine, adapter, clock=FixedClock(now)
    ).acquire(acquisition_cases._command(ctx))

    with engine.connect() as conn:
        value = conn.execute(
            select(schema.world_result.c.value_json).where(
                schema.world_result.c.world_result_id == result.world_result_id
            )
        ).scalar_one()
    assert [event["occurrence_ref"] for event in value["events"]] == [
        "series-1-moved"
    ]
    assert value["events"][0]["series_ref"] == "series-1"
    assert value["events"][0]["exception_ref"] == "series-1-original-slot"


def test_exit_master_only_recurrence_provider_is_rejected(engine, now):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    window = ctx["prepared"].window
    master = NormalizedCalendarEvent(
        occurrence_ref="series-master",
        title="Recurring master",
        start_at=window.window_start + timedelta(hours=9),
        end_at=window.window_start + timedelta(hours=10),
        all_day=False,
        record_kind="MASTER",  # adversarial runtime value outside the contract
    )
    adapter = acquisition_cases._FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(master,),
                snapshot_ref="snapshot-master-only",
                snapshot_as_of=now,
                next_page_token=None,
                terminal=True,
            )
        ]
    )
    with pytest.raises(DomainError) as incomplete:
        acquisition_cases._acquisition(
            engine, adapter, clock=FixedClock(now)
        ).acquire(acquisition_cases._command(ctx))
    assert _code(incomplete) == "CALENDAR_RECURRENCE_EXPANSION_INCOMPLETE"
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_world_result)
        ).scalar_one() == 0


def test_exit_failed_pagination_fresh_traversal_cannot_mix_partial_pages(engine, now):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    first = acquisition_cases._FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(),
                snapshot_ref="snapshot-old-partial",
                snapshot_as_of=now,
                next_page_token="old-cursor",
                terminal=False,
            )
        ]
    )
    one_page_contract = replace(acquisition_cases._contract(), max_pages=1)
    with pytest.raises(DomainError) as incomplete:
        acquisition_cases._acquisition(
            engine,
            first,
            contract=one_page_contract,
            clock=FixedClock(now),
        ).acquire(acquisition_cases._command(ctx))
    assert _code(incomplete) == "CALENDAR_PAGINATION_LIMIT_EXCEEDED"

    source_event = acquisition_cases._append_counterpart_event(
        ctx["foundation"],
        ctx["ids"],
        now,
        "What's on my calendar on 2026-09-12?",
    )
    investigation = ctx["foundation"].start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ctx["ids"].companion_person_id,
            relationship_id=ctx["ids"].relationship_id,
            objective="Restart one bounded calendar traversal after fail-closed pagination.",
            conversation_id="f5a-exit-audit",
        )
    )
    observation = ctx["foundation"].start_observation(
        StartObservationCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            acquisition_kind="PERSONAL_CALENDAR_READ",
            request_descriptor={"purpose": "calendar.events.read"},
        )
    )
    prepared = ctx["calendar"].prepare_observation(
        PreparePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            source_interaction_event_id=source_event.event_id,
        )
    )
    fresh_ctx = dict(ctx)
    fresh_ctx.update(
        {
            "source_event": source_event,
            "investigation": investigation,
            "observation": observation,
            "prepared": prepared,
        }
    )
    second = acquisition_cases._FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(),
                snapshot_ref="snapshot-new-complete",
                snapshot_as_of=now,
                next_page_token=None,
                terminal=True,
            )
        ]
    )
    result = acquisition_cases._acquisition(
        engine, second, clock=FixedClock(now)
    ).acquire(acquisition_cases._command(fresh_ctx))

    with engine.connect() as conn:
        attempts = conn.execute(
            select(schema.personal_calendar_acquisition_attempt)
        ).mappings().all()
        capture = conn.execute(
            select(schema.personal_calendar_source_capture).where(
                schema.personal_calendar_source_capture.c.source_capture_id
                == result.source_capture_id
            )
        ).mappings().one()
        fresh_pages = conn.execute(
            select(schema.personal_calendar_acquisition_page).where(
                schema.personal_calendar_acquisition_page.c.acquisition_attempt_id
                == capture["acquisition_attempt_id"]
            )
        ).mappings().all()
    assert {attempt["status"] for attempt in attempts} == {"FAILED", "SUCCEEDED"}
    assert len(fresh_pages) == 1
    assert fresh_pages[0]["snapshot_ref"] == "snapshot-new-complete"
    assert capture["snapshot_ref"] == "snapshot-new-complete"


def test_exit_long_traversal_preserves_old_anchor_and_stales_before_projection(engine, now):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    adapter = acquisition_cases._FakeCalendarAdapter(
        [
            PersonalCalendarReadPage(
                events=(),
                snapshot_ref="snapshot-long-traversal",
                snapshot_as_of=now,
                next_page_token=None,
                terminal=True,
            )
        ]
    )
    later = now + timedelta(hours=2)
    result = acquisition_cases._acquisition(
        engine, adapter, clock=FixedClock(later)
    ).acquire(acquisition_cases._command(ctx))
    assert result.freshness_anchor_at == now

    cognition = PersonalCalendarCognitionServices(
        engine, adapter=None, clock=FixedClock(later), ids=UUIDGenerator()
    )
    cognition.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-freshness-exit-audit-v1",
            max_age_seconds=3600,
        )
    )
    with pytest.raises(DomainError) as stale:
        cognition.build_projection(
            BuildPersonalCalendarProjectionCommand(
                operation_id=uuid4(),
                world_result_id=result.world_result_id,
                current_input_event_id=ctx["source_event"].event_id,
            )
        )
    assert _code(stale) == "CALENDAR_RESULT_STALE"

    with engine.connect() as conn:
        capture = conn.execute(
            select(schema.personal_calendar_source_capture).where(
                schema.personal_calendar_source_capture.c.source_capture_id
                == result.source_capture_id
            )
        ).mappings().one()
    assert capture["snapshot_as_of"].replace(tzinfo=timezone.utc) == now
    assert capture["freshness_anchor_at"].replace(tzinfo=timezone.utc) == now
    assert capture["capture_committed_at"].replace(tzinfo=timezone.utc) == later
