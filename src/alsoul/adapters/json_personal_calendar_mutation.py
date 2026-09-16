from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.personal_calendar_action import CALENDAR_EVENT_CREATE
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
    CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION,
    PersonalCalendarCreateMutationRequest,
    PersonalCalendarCreateMutationResponse,
)


CALENDAR_MUTATION_WIRE_SCHEMA_VERSION = 1


@runtime_checkable
class CredentialSecretResolver(Protocol):
    """Resolve one non-secret credential reference inside the trusted adapter boundary."""

    def resolve_secret(self, secret_ref: str) -> str:
        ...


@dataclass(frozen=True, slots=True)
class CalendarMutationHttpResponse:
    status_code: int
    resolved_endpoint: str
    content: str


@runtime_checkable
class CalendarMutationWireTransport(Protocol):
    """Dedicated one-shot transport for the minimized calendar-create wire request.

    The method intentionally does not accept arbitrary headers, tracing context,
    retry configuration, or host-side Action/authority objects. The bearer token and
    allowlisted body cross only this exact transport boundary.
    """

    def post_create(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        authorization_token: str,
        timeout_seconds: float,
    ) -> CalendarMutationHttpResponse:
        ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Never forward a mutation credential or request body across redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(slots=True)
class UrllibCalendarMutationTransport:
    """One-shot HTTPS transport with no redirect, retry, logging, or middleware hooks."""

    max_response_bytes: int = 65_536
    user_agent: str = "Alsoul-F5/0.0.1"

    def __post_init__(self) -> None:
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if not self.user_agent.strip():
            raise ValueError("user_agent must be non-empty")

    def post_create(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        authorization_token: str,
        timeout_seconds: float,
    ) -> CalendarMutationHttpResponse:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {authorization_token}",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        opener = build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = self._read_bounded(response, charset=charset)
                return CalendarMutationHttpResponse(
                    status_code=int(response.status),
                    resolved_endpoint=response.geturl(),
                    content=content,
                )
        except HTTPError as exc:
            return CalendarMutationHttpResponse(
                status_code=int(exc.code),
                resolved_endpoint=exc.geturl(),
                content="",
            )

    def _read_bounded(self, response, *, charset: str) -> str:  # noqa: ANN001
        raw = response.read(self.max_response_bytes + 1)
        if len(raw) > self.max_response_bytes:
            raise AdapterRejected(
                "calendar mutation endpoint response exceeded configured size limit"
            )
        try:
            return raw.decode(charset)
        except (UnicodeDecodeError, LookupError) as exc:
            raise AdapterRejected(
                "calendar mutation endpoint returned an undecodable response body"
            ) from exc


@dataclass(slots=True)
class JsonPersonalCalendarMutationAdapter:
    """Trusted provider-neutral HTTPS adapter for one fenced calendar-create Action.

    Host-only Action/ExecutionAttempt identities and authority provenance never enter
    the provider wire request. The credential is resolved from its non-secret reference
    only inside this adapter immediately before the dedicated one-shot transport call.
    No internal retry exists: transport ambiguity is returned as ``AdapterOutcomeUnknown``
    so canonical fence/correlation reconciliation remains authoritative.
    """

    endpoint: str
    adapter_binding_ref: str
    adapter_contract_version: str
    capability_contract_version: str
    external_system_ref: str
    secret_resolver: CredentialSecretResolver
    timeout_seconds: float = 10.0
    transport: CalendarMutationWireTransport = field(
        default_factory=UrllibCalendarMutationTransport
    )

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if parsed.scheme.lower() != "https" or not parsed.netloc or parsed.hostname is None:
            raise ValueError("calendar mutation endpoint must be an absolute https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("calendar mutation endpoint must not contain embedded credentials")
        if parsed.fragment:
            raise ValueError("calendar mutation endpoint must not contain a URL fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("calendar mutation timeout_seconds must be positive")
        for name, value in (
            ("adapter_binding_ref", self.adapter_binding_ref),
            ("adapter_contract_version", self.adapter_contract_version),
            ("capability_contract_version", self.capability_contract_version),
            ("external_system_ref", self.external_system_ref),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not callable(getattr(self.secret_resolver, "resolve_secret", None)):
            raise ValueError("secret_resolver must implement resolve_secret")
        if not callable(getattr(self.transport, "post_create", None)):
            raise ValueError("transport must implement post_create")

    def create_event(
        self, request: PersonalCalendarCreateMutationRequest
    ) -> PersonalCalendarCreateMutationResponse:
        self._validate_request(request)
        try:
            authorization_token = self.secret_resolver.resolve_secret(
                request.credential_secret_ref
            )
        except AdapterRejected:
            raise
        except Exception as exc:
            raise AdapterRejected("calendar mutation credential could not be resolved") from exc
        if not isinstance(authorization_token, str) or not authorization_token.strip():
            raise AdapterRejected("calendar mutation credential resolver returned no secret")

        body = self._wire_body(request)
        try:
            response = self.transport.post_create(
                self.endpoint,
                body=body,
                authorization_token=authorization_token,
                timeout_seconds=self.timeout_seconds,
            )
        except (AdapterRejected, AdapterOutcomeUnknown):
            raise
        except (TimeoutError, URLError, OSError) as exc:
            raise AdapterOutcomeUnknown(
                "calendar mutation transport outcome could not be established"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise AdapterRejected(
                f"calendar mutation endpoint returned HTTP {response.status_code}"
            )
        if not _same_https_origin(
            urlsplit(self.endpoint), urlsplit(response.resolved_endpoint)
        ):
            raise AdapterRejected(
                "calendar mutation endpoint resolved outside configured HTTPS origin"
            )

        payload = self._parse_response(response.content)
        return PersonalCalendarCreateMutationResponse(
            correlation_key=payload["correlation_key"],
            external_effect_ref=payload["effect_ref"],
            external_system_ref=payload["system_ref"],
            external_resource_ref=payload["resource_ref"],
            summary=payload["summary"],
            normalized_start_at=_parse_aware_datetime(payload["start_at"], "start_at"),
            normalized_end_at=_parse_aware_datetime(payload["end_at"], "end_at"),
            receipt_ref=payload["receipt_ref"],
            observed_at=_parse_aware_datetime(payload["observed_at"], "observed_at"),
            provider_status="CREATED",
            evidence_schema_version=CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
        )

    def _validate_request(self, request: PersonalCalendarCreateMutationRequest) -> None:
        if not isinstance(request, PersonalCalendarCreateMutationRequest):
            raise AdapterRejected("calendar mutation request contract is invalid")
        if request.request_contract_version != CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION:
            raise AdapterRejected("calendar mutation request contract version is unsupported")
        if request.adapter_contract_version != self.adapter_contract_version:
            raise AdapterRejected("calendar mutation adapter contract does not match request")
        if request.capability_contract_version != self.capability_contract_version:
            raise AdapterRejected("calendar mutation capability contract does not match request")
        if request.external_system_ref != self.external_system_ref:
            raise AdapterRejected("calendar mutation external system does not match adapter")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                request.external_resource_ref,
                request.summary,
                request.correlation_key,
                request.credential_secret_ref,
            )
        ):
            raise AdapterRejected("calendar mutation request contains an empty wire field")
        if (
            request.normalized_start_at.tzinfo is None
            or request.normalized_start_at.utcoffset() is None
            or request.normalized_end_at.tzinfo is None
            or request.normalized_end_at.utcoffset() is None
            or request.normalized_end_at <= request.normalized_start_at
        ):
            raise AdapterRejected("calendar mutation request times must be valid offset-aware instants")

    @staticmethod
    def _wire_body(request: PersonalCalendarCreateMutationRequest) -> dict[str, Any]:
        return {
            "schema_version": CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
            "operation": CALENDAR_EVENT_CREATE,
            "resource_ref": request.external_resource_ref,
            "summary": request.summary,
            "start_at": request.normalized_start_at.isoformat(),
            "end_at": request.normalized_end_at.isoformat(),
            "correlation_key": request.correlation_key,
        }

    @staticmethod
    def _parse_response(content: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AdapterRejected(
                "calendar mutation endpoint returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise AdapterRejected(
                "calendar mutation endpoint response must be a JSON object"
            )
        expected = {
            "schema_version",
            "operation",
            "status",
            "correlation_key",
            "effect_ref",
            "system_ref",
            "resource_ref",
            "summary",
            "start_at",
            "end_at",
            "receipt_ref",
            "observed_at",
        }
        if set(payload) != expected:
            raise AdapterRejected(
                "calendar mutation endpoint returned fields outside the minimized response contract"
            )
        if (
            payload["schema_version"] != CALENDAR_MUTATION_WIRE_SCHEMA_VERSION
            or payload["operation"] != CALENDAR_EVENT_CREATE
            or payload["status"] != "CREATED"
        ):
            raise AdapterRejected(
                "calendar mutation endpoint returned an unsupported response contract"
            )
        for key in (
            "correlation_key",
            "effect_ref",
            "system_ref",
            "resource_ref",
            "summary",
            "start_at",
            "end_at",
            "receipt_ref",
            "observed_at",
        ):
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise AdapterRejected(
                    "calendar mutation endpoint returned an empty normalized field"
                )
        return payload


def _parse_aware_datetime(value: str, field_name: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AdapterRejected(
            f"calendar mutation endpoint returned invalid {field_name}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterRejected(
            f"calendar mutation endpoint returned non-offset-aware {field_name}"
        )
    return parsed


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
    "CALENDAR_MUTATION_WIRE_SCHEMA_VERSION",
    "CalendarMutationHttpResponse",
    "CalendarMutationWireTransport",
    "CredentialSecretResolver",
    "JsonPersonalCalendarMutationAdapter",
    "UrllibCalendarMutationTransport",
]
