from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Mapping
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest

from alsoul.adapters import AdapterRejected, HttpResponse, JsonHttpResponse
from alsoul.domain.commands import AdmitPersonMemoryClaimCommand, AppendCounterpartInputCommand
from alsoul.host.config import FoundationHostConfig
from alsoul.services import (
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
)
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.surface import (
    LocalFirstPartySurfaceApplication,
    LocalSurfaceIdentity,
    LocalSurfaceInteractionResult,
    LocalSurfaceServer,
    LocalSurfaceStore,
)


@dataclass(slots=True)
class StubWorldTransport:
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
class StubModelTransport:
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


def _host_config(db_path) -> FoundationHostConfig:
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
                provider_binding_ref="local-surface-provider",
                model_ref="local-surface-model-v1",
                timeout_seconds=8.0,
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://surface.invalid/present",
                timeout_seconds=5.0,
            ),
        ),
    )


def _seed_memory(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="local-surface",
        external_subject="u1",
    )
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="local-surface-memory",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="local-first-party",
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
            source_event_id=event.event_id,
        )
    )
    return ids


def test_local_surface_survives_process_recomposition_without_duplicate_work(
    services, bootstrapper, db_path, now
):
    ids = _seed_memory(services, bootstrapper, now)
    services.engine.dispose()
    state_path = db_path.with_name("surface-state.db")
    identity = LocalSurfaceIdentity(
        identity_namespace="local-surface",
        external_subject="u1",
    )

    world1 = StubWorldTransport()
    model1 = StubModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_host_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        world_transport=world1,
        model_transport=model1,
    ) as app1:
        first = app1.interact(
            "Would the current software run on my machine?",
            transport_event_id="local-event-1",
        )
        assert app1.surface_store.count() == 1

    assert first.companion_person_id == ids.companion_person_id
    assert first.counterpart_id == ids.counterpart_id
    assert first.relationship_id == ids.relationship_id
    assert "You told me" in first.content_text
    assert "I checked" in first.content_text
    assert "My take" in first.content_text
    assert world1.calls == 1
    assert model1.calls == 1

    world2 = StubWorldTransport()
    model2 = StubModelTransport()
    with LocalFirstPartySurfaceApplication(
        config=_host_config(db_path),
        identity=identity,
        surface_state_path=state_path,
        world_transport=world2,
        model_transport=model2,
    ) as app2:
        replay = app2.interact(
            "Would the current software run on my machine?",
            transport_event_id="local-event-1",
        )
        assert app2.surface_store.count() == 1

    assert replay.idempotent_input_replay is True
    assert replay.input_event_id == first.input_event_id
    assert replay.presented_event_id == first.presented_event_id
    assert replay.companion_output_id == first.companion_output_id
    assert replay.content_text == first.content_text
    assert replay.companion_person_id == first.companion_person_id
    assert replay.relationship_id == first.relationship_id
    assert world2.calls == 0
    assert model2.calls == 0


def test_local_surface_input_reservation_preserves_original_occurrence(now, tmp_path):
    store = LocalSurfaceStore(tmp_path / "surface.db")
    arguments = {
        "transport_event_id": "event-1",
        "identity_namespace": "local-surface",
        "external_subject": "u1",
        "surface_namespace": "alsoul.first_party",
        "surface_ref": "primary-text-surface",
        "channel_namespace": "alsoul.first_party",
        "channel_ref": "primary-text-channel",
        "content_text": "hello",
        "conversation_id": "local-first-party",
    }

    first = store.reserve_input(**arguments, occurred_at=now)
    replay = store.reserve_input(**arguments, occurred_at=now + timedelta(hours=1))

    assert first.existing is False
    assert first.occurred_at == now
    assert replay.existing is True
    assert replay.occurred_at == now

    with pytest.raises(ValueError):
        store.reserve_input(
            **{**arguments, "content_text": "different"},
            occurred_at=now + timedelta(hours=2),
        )


def test_local_surface_store_rejects_key_reuse_with_different_content(tmp_path):
    store = LocalSurfaceStore(tmp_path / "surface.db")
    ids = [uuid4() for _ in range(3)]
    first = store.accept(
        presentation_key="k1",
        companion_output_id=ids[0],
        surface_binding_id=ids[1],
        channel_binding_id=ids[2],
        content_text="hello",
        content_digest="digest-a",
    )
    replay = store.accept(
        presentation_key="k1",
        companion_output_id=ids[0],
        surface_binding_id=ids[1],
        channel_binding_id=ids[2],
        content_text="hello",
        content_digest="digest-a",
    )
    assert replay == first
    assert store.count() == 1

    with pytest.raises(AdapterRejected):
        store.accept(
            presentation_key="k1",
            companion_output_id=ids[0],
            surface_binding_id=ids[1],
            channel_binding_id=ids[2],
            content_text="changed",
            content_digest="digest-b",
        )


class _DummySurfaceApplication:
    readiness = SimpleNamespace(ready=True)

    def interact(
        self,
        content_text: str,
        *,
        transport_event_id: str | None = None,
        conversation_id: str | None = None,
    ) -> LocalSurfaceInteractionResult:
        del conversation_id
        value = uuid4()
        return LocalSurfaceInteractionResult(
            companion_person_id=value,
            counterpart_id=uuid4(),
            relationship_id=uuid4(),
            input_event_id=uuid4(),
            presented_event_id=uuid4(),
            companion_output_id=uuid4(),
            content_text=f"reply:{content_text}",
            transport_event_id=transport_event_id or "generated",
            idempotent_input_replay=False,
        )


def test_local_surface_http_requires_session_token_and_returns_first_party_content():
    surface = LocalSurfaceServer(application=_DummySurfaceApplication(), port=0)  # type: ignore[arg-type]
    thread = threading.Thread(target=surface.serve_forever, daemon=True)
    thread.start()
    try:
        page = urlopen(surface.url, timeout=2).read().decode("utf-8")
        assert "Alsoul" in page
        assert "Local first-party surface" in page

        body = json.dumps(
            {"content_text": "hello", "transport_event_id": "browser-event-1"}
        ).encode("utf-8")
        request = Request(
            surface.url + "api/interact",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Alsoul-Surface-Token": surface.session_token,
            },
        )
        payload = json.loads(urlopen(request, timeout=2).read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["result"]["content_text"] == "reply:hello"
        assert payload["result"]["transport_event_id"] == "browser-event-1"
    finally:
        surface.httpd.shutdown()
        thread.join(timeout=2)
        surface.close()
