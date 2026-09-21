from __future__ import annotations

import json
from datetime import timedelta
from urllib.request import HTTPRedirectHandler
from uuid import uuid4

import pytest
from sqlalchemy import select

import alsoul.adapters.json_personal_calendar_mutation as mutation_wire
from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.adapters.json_personal_calendar_mutation import (
    CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
    CalendarMutationHttpResponse,
    JsonPersonalCalendarMutationAdapter,
    UrllibCalendarMutationTransport,
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
        if self.mode == "sensitive-exception":
            raise RuntimeError(
                f"secret={authorization_token}; body={json.dumps(body, sort_keys=True)}"
            )
        if self.mode == "invalid-json":
            return CalendarMutationHttpResponse(
                status_code=200,
                resolved_endpoint=endpoint,
                content=(
                    "raw-response secret=provider-private-value "
                    "correlation=calendar-create:wire-correlation"
                ),
            )

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


class _Headers:
    def get_content_charset(self):
        return "utf-8"


class _BufferedHttpResponse:
    def __init__(self, endpoint: str, content: bytes, *, status: int = 200) -> None:
        self.endpoint = endpoint
        self.content = content
        self.status = status
        self.headers = _Headers()
        self.read_sizes: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self.content[:size]

    def geturl(self) -> str:
        return self.endpoint


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


def test_urllib_mutation_transport_uses_one_fixed_no_redirect_request(monkeypatch):
    endpoint = "https://calendar.connector.test/v1/calendar/create"
    response = _BufferedHttpResponse(endpoint, b'{"accepted":true}', status=201)
    calls: dict[str, object] = {"open_count": 0}

    class _Opener:
        def open(self, request, *, timeout):
            calls["open_count"] = int(calls["open_count"]) + 1
            calls["request"] = request
            calls["timeout"] = timeout
            return response

    def fake_build_opener(*handlers):
        calls["handlers"] = handlers
        return _Opener()

    monkeypatch.setattr(mutation_wire, "build_opener", fake_build_opener)
    transport = UrllibCalendarMutationTransport(
        max_response_bytes=128,
        user_agent="Alsoul-F5-test/1",
    )
    body = {
        "schema_version": CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
        "operation": CALENDAR_EVENT_CREATE,
        "resource_ref": "primary",
        "summary": "Wire boundary review",
        "start_at": "2026-09-06T12:00:00+00:00",
        "end_at": "2026-09-06T13:00:00+00:00",
        "correlation_key": "calendar-create:wire-correlation",
    }

    result = transport.post_create(
        endpoint,
        body=body,
        authorization_token="ephemeral-calendar-token",
        timeout_seconds=7.5,
    )

    assert result == CalendarMutationHttpResponse(
        status_code=201,
        resolved_endpoint=endpoint,
        content='{"accepted":true}',
    )
    assert calls["open_count"] == 1
    assert calls["timeout"] == 7.5
    request = calls["request"]
    assert request.get_method() == "POST"
    assert request.full_url == endpoint
    assert request.data == json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert {key.lower(): value for key, value in request.header_items()} == {
        "accept": "application/json",
        "authorization": "Bearer ephemeral-calendar-token",
        "content-type": "application/json",
        "user-agent": "Alsoul-F5-test/1",
    }
    handlers = calls["handlers"]
    assert len(handlers) == 1
    assert isinstance(handlers[0], HTTPRedirectHandler)
    assert (
        handlers[0].redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "https://unexpected.example/redirect",
        )
        is None
    )
    assert response.read_sizes == [129]


def test_urllib_mutation_transport_rejects_oversized_response_without_body_diagnostic(
    monkeypatch,
):
    endpoint = "https://calendar.connector.test/v1/calendar/create"
    sensitive = b"provider-private-response-body"
    response = _BufferedHttpResponse(endpoint, sensitive)

    class _Opener:
        def open(self, request, *, timeout):
            return response

    monkeypatch.setattr(mutation_wire, "build_opener", lambda *handlers: _Opener())
    transport = UrllibCalendarMutationTransport(max_response_bytes=8)

    with pytest.raises(AdapterRejected) as rejected:
        transport.post_create(
            endpoint,
            body={"schema_version": CALENDAR_MUTATION_WIRE_SCHEMA_VERSION},
            authorization_token="ephemeral-calendar-token",
            timeout_seconds=7.5,
        )

    assert sensitive.decode("utf-8") not in str(rejected.value)
    assert response.read_sizes == [9]


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


def test_transport_exception_diagnostics_are_sanitized_without_sensitive_context(now):
    adapter, _, wire = _adapter(now, mode="sensitive-exception")

    with pytest.raises(AdapterOutcomeUnknown) as unknown:
        adapter.create_event(_request(now))

    assert len(wire.calls) == 1
    assert unknown.value.__cause__ is None
    assert unknown.value.__context__ is None
    diagnostic = str(unknown.value)
    for forbidden in (
        "ephemeral-calendar-token",
        "Wire boundary review",
        "calendar-create:wire-correlation",
        "primary",
    ):
        assert forbidden not in diagnostic


def test_invalid_raw_provider_response_is_not_retained_as_exception_context(now):
    adapter, _, wire = _adapter(now, mode="invalid-json")

    with pytest.raises(AdapterRejected) as invalid:
        adapter.create_event(_request(now))

    assert len(wire.calls) == 1
    assert invalid.value.__cause__ is None
    assert invalid.value.__context__ is None
    diagnostic = str(invalid.value)
    assert "provider-private-value" not in diagnostic
    assert "calendar-create:wire-correlation" not in diagnostic


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
