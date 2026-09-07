from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import FakePresentationAdapter
from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services import FoundationConversationalResponseCoordinator
from alsoul.services.interaction_routing import classify_f4_interaction_text
from alsoul.storage import schema


@dataclass(slots=True)
class ContextAwareConversationModel:
    provider_binding_ref: str = "context-conversation-provider"
    model_ref: str = "context-conversation-model-v1"
    calls: int = 0
    contexts: list[dict] = field(default_factory=list)

    def provider_request_digest(self, provider_context: dict) -> str:
        encoded = json.dumps(
            provider_context,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        self.calls += 1
        self.contexts.append(provider_context)
        if "prior_timeline_context" in provider_context:
            text = "I think that exchange was clear."
        else:
            text = "Hello. I'm here."
        return FoundationResponseDraft(
            segments=(
                FoundationResponseSegment(
                    "COMPANION_EXPRESSION",
                    text,
                    None,
                ),
            )
        )


def _append_input(
    services,
    ids,
    now,
    *,
    key: str,
    text: str,
    conversation_id: str = "context-thread",
):
    return services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=key,
            content_text=text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id=conversation_id,
        )
    )


def _present_first_exchange(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="prior-timeline-context",
        external_subject=str(uuid4()),
    )
    first_input = _append_input(
        services,
        ids,
        now,
        key="first-input",
        text="Hello.",
    )
    model = ContextAwareConversationModel()
    presentation = FakePresentationAdapter()
    coordinator = FoundationConversationalResponseCoordinator(services)
    first_result = coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=first_input.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )
    return ids, first_input, first_result, model, presentation, coordinator


def test_bounded_contextual_form_projects_exact_immediately_prior_exchange(
    services, bootstrapper, now
):
    ids, first_input, first_result, model, presentation, coordinator = (
        _present_first_exchange(services, bootstrapper, now)
    )
    current = _append_input(
        services,
        ids,
        now,
        key="contextual-input",
        text="What do you think about that?",
    )

    assert (
        classify_f4_interaction_text("What do you think about that?")
        == "CONVERSATIONAL_RESPONSE"
    )

    result = coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )

    assert model.calls == 2
    assert "prior_timeline_context" not in model.contexts[0]
    prior_context = model.contexts[1]["prior_timeline_context"]
    assert prior_context["selection_policy"] == "IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE"
    assert [event["content_text"] for event in prior_context["events"]] == [
        "Hello.",
        "Hello. I'm here.",
    ]
    assert [event["event_kind"] for event in prior_context["events"]] == [
        "COUNTERPART_INPUT",
        "COMPANION_PRESENTED_OUTPUT",
    ]
    assert model.contexts[1]["personal_context"] == []
    assert model.contexts[1]["world_context"] == []

    with services.engine.connect() as conn:
        selected = conn.execute(
            select(schema.context_projection_event)
            .where(
                schema.context_projection_event.c.projection_id
                == result.context_projection_id
            )
            .order_by(schema.context_projection_event.c.ordinal)
        ).mappings().all()
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()
        world_result_count = conn.execute(
            select(func.count()).select_from(schema.world_result)
        ).scalar_one()
        invocation = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.context_projection_id
                == result.context_projection_id
            )
        ).mappings().one()

    assert [row["event_id"] for row in selected] == [
        first_input.event_id,
        first_result.presented_event_id,
        current.event_id,
    ]
    assert investigation_count == 0
    assert world_result_count == 0
    assert invocation["renderer_version"] == "f4-renderer-v2"


def test_contextual_form_fails_closed_without_immediately_prior_presented_exchange(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="prior-timeline-empty",
        external_subject=str(uuid4()),
    )
    current = _append_input(
        services,
        ids,
        now,
        key="contextual-first-input",
        text="What do you think about that?",
    )
    model = ContextAwareConversationModel()
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

    assert excinfo.value.code == "CONVERSATIONAL_CONTEXT_UNAVAILABLE"
    assert model.calls == 0
    assert presentation.attempts == 0
    with services.engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count()).select_from(schema.context_projection)
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                select(func.count()).select_from(schema.model_invocation)
            ).scalar_one()
            == 0
        )


def test_contextual_reference_does_not_cross_conversation_boundary(
    services, bootstrapper, now
):
    ids, _first_input, _first_result, model, presentation, coordinator = (
        _present_first_exchange(services, bootstrapper, now)
    )
    current = _append_input(
        services,
        ids,
        now,
        key="other-thread-contextual-input",
        text="Tell me what you think about it.",
        conversation_id="other-thread",
    )

    with pytest.raises(DomainError) as excinfo:
        coordinator.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=presentation,
        )

    assert excinfo.value.code == "CONVERSATIONAL_CONTEXT_BOUNDARY_MISMATCH"
    assert model.calls == 1
    assert presentation.attempts == 1


def test_contextual_projection_survives_process_loss_after_generation_without_reselection(
    services, bootstrapper, now
):
    ids, first_input, first_result, model, presentation, coordinator = (
        _present_first_exchange(services, bootstrapper, now)
    )
    current = _append_input(
        services,
        ids,
        now,
        key="contextual-recovery-input",
        text="What do you think of it?",
    )

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

    assert model.calls == 2
    recovered = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
        after_process_loss=True,
    )
    assert model.calls == 2

    with services.engine.connect() as conn:
        selected = conn.execute(
            select(schema.context_projection_event)
            .where(
                schema.context_projection_event.c.projection_id
                == recovered.context_projection_id
            )
            .order_by(schema.context_projection_event.c.ordinal)
        ).mappings().all()

    assert [row["event_id"] for row in selected] == [
        first_input.event_id,
        first_result.presented_event_id,
        current.event_id,
    ]
