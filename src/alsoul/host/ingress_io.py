from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from alsoul.services import TrustedCounterpartInputEnvelope


class IngressEnvelopeError(ValueError):
    pass


def parse_ingress_envelope(raw_text: str) -> TrustedCounterpartInputEnvelope:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise IngressEnvelopeError("ingress envelope must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise IngressEnvelopeError("ingress envelope must be a JSON object")

    allowed = {
        "identity_namespace",
        "external_subject",
        "surface_namespace",
        "surface_ref",
        "channel_namespace",
        "channel_ref",
        "transport_event_id",
        "content_text",
        "occurred_at",
        "conversation_id",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise IngressEnvelopeError(
            f"ingress envelope contains unsupported field(s): {', '.join(unknown)}"
        )

    required = allowed - {"conversation_id"}
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise IngressEnvelopeError(
            f"ingress envelope is missing required field(s): {', '.join(missing)}"
        )

    occurred_at = _parse_datetime(payload.get("occurred_at"))
    conversation_id = payload.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        raise IngressEnvelopeError("conversation_id must be a string or null")

    try:
        return TrustedCounterpartInputEnvelope(
            identity_namespace=_string(payload, "identity_namespace"),
            external_subject=_string(payload, "external_subject"),
            surface_namespace=_string(payload, "surface_namespace"),
            surface_ref=_string(payload, "surface_ref"),
            channel_namespace=_string(payload, "channel_namespace"),
            channel_ref=_string(payload, "channel_ref"),
            transport_event_id=_string(payload, "transport_event_id"),
            content_text=_string(payload, "content_text"),
            occurred_at=occurred_at,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise IngressEnvelopeError(str(exc)) from exc


def _string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise IngressEnvelopeError(f"{field} must be a string")
    return value


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IngressEnvelopeError("occurred_at must be an RFC 3339 timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IngressEnvelopeError("occurred_at must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IngressEnvelopeError("occurred_at must include a timezone offset")
    return parsed


__all__ = ["IngressEnvelopeError", "parse_ingress_envelope"]
