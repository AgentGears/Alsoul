from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.services import F4ConversationOpenLoopService
from alsoul.storage import schema

_CLOSURE_RECEIPT_SCOPE = "ConversationOpenLoopClosure"


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
            conversation_id="alias-closure-replay",
        )
    )


def _open_and_label(services, ids, now):
    service = F4ConversationOpenLoopService(services)
    opening = _append(
        services,
        ids,
        now,
        key="open",
        text="I need to decide between A and B.",
    )
    opened = service.consider_event(opening.event_id)
    label = _append(
        services,
        ids,
        now,
        key="label",
        text='Call the decision between A and B "work".',
    )
    labeled = service.consider_event(label.event_id)
    return service, opened, labeled


@pytest.mark.parametrize(
    ("text", "expected_disposition"),
    [
        ('Resolve decision "work".', "RESOLVED"),
        ('Cancel decision "work".', "CANCELLED"),
    ],
)
def test_alias_selected_closure_replay_preserves_selector_identity(
    services,
    bootstrapper,
    now,
    text,
    expected_disposition,
):
    ids = bootstrapper.bootstrap(
        identity_namespace=f"alias-closure-{expected_disposition.lower()}",
        external_subject=str(uuid4()),
    )
    service, opened, labeled = _open_and_label(services, ids, now)
    closure_event = _append(
        services,
        ids,
        now,
        key=f"close-{expected_disposition.lower()}",
        text=text,
    )

    first = service.consider_event(closure_event.event_id)
    replay = service.consider_event(closure_event.event_id)

    assert first.disposition == expected_disposition
    assert first.open_loop_id == opened.open_loop_id
    assert first.loop_kind == "DECISION"
    assert first.open_loop_alias_id == labeled.open_loop_alias_id

    assert replay.idempotent_replay
    assert replay.disposition == first.disposition
    assert replay.open_loop_id == first.open_loop_id
    assert replay.loop_kind == first.loop_kind
    assert replay.open_loop_reference_id == first.open_loop_reference_id
    assert replay.open_loop_alias_id == first.open_loop_alias_id

    with services.engine.connect() as conn:
        receipt = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope == _CLOSURE_RECEIPT_SCOPE,
                schema.operation_receipt.c.operation_id == closure_event.event_id,
            )
        ).mappings().one()

    assert receipt["result_ref"] == opened.open_loop_id
    assert receipt["result_json"]["open_loop_alias_id"] == str(labeled.open_loop_alias_id)
