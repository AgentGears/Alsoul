from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import FakePresentationAdapter
from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services import FoundationConversationalResponseCoordinator
from alsoul.storage import schema


@dataclass(slots=True)
class CountingConversationalModelAdapter:
    provider_binding_ref: str = "conversation-fixture-provider"
    model_ref: str = "conversation-fixture-model-v1"
    source_ref: UUID | None = None
    calls: int = 0

    def provider_request_digest(self, provider_context: dict) -> str:
        encoded = json.dumps(
            provider_context,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        self.calls += 1
        assert provider_context["personal_context"] == []
        assert provider_context["world_context"] == []
        return FoundationResponseDraft(
            segments=(
                FoundationResponseSegment(
                    "COMPANION_EXPRESSION",
                    "I'm here and ready to talk with you.",
                    self.source_ref,
                ),
            )
        )


def _prepare_conversational_input(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="conversation-response",
        external_subject=str(uuid4()),
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="conversation-input",
            content_text="How are you?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="conversation-response",
        )
    )
    return ids, current


def test_conversational_response_skips_world_state_and_presents_one_expression(
    services, bootstrapper, now
):
    ids, current = _prepare_conversational_input(services, bootstrapper, now)
    model = CountingConversationalModelAdapter()
    presentation = FakePresentationAdapter()
    coordinator = FoundationConversationalResponseCoordinator(services)

    result = coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )

    with services.engine.connect() as conn:
        counts = {
            "investigations": conn.execute(
                select(func.count()).select_from(schema.investigation)
            ).scalar_one(),
            "observations": conn.execute(
                select(func.count()).select_from(schema.observation)
            ).scalar_one(),
            "world_results": conn.execute(
                select(func.count()).select_from(schema.world_result)
            ).scalar_one(),
            "projections": conn.execute(
                select(func.count()).select_from(schema.context_projection)
            ).scalar_one(),
            "personal_items": conn.execute(
                select(func.count()).select_from(schema.context_projection_personal_item)
            ).scalar_one(),
            "world_items": conn.execute(
                select(func.count()).select_from(schema.context_projection_world_item)
            ).scalar_one(),
            "model_invocations": conn.execute(
                select(func.count()).select_from(schema.model_invocation)
            ).scalar_one(),
            "generated": conn.execute(
                select(func.count()).select_from(schema.generated_output)
            ).scalar_one(),
            "outputs": conn.execute(
                select(func.count()).select_from(schema.companion_output)
            ).scalar_one(),
            "presented": conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT"
                )
            ).scalar_one(),
        }
        generated = conn.execute(
            select(schema.generated_output).where(
                schema.generated_output.c.generated_output_id
                == result.generated_output_id
            )
        ).mappings().one()
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == result.presented_event_id
            )
        ).mappings().one()

    assert counts == {
        "investigations": 0,
        "observations": 0,
        "world_results": 0,
        "projections": 1,
        "personal_items": 0,
        "world_items": 0,
        "model_invocations": 1,
        "generated": 1,
        "outputs": 1,
        "presented": 1,
    }
    assert model.calls == 1
    assert presentation.attempts == 1
    assert generated["semantic_payload_json"] == {
        "segments": [
            {
                "epistemic_kind": "COMPANION_EXPRESSION",
                "text": "I'm here and ready to talk with you.",
                "source_ref": None,
            }
        ]
    }
    assert event["content_text"] == "I'm here and ready to talk with you."
    assert event["reply_to_event_id"] == current.event_id

    replay = coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )
    assert replay == result
    assert model.calls == 1
    assert presentation.attempts == 1


def test_conversational_response_recovers_committed_generation_without_regeneration(
    services, bootstrapper, now
):
    ids, current = _prepare_conversational_input(services, bootstrapper, now)
    model = CountingConversationalModelAdapter()
    presentation = FakePresentationAdapter()
    coordinator = FoundationConversationalResponseCoordinator(services)

    class ProcessLost(RuntimeError):
        pass

    def checkpoint(stage: str) -> None:
        if stage == "GENERATED_OUTPUT_COMMITTED":
            raise ProcessLost()

    with pytest.raises(ProcessLost):
        coordinator.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=presentation,
            checkpoint=checkpoint,
        )

    assert model.calls == 1
    assert presentation.attempts == 0

    recovered = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
        after_process_loss=True,
    )

    assert recovered.presented_event_id is not None
    assert model.calls == 1
    assert presentation.attempts == 1


def test_conversational_adoption_rejects_source_attribution(
    services, bootstrapper, now
):
    ids, current = _prepare_conversational_input(services, bootstrapper, now)
    model = CountingConversationalModelAdapter(source_ref=uuid4())
    presentation = FakePresentationAdapter()

    with pytest.raises(DomainError) as excinfo:
        FoundationConversationalResponseCoordinator(services).respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=presentation,
        )

    assert excinfo.value.code == "OUTPUT_CONTENT_POLICY_REJECTED"
    assert model.calls == 1
    assert presentation.attempts == 0
    with services.engine.connect() as conn:
        generated_count = conn.execute(
            select(func.count()).select_from(schema.generated_output)
        ).scalar_one()
        output_count = conn.execute(
            select(func.count()).select_from(schema.companion_output)
        ).scalar_one()
    assert generated_count == 1
    assert output_count == 0
