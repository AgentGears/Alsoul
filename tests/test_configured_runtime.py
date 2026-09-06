from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import HttpResponse, JsonHttpResponse
from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AppendCounterpartInputCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    ConfiguredFoundationRuntime,
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    RuntimeSecrets,
    WorldRuntimeConfig,
)
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.storage import schema


@dataclass(slots=True)
class StubWorldTransport:
    response: HttpResponse
    last_locator: str | None = None
    last_headers: Mapping[str, str] | None = None

    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        self.last_locator = locator
        self.last_headers = headers
        return self.response


@dataclass(slots=True)
class ContractModelTransport:
    last_endpoint: str | None = None
    last_body: dict[str, Any] | None = None
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
        self.last_headers = headers
        context = body["provider_context"]
        claim = context["personal_context"][0]
        world = context["world_context"][0]
        payload = {
            "segments": [
                {
                    "epistemic_kind": "REMEMBERED_COUNTERPART_STATEMENT",
                    "text": f"You told me your machine has {claim['value']} GB RAM.",
                    "source_ref": claim["claim_id"],
                },
                {
                    "epistemic_kind": "CURRENT_CHECKED_WORLD",
                    "text": f"I checked the current requirement; it is {world['value']} GB.",
                    "source_ref": world["world_result_id"],
                },
                {
                    "epistemic_kind": "COMPANION_INTERPRETATION",
                    "text": "My take is that this machine does not meet that requirement.",
                    "source_ref": None,
                },
            ]
        }
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )


@dataclass(slots=True)
class ContractPresentationTransport:
    last_endpoint: str | None = None
    last_body: dict[str, Any] | None = None
    attempts: int = 0
    accepted: dict[str, str] = field(default_factory=dict)

    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        del timeout_seconds, headers
        self.attempts += 1
        self.last_endpoint = endpoint
        self.last_body = body
        key = body["presentation_key"]
        digest = body["content_digest"]
        previous = self.accepted.get(key)
        if previous is not None and previous != digest:
            return JsonHttpResponse(
                status_code=409,
                resolved_endpoint=endpoint,
                content="{}",
                headers={"content-type": "application/json"},
            )
        self.accepted[key] = digest
        payload = {
            "schema_version": 1,
            "status": "ACCEPTED",
            "presentation_key": key,
            "receipt_ref": f"presentation-receipt:{key}",
            "content_digest": digest,
        }
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )


def _config() -> FoundationRuntimeConfig:
    return FoundationRuntimeConfig(
        world=WorldRuntimeConfig(
            locator="https://source.invalid/requirements",
            timeout_seconds=4.0,
        ),
        model=ModelRuntimeConfig(
            endpoint="https://model.invalid/generate",
            provider_binding_ref="configured-provider",
            model_ref="configured-model-v1",
            timeout_seconds=8.0,
        ),
        presentation=PresentationRuntimeConfig(
            endpoint="https://surface.invalid/present",
            timeout_seconds=5.0,
        ),
    )


def _prepare_current_input(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="configured-runtime",
        external_subject=str(uuid4()),
    )
    memory_event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="configured-memory",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=16,
            source_event_id=memory_event.event_id,
        )
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="configured-current",
            content_text="Would the current software run on my machine?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    return ids, current


def test_configured_runtime_executes_controlled_reactive_vertical_slice(
    services,
    bootstrapper,
    now,
):
    ids, current = _prepare_current_input(services, bootstrapper, now)
    world_transport = StubWorldTransport(
        HttpResponse(
            resolved_locator="https://source.invalid/requirements/current",
            content='{"minimum_memory_gb":24}',
            headers={"etag": '"runtime-1"'},
        )
    )
    model_transport = ContractModelTransport()
    presentation_transport = ContractPresentationTransport()
    secret = "runtime-secret-token"
    runtime = ConfiguredFoundationRuntime(
        services,
        config=_config(),
        secrets=RuntimeSecrets(model_authorization_token=secret),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        world_transport=world_transport,
        model_transport=model_transport,
        presentation_transport=presentation_transport,
    )

    before = runtime.diagnose(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert before.recovery_stage == "INPUT_ADMITTED"
    assert before.next_action == "START_INVESTIGATION"

    result = runtime.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )

    after = runtime.diagnose(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert after.recovery_stage == "PRESENTED"
    assert after.next_action == "NONE"
    assert after.presented_event_id == result.presented_event_id
    assert after.investigation_id is not None
    assert tuple(item.status for item in after.observation_states) == ("SUCCEEDED",)
    assert len(after.world_result_ids) == 1
    assert tuple(item.outcome for item in after.model_attempts) == ("SUCCEEDED",)

    assert world_transport.last_locator == "https://source.invalid/requirements"
    assert model_transport.last_endpoint == "https://model.invalid/generate"
    assert model_transport.last_headers is not None
    assert model_transport.last_headers["Authorization"] == f"Bearer {secret}"
    assert presentation_transport.last_endpoint == "https://surface.invalid/present"
    assert presentation_transport.attempts == 1
    assert presentation_transport.last_body is not None
    assert presentation_transport.last_body["companion_output_id"] == str(
        result.companion_output_id
    )
    assert "You told me" in presentation_transport.last_body["content_text"]
    assert secret not in repr(runtime.secrets)
    assert secret not in json.dumps(runtime.config.public_snapshot(), sort_keys=True)

    with services.engine.connect() as conn:
        invocation = conn.execute(select(schema.model_invocation)).mappings().one()
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == result.presented_event_id
            )
        ).mappings().one()
    assert invocation["provider_binding_ref"] == "configured-provider"
    assert invocation["model_ref"] == "configured-model-v1"
    assert secret not in invocation["provider_binding_ref"]
    assert secret not in invocation["model_ref"]
    assert "You told me" in event["content_text"]
    assert "I checked" in event["content_text"]
    assert "My take" in event["content_text"]


def test_configured_runtime_rejects_cross_origin_world_material_before_result_admission(
    services,
    bootstrapper,
    now,
):
    ids, current = _prepare_current_input(services, bootstrapper, now)
    presentation_transport = ContractPresentationTransport()
    runtime = ConfiguredFoundationRuntime(
        services,
        config=_config(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        world_transport=StubWorldTransport(
            HttpResponse(
                resolved_locator="https://other.invalid/requirements",
                content='{"minimum_memory_gb":24}',
                headers={},
            )
        ),
        model_transport=ContractModelTransport(),
        presentation_transport=presentation_transport,
    )

    with pytest.raises(DomainError) as excinfo:
        runtime.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    assert excinfo.value.code == "WORLD_EXTRACTION_REJECTED"
    assert presentation_transport.attempts == 0

    with services.engine.connect() as conn:
        captures = conn.execute(
            select(func.count()).select_from(schema.world_source_capture)
        ).scalar_one()
        results = conn.execute(
            select(func.count()).select_from(schema.world_result)
        ).scalar_one()
    assert captures == 1
    assert results == 0


def test_model_contract_probe_uses_synthetic_context_and_creates_no_canonical_cognition(
    services,
    now,
):
    model_transport = ContractModelTransport()
    presentation_transport = ContractPresentationTransport()
    runtime = ConfiguredFoundationRuntime(
        services,
        config=_config(),
        secrets=RuntimeSecrets(model_authorization_token="probe-secret"),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        world_transport=StubWorldTransport(
            HttpResponse(
                resolved_locator="https://source.invalid/requirements",
                content='{"minimum_memory_gb":24}',
                headers={},
            )
        ),
        model_transport=model_transport,
        presentation_transport=presentation_transport,
    )

    probe = runtime.probe_model_contract()

    assert probe.provider_binding_ref == "configured-provider"
    assert probe.model_ref == "configured-model-v1"
    assert probe.epistemic_kinds == (
        "REMEMBERED_COUNTERPART_STATEMENT",
        "CURRENT_CHECKED_WORLD",
        "COMPANION_INTERPRETATION",
    )
    assert model_transport.last_body is not None
    assert "Operational contract probe" in model_transport.last_body["provider_context"]["current_input"]
    assert presentation_transport.attempts == 0

    with services.engine.connect() as conn:
        invocations = conn.execute(
            select(func.count()).select_from(schema.model_invocation)
        ).scalar_one()
        generated = conn.execute(
            select(func.count()).select_from(schema.generated_output)
        ).scalar_one()
    assert invocations == 0
    assert generated == 0


def test_runtime_configuration_rejects_insecure_world_locator():
    with pytest.raises(ValueError, match="HTTPS"):
        WorldRuntimeConfig(locator="http://source.invalid/requirements")


def test_runtime_configuration_rejects_embedded_model_credentials():
    with pytest.raises(ValueError, match="without embedded credentials"):
        ModelRuntimeConfig(
            endpoint="https://user:pass@model.invalid/generate",
            provider_binding_ref="provider",
            model_ref="model",
        )


def test_runtime_configuration_rejects_insecure_presentation_endpoint():
    with pytest.raises(ValueError, match="HTTPS"):
        PresentationRuntimeConfig(endpoint="http://surface.invalid/present")
