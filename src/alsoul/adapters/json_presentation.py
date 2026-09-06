from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.parse import SplitResult, urlsplit
from uuid import UUID

from alsoul.adapters.contracts import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    FirstPartyPresentationAcceptance,
)
from alsoul.adapters.json_model import JsonHttpTransport, UrllibJsonTransport


@dataclass(slots=True)
class JsonFirstPartyPresentationAdapter:
    """HTTPS adapter for one idempotent first-party presentation sink.

    The sink must deduplicate by ``presentation_key`` and return the same acceptance
    receipt for an exact replay. A successful response establishes sink acceptance
    only; it does not establish that the counterpart read or heard the output.
    """

    endpoint: str
    timeout_seconds: float = 10.0
    transport: JsonHttpTransport = field(default_factory=UrllibJsonTransport)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "presentation endpoint must be an absolute HTTPS URL without embedded credentials"
            )
        if parsed.fragment:
            raise ValueError("presentation endpoint must not contain a URL fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("presentation timeout_seconds must be positive")

    def present(
        self,
        *,
        presentation_key: str,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        content_text: str,
        content_digest: str,
    ) -> FirstPartyPresentationAcceptance:
        if not presentation_key.strip():
            raise AdapterRejected("presentation key is required")
        if not content_digest.strip():
            raise AdapterRejected("presentation content digest is required")

        body: dict[str, Any] = {
            "schema_version": 1,
            "presentation_key": presentation_key,
            "companion_output_id": str(companion_output_id),
            "surface_binding_id": str(surface_binding_id),
            "channel_binding_id": str(channel_binding_id),
            "content_text": content_text,
            "content_digest": content_digest,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Alsoul-F4/0.0.1",
        }
        try:
            response = self.transport.post_json(
                self.endpoint,
                body=body,
                timeout_seconds=self.timeout_seconds,
                headers=headers,
            )
        except AdapterRejected:
            raise
        except (TimeoutError, URLError, OSError) as exc:
            raise AdapterOutcomeUnknown(
                "first-party presentation outcome could not be established"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise AdapterRejected(
                f"presentation endpoint returned HTTP {response.status_code}"
            )
        if not _same_https_origin(urlsplit(self.endpoint), urlsplit(response.resolved_endpoint)):
            raise AdapterRejected(
                "presentation endpoint resolved outside configured HTTPS origin"
            )

        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise AdapterRejected(
                "presentation endpoint returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise AdapterRejected("presentation endpoint response must be an object")

        receipt_ref = payload.get("receipt_ref")
        if (
            payload.get("schema_version") != 1
            or payload.get("status") != "ACCEPTED"
            or payload.get("presentation_key") != presentation_key
            or payload.get("content_digest") != content_digest
            or not isinstance(receipt_ref, str)
            or not receipt_ref.strip()
        ):
            raise AdapterRejected(
                "presentation endpoint returned an invalid acceptance receipt"
            )

        return FirstPartyPresentationAcceptance(
            presentation_key=presentation_key,
            receipt_ref=receipt_ref.strip(),
            content_digest=content_digest,
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


__all__ = ["JsonFirstPartyPresentationAdapter"]
