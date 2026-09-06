from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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


class _NoRedirectHandler(HTTPRedirectHandler):
    """Do not forward model credentials across HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(slots=True)
class UrllibJsonTransport:
    """Bounded, no-redirect HTTPS JSON transport for a configured model endpoint."""

    max_response_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")

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
        opener = build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = self._read_bounded(response, charset=charset)
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
            content = self._read_bounded(exc, charset=charset, errors="replace")
            return JsonHttpResponse(
                status_code=int(exc.code),
                resolved_endpoint=exc.geturl(),
                content=content,
                headers={key.lower(): value for key, value in exc.headers.items()},
            )

    def _read_bounded(
        self,
        response,
        *,
        charset: str,
        errors: str = "strict",
    ) -> str:
        raw = response.read(self.max_response_bytes + 1)
        if len(raw) > self.max_response_bytes:
            raise AdapterRejected("model endpoint response exceeded configured size limit")
        return raw.decode(charset, errors=errors)


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
        if parsed.scheme.lower() != "https" or not parsed.netloc or parsed.hostname is None:
            raise ValueError("model endpoint must be an absolute https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("model endpoint must not contain embedded credentials")
        if parsed.fragment:
            raise ValueError("model endpoint must not contain a URL fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("model timeout_seconds must be positive")
        if not self.provider_binding_ref.strip():
            raise ValueError("provider_binding_ref is required")
        if not self.model_ref.strip():
            raise ValueError("model_ref is required")

    def provider_request_digest(self, provider_context: dict[str, Any]) -> str:
        body = self._request_body(provider_context)
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(encoded).hexdigest()

    def generate(self, provider_context: dict[str, Any]) -> FoundationResponseDraft:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Alsoul-F4/0.0.1",
        }
        if self.authorization_token:
            headers["Authorization"] = f"Bearer {self.authorization_token}"

        request_body = self._request_body(provider_context)
        try:
            response = self.transport.post_json(
                self.endpoint,
                body=request_body,
                timeout_seconds=self.timeout_seconds,
                headers=headers,
            )
        except AdapterRejected:
            raise
        except (TimeoutError, URLError, OSError) as exc:
            raise AdapterOutcomeUnknown(
                "model transport outcome could not be established"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise AdapterRejected(
                f"model endpoint returned HTTP {response.status_code}"
            )
        if not _same_https_origin(urlsplit(self.endpoint), urlsplit(response.resolved_endpoint)):
            raise AdapterRejected("model endpoint resolved outside configured HTTPS origin")

        try:
            payload = json.loads(response.content)
            if not isinstance(payload, dict):
                raise TypeError("response payload must be an object")
            draft = FoundationResponseDraft.from_payload(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AdapterRejected(
                "model endpoint returned an invalid FoundationResponseDraft"
            ) from exc

        required_kinds = self._required_kinds()
        if tuple(segment.epistemic_kind for segment in draft.segments) != required_kinds:
            raise AdapterRejected(
                "model endpoint returned an invalid F4 epistemic segment sequence"
            )
        if any(not segment.text.strip() for segment in draft.segments):
            raise AdapterRejected("model endpoint returned an empty response segment")
        if (
            draft.segments[0].source_ref is None
            or draft.segments[1].source_ref is None
            or draft.segments[2].source_ref is not None
        ):
            raise AdapterRejected(
                "model endpoint returned invalid F4 source attribution shape"
            )
        return draft

    def _request_body(self, provider_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "model_ref": self.model_ref,
            "provider_context": provider_context,
            "response_contract": {
                "type": "FoundationResponseDraft",
                "required_epistemic_kinds": list(self._required_kinds()),
            },
        }

    @staticmethod
    def _required_kinds() -> tuple[str, str, str]:
        return (
            "REMEMBERED_COUNTERPART_STATEMENT",
            "CURRENT_CHECKED_WORLD",
            "COMPANION_INTERPRETATION",
        )


def _same_https_origin(expected: SplitResult, actual: SplitResult) -> bool:
    try:
        expected_port = expected.port or 443
        actual_port = actual.port or 443
    except ValueError:
        return False
    return (
        actual.scheme.lower() == "https"
        and expected.hostname is not None
        and actual.hostname is not None
        and expected.hostname.lower() == actual.hostname.lower()
        and expected_port == actual_port
    )


__all__ = [
    "JsonHttpResponse",
    "JsonHttpTransport",
    "JsonModelProviderAdapter",
    "UrllibJsonTransport",
]
