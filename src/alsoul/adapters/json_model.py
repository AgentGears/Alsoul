from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.models import FoundationResponseDraft


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    status_code: int
    resolved_endpoint: str
    content: str
    headers: Mapping[str, str]


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        ...


@dataclass(slots=True)
class UrllibJsonTransport:
    """Standard-library HTTPS JSON transport for a configured model endpoint."""

    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read().decode(charset)
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                return JsonHttpResponse(
                    status_code=int(response.status),
                    resolved_endpoint=response.geturl(),
                    content=content,
                    headers=response_headers,
                )
        except HTTPError as exc:
            charset = exc.headers.get_content_charset() or "utf-8"
            content = exc.read().decode(charset, errors="replace")
            return JsonHttpResponse(
                status_code=int(exc.code),
                resolved_endpoint=exc.geturl(),
                content=content,
                headers={key.lower(): value for key, value in exc.headers.items()},
            )


@dataclass(slots=True)
class JsonModelProviderAdapter:
    """Production-capable adapter for an Alsoul-compatible HTTPS model endpoint.

    Credentials are construction-time transport configuration. They are never
    placed in provider context, persisted model identity, or semantic payloads.
    The endpoint must return the FoundationResponseDraft wire shape.
    """

    endpoint: str
    provider_binding_ref: str
    model_ref: str
    authorization_token: str | None = None
    timeout_seconds: float = 30.0
    transport: JsonHttpTransport = field(default_factory=UrllibJsonTransport)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("model endpoint must be an absolute https URL")
        if self.timeout_seconds <= 0:
            raise ValueError("model timeout_seconds must be positive")
        if not self.provider_binding_ref.strip():
            raise ValueError("provider_binding_ref is required")
        if not self.model_ref.strip():
            raise ValueError("model_ref is required")

    def generate(self, provider_context: dict[str, Any]) -> FoundationResponseDraft:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Alsoul-F4/0.0.1",
        }
        if self.authorization_token:
            headers["Authorization"] = f"Bearer {self.authorization_token}"

        request_body = {
            "schema_version": 1,
            "model_ref": self.model_ref,
            "provider_context": provider_context,
            "response_contract": {
                "type": "FoundationResponseDraft",
                "required_epistemic_kinds": [
                    "REMEMBERED_COUNTERPART_STATEMENT",
                    "CURRENT_CHECKED_WORLD",
                    "COMPANION_INTERPRETATION",
                ],
            },
        }
        try:
            response = self.transport.post_json(
                self.endpoint,
                body=request_body,
                timeout_seconds=self.timeout_seconds,
                headers=headers,
            )
        except (TimeoutError, URLError, OSError) as exc:
            raise AdapterOutcomeUnknown(
                "model transport outcome could not be established"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise AdapterRejected(
                f"model endpoint returned HTTP {response.status_code}"
            )
        if urlsplit(response.resolved_endpoint).scheme.lower() != "https":
            raise AdapterRejected("model endpoint resolved outside https")

        try:
            payload = json.loads(response.content)
            if not isinstance(payload, dict):
                raise TypeError("response payload must be an object")
            draft = FoundationResponseDraft.from_payload(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AdapterRejected(
                "model endpoint returned an invalid FoundationResponseDraft"
            ) from exc

        allowed = {
            "REMEMBERED_COUNTERPART_STATEMENT",
            "CURRENT_CHECKED_WORLD",
            "COMPANION_INTERPRETATION",
        }
        if not draft.segments or any(
            segment.epistemic_kind not in allowed or not segment.text.strip()
            for segment in draft.segments
        ):
            raise AdapterRejected(
                "model endpoint returned invalid semantic response segments"
            )
        return draft


__all__ = [
    "JsonHttpResponse",
    "JsonHttpTransport",
    "JsonModelProviderAdapter",
    "UrllibJsonTransport",
]
