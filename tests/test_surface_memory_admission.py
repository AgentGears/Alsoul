from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
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
class _WorldTransport:
    calls: int = 0

    def fetch(
        self,
        locator: str,
        *,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        del timeout_seconds, headers
        self.calls += 1
        return HttpResponse(
            resolved_locator=locator,
            content=json.dumps(
                {"software": "current-suite", "minimum_memory_gb": 24},
                sort_keys=True,
                separators=(",", ":"),
            ),
            headers={"content-type": "application/json"},
        )


@dataclass(slots=True)
class _ModelTransport:
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
                    "text": f"I checked the current requirement; it is {world['value']} GB RAM.",
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


def _config(db_path) -> FoundationHostConfig:
    return FoundationHostConfig(
        host_config_version=2,
        database_path=db_path.resolve(),
        runtime=FoundationRuntimeConfig(
            world=WorldRuntimeConfig(
                locator="https://source.invalid/requirements",
                timeout_seconds=4.0,
            ),
            model=ModelRuntimeConfig(
                endpoint="https://model.invalid/generate",
                provider_binding_ref="memory-surface-provider",
                model_ref="memory-surface-model-v1",
                timeout_seconds=8.0,
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://surface.invalid/present",
                timeout_seconds=5.0,
            ),
        ),
    )


def test_local_surface_routes_memory_only_then_recovers_it_for_later_world_question(
    services, bootstrapper, db_path, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="surface-memory",
        external_subject="u1",
    )
    services.engine.dispose()
    state_path = db_path.with_name("surface-memory-state.db")
    identity = LocalSurfaceIdentity(
        identity_namespace="surface-memory",
        external_subject="u1",
    )

    world1 = _WorldTransport()
    model1 = _ModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        clock=FixedClock(now),
        world_transport=world1,
        model_transport=model1,
    ) as app1:
        first = app1.interact(
            "My machine has 16 GB RAM.",
            transport_event_id="surface-memory-1",
        )
        assert app1.surface_store.count() == 0
        with app1.engine.connect() as conn:
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

    assert first.companion_person_id == ids.companion_person_id
    assert first.relationship_id == ids.relationship_id
    assert first.interaction_purpose == "MEMORY_STATEMENT"
    assert first.memory_disposition == "ADMITTED"
    assert first.memory_claim_id is not None
    assert first.presented_event_id is None
    assert first.companion_output_id is None
    assert first.content_text is None
    assert first.surface_notice == "Memory updated"
    assert world1.calls == 0
    assert model1.calls == 0
    assert investigations == 0
    assert invocations == 0
    assert outputs == 0
    assert presentations == 0

    later = now + timedelta(hours=1)
    world2 = _WorldTransport()
    model2 = _ModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        clock=FixedClock(later),
        world_transport=world2,
        model_transport=model2,
    ) as app2:
        second = app2.interact(
            "Would the current software run on my machine?",
            transport_event_id="surface-memory-2",
        )

    assert second.companion_person_id == first.companion_person_id
    assert second.relationship_id == first.relationship_id
    assert second.interaction_purpose == "WORLD_QUESTION"
    assert second.memory_disposition == "NO_CANDIDATE"
    assert second.presented_event_id is not None
    assert second.companion_output_id is not None
    assert second.content_text is not None
    assert "You told me your machine has 16 GB RAM." in second.content_text
    assert "I checked the current requirement; it is 24 GB RAM." in second.content_text
    assert world2.calls == 1
    assert model2.calls == 1
