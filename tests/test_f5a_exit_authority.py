from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

import test_f5_personal_calendar_authority as authority_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    SetCredentialBindingStatusCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationServices
from alsoul.services.personal_calendar import (
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
    all_day_event_interval,
    timed_event_overlaps_day,
)
from alsoul.storage import schema


def _code(exc: pytest.ExceptionInfo[DomainError]) -> str:
    return exc.value.code


def test_exit_identity_survives_credential_rebind_and_service_recomposition(engine, now):
    (
        ids,
        _foundation,
        calendar,
        observation,
        resource,
        credential,
        permission,
        _prepared,
        _source_event,
        _grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)

    calendar.set_credential_status(
        SetCredentialBindingStatusCommand(
            operation_id=uuid4(),
            credential_binding_id=credential.credential_binding_id,
        )
    )
    rebound = calendar.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-account-rebound",
            secret_ref="secret://calendar/rebound",
            provider_scopes=(authority_cases._PROVIDER_SCOPE,),
        )
    )

    FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())
    recomposed = PersonalCalendarReadServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    fence = recomposed.fence_read_page(
        authority_cases.FencePersonalCalendarReadPageCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            page_ordinal=0,
            permission_id=permission.permission_id,
            credential_binding_id=rebound.credential_binding_id,
        )
    )

    assert fence.personal_resource_binding_id == resource.personal_resource_binding_id
    assert fence.relationship_authority_revision == 1
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.companion_person)
        ).scalar_one() == 1
        assert conn.execute(
            select(func.count()).select_from(schema.counterpart_person)
        ).scalar_one() == 1
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()
        assert relationship["companion_person_id"] == ids.companion_person_id
        assert relationship["counterpart_id"] == ids.counterpart_id
        assert conn.execute(
            select(func.count()).select_from(schema.credential_binding)
        ).scalar_one() == 2


def test_exit_permission_missing_expired_or_forged_grantor_blocks_dispatch(engine, now):
    (
        _ids,
        _foundation,
        calendar,
        observation,
        _resource,
        credential,
        permission,
        _prepared,
        _source_event,
        _grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)

    with pytest.raises(DomainError) as missing:
        calendar.fence_read_page(
            authority_cases.FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=uuid4(),
                credential_binding_id=credential.credential_binding_id,
            )
        )
    assert _code(missing) == "CALENDAR_READ_PERMISSION_MISSING"

    with engine.begin() as conn:
        conn.execute(
            update(schema.permission_grant)
            .where(schema.permission_grant.c.permission_id == permission.permission_id)
            .values(expires_at=now)
        )
    with pytest.raises(DomainError) as expired:
        calendar.fence_read_page(
            authority_cases.FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=permission.permission_id,
                credential_binding_id=credential.credential_binding_id,
            )
        )
    assert _code(expired) == "CALENDAR_READ_PERMISSION_EXPIRED"

    with engine.begin() as conn:
        conn.execute(
            update(schema.permission_grant)
            .where(schema.permission_grant.c.permission_id == permission.permission_id)
            .values(expires_at=None, grantor_ref="counterpart-account")
        )
    with pytest.raises(DomainError) as forged:
        calendar.fence_read_page(
            authority_cases.FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=permission.permission_id,
                credential_binding_id=credential.credential_binding_id,
            )
        )
    assert _code(forged) == "CALENDAR_READ_PERMISSION_MISMATCH"

    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_read_authority_fence
            )
        ).scalar_one() == 0


def test_exit_time_boundaries_fail_closed_and_overlap_is_half_open():
    resolver = ZoneInfoCalendarTimeResolver(rules_version="exit-audit-tzdb-v1")

    with pytest.raises(DomainError) as nonexistent:
        resolver.resolve_midnight(
            zone_name="Pacific/Apia",
            local_date=date(2011, 12, 30),
        )
    assert _code(nonexistent) == "CALENDAR_TIME_BOUNDARY_NONEXISTENT"

    with pytest.raises(DomainError) as ambiguous:
        resolver.resolve_midnight(
            zone_name="America/Havana",
            local_date=date(2006, 10, 29),
        )
    assert _code(ambiguous) == "CALENDAR_TIME_BOUNDARY_AMBIGUOUS"

    with pytest.raises(DomainError) as all_day_nonexistent:
        all_day_event_interval(
            resolver=resolver,
            zone_name="Pacific/Apia",
            start_date=date(2011, 12, 30),
            end_date_exclusive=date(2011, 12, 31),
        )
    assert _code(all_day_nonexistent) == "CALENDAR_TIME_BOUNDARY_NONEXISTENT"

    window = resolver.resolve_day(zone_name="UTC", local_date=date(2026, 9, 12))
    assert timed_event_overlaps_day(
        window=window,
        event_start=window.window_start - timedelta(days=1),
        event_end=window.window_end + timedelta(days=1),
    )
    assert not timed_event_overlaps_day(
        window=window,
        event_start=window.window_end,
        event_end=window.window_end + timedelta(minutes=1),
    )
    assert not timed_event_overlaps_day(
        window=window,
        event_start=window.window_start - timedelta(minutes=1),
        event_end=window.window_start,
    )
