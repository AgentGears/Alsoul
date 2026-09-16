from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.adapters.json_personal_calendar_mutation import (
    CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
    CalendarMutationHttpResponse,
    JsonPersonalCalendarMutationAdapter,
)
from alsoul.domain.personal_calendar_action import CALENDAR_EVENT_CREATE
from alsoul.domain.personal_calendar_transport import PersonalCalendarCreateMutationRequest
from alsoul.storage import schema

import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_mutation_transport as transport_cases


class _SecretResolver:
    def __init__(self, secret: str = "ephemeral-calendar-token") -> None:
        self.secret = secret
        self.calls: list[str] = []

    def resolve_secret(self, secret_ref: str) -> str:
        self.calls.append(secret_ref)
        return self.secret


class _WireTransport:
    def __init__(self, now, *, mode: str = "success") -> None:
        self.now = now
        self.mode = mode
        self.calls: list[dict[str, object]] = []

    def post_create(
        self,
        endpoint: str,
        *,
        body: dict[str, object],
        authorization_token: str,
        timeout_seconds: float,
    ) -> CalendarMutationHttpResponse:
        self.calls.append(
            {
                "endpoint": endpoint,
                "body": dict(body),
                "authorization_token": authorization_token,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.mode == "timeout":
            raise TimeoutError("wire outcome unavailable")

        payload: dict[str, object] = {
            "schema_version": CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
            "operation": CALENDAR_EVENT_CREATE,
            "status": "CREATED",
            "correlation_key": body["correlation_key"],
            "effect_ref": "provider-event:created-wire-1",
            "system_ref": "calendar.test",
            "resource_ref": body["resource_ref"],
            "summary": body["summary"],
            "start_at": body["start_at"],
            "end_at": body["end_at"],
            "receipt_ref": "provider-receipt:wire-1",
            "observed_at": self.now.isoformat(),
        }
        if self.mode == "extra-response-field":
            payload["raw_provider_blob"] = "must-not-cross-normalization"

        resolved = endpoint
        if self.mode == "cross-origin":
            resolved = "https://unexpected.example/v1/calendar/create"
        return CalendarMutationHttpResponse(
            status_code=200,
            resolved_endpoint=resolved,
            content=json.dumps(payload),
        )


def _adapter(now, *, mode: str = "success"):
    resolver = _SecretResolver()
    wire = _WireTransport(now, mode=mode)
    adapter = JsonPersonalCalendarMutationAdapter(
        endpoint="https://calendar.connector.test/v1/calendar/create",
        adapter_binding_ref="calendar-create:test-adapter",
        adapter_contract_version="calendar-create.adapter.v1",
        capability_contract_version=action_cases._CREATE_CAPABILITY_VERSION,
        external_system_ref="calendar.test",
        secret_resolver=resolver,
        timeout_seconds=7.5,
        transport=wire,
    )
    return adapter, resolver, wire


def _request(now):
    return PersonalCalendarCreateMutationRequest(
        execution_attempt_id=uuid4(),
        action_id=uuid4(),
        external_system_ref="calendar.test",
        external_resource_ref="primary",
        summary="Wire boundary review",
        normalized_start_at=now,
        normalized_end_at=now + timedelta(hours=1),
        correlation_key="calendar-create:wire-correlation",
        credential_secret_ref="secret-ref:calendar-write",
        capability_contract_version=action_cases._CREATE_CAPABILITY_VERSION,
        adapter_contract_version="calendar-create.adapter.v1",
    )


def test_concrete_mutation_adapter_sends_only_allowlisted_wire_fields(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    adapter, resolver, wire = _adapter(now)
    service = transport_cases._service(engine, now, adapter)

    result = transport_cases._dispatch(service, lineage["attempt"])

    assert result.status == "MATCHED_EFFECT_EVIDENCE"
    assert len(wire.calls) == 1
    assert resolver.calls == ["secret-ref:calendar-write"]
    call = wire.calls[0]
    body = call["body"]
    assert body == {
        "schema_version": CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
        "operation": CALENDAR_EVENT_CREATE,
        "resource_ref": "primary",
        "summary": lineage["action"].summary,
        "start_at": lineage["action"].normalized_start_at.isoformat(),
        "end_at": lineage["action"].normalized_end_at.isoformat(),
        "correlation_key": lineage["attempt"].correlation_key,
    }
    assert call["authorization_token"] == "ephemeral-calendar-token"
    assert call["timeout_seconds"] == 7.5
    serialized = json.dumps(body, sort_keys=True)
    for forbidden in (
        str(lineage["attempt"].execution_attempt_id),
        str(lineage["action"].action_id),
        "secret-ref:calendar-write",
        "ephemeral-calendar-token",
        "calendar-create.adapter.v1",
        action_cases._CREATE_CAPABILITY_VERSION,
    ):
        assert forbidden not in serialized

    with engine.connect() as conn:
        dispatch = conn.execute(
            select(schema.personal_calendar_create_mutation_dispatch).where(
                schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).mappings().one()
        evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == result.effect_evidence_id
            )
        ).mappings().one()
    assert set(dispatch) == {
        "execution_attempt_id",
        "action_id",
        "request_contract_version",
        "started_at",
    }
    durable = json.dumps(
        {**dict(dispatch), **dict(evidence)},
        default=str,
        sort_keys=True,
    )
    assert "ephemeral-calendar-token" not in durable
    assert "secret-ref:calendar-write" not in durable


def test_concrete_mutation_adapter_has_no_internal_retry_on_unknown_wire_outcome(now):
    adapter, resolver, wire = _adapter(now, mode="timeout")

    with pytest.raises(AdapterOutcomeUnknown):
        adapter.create_event(_request(now))

    assert resolver.calls == ["secret-ref:calendar-write"]
    assert len(wire.calls) == 1


def test_concrete_mutation_adapter_rejects_non_minimized_response_before_domain_crossing(now):
    adapter, _, wire = _adapter(now, mode="extra-response-field")

    with pytest.raises(AdapterRejected):
        adapter.create_event(_request(now))

    assert len(wire.calls) == 1


def test_concrete_mutation_adapter_rejects_cross_origin_resolution(now):
    adapter, _, wire = _adapter(now, mode="cross-origin")

    with pytest.raises(AdapterRejected):
        adapter.create_event(_request(now))

    assert len(wire.calls) == 1
