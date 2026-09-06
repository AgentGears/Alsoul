from __future__ import annotations

import json

import pytest

from alsoul.host.ingress_io import IngressEnvelopeError, parse_ingress_envelope


def _payload(now):
    return {
        "identity_namespace": "first-party",
        "external_subject": "subject-1",
        "surface_namespace": "alsoul.first_party",
        "surface_ref": "primary-text-surface",
        "channel_namespace": "alsoul.first_party",
        "channel_ref": "primary-text-channel",
        "transport_event_id": "event-1",
        "content_text": "hello",
        "occurred_at": now.isoformat(),
        "conversation_id": "thread-1",
    }


def test_parse_ingress_envelope_requires_timezone_and_strict_fields(now):
    envelope = parse_ingress_envelope(json.dumps(_payload(now)))
    assert envelope.transport_event_id == "event-1"
    assert envelope.occurred_at == now

    bad = _payload(now)
    bad["unexpected"] = "value"
    with pytest.raises(IngressEnvelopeError, match="unsupported field"):
        parse_ingress_envelope(json.dumps(bad))

    bad_time = _payload(now)
    bad_time["occurred_at"] = "2026-09-06T12:00:00"
    with pytest.raises(IngressEnvelopeError, match="timezone"):
        parse_ingress_envelope(json.dumps(bad_time))
