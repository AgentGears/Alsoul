from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from uuid import UUID

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.adapters.json_model import JsonHttpTransport, UrllibJsonTransport
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
)


@dataclass(slots=True)
class JsonPersonalCalendarPresentationAdapter:
    endpoint: str
    status_endpoint: str
    timeout_seconds: float = 10.0
    transport: JsonHttpTransport = field(default_factory=UrllibJsonTransport)
    presentation_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version: str = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for label, value in (("presentation", self.endpoint), ("status", self.status_endpoint)):
            parsed = urlsplit(value)
            if parsed.scheme.lower() != "https" or not parsed.netloc or parsed.hostname is None or parsed.username or parsed.password or parsed.fragment:
                raise ValueError(f"{label} endpoint must be an absolute HTTPS URL without embedded credentials or fragment")
        if _origin(self.endpoint) != _origin(self.status_endpoint):
            raise ValueError("presentation endpoints must share one HTTPS origin")
        if self.timeout_seconds <= 0:
            raise ValueError("presentation timeout_seconds must be positive")

    def present_personal(
        self,
        *,
        presentation_key: str,
        presentation_attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        content_text: str,
        content_digest: str,
    ) -> PersonalCalendarPresentationDispatchResult:
        body = {
            "schema_version": 1,
            "presentation_contract_version": self.presentation_contract_version,
            "status_contract_version": self.status_contract_version,
            "presentation_key": presentation_key,
            "presentation_attempt_generation": presentation_attempt_generation,
            "presentation_transport_fence_scope_id": str(presentation_transport_fence_scope_id),
            "companion_output_id": str(companion_output_id),
            "surface_binding_id": str(surface_binding_id),
            "channel_binding_id": str(channel_binding_id),
            "content_text": content_text,
            "content_digest": content_digest,
        }
        payload = self._post(self.endpoint, body)
        return self._parse(payload, presentation_key, presentation_attempt_generation, presentation_transport_fence_scope_id, allow_unknown=False)

    def lookup_personal_status(
        self,
        *,
        presentation_key: str,
        presentation_attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
    ) -> PersonalCalendarPresentationStatusResult:
        body = {
            "schema_version": 1,
            "status_contract_version": self.status_contract_version,
            "presentation_key": presentation_key,
            "presentation_attempt_generation": presentation_attempt_generation,
            "presentation_transport_fence_scope_id": str(presentation_transport_fence_scope_id),
        }
        parsed = self._parse(
            self._post(self.status_endpoint, body),
            presentation_key,
            presentation_attempt_generation,
            presentation_transport_fence_scope_id,
            allow_unknown=True,
        )
        return PersonalCalendarPresentationStatusResult(**parsed.__dict__)

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.transport.post_json(
                endpoint,
                body=body,
                timeout_seconds=self.timeout_seconds,
                headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Alsoul-F5/0.0.1"},
            )
        except AdapterRejected:
            raise
        except (TimeoutError, URLError, OSError) as exc:
            raise AdapterOutcomeUnknown("personal presentation outcome is unknown") from exc
        if not 200 <= response.status_code < 300 or _origin(endpoint) != _origin(response.resolved_endpoint):
            raise AdapterRejected("personal presentation endpoint response is not trusted")
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise AdapterRejected("personal presentation endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterRejected("personal presentation endpoint response must be an object")
        return payload

    def _parse(self, payload: dict[str, Any], key: str, generation: int, fence_id: UUID, *, allow_unknown: bool) -> PersonalCalendarPresentationDispatchResult:
        if payload.get("schema_version") != 1 or payload.get("status_contract_version") != self.status_contract_version or payload.get("presentation_key") != key or payload.get("presentation_attempt_generation") != generation or payload.get("presentation_transport_fence_scope_id") != str(fence_id):
            raise AdapterRejected("personal presentation status identity is invalid")
        state = payload.get("status")
        if state == "UNKNOWN" and allow_unknown:
            return _result(key, generation, fence_id, state, self.status_contract_version)
        if state == "ACCEPTED":
            receipt = payload.get("receipt_ref")
            if not isinstance(receipt, str) or not receipt.strip():
                raise AdapterRejected("acceptance receipt is missing")
            return _result(key, generation, fence_id, state, self.status_contract_version, receipt_ref=receipt.strip(), accepted_at=_dt(payload.get("accepted_at")))
        if state == "NOT_ACCEPTED":
            proof = payload.get("terminal_proof_kind")
            settled = payload.get("settled_through_ref")
            if not isinstance(proof, str) or not proof.strip() or not isinstance(settled, str) or not settled.strip():
                raise AdapterRejected("NOT_ACCEPTED lacks terminal-negative evidence")
            return _result(key, generation, fence_id, state, self.status_contract_version, terminal_proof_kind=proof.strip(), settled_through_ref=settled.strip(), proved_at=_dt(payload.get("proved_at")))
        raise AdapterRejected("personal presentation endpoint returned unsupported status")


def _result(key: str, generation: int, fence_id: UUID, state: str, status_version: str, **kwargs: Any) -> PersonalCalendarPresentationDispatchResult:
    return PersonalCalendarPresentationDispatchResult(
        presentation_key=key,
        presentation_attempt_generation=generation,
        presentation_transport_fence_scope_id=fence_id,
        state=state,
        status_contract_version=status_version,
        **kwargs,
    )


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or 443)


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AdapterRejected("presentation status timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AdapterRejected("presentation status timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterRejected("presentation status timestamp must be timezone-aware")
    return parsed


__all__ = ["JsonPersonalCalendarPresentationAdapter"]
