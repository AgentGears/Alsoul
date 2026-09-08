from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.services import F4ConversationOpenLoopService
from alsoul.services.conversation_open_loop_context import parse_open_loop_directive
from alsoul.services.interaction_routing import classify_f4_interaction_text
from alsoul.storage import schema

_ALIAS_ASSIGNMENT_RECEIPT_SCOPE = "ConversationOpenLoopAliasAssignment"


def _append(services, ids, now, *, key: str, text: str):
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
            conversation_id="alias-review-regression",
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
    return F4ConversationOpenLoopService(services).consider_event(event.event_id)


def _label(services, ids, now, *, key: str, a: str, b: str, label: str):
    event = _append(
        services,
        ids,
        now,
        key=key,
        text=f'Call the decision between {a} and {b} "{label}".',
    )
    result = F4ConversationOpenLoopService(services).consider_event(event.event_id)
    return event, result


def test_same_loop_alias_noop_receipt_survives_later_retirement(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-review-receipt",
        external_subject=str(uuid4()),
    )
    opened = _open(services, ids, now, key="open", a="A", b="B")
    _first_event, first = _label(
        services,
        ids,
        now,
        key="label-first",
        a="A",
        b="B",
        label="work",
    )
    repeat_event, repeated = _label(
        services,
        ids,
        now,
        key="label-repeat",
        a="B",
        b="A",
        label="WORK",
    )

    assert repeated.idempotent_replay
    assert repeated.open_loop_id == opened.open_loop_id
    assert repeated.open_loop_alias_id == first.open_loop_alias_id

    with services.engine.connect() as conn:
        receipt = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope
                == _ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                schema.operation_receipt.c.operation_id == repeat_event.event_id,
            )
        ).mappings().one()
    assert receipt["result_ref"] == first.open_loop_alias_id

    remove_event = _append(
        services,
        ids,
        now,
        key="remove",
        text='Remove label "work".',
    )
    service = F4ConversationOpenLoopService(services)
    service.consider_event(remove_event.event_id)

    replay = service.consider_event(repeat_event.event_id)
    assert replay.idempotent_replay
    assert replay.open_loop_id == repeated.open_loop_id
    assert replay.loop_kind == repeated.loop_kind
    assert replay.open_loop_alias_id == repeated.open_loop_alias_id

    with pytest.raises(DomainError) as excinfo:
        service.resolve_decision_loop(
            ids.relationship_id,
            parse_open_loop_directive('Back to decision "work".'),
        )
    assert excinfo.value.code == "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND"


@pytest.mark.parametrize(
    "text",
    [
        'Call the decision between A and B "   ".',
        'Back to decision "   ".',
        'Resolve decision "   ".',
        'Cancel decision "   ".',
        'Rename decision "   " to "work".',
        'Rename decision "work" to "   ".',
        'Remove label "   ".',
    ],
)
def test_blank_alias_directives_are_bounded_as_unsupported(text):
    assert parse_open_loop_directive(text).operation == "NONE"
    assert classify_f4_interaction_text(text) == "UNSUPPORTED"


def test_rename_replay_preserves_original_semantic_result(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-review-rename",
        external_subject=str(uuid4()),
    )
    _open(services, ids, now, key="open", a="A", b="B")
    _label(
        services,
        ids,
        now,
        key="label",
        a="A",
        b="B",
        label="work",
    )
    rename_event = _append(
        services,
        ids,
        now,
        key="rename",
        text='Rename decision "work" to "office".',
    )
    service = F4ConversationOpenLoopService(services)

    first = service.consider_event(rename_event.event_id)
    replay = service.consider_event(rename_event.event_id)

    assert replay.idempotent_replay
    assert replay.disposition == first.disposition == "RENAMED"
    assert replay.open_loop_id == first.open_loop_id
    assert replay.loop_kind == first.loop_kind == "DECISION"
    assert replay.open_loop_alias_id == first.open_loop_alias_id
    assert replay.replacement_alias_id == first.replacement_alias_id


def test_remove_replay_preserves_original_semantic_result(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="alias-review-remove",
        external_subject=str(uuid4()),
    )
    _open(services, ids, now, key="open", a="A", b="B")
    _label(
        services,
        ids,
        now,
        key="label",
        a="A",
        b="B",
        label="work",
    )
    remove_event = _append(
        services,
        ids,
        now,
        key="remove",
        text='Remove label "work".',
    )
    service = F4ConversationOpenLoopService(services)

    first = service.consider_event(remove_event.event_id)
    replay = service.consider_event(remove_event.event_id)

    assert replay.idempotent_replay
    assert replay.disposition == first.disposition == "ALIAS_REMOVED"
    assert replay.open_loop_id == first.open_loop_id
    assert replay.loop_kind == first.loop_kind == "DECISION"
    assert replay.open_loop_alias_id == first.open_loop_alias_id
