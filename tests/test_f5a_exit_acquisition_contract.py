from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select

import test_f5_personal_calendar_acquisition as acquisition_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_acquisition import PersonalCalendarReadPage
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarAcquisitionServices
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.storage import schema


class _QualifiedNoTransportAdapter:
    adapter_binding_ref = "calendar.test/exit-contract"
    adapter_version = "calendar-exit-contract-v1"
    capability_contract_version = "calendar.events.read.v1"

    def __init__(self):
        self.requests = []

    def read_page(self, request):
        self.requests.append(request)
        raise AssertionError("contract rejection must occur before provider transport")


class _WrongCapabilityAdapter(_QualifiedNoTransportAdapter):
    capability_contract_version = "calendar.events.read.other"


def _service(engine, now, adapter, contract):
    return PersonalCalendarAcquisitionServices(
        engine,
        capability_contract=contract,
        adapter=adapter,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=acquisition_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def test_exit_calendar_adapter_must_bind_exact_capability_contract_before_transport(
    engine, now
):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    adapter = _WrongCapabilityAdapter()
    with pytest.raises(DomainError) as mismatch:
        _service(engine, now, adapter, acquisition_cases._contract()).acquire(
            acquisition_cases._command(ctx)
        )
    assert mismatch.value.code == "CALENDAR_ADAPTER_CAPABILITY_MISMATCH"
    assert adapter.requests == []


@pytest.mark.parametrize(
    "contract",
    [
        replace(
            acquisition_cases._contract(),
            query_interval_semantics="START_WITHIN_WINDOW",
        ),
        replace(
            acquisition_cases._contract(),
            history_compensation_mode="UNBOUNDED_LOOKBACK",
        ),
    ],
)
def test_exit_calendar_query_contract_requires_complete_bounded_overlap_semantics(
    engine, now, contract
):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    adapter = _QualifiedNoTransportAdapter()
    with pytest.raises(DomainError) as untrusted:
        _service(engine, now, adapter, contract).acquire(acquisition_cases._command(ctx))
    assert untrusted.value.code == "CALENDAR_QUERY_SEMANTICS_UNTRUSTED"
    assert adapter.requests == []


def test_exit_calendar_same_observation_restart_budget_is_bounded(engine, now):
    ctx = acquisition_cases._bootstrap_calendar(engine, now)
    contract = replace(acquisition_cases._contract(), max_pages=1, max_restarts=1)
    page = PersonalCalendarReadPage(
        events=(),
        snapshot_ref="snapshot-restart-bound",
        snapshot_as_of=now,
        next_page_token="cursor-never-terminal",
        terminal=False,
    )
    adapter = acquisition_cases._FakeCalendarAdapter([page, page])
    service = _service(engine, now, adapter, contract)

    with pytest.raises(DomainError) as first:
        service.acquire(acquisition_cases._command(ctx))
    assert first.value.code == "CALENDAR_PAGINATION_LIMIT_EXCEEDED"

    with engine.connect() as conn:
        observation = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == ctx["observation"].observation_id
            )
        ).mappings().one()
    assert observation["status"] == "STARTED"

    with pytest.raises(DomainError) as second:
        service.acquire(acquisition_cases._command(ctx))
    assert second.value.code == "CALENDAR_PAGINATION_LIMIT_EXCEEDED"

    with engine.connect() as conn:
        observation = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == ctx["observation"].observation_id
            )
        ).mappings().one()
        attempts = conn.execute(
            select(schema.personal_calendar_acquisition_attempt)
            .where(
                schema.personal_calendar_acquisition_attempt.c.observation_id
                == ctx["observation"].observation_id
            )
            .order_by(schema.personal_calendar_acquisition_attempt.c.generation)
        ).mappings().all()
    assert observation["status"] == "FAILED"
    assert [(row["generation"], row["status"]) for row in attempts] == [
        (1, "FAILED"),
        (2, "FAILED"),
    ]

    with pytest.raises(DomainError) as third:
        service.acquire(acquisition_cases._command(ctx))
    assert third.value.code == "CALENDAR_OBSERVATION_NOT_OPEN"
    assert len(adapter.requests) == 2
