from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    GrantCalendarReadPermissionCommand,
    RegisterPersonalCalendarResourceCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.services.personal_calendar import (
    CALENDAR_READ_PERMISSION_GRANT_TEXT,
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
)
from alsoul.storage import schema

_RULES_VERSION = "test-tzdb-v1"
_CAPABILITY_VERSION = "calendar.events.read.v1"
_GRANT_POLICY_VERSION = "first-party-grant-v1"


def _append_grant_event(foundation, ids, now):
    return foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=CALENDAR_READ_PERMISSION_GRANT_TEXT,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )


def test_calendar_permission_grant_must_follow_selected_resource_activation(engine, now):
    ids = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).bootstrap(
        identity_namespace="f5-grant-frontier",
        external_subject=str(uuid4()),
    )
    foundation = FoundationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    calendar = PersonalCalendarReadServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    stale_grant = _append_grant_event(foundation, ids, now)
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

    with pytest.raises(DomainError) as stale:
        calendar.grant_read_permission(
            GrantCalendarReadPermissionCommand(
                operation_id=uuid4(),
                holder_companion_person_id=ids.companion_person_id,
                counterpart_id=ids.counterpart_id,
                relationship_id=ids.relationship_id,
                personal_resource_binding_id=resource.personal_resource_binding_id,
                capability_contract_version=_CAPABILITY_VERSION,
                grant_policy_version=_GRANT_POLICY_VERSION,
                source_interaction_event_id=stale_grant.event_id,
            )
        )
    assert stale.value.code == "PERMISSION_PROVENANCE_INVALID"

    fresh_grant = _append_grant_event(foundation, ids, now)
    permission = calendar.grant_read_permission(
        GrantCalendarReadPermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            capability_contract_version=_CAPABILITY_VERSION,
            grant_policy_version=_GRANT_POLICY_VERSION,
            source_interaction_event_id=fresh_grant.event_id,
        )
    )

    with engine.connect() as conn:
        registration = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope
                == "RegisterPersonalCalendarResource",
                schema.operation_receipt.c.result_ref
                == resource.personal_resource_binding_id,
            )
        ).mappings().one()
        grant_row = conn.execute(
            select(schema.permission_grant).where(
                schema.permission_grant.c.permission_id == permission.permission_id
            )
        ).mappings().one()

    frontier = int(registration["result_json"]["activation_timeline_frontier"])
    assert stale_grant.timeline_seq <= frontier
    assert fresh_grant.timeline_seq > frontier
    assert grant_row["constraints_json"]["resource_activation_timeline_frontier"] == frontier
