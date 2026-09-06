from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

import pytest

from alsoul.adapters import (
    FakeModelAdapter,
    FakeWorldAdapter,
    HttpResponse,
    HttpWorldAdapter,
    ModelProviderAdapter,
    WorldAcquisitionAdapter,
)


@dataclass(slots=True)
class StubHttpTransport:
    response: HttpResponse
    last_locator: str | None = None
    last_timeout_seconds: float | None = None
    last_headers: Mapping[str, str] | None = None

    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        self.last_locator = locator
        self.last_timeout_seconds = timeout_seconds
        self.last_headers = headers
        return self.response


def test_fakes_conform_to_provider_independent_contracts():
    assert isinstance(FakeWorldAdapter(), WorldAcquisitionAdapter)
    assert isinstance(FakeModelAdapter(), ModelProviderAdapter)


def test_http_world_adapter_preserves_source_identity_and_metadata():
    captured_at = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    transport = StubHttpTransport(
        HttpResponse(
            resolved_locator="https://source.invalid/requirements-v2",
            content='{"minimum_memory_gb":24}',
            headers={
                "etag": '"revision-7"',
                "last-modified": "Sun, 06 Sep 2026 11:00:00 GMT",
            },
        )
    )
    adapter = HttpWorldAdapter(
        locator="https://source.invalid/requirements",
        timeout_seconds=3.5,
        transport=transport,
    )

    acquired = adapter.acquire(captured_at=captured_at)

    assert isinstance(adapter, WorldAcquisitionAdapter)
    assert acquired.requested_locator == "https://source.invalid/requirements"
    assert acquired.resolved_locator == "https://source.invalid/requirements-v2"
    assert acquired.source_identity == acquired.resolved_locator
    assert acquired.source_version == '"revision-7"'
    assert acquired.source_modified_at == datetime(
        2026, 9, 6, 11, 0, tzinfo=timezone.utc
    )
    assert acquired.captured_at == captured_at
    assert acquired.content == '{"minimum_memory_gb":24}'
    assert transport.last_locator == adapter.locator
    assert transport.last_timeout_seconds == 3.5
    assert transport.last_headers is not None
    assert "application/json" in transport.last_headers["Accept"]


def test_http_world_adapter_does_not_invent_invalid_source_time():
    captured_at = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    transport = StubHttpTransport(
        HttpResponse(
            resolved_locator="https://source.invalid/requirements",
            content='{"minimum_memory_gb":24}',
            headers={"last-modified": "not-a-date"},
        )
    )

    acquired = HttpWorldAdapter(
        locator="https://source.invalid/requirements",
        transport=transport,
    ).acquire(captured_at=captured_at)

    assert acquired.source_modified_at is None


def test_http_world_adapter_rejects_non_http_locator():
    with pytest.raises(ValueError, match="http or https"):
        HttpWorldAdapter(locator="file:///tmp/source.json")


def test_http_world_adapter_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="positive"):
        HttpWorldAdapter(locator="https://source.invalid/requirements", timeout_seconds=0)
