from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping
from urllib.error import URLError
from uuid import uuid4

import pytest

from alsoul.adapters import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    JsonHttpResponse,
    JsonModelProviderAdapter,
    ModelProviderAdapter,
)


@dataclass(slots=True)
class StubJsonTransport:
    response: JsonHttpResponse | None = None
    error: Exception | None = None
    last_endpoint: str | None = None
    last_body: dict[str, Any] | None = None
    last_timeout_seconds: float | None = None
    last_headers: Mapping[str, str] | None = None

    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        self.last_endpoint = endpoint
        self.last_body = body
        self.last_timeout_seconds = timeout_seconds
        self.last_headers = headers
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _provider_context() -> dict[str, Any]:
    claim_id = uuid4()
    world_result_id = uuid4()
    return {
        "person": {
            "person_id": str(uuid4()),
            "role": "PERSONAL_COMPANION",
            "preferred_name": "Alsoul",
            "self_revision": 1,
        },
        "relationship_id": str(uuid4()),
        "current_input": "Would it run?",
        "personal_context": [
            {
                "claim_id": str(claim_id),
                "predicate": "primary_machine.memory_gb",
                "value": 16,
                "epistemic_basis": "COUNTERPART_STATED_MEMORY",
            }
        ],
        "world_context": [
            {
                "world_result_id": str(world_result_id),
                "predicate": "software.minimum_memory_gb",
                "value": 24,
                "epistemic_mode": "CURRENT_CHECKED",
            }
        ],
    }


def _draft_json(context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "segments": [
                {
                    "epistemic_kind": "REMEMBERED_COUNTERPART_STATEMENT",
                    "text": "You told me your machine has 16 GB RAM.",
                    "source_ref": context["personal_context"][0]["claim_id"],
                },
                {
                    "epistemic_kind": "CURRENT_CHECKED_WORLD",
                    "text": "I checked the current requirement; it is 24 GB RAM.",
                    "source_ref": context["world_context"][0]["world_result_id"],
                },
                {
                    "epistemic_kind": "COMPANION_INTERPRETATION",
                    "text": "My take is that this machine does not meet that requirement.",
                    "source_ref": None,
                },
            ]
        },
        sort_keys=True,
    )


def test_json_model_adapter_sends_context_without_persistable_credential_material():
    context = _provider_context()
    transport = StubJsonTransport(
        response=JsonHttpResponse(
            status_code=200,
            resolved_endpoint="https://model.invalid/invoke",
            content=_draft_json(context),
            headers={"content-type": "application/json"},
        )
    )
    adapter = JsonModelProviderAdapter(
        endpoint="https://model.invalid/invoke",
        provider_binding_ref="primary-cognition-route",
        model_ref="foundation-expression-v1",
        authorization_token="secret-token",
        timeout_seconds=5.0,
        transport=transport,
    )

    expected_digest = adapter.provider_request_digest(context)
    draft = adapter.generate(context)

    assert isinstance(adapter, ModelProviderAdapter)
    assert draft.render_text().startswith("You told me")
    assert transport.last_endpoint == "https://model.invalid/invoke"
    assert transport.last_timeout_seconds == 5.0
    assert transport.last_body is not None
    assert transport.last_body["provider_context"] == context
    canonical_body = json.dumps(
        transport.last_body,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert expected_digest == sha256(canonical_body).hexdigest()
    assert "secret-token" not in json.dumps(transport.last_body)
    assert transport.last_headers is not None
    assert transport.last_headers["Authorization"] == "Bearer secret-token"


def test_json_model_adapter_requires_https_endpoint():
    with pytest.raises(ValueError):
        JsonModelProviderAdapter(
            endpoint="http://model.invalid/invoke",
            provider_binding_ref="route",
            model_ref="model",
        )


def test_json_model_adapter_rejects_embedded_endpoint_credentials():
    with pytest.raises(ValueError):
        JsonModelProviderAdapter(
            endpoint="https://user:secret@model.invalid/invoke",
            provider_binding_ref="route",
            model_ref="model",
        )


def test_json_model_adapter_maps_network_uncertainty_to_unknown():
    adapter = JsonModelProviderAdapter(
        endpoint="https://model.invalid/invoke",
        provider_binding_ref="route",
        model_ref="model",
        transport=StubJsonTransport(error=URLError("timeout")),
    )

    with pytest.raises(AdapterOutcomeUnknown):
        adapter.generate(_provider_context())


def test_json_model_adapter_maps_definite_http_failure_to_rejected():
    adapter = JsonModelProviderAdapter(
        endpoint="https://model.invalid/invoke",
        provider_binding_ref="route",
        model_ref="model",
        transport=StubJsonTransport(
            response=JsonHttpResponse(
                status_code=422,
                resolved_endpoint="https://model.invalid/invoke",
                content='{"error":"invalid request"}',
                headers={},
            )
        ),
    )

    with pytest.raises(AdapterRejected):
        adapter.generate(_provider_context())


def test_json_model_adapter_rejects_cross_origin_resolution():
    context = _provider_context()
    adapter = JsonModelProviderAdapter(
        endpoint="https://model.invalid/invoke",
        provider_binding_ref="route",
        model_ref="model",
        transport=StubJsonTransport(
            response=JsonHttpResponse(
                status_code=200,
                resolved_endpoint="https://other.invalid/invoke",
                content=_draft_json(context),
                headers={},
            )
        ),
    )

    with pytest.raises(AdapterRejected):
        adapter.generate(context)


def test_json_model_adapter_rejects_invalid_semantic_payload():
    adapter = JsonModelProviderAdapter(
        endpoint="https://model.invalid/invoke",
        provider_binding_ref="route",
        model_ref="model",
        transport=StubJsonTransport(
            response=JsonHttpResponse(
                status_code=200,
                resolved_endpoint="https://model.invalid/invoke",
                content='{"segments":[{"epistemic_kind":"UNKNOWN","text":"x","source_ref":null}]}',
                headers={},
            )
        ),
    )

    with pytest.raises(AdapterRejected):
        adapter.generate(_provider_context())
