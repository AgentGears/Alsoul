from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import URLError
from uuid import uuid4

import pytest

from alsoul.adapters import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    JsonFirstPartyPresentationAdapter,
    JsonHttpResponse,
)


@dataclass(slots=True)
class StubJsonTransport:
    response: JsonHttpResponse | None = None
    error: Exception | None = None
    last_body: dict[str, Any] | None = None

    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        del timeout_seconds, headers
        self.last_body = body
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _acceptance_response(endpoint: str, key: str, digest: str) -> JsonHttpResponse:
    return JsonHttpResponse(
        status_code=200,
        resolved_endpoint=endpoint,
        content=json.dumps(
            {
                "schema_version": 1,
                "status": "ACCEPTED",
                "presentation_key": key,
                "receipt_ref": "receipt-1",
                "content_digest": digest,
            }
        ),
        headers={"content-type": "application/json"},
    )


def test_json_presentation_adapter_accepts_exact_receipt():
    endpoint = "https://surface.invalid/present"
    key = "presentation-key-1"
    digest = "abc123"
    transport = StubJsonTransport(
        response=_acceptance_response(endpoint, key, digest)
    )
    adapter = JsonFirstPartyPresentationAdapter(endpoint=endpoint, transport=transport)

    acceptance = adapter.present(
        presentation_key=key,
        companion_output_id=uuid4(),
        surface_binding_id=uuid4(),
        channel_binding_id=uuid4(),
        content_text="hello",
        content_digest=digest,
    )

    assert acceptance.presentation_key == key
    assert acceptance.receipt_ref == "receipt-1"
    assert acceptance.content_digest == digest
    assert transport.last_body is not None
    assert transport.last_body["content_text"] == "hello"


def test_json_presentation_adapter_rejects_receipt_for_different_digest():
    endpoint = "https://surface.invalid/present"
    key = "presentation-key-1"
    transport = StubJsonTransport(
        response=_acceptance_response(endpoint, key, "other-digest")
    )
    adapter = JsonFirstPartyPresentationAdapter(endpoint=endpoint, transport=transport)

    with pytest.raises(AdapterRejected, match="invalid acceptance receipt"):
        adapter.present(
            presentation_key=key,
            companion_output_id=uuid4(),
            surface_binding_id=uuid4(),
            channel_binding_id=uuid4(),
            content_text="hello",
            content_digest="expected-digest",
        )


def test_json_presentation_adapter_treats_transport_loss_as_unknown():
    adapter = JsonFirstPartyPresentationAdapter(
        endpoint="https://surface.invalid/present",
        transport=StubJsonTransport(error=URLError("connection lost")),
    )

    with pytest.raises(AdapterOutcomeUnknown):
        adapter.present(
            presentation_key="presentation-key-1",
            companion_output_id=uuid4(),
            surface_binding_id=uuid4(),
            channel_binding_id=uuid4(),
            content_text="hello",
            content_digest="digest",
        )


def test_json_presentation_adapter_rejects_cross_origin_resolution():
    key = "presentation-key-1"
    digest = "digest"
    adapter = JsonFirstPartyPresentationAdapter(
        endpoint="https://surface.invalid/present",
        transport=StubJsonTransport(
            response=_acceptance_response(
                "https://other.invalid/present",
                key,
                digest,
            )
        ),
    )

    with pytest.raises(AdapterRejected, match="outside configured HTTPS origin"):
        adapter.present(
            presentation_key=key,
            companion_output_id=uuid4(),
            surface_binding_id=uuid4(),
            channel_binding_id=uuid4(),
            content_text="hello",
            content_digest=digest,
        )
