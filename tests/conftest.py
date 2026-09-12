from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.storage import create_schema, create_sqlite_engine


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "alsoul.db"


@pytest.fixture
def engine(db_path: Path) -> Engine:
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    return engine


@pytest.fixture
def services(engine: Engine, now: datetime) -> FoundationServices:
    return FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())


@pytest.fixture
def bootstrapper(engine: Engine, now: datetime) -> FoundationBootstrapper:
    return FoundationBootstrapper(engine, clock=FixedClock(now), ids=UUIDGenerator())


@pytest.fixture(autouse=True)
def _stable_f5_calendar_identity_for_repeated_scenarios(request, monkeypatch):
    """Keep one foundation identity while a test exercises multiple acquisitions.

    The acquisition acceptance module contains a few compound tests that need a fresh
    Investigation/Observation after the first scenario has deliberately failed.  A
    second Foundation bootstrap in the same store is not a valid way to obtain that
    fresh semantic work item because first-party surface/channel bindings are durable
    identity infrastructure.  Wrap only that module's local helper so repeated calls
    reuse the already bootstrapped Person/Relationship/resource/Permission and create
    a new bounded Observation instead.
    """

    module = request.module
    if module.__name__ != "test_f5_personal_calendar_acquisition":
        yield
        return

    original_bootstrap = module._bootstrap_calendar
    persistent: dict[str, object] = {}

    def bootstrap_calendar(engine, now):
        base = persistent.get("base")
        if base is None:
            created = original_bootstrap(engine, now)
            persistent["base"] = created
            return created

        ids = base["ids"]
        foundation = FoundationServices(
            engine,
            clock=FixedClock(now),
            ids=UUIDGenerator(),
        )
        calendar = module.PersonalCalendarReadServices(
            engine,
            time_resolver=module.ZoneInfoCalendarTimeResolver(
                rules_version=module._RULES_VERSION
            ),
            clock=FixedClock(now),
            ids=UUIDGenerator(),
        )
        source_event = module._append_counterpart_event(
            foundation,
            ids,
            now,
            "What's on my calendar on 2026-09-12?",
        )
        investigation = foundation.start_investigation(
            module.StartInvestigationCommand(
                operation_id=module.uuid4(),
                initiated_by_companion_person_id=ids.companion_person_id,
                relationship_id=ids.relationship_id,
                objective="Acquire one bounded coherent personal calendar schedule.",
                conversation_id="f5-calendar-acquisition-test",
            )
        )
        observation = foundation.start_observation(
            module.StartObservationCommand(
                operation_id=module.uuid4(),
                investigation_id=investigation.investigation_id,
                acquisition_kind="PERSONAL_CALENDAR_READ",
                request_descriptor={"purpose": "calendar.events.read"},
            )
        )
        prepared = calendar.prepare_observation(
            module.PreparePersonalCalendarObservationCommand(
                operation_id=module.uuid4(),
                observation_id=observation.observation_id,
                source_interaction_event_id=source_event.event_id,
            )
        )
        return {
            "ids": ids,
            "foundation": foundation,
            "calendar": calendar,
            "resource": base["resource"],
            "credential": base["credential"],
            "permission": base["permission"],
            "source_event": source_event,
            "investigation": investigation,
            "observation": observation,
            "prepared": prepared,
        }

    monkeypatch.setattr(module, "_bootstrap_calendar", bootstrap_calendar)
    yield
