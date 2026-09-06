from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Mapping, Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from alsoul.domain.models import WorldAcquisitionSuccess


@dataclass(frozen=True, slots=True)
class HttpResponse:
    resolved_locator: str
    content: str
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        ...


@dataclass(slots=True)
class UrllibHttpTransport:
    """Small standard-library transport used by the first real world adapter."""

    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        request = Request(locator, headers=dict(headers), method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read().decode(charset)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return HttpResponse(
                resolved_locator=response.geturl(),
                content=content,
                headers=response_headers,
            )


@dataclass(slots=True)
class HttpWorldAdapter:
    """Fetch immutable source material from one explicitly configured HTTP locator.

    The adapter only acquires bytes/text and source metadata. It does not admit an
    Observation, EvidenceItem, or WorldResult; those remain FoundationServices
    boundaries so transport success cannot become epistemic authority by itself.
    """

    locator: str
    timeout_seconds: float = 10.0
    transport: HttpTransport = field(default_factory=UrllibHttpTransport)
    user_agent: str = "Alsoul-F4/0.0.1"

    def __post_init__(self) -> None:
        scheme = urlsplit(self.locator).scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("HttpWorldAdapter locator must use http or https")
        if self.timeout_seconds <= 0:
            raise ValueError("HttpWorldAdapter timeout_seconds must be positive")

    def acquire(self, *, captured_at: datetime) -> WorldAcquisitionSuccess:
        response = self.transport.fetch(
            self.locator,
            timeout_seconds=self.timeout_seconds,
            headers={
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
                "User-Agent": self.user_agent,
            },
        )
        last_modified = _parse_http_datetime(response.headers.get("last-modified"))
        return WorldAcquisitionSuccess(
            source_identity=response.resolved_locator,
            requested_locator=self.locator,
            resolved_locator=response.resolved_locator,
            content=response.content,
            captured_at=captured_at,
            source_version=response.headers.get("etag"),
            source_modified_at=last_modified,
        )


def _parse_http_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed


__all__ = ["HttpResponse", "HttpTransport", "HttpWorldAdapter", "UrllibHttpTransport"]
