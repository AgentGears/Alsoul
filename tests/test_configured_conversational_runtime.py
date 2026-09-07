from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import HttpResponse, JsonHttpResponse
from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    ConfiguredFoundationRuntime,
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
)
from alsoul.storage import schema


@dataclass(slots=True)
class NoWorldTransport:
    calls: int = 0

    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        del locator, timeout_seconds, headers
        self.calls += 1
        raise AssertionError("conversational path must not perform world acquisition")


@dataclass(slots=True)
class ConversationalModelTransport:
    calls: int = 0
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
        self.calls += 1
        self.last_body = body
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(
                {
                    "segments": [
                        {
                            "epistemic_kind": "COMPANION_EXPRESSION",
                            "text": "I'm here and ready to talk with you.",
                            "source_ref": None,
                        }
                    ]
                }
            ),
            headers={"content-type": "application/json"},
        )


@dataclass(slots=True)
class PresentationTransport:
    calls: int = 0
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
        self.calls += 1
        key = body["presentation_key"]
        digest = body["content_digest"]
        previous = self.accepted.get(key)
        if previous is not None and previous != digest:
            return JsonHttpResponse(
                status_code=409,
                resolved_endpoint=endpoint,
                content="{}",
                headers={},
            )
        self.accepted[key] = digest
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(
                {
                    "schema_version": 1,
                    "status": "ACCEPTED",
                    "presentation_key": key,
                    "receipt_ref": f"conversation-presentation:{key}",
                    "content_digest": digest,
                }
            ),
            headers={"content-type": "application/json"},
        )


def _config() -> FoundationRuntimeConfig:
    return FoundationRuntimeConfig(
        world=WorldRuntimeConfig(
            locator="https://world.invalid/requirements",
            timeout_seconds=1,
        ),
        model=ModelRuntimeConfig(
            endpoint="https://model.invalid/generate",
            provider_binding_ref="conversation-provider",
            model_ref="conversation-model-v1",
            timeout_seconds=1,
        ),
        presentation=PresentationRuntimeConfig(
            endpoint="https://presentation.invalid/present",
            timeout_seconds=1,
        ),
    )


def _current_input(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="configured-conversation",
        external_subject=str(uuid4()),
    )
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="configured-conversation-input",
            content_text="How are you?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="configured-conversation",
        )
    )
    return ids, event


def test_configured_runtime_routes_conversation_without_world_work(
    services, bootstrapper, now
):
    ids, event = _current_input(services, bootstrapper, now)
    world = NoWorldTransport()
    model = ConversationalModelTransport()
    presentation = PresentationTransport()
    runtime = ConfiguredFoundationRuntime(
        services,
        config=_config(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        world_transport=world,
        model_transport=model,
        presentation_transport=presentation,
    )

    interaction = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=event.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )

    assert interaction.interaction_purpose == "CONVERSATIONAL_RESPONSE"
    assert interaction.memory_admission is None
    assert interaction.response is not None
    assert world.calls == 0
    assert model.calls == 1
    assert presentation.calls == 1
    assert model.last_body is not None
    assert model.last_body["provider_context"]["personal_context"] == []
    assert model.last_body["provider_context"]["world_context"] == []
    assert model.last_body["response_contract"]["required_epistemic_kinds"] == [
        "COMPANION_EXPRESSION"
    ]

    with services.engine.connect() as conn:
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()
        world_result_count = conn.execute(
            select(func.count()).select_from(schema.world_result)
        ).scalar_one()
        presented = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == interaction.response.presented_event_id
            )
        ).mappings().one()
    assert investigation_count == 0
    assert world_result_count == 0
    assert presented["content_text"] == "I'm here and ready to talk with you."


def test_lower_level_checked_respond_rejects_conversational_input_before_provider_work(
    services, bootstrapper, now
):
    ids, event = _current_input(services, bootstrapper, now)
    world = NoWorldTransport()
    model = ConversationalModelTransport()
    presentation = PresentationTransport()
    runtime = ConfiguredFoundationRuntime(
        services,
        config=_config(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
        world_transport=world,
        model_transport=model,
        presentation_transport=presentation,
    )

    with pytest.raises(DomainError) as excinfo:
        runtime.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=event.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )

    assert excinfo.value.code == "RESPONSE_PATH_PURPOSE_MISMATCH"
    assert world.calls == 0
    assert model.calls == 0
    assert presentation.calls == 0
