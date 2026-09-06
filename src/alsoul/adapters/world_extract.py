from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from alsoul.adapters.contracts import AdapterRejected
from alsoul.domain.models import CapturedWorldMaterial, ExtractedWorldResult


@dataclass(frozen=True, slots=True)
class F4JsonMemoryRequirementExtractor:
    """Bounded F4 interpreter for one configured JSON world-source contract.

    The extractor converts recoverable captured material into a proposition proposal.
    It never admits that proposal as a WorldResult. When `expected_https_origin` is
    configured, material from another source origin is rejected even if its bytes
    happen to contain the expected field.
    """

    expected_https_origin: str | None = None
    predicate: str = "software.minimum_memory_gb"
    result_kind: str = "REQUIREMENT"
    field_name: str = "minimum_memory_gb"

    def __post_init__(self) -> None:
        if not self.predicate.strip():
            raise ValueError("predicate is required")
        if not self.result_kind.strip():
            raise ValueError("result_kind is required")
        if not self.field_name.strip():
            raise ValueError("field_name is required")
        if self.expected_https_origin is not None:
            parsed = urlsplit(self.expected_https_origin)
            if (
                parsed.scheme.lower() != "https"
                or not parsed.netloc
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError(
                    "expected_https_origin must be an absolute HTTPS origin without path, query, fragment, or credentials"
                )

    def extract(self, material: CapturedWorldMaterial) -> ExtractedWorldResult:
        if not material.source_identity.strip():
            raise AdapterRejected("captured world source has no source identity")
        if self.expected_https_origin is not None and not _same_https_origin(
            urlsplit(self.expected_https_origin),
            urlsplit(material.source_identity),
        ):
            raise AdapterRejected(
                "captured world source identity is outside the configured HTTPS origin"
            )

        try:
            payload = json.loads(material.content)
        except json.JSONDecodeError as exc:
            raise AdapterRejected("captured world source is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterRejected("captured world source JSON must be an object")

        value = payload.get(self.field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AdapterRejected(
                f"captured world source does not contain a valid {self.field_name}"
            )

        return ExtractedWorldResult(
            result_kind=self.result_kind,
            predicate=self.predicate,
            value=value,
            valid_as_of=material.captured_at,
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


def https_origin(locator: str) -> str:
    """Return the normalized HTTPS origin for a validated absolute locator."""

    parsed = urlsplit(locator)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("locator must be an absolute HTTPS URL without embedded credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("locator contains an invalid port") from exc
    host = parsed.hostname.lower()
    if port is None or port == 443:
        return f"https://{host}"
    return f"https://{host}:{port}"


__all__ = ["F4JsonMemoryRequirementExtractor", "https_origin"]
