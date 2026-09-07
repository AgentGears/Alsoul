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
from alsoul.services import F4ConversationOpenLoopService, FoundationConversationalResponseCoordinator
from alsoul.services.conversation_open_loop_context import (
    DECISION_REFERENCE_CONTRACT_VERSION,
    canonicalize_decision_option_pair,
    parse_open_loop_directive,
)
from alsoul.services.projection_reuse import projection_reuse_blocker
from alsoul.storage import schema


@dataclass(slots=True)
class TargetableLoopModel:
    provider_binding_ref: str = "targetable-loop-provider"
    model_ref: str = "targetable-loop-model-v1"
    calls: int = 0
    contexts: list[dict] = field(default_factory=list)

    def provider_request_digest(self, provider_context: dict) -> str:
        return sha256(
            json.dumps(provider_context, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        self.calls += 1
        self.contexts.append(provider_context)
        return FoundationResponseDraft(
            segments=(FoundationResponseSegment("COMPANION_EXPRESSION", "Understood.", None),)
        )


def _append(services, ids, now, *, key: str, text: str, conversation_id: str = "target-thread"):
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


def _open(services, ids, now, *, key: str, a: str, b: str):
    event = _append(
        services,
        ids,
        now,
        key=key,
        text=f"I need to decide between {a} and {b}.",
    )
    result = F4ConversationOpenLoopService(services).consider_event(event.event_id)
    return event, result


def test_reference_normalization_is_mechanical_and_order_independent():
    opening = parse_open_loop_directive("I need to decide between  A  and B.")
    reverse = parse_open_loop_directive("Back to the decision between b and a.")
    paraphrase = parse_open_loop_directive("Back to the decision between alpha and beta.")

    assert opening.operation == "OPEN"
    assert reverse.operation == "RESUME"
    assert opening.selector_contract_version == DECISION_REFERENCE_CONTRACT_VERSION
    assert opening.selector_key == reverse.selector_key
    assert opening.selector_key == canonicalize_decision_option_pair("A", "B")
    assert paraphrase.selector_key != opening.selector_key


def test_opening_atomically_persists_distinct_reference_identity(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-open", external_subject=str(uuid4()))
    event, opened = _open(services, ids, now, key="open", a="A", b="B")

    assert opened.open_loop_id is not None
    assert opened.open_loop_reference_id is not None
    assert opened.open_loop_id != opened.open_loop_reference_id

    with services.engine.connect() as conn:
        reference = conn.execute(
            select(schema.conversation_open_loop_reference).where(
                schema.conversation_open_loop_reference.c.open_loop_reference_id
                == opened.open_loop_reference_id
            )
        ).mappings().one()
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        investigation_count = conn.execute(select(func.count()).select_from(schema.investigation)).scalar_one()

    assert reference["open_loop_id"] == opened.open_loop_id
    assert reference["source_event_id"] == event.event_id
    assert reference["canonical_reference_key"] == canonicalize_decision_option_pair("A", "B")
    assert claim_count == 0
    assert investigation_count == 0


def test_explicit_reference_selects_one_of_multiple_active_loops(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-select", external_subject=str(uuid4()))
    first_event, first = _open(services, ids, now, key="one", a="A", b="B")
    _open(services, ids, now, key="two", a="C", b="D")

    current = _append(
        services,
        ids,
        now,
        key="resume-a-b",
        text="Back to the decision between B and A.",
        conversation_id="other-thread",
    )
    model = TargetableLoopModel()
    result = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=FakePresentationAdapter(),
    )

    assert model.calls == 1
    context = model.contexts[0]["conversation_open_loop_context"]
    assert context["selection_policy"] == "EXPLICIT_DECISION_REFERENCE"
    assert context["reference_kind"] == "DECISION_OPTION_PAIR"
    assert context["opened_by_event"]["event_id"] == str(first_event.event_id)

    with services.engine.connect() as conn:
        selector = conn.execute(
            select(schema.context_projection_open_loop_selector).where(
                schema.context_projection_open_loop_selector.c.projection_id
                == result.context_projection_id
            )
        ).mappings().one()
        invocation = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.context_projection_id == result.context_projection_id
            )
        ).mappings().one()

    assert selector["open_loop_id"] == first.open_loop_id
    assert selector["open_loop_reference_id"] == first.open_loop_reference_id
    assert selector["selection_basis"] == "EXPLICIT_DECISION_REFERENCE"
    assert invocation["renderer_version"] == "f4-renderer-v4"


def test_unqualified_reference_remains_ambiguous_with_multiple_active_loops(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-unqualified", external_subject=str(uuid4()))
    _open(services, ids, now, key="one", a="A", b="B")
    _open(services, ids, now, key="two", a="C", b="D")
    current = _append(services, ids, now, key="resume", text="Back to that decision.")
    model = TargetableLoopModel()

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


def test_explicit_reference_missing_or_duplicate_fails_before_model(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-errors", external_subject=str(uuid4()))
    _open(services, ids, now, key="one", a="A", b="B")

    missing = _append(services, ids, now, key="missing", text="Back to the decision between C and D.")
    with pytest.raises(DomainError) as excinfo:
        FoundationConversationalResponseCoordinator(services).respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=missing.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            model_adapter=TargetableLoopModel(),
            presentation_adapter=FakePresentationAdapter(),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND"

    _open(services, ids, now, key="duplicate", a="B", b="A")
    current = _append(services, ids, now, key="duplicate-resume", text="Back to the decision between A and B.")
    model = TargetableLoopModel()
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


def test_qualified_closure_targets_only_matching_loop(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-close", external_subject=str(uuid4()))
    _event_one, first = _open(services, ids, now, key="one", a="A", b="B")
    _event_two, second = _open(services, ids, now, key="two", a="C", b="D")

    close_event = _append(
        services,
        ids,
        now,
        key="close-a-b",
        text="The decision between B and A is settled.",
    )
    closed = F4ConversationOpenLoopService(services).consider_event(close_event.event_id)
    assert closed.open_loop_id == first.open_loop_id

    service = F4ConversationOpenLoopService(services)
    selection = service.resolve_decision_loop(
        ids.relationship_id,
        parse_open_loop_directive("Back to the decision between C and D."),
    )
    assert selection.open_loop_id == second.open_loop_id


def test_explicit_projection_reuse_ignores_unrelated_loop_but_rejects_matching_loop(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="target-ref-reuse", external_subject=str(uuid4()))
    _open(services, ids, now, key="one", a="A", b="B")

    unrelated_event = _append(
        services,
        ids,
        now,
        key="unrelated-opening",
        text="I need to decide between C and D.",
    )
    matching_event = _append(
        services,
        ids,
        now,
        key="matching-opening",
        text="I need to decide between B and A.",
    )
    current = _append(
        services,
        ids,
        now,
        key="explicit-resume",
        text="Back to the decision between A and B.",
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

    F4ConversationOpenLoopService(services).consider_event(unrelated_event.event_id)
    with services.engine.connect() as conn:
        row = conn.execute(
            select(schema.context_projection).where(
                schema.context_projection.c.projection_id == projection.projection_id
            )
        ).mappings().one()
        assert projection_reuse_blocker(conn, dict(row)) is None

    F4ConversationOpenLoopService(services).consider_event(matching_event.event_id)
    with services.engine.connect() as conn:
        row = conn.execute(
            select(schema.context_projection).where(
                schema.context_projection.c.projection_id == projection.projection_id
            )
        ).mappings().one()
        assert projection_reuse_blocker(conn, dict(row)) == "CONVERSATION_OPEN_LOOP_SELECTION_AMBIGUOUS"
