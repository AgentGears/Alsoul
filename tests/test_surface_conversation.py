from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import func, select

from alsoul.adapters import HttpResponse, JsonHttpResponse
from alsoul.domain.types import FixedClock
from alsoul.host.config import FoundationHostConfig
from alsoul.services import (
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
)
from alsoul.storage import schema
from alsoul.surface import LocalFirstPartySurfaceApplication, LocalSurfaceIdentity


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
        raise AssertionError("local conversational response must not acquire world state")


@dataclass(slots=True)
class ConversationModelTransport:
    calls: int = 0

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
        assert body["response_contract"]["required_epistemic_kinds"] == [
            "COMPANION_EXPRESSION"
        ]
        assert body["provider_context"]["personal_context"] == []
        assert body["provider_context"]["world_context"] == []
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(
                {
                    "segments": [
                        {
                            "epistemic_kind": "COMPANION_EXPRESSION",
                            "text": "Hello. I'm here.",
                            "source_ref": None,
                        }
                    ]
                }
            ),
            headers={"content-type": "application/json"},
        )


def _config(db_path) -> FoundationHostConfig:
    return FoundationHostConfig(
        host_config_version=2,
        database_path=db_path.resolve(),
        runtime=FoundationRuntimeConfig(
            world=WorldRuntimeConfig(
                locator="https://world.invalid/requirements",
                timeout_seconds=1,
            ),
            model=ModelRuntimeConfig(
                endpoint="https://model.invalid/generate",
                provider_binding_ref="surface-conversation-provider",
                model_ref="surface-conversation-model-v1",
                timeout_seconds=1,
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://surface.invalid/present",
                timeout_seconds=1,
            ),
        ),
    )


def test_local_surface_conversation_survives_complete_recomposition_without_world_work(
    services, bootstrapper, db_path, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="surface-conversation",
        external_subject="u1",
    )
    services.engine.dispose()
    state_path = db_path.with_name("surface-conversation-state.db")
    identity = LocalSurfaceIdentity(
        identity_namespace="surface-conversation",
        external_subject="u1",
    )

    world1 = NoWorldTransport()
    model1 = ConversationModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        clock=FixedClock(now),
        world_transport=world1,
        model_transport=model1,
    ) as app1:
        first = app1.interact(
            "Hello.",
            transport_event_id="surface-conversation-1",
        )

    assert first.companion_person_id == ids.companion_person_id
    assert first.relationship_id == ids.relationship_id
    assert first.interaction_purpose == "CONVERSATIONAL_RESPONSE"
    assert first.presented_event_id is not None
    assert first.companion_output_id is not None
    assert first.content_text == "Hello. I'm here."
    assert first.surface_notice is None
    assert world1.calls == 0
    assert model1.calls == 1

    world2 = NoWorldTransport()
    model2 = ConversationModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        clock=FixedClock(now),
        world_transport=world2,
        model_transport=model2,
    ) as app2:
        replay = app2.interact(
            "Hello.",
            transport_event_id="surface-conversation-1",
        )
        with app2.engine.connect() as conn:
            investigations = conn.execute(
                select(func.count()).select_from(schema.investigation)
            ).scalar_one()
            invocations = conn.execute(
                select(func.count()).select_from(schema.model_invocation)
            ).scalar_one()
            outputs = conn.execute(
                select(func.count()).select_from(schema.companion_output)
            ).scalar_one()
            presentations = conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT"
                )
            ).scalar_one()

    assert replay.input_event_id == first.input_event_id
    assert replay.companion_output_id == first.companion_output_id
    assert replay.presented_event_id == first.presented_event_id
    assert replay.content_text == first.content_text
    assert replay.idempotent_input_replay is True
    assert world2.calls == 0
    assert model2.calls == 0
    assert investigations == 0
    assert invocations == 1
    assert outputs == 1
    assert presentations == 1
