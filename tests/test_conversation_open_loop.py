from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import FakePresentationAdapter
from alsoul.domain.commands import AppendCounterpartInputCommand, BuildContextProjectionCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services import (
    F4ConversationOpenLoopService,
    FoundationConversationalResponseCoordinator,
)
from alsoul.services.interaction_routing import classify_f4_interaction_text
from alsoul.storage import schema


@dataclass(slots=True)
class OpenLoopConversationModel:
    provider_binding_ref: str = "open-loop-provider"
    model_ref: str = "open-loop-model-v1"
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
        text = (
            "We can return to that decision."
            if "conversation_open_loop_context" in provider_context
            else "Understood."
        )
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
    conversation_id: str = "open-loop-thread",
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


def test_open_loop_opening_is_durable_state_not_memory_or_work(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="open-loop-opening",
        external_subject=str(uuid4()),
    )
    source = _append_input(
        services,
        ids,
        now,
        key="decision-open",
        text="I need to decide between A and B.",
    )

    assert classify_f4_interaction_text("I need to decide between A and B.") == (
        "CONVERSATIONAL_RESPONSE"
    )

    lifecycle = F4ConversationOpenLoopService(services)
    admitted = lifecycle.consider_event(source.event_id)
    replay = lifecycle.consider_event(source.event_id)

    assert admitted.disposition == "OPENED"
    assert admitted.open_loop_id is not None
    assert replay.open_loop_id == admitted.open_loop_id
    assert replay.idempotent_replay is True

    with services.engine.connect() as conn:
        loop = conn.execute(
            select(schema.conversation_open_loop).where(
                schema.conversation_open_loop.c.open_loop_id == admitted.open_loop_id
            )
        ).mappings().one()
        closure_count = conn.execute(
            select(func.count()).select_from(schema.conversation_open_loop_closure)
        ).scalar_one()
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()

    assert loop["relationship_id"] == ids.relationship_id
    assert loop["loop_kind"] == "DECISION"
    assert loop["opened_by_event_id"] == source.event_id
    assert closure_count == 0
    assert claim_count == 0
    assert investigation_count == 0


def test_resume_uses_relationship_scoped_open_loop_after_intervening_exchange(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="open-loop-resume",
        external_subject=str(uuid4()),
    )
    lifecycle = F4ConversationOpenLoopService(services)
    model = OpenLoopConversationModel()
    presentation = FakePresentationAdapter()
    coordinator = FoundationConversationalResponseCoordinator(services)

    opening = _append_input(
        services,
        ids,
        now,
        key="decision-open",
        text="I need to decide between the smaller option and the larger option.",
        conversation_id="thread-a",
    )
    lifecycle.consider_event(opening.event_id)
    coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=opening.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )

    intervening = _append_input(
        services,
        ids,
        now,
        key="intervening-thanks",
        text="Thanks.",
        conversation_id="thread-a",
    )
    coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=intervening.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )

    current = _append_input(
        services,
        ids,
        now,
        key="decision-resume",
        text="Back to that decision.",
        conversation_id="thread-b",
    )
    result = coordinator.respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
    )

    assert model.calls == 3
    context = model.contexts[-1]
    assert "prior_timeline_context" not in context
    loop_context = context["conversation_open_loop_context"]
    assert loop_context["selection_policy"] == "CURRENT_OPEN_DECISION_LOOP"
    assert loop_context["loop_kind"] == "DECISION"
    assert loop_context["opened_by_event"]["event_id"] == str(opening.event_id)
    assert loop_context["opened_by_event"]["content_text"].startswith(
        "I need to decide between"
    )
    assert context["personal_context"] == []
    assert context["world_context"] == []

    with services.engine.connect() as conn:
        selected = conn.execute(
            select(schema.context_projection_event)
            .where(
                schema.context_projection_event.c.projection_id
                == result.context_projection_id
            )
            .order_by(schema.context_projection_event.c.ordinal)
        ).mappings().all()
        loop_item = conn.execute(
            select(schema.context_projection_open_loop_item).where(
                schema.context_projection_open_loop_item.c.projection_id
                == result.context_projection_id
            )
        ).mappings().one()
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()

    assert [row["event_id"] for row in selected] == [opening.event_id, current.event_id]
    assert loop_item["selection_basis"] == "CURRENT_OPEN_DECISION_LOOP"
    assert investigation_count == 0


@pytest.mark.parametrize(
    ("closure_text", "expected_disposition", "expected_kind"),
    [
        ("I made that decision.", "RESOLVED", "RESOLVED"),
        ("Let's drop that decision.", "CANCELLED", "CANCELLED"),
    ],
)
def test_terminal_loop_transition_is_append_only_and_blocks_resume(
    services,
    bootstrapper,
    now,
    closure_text,
    expected_disposition,
    expected_kind,
):
    ids = bootstrapper.bootstrap(
        identity_namespace=f"open-loop-close-{expected_kind.lower()}",
        external_subject=str(uuid4()),
    )
    lifecycle = F4ConversationOpenLoopService(services)
    opening = _append_input(
        services,
        ids,
        now,
        key="decision-open",
        text="I need to decide between A and B.",
    )
    opened = lifecycle.consider_event(opening.event_id)

    closure_event = _append_input(
        services,
        ids,
        now,
        key="decision-close",
        text=closure_text,
    )
    closed = lifecycle.consider_event(closure_event.event_id)
    replay = lifecycle.consider_event(closure_event.event_id)

    assert closed.disposition == expected_disposition
    assert closed.open_loop_id == opened.open_loop_id
    assert replay.idempotent_replay is True

    with services.engine.connect() as conn:
        closure = conn.execute(
            select(schema.conversation_open_loop_closure).where(
                schema.conversation_open_loop_closure.c.open_loop_id
                == opened.open_loop_id
            )
        ).mappings().one()
    assert closure["closure_kind"] == expected_kind
    assert closure["source_event_id"] == closure_event.event_id

    resume = _append_input(
        services,
        ids,
        now,
        key="decision-resume",
        text="Back to that decision.",
    )
    model = OpenLoopConversationModel()
    with pytest.raises(DomainError) as excinfo:
        FoundationConversationalResponseCoordinator(services).respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=resume.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=FakePresentationAdapter(),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_UNAVAILABLE"
    assert model.calls == 0


def test_multiple_open_decision_loops_fail_closed_instead_of_latest_wins(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="open-loop-ambiguous",
        external_subject=str(uuid4()),
    )
    lifecycle = F4ConversationOpenLoopService(services)
    first = _append_input(
        services,
        ids,
        now,
        key="decision-one",
        text="I need to decide between A and B.",
    )
    second = _append_input(
        services,
        ids,
        now,
        key="decision-two",
        text="I need to decide between C and D.",
    )
    lifecycle.consider_event(first.event_id)
    lifecycle.consider_event(second.event_id)

    current = _append_input(
        services,
        ids,
        now,
        key="resume-ambiguous",
        text="Back to that decision.",
    )
    model = OpenLoopConversationModel()
    with pytest.raises(DomainError) as excinfo:
        FoundationConversationalResponseCoordinator(services).respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=FakePresentationAdapter(),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_AMBIGUOUS"
    assert model.calls == 0


def test_projection_reuse_rechecks_active_loop_uniqueness_before_provider_execution(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="open-loop-reuse-ambiguity",
        external_subject=str(uuid4()),
    )
    lifecycle = F4ConversationOpenLoopService(services)

    first = _append_input(
        services,
        ids,
        now,
        key="decision-one",
        text="I need to decide between A and B.",
    )
    lifecycle.consider_event(first.event_id)

    # This opening is already durable Timeline history but has not yet been admitted
    # as an open loop. It can therefore become loop state after the current-input
    # frontier and projection are already fixed, without advancing the Timeline.
    second = _append_input(
        services,
        ids,
        now,
        key="decision-two",
        text="I need to decide between C and D.",
    )
    current = _append_input(
        services,
        ids,
        now,
        key="resume-one",
        text="Back to that decision.",
    )

    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            required_personal_predicates=(),
            required_world_result_ids=(),
        )
    )

    with services.engine.connect() as conn:
        timeline_frontier = conn.execute(
            select(schema.relationship_timeline_head.c.last_timeline_seq).where(
                schema.relationship_timeline_head.c.relationship_id == ids.relationship_id
            )
        ).scalar_one()
    assert projection.source_timeline_frontier == timeline_frontier

    lifecycle.consider_event(second.event_id)

    # Recovery sees the old projection, but provider execution must not reuse it now
    # that the relationship has two unresolved decision loops. Rebuilding under the
    # current contract fails closed as ambiguous, and the model is never called.
    model = OpenLoopConversationModel()
    with pytest.raises(DomainError) as excinfo:
        FoundationConversationalResponseCoordinator(services).respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=model,
            presentation_adapter=FakePresentationAdapter(),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_AMBIGUOUS"
    assert model.calls == 0
