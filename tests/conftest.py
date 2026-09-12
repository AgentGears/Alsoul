from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from sqlalchemy import Engine

from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
)
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
def _qualified_f5_calendar_test_adapters(monkeypatch):
    """Mark trusted local F5.A fakes with their explicit executable contracts."""

    for module_name, class_name in (
        ("test_f5_personal_calendar_acquisition", "_FakeCalendarAdapter"),
        ("test_f5_personal_calendar_cognition", "_CalendarAdapter"),
        ("test_f5_personal_calendar_generic_guards", "_CalendarAdapter"),
        ("test_f5_personal_calendar_presentation", "_CalendarAdapter"),
    ):
        module = sys.modules.get(module_name)
        adapter_class = getattr(module, class_name, None) if module is not None else None
        if adapter_class is not None:
            monkeypatch.setattr(
                adapter_class,
                "capability_contract_version",
                "calendar.events.read.v1",
                raising=False,
            )

    presentation_module = sys.modules.get("test_f5_personal_calendar_presentation")
    presentation_class = (
        getattr(presentation_module, "_PresentationAdapter", None)
        if presentation_module is not None
        else None
    )
    if presentation_class is not None:
        monkeypatch.setattr(
            presentation_class,
            "terminal_negative_semantics",
            PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
            raising=False,
        )
    yield


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


@pytest.fixture(autouse=True)
def _stable_f5_presentation_test_sink(request, monkeypatch):
    """Give the local presentation fake one explicit concrete sink identity."""

    module = request.module
    if module.__name__ == "test_f5_personal_calendar_presentation":
        monkeypatch.setattr(
            module._PresentationAdapter,
            "sink_binding_ref",
            "presentation.test/primary",
            raising=False,
        )
    yield
