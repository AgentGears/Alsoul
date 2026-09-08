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
    USER_ALIAS_CONTRACT_VERSION,
    normalize_user_alias,
    parse_open_loop_directive,
)
from alsoul.services.projection_reuse import projection_reuse_blocker
from alsoul.storage import schema


@dataclass(slots=True)
class AliasConversationModel:
    provider_binding_ref: str = "alias-provider"
    model_ref: str = "alias-model-v1"
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


def _append(services, ids, now, *, key: str, text: str, conversation_id: str = "alias-thread"):
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
    return event, F4ConversationOpenLoopService(services).consider_event(event.event_id)


def _label(services, ids, now, *, key: str, a: str, b: str, label: str):
    event = _append(
        services,
        ids,
        now,
        key=key,
        text=f'Call the decision between {a} and {b} "{label}".',
    )
    return event, F4ConversationOpenLoopService(services).consider_event(event.event_id)


def test_user_alias_normalization_is_mechanical():
    directive = parse_open_loop_directive(
        'Call the decision between A and B "  Work   Laptop  ".'
    )
    resume = parse_open_loop_directive('Back to decision "work laptop".')

    assert directive.operation == "LABEL"
    assert directive.alias_key == "work laptop"
    assert resume.operation == "RESUME"
    assert resume.selector_kind == "USER_ALIAS"
    assert resume.selector_contract_version == USER_ALIAS_CONTRACT_VERSION
    assert resume.selector_key == directive.alias_key
    assert normalize_user_alias("Office Computer") != directive.alias_key


def test_alias_assignment_is_source_grounded_and_same_loop_repeat_is_idempotent(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-open", external_subject=str(uuid4())
    )
    _opening, opened = _open(services, ids, now, key="open", a="A", b="B")
    label_event, labeled = _label(
        services, ids, now, key="label", a="A", b="B", label="Work Laptop"
    )
    repeat_event, repeated = _label(
        services, ids, now, key="label-repeat", a="B", b="A", label="work   laptop"
    )

    assert labeled.open_loop_id == opened.open_loop_id
    assert labeled.open_loop_alias_id is not None
    assert repeated.open_loop_alias_id == labeled.open_loop_alias_id
    assert repeated.idempotent_replay

    with services.engine.connect() as conn:
        aliases = conn.execute(select(schema.conversation_open_loop_alias)).mappings().all()
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()

    assert len(aliases) == 1
    assert aliases[0]["open_loop_id"] == opened.open_loop_id
    assert aliases[0]["source_event_id"] == label_event.event_id
    assert aliases[0]["display_label"] == "Work Laptop"
    assert aliases[0]["canonical_alias_key"] == "work laptop"
    assert repeat_event.event_id != label_event.event_id
    assert claim_count == 0
    assert investigation_count == 0


def test_active_alias_namespace_rejects_conflicting_loop(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-conflict", external_subject=str(uuid4())
    )
    _open(services, ids, now, key="one", a="A", b="B")
    _label(services, ids, now, key="label-one", a="A", b="B", label="work")
    _open(services, ids, now, key="two", a="C", b="D")
    conflict = _append(
        services,
        ids,
        now,
        key="label-two",
        text='Call the decision between C and D "WORK".',
    )

    with pytest.raises(DomainError) as excinfo:
        F4ConversationOpenLoopService(services).consider_event(conflict.event_id)
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_ALIAS_CONFLICT"


def test_alias_can_target_one_loop_when_source_reference_is_ambiguous(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-select", external_subject=str(uuid4())
    )
    first_event, first = _open(services, ids, now, key="one", a="A", b="B")
    _label(services, ids, now, key="label", a="A", b="B", label="work laptop")
    _open(services, ids, now, key="two", a="B", b="A")

    current = _append(
        services,
        ids,
        now,
        key="resume-alias",
        text='Back to decision "Work   Laptop".',
        conversation_id="later-thread",
    )
    model = AliasConversationModel()
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
    assert context["selection_policy"] == "EXPLICIT_USER_ALIAS"
    assert context["alias_kind"] == "USER_LABEL"
    assert context["opened_by_event"]["event_id"] == str(first_event.event_id)

    with services.engine.connect() as conn:
        selector = conn.execute(
            select(schema.context_projection_open_loop_alias_selector).where(
                schema.context_projection_open_loop_alias_selector.c.projection_id
                == result.context_projection_id
            )
        ).mappings().one()
        invocation = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.context_projection_id == result.context_projection_id
            )
        ).mappings().one()

    assert selector["open_loop_id"] == first.open_loop_id
    assert selector["selection_basis"] == "EXPLICIT_USER_ALIAS"
    assert selector["selector_key"] == "work laptop"
    assert invocation["renderer_version"] == "f4-renderer-v5"


def test_alias_rename_is_append_oriented_and_old_alias_stops_resolving(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-rename", external_subject=str(uuid4())
    )
    _open(services, ids, now, key="open", a="A", b="B")
    _event, labeled = _label(
        services, ids, now, key="label", a="A", b="B", label="work laptop"
    )

    rename_event = _append(
        services,
        ids,
        now,
        key="rename",
        text='Rename decision "work laptop" to "new laptop".',
    )
    renamed = F4ConversationOpenLoopService(services).consider_event(rename_event.event_id)
    assert renamed.disposition == "RENAMED"
    assert renamed.open_loop_alias_id == labeled.open_loop_alias_id
    assert renamed.replacement_alias_id is not None

    service = F4ConversationOpenLoopService(services)
    with pytest.raises(DomainError) as excinfo:
        service.resolve_decision_loop(
            ids.relationship_id,
            parse_open_loop_directive('Back to decision "work laptop".'),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND"

    selected = service.resolve_decision_loop(
        ids.relationship_id,
        parse_open_loop_directive('Back to decision "NEW LAPTOP".'),
    )
    assert selected.open_loop_id == renamed.open_loop_id
    assert selected.open_loop_alias_id == renamed.replacement_alias_id

    with services.engine.connect() as conn:
        aliases = conn.execute(
            select(schema.conversation_open_loop_alias).order_by(
                schema.conversation_open_loop_alias.c.created_at,
                schema.conversation_open_loop_alias.c.open_loop_alias_id,
            )
        ).mappings().all()
        retirement = conn.execute(
            select(schema.conversation_open_loop_alias_retirement)
        ).mappings().one()
    assert len(aliases) == 2
    assert retirement["retirement_kind"] == "RENAMED"
    assert retirement["replacement_alias_id"] == renamed.replacement_alias_id


def test_remove_alias_does_not_close_loop_and_closed_alias_can_be_reused(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-remove", external_subject=str(uuid4())
    )
    _open(services, ids, now, key="one", a="A", b="B")
    _label(services, ids, now, key="label-one", a="A", b="B", label="work")

    remove_event = _append(
        services, ids, now, key="remove", text='Remove label "WORK".'
    )
    removed = F4ConversationOpenLoopService(services).consider_event(remove_event.event_id)
    assert removed.disposition == "ALIAS_REMOVED"

    service = F4ConversationOpenLoopService(services)
    selection = service.select_current_decision_loop(ids.relationship_id)
    assert selection.open_loop_id == removed.open_loop_id
    with pytest.raises(DomainError) as excinfo:
        service.resolve_decision_loop(
            ids.relationship_id,
            parse_open_loop_directive('Back to decision "work".'),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND"

    close_event = _append(
        services, ids, now, key="close", text="That decision is settled."
    )
    service.consider_event(close_event.event_id)
    _open(services, ids, now, key="two", a="C", b="D")
    _event, reused = _label(
        services, ids, now, key="label-two", a="C", b="D", label="work"
    )
    assert reused.open_loop_alias_id is not None


def test_alias_selected_projection_reuse_ignores_unrelated_loop_but_alias_retirement_blocks(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-reuse", external_subject=str(uuid4())
    )
    _open(services, ids, now, key="one", a="A", b="B")
    _label(services, ids, now, key="label", a="A", b="B", label="work")

    unrelated_event = _append(
        services,
        ids,
        now,
        key="unrelated-opening",
        text="I need to decide between C and D.",
    )
    current = _append(
        services,
        ids,
        now,
        key="alias-resume",
        text='Back to decision "work".',
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

    remove_event = _append(
        services, ids, now, key="remove", text='Remove label "work".'
    )
    F4ConversationOpenLoopService(services).consider_event(remove_event.event_id)
    with services.engine.connect() as conn:
        row = conn.execute(
            select(schema.context_projection).where(
                schema.context_projection.c.projection_id == projection.projection_id
            )
        ).mappings().one()
        assert projection_reuse_blocker(conn, dict(row)) == "CONVERSATION_OPEN_LOOP_ALIAS_RETIRED"


def test_alias_resolve_targets_only_labeled_loop(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-close", external_subject=str(uuid4())
    )
    _open(services, ids, now, key="one", a="A", b="B")
    _event, labeled = _label(
        services, ids, now, key="label", a="A", b="B", label="work"
    )
    _event_two, second = _open(services, ids, now, key="two", a="C", b="D")

    close_event = _append(
        services, ids, now, key="close", text='Resolve decision "work".'
    )
    closed = F4ConversationOpenLoopService(services).consider_event(close_event.event_id)
    assert closed.open_loop_id == labeled.open_loop_id

    selection = F4ConversationOpenLoopService(services).resolve_decision_loop(
        ids.relationship_id,
        parse_open_loop_directive("Back to the decision between C and D."),
    )
    assert selection.open_loop_id == second.open_loop_id
