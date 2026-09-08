from __future__ import annotations

from typing import Any

from sqlalchemy import select

from alsoul.services.conversation_context import requires_prior_timeline_context
from alsoul.services.conversation_open_loop_context import (
    DECISION_REFERENCE_KIND,
    parse_open_loop_directive,
    requires_conversation_open_loop_context,
)
from alsoul.storage import schema


def projection_reuse_blocker(conn, projection: dict[str, Any]) -> str | None:
    """Return why one reactive ContextProjection must not be reused.

    F4 retries may reuse an immutable projection only while the canonical state it
    fenced is still current. Context-dependent inputs additionally require the exact
    durable selection contract associated with their committed projection; durable
    selection lineage takes precedence over re-running reference resolution.
    """

    if projection["purpose"] != "RESPOND_TO_INTERACTION":
        return "WRONG_PURPOSE"
    if (
        projection["relationship_id"] is None
        or projection["current_input_event_id"] is None
        or projection["source_relationship_revision"] is None
        or projection["source_timeline_frontier"] is None
    ):
        return "REACTIVE_BINDING_INCOMPLETE"

    current_input = conn.execute(
        select(schema.interaction_event).where(
            schema.interaction_event.c.event_id == projection["current_input_event_id"]
        )
    ).mappings().one_or_none()
    if (
        current_input is None
        or current_input["relationship_id"] != projection["relationship_id"]
        or current_input["event_kind"] != "COUNTERPART_INPUT"
        or current_input["actor_kind"] != "COUNTERPART"
    ):
        return "CURRENT_INPUT_INVALID"

    projected_input = conn.execute(
        select(schema.context_projection_event.c.event_id).where(
            schema.context_projection_event.c.projection_id == projection["projection_id"],
            schema.context_projection_event.c.event_id == projection["current_input_event_id"],
        )
    ).scalar_one_or_none()
    if projected_input is None:
        return "CURRENT_INPUT_NOT_PROJECTED"

    open_loop_item = conn.execute(
        select(schema.context_projection_open_loop_item.c.open_loop_id).where(
            schema.context_projection_open_loop_item.c.projection_id
            == projection["projection_id"]
        )
    ).scalar_one_or_none()
    if open_loop_item is not None or requires_conversation_open_loop_context(
        current_input["content_text"]
    ):
        blocker = _open_loop_selection_blocker(
            conn,
            projection=projection,
            current_input=dict(current_input),
        )
        if blocker is not None:
            return blocker
    elif requires_prior_timeline_context(current_input["content_text"]):
        blocker = _contextual_selection_blocker(
            conn,
            projection=projection,
            current_input=dict(current_input),
        )
        if blocker is not None:
            return blocker

    self_head = conn.execute(
        select(schema.self_head).where(
            schema.self_head.c.person_id == projection["companion_person_id"]
        )
    ).mappings().one_or_none()
    if self_head is None:
        return "SELF_HEAD_MISSING"
    if self_head["current_revision"] != projection["source_self_revision"]:
        return "SELF_REVISION_CHANGED"

    relationship_head = conn.execute(
        select(schema.relationship_head).where(
            schema.relationship_head.c.relationship_id == projection["relationship_id"]
        )
    ).mappings().one_or_none()
    if relationship_head is None:
        return "RELATIONSHIP_HEAD_MISSING"
    if (
        relationship_head["current_revision"]
        != projection["source_relationship_revision"]
    ):
        return "RELATIONSHIP_REVISION_CHANGED"

    timeline_head = conn.execute(
        select(schema.relationship_timeline_head).where(
            schema.relationship_timeline_head.c.relationship_id
            == projection["relationship_id"]
        )
    ).mappings().one_or_none()
    if timeline_head is None:
        return "TIMELINE_HEAD_MISSING"
    if timeline_head["last_timeline_seq"] != projection["source_timeline_frontier"]:
        return "TIMELINE_ADVANCED"
    if current_input["timeline_seq"] != projection["source_timeline_frontier"]:
        return "CURRENT_INPUT_NOT_AT_FRONTIER"

    return None


def _open_loop_selection_blocker(
    conn,
    *,
    projection: dict[str, Any],
    current_input: dict[str, Any],
) -> str | None:
    relationship = conn.execute(
        select(schema.relationship_identity).where(
            schema.relationship_identity.c.relationship_id
            == projection["relationship_id"]
        )
    ).mappings().one_or_none()
    if relationship is None:
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"

    items = conn.execute(
        select(
            schema.context_projection_open_loop_item,
            schema.conversation_open_loop.c.relationship_id,
            schema.conversation_open_loop.c.loop_kind,
            schema.conversation_open_loop.c.opened_by_event_id,
        )
        .join(
            schema.conversation_open_loop,
            schema.context_projection_open_loop_item.c.open_loop_id
            == schema.conversation_open_loop.c.open_loop_id,
        )
        .where(
            schema.context_projection_open_loop_item.c.projection_id
            == projection["projection_id"]
        )
    ).mappings().all()
    if len(items) != 1:
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
    item = items[0]
    if (
        int(item["ordinal"]) != 0
        or item["selection_basis"] != "CURRENT_OPEN_DECISION_LOOP"
        or item["relationship_id"] != projection["relationship_id"]
        or item["loop_kind"] != "DECISION"
    ):
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"

    selector = conn.execute(
        select(schema.context_projection_open_loop_selector).where(
            schema.context_projection_open_loop_selector.c.projection_id
            == projection["projection_id"]
        )
    ).mappings().one_or_none()

    explicit = False
    pinned_contract = None
    pinned_key = None
    if selector is None:
        # Compatibility for schema-v2 projections. Those could only have been
        # admitted by the unqualified decision-resume contract.
        directive = parse_open_loop_directive(current_input["content_text"])
        if directive.operation != "RESUME" or directive.selector_kind != "UNQUALIFIED":
            return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
    else:
        if selector["open_loop_id"] != item["open_loop_id"]:
            return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
        if selector["selection_basis"] == "CURRENT_OPEN_DECISION_LOOP":
            if any(
                selector[name] is not None
                for name in (
                    "open_loop_reference_id",
                    "selector_contract_version",
                    "selector_key",
                )
            ):
                return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
        elif selector["selection_basis"] == "EXPLICIT_DECISION_REFERENCE":
            if any(
                selector[name] is None
                for name in (
                    "open_loop_reference_id",
                    "selector_contract_version",
                    "selector_key",
                )
            ):
                return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
            reference = conn.execute(
                select(schema.conversation_open_loop_reference).where(
                    schema.conversation_open_loop_reference.c.open_loop_reference_id
                    == selector["open_loop_reference_id"]
                )
            ).mappings().one_or_none()
            if (
                reference is None
                or reference["open_loop_id"] != item["open_loop_id"]
                or reference["reference_kind"] != DECISION_REFERENCE_KIND
                or reference["reference_contract_version"]
                != selector["selector_contract_version"]
                or reference["canonical_reference_key"] != selector["selector_key"]
            ):
                return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
            explicit = True
            pinned_contract = selector["selector_contract_version"]
            pinned_key = selector["selector_key"]
        else:
            return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"

    # Reuse preserves the semantics of the selector that originally chose this loop.
    # Unqualified selection requires global uniqueness among active decision loops.
    # Explicit selection requires uniqueness only among active loops matching the
    # exact pinned reference contract and key; unrelated loops do not invalidate it.
    if explicit:
        active_loop_ids = conn.execute(
            select(schema.conversation_open_loop.c.open_loop_id)
            .join(
                schema.conversation_open_loop_reference,
                schema.conversation_open_loop_reference.c.open_loop_id
                == schema.conversation_open_loop.c.open_loop_id,
            )
            .outerjoin(
                schema.conversation_open_loop_closure,
                schema.conversation_open_loop_closure.c.open_loop_id
                == schema.conversation_open_loop.c.open_loop_id,
            )
            .where(
                schema.conversation_open_loop.c.relationship_id
                == projection["relationship_id"],
                schema.conversation_open_loop.c.loop_kind == "DECISION",
                schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
                schema.conversation_open_loop_reference.c.reference_kind
                == DECISION_REFERENCE_KIND,
                schema.conversation_open_loop_reference.c.reference_contract_version
                == pinned_contract,
                schema.conversation_open_loop_reference.c.canonical_reference_key
                == pinned_key,
            )
        ).scalars().all()
    else:
        active_loop_ids = conn.execute(
            select(schema.conversation_open_loop.c.open_loop_id)
            .outerjoin(
                schema.conversation_open_loop_closure,
                schema.conversation_open_loop_closure.c.open_loop_id
                == schema.conversation_open_loop.c.open_loop_id,
            )
            .where(
                schema.conversation_open_loop.c.relationship_id
                == projection["relationship_id"],
                schema.conversation_open_loop.c.loop_kind == "DECISION",
                schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
            )
        ).scalars().all()

    if item["open_loop_id"] not in active_loop_ids:
        return "CONVERSATION_OPEN_LOOP_NO_LONGER_ACTIVE"
    if len(active_loop_ids) != 1:
        return "CONVERSATION_OPEN_LOOP_SELECTION_AMBIGUOUS"

    selected = conn.execute(
        select(
            schema.context_projection_event.c.ordinal,
            schema.interaction_event,
        )
        .join(
            schema.interaction_event,
            schema.context_projection_event.c.event_id
            == schema.interaction_event.c.event_id,
        )
        .where(
            schema.context_projection_event.c.projection_id == projection["projection_id"]
        )
        .order_by(schema.context_projection_event.c.ordinal)
    ).mappings().all()
    if len(selected) != 2 or [int(row["ordinal"]) for row in selected] != [0, 1]:
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"

    opening, selected_current = selected
    if (
        opening["event_id"] != item["opened_by_event_id"]
        or selected_current["event_id"] != current_input["event_id"]
    ):
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
    if (
        opening["relationship_id"] != projection["relationship_id"]
        or opening["event_kind"] != "COUNTERPART_INPUT"
        or opening["actor_kind"] != "COUNTERPART"
        or opening["actor_ref"] != relationship["counterpart_id"]
    ):
        return "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"

    # ConversationOpenLoop is relationship-scoped. Its source may legitimately come
    # from another thread/surface/channel; durable relationship identity is the
    # continuity boundary rather than transport adjacency.
    return None


def _contextual_selection_blocker(
    conn,
    *,
    projection: dict[str, Any],
    current_input: dict[str, Any],
) -> str | None:
    """Validate the exact F4 immediate-prior contextual event set for reuse."""

    relationship = conn.execute(
        select(schema.relationship_identity).where(
            schema.relationship_identity.c.relationship_id
            == projection["relationship_id"]
        )
    ).mappings().one_or_none()
    if relationship is None:
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    selected = conn.execute(
        select(
            schema.context_projection_event.c.ordinal,
            schema.interaction_event,
        )
        .join(
            schema.interaction_event,
            schema.context_projection_event.c.event_id
            == schema.interaction_event.c.event_id,
        )
        .where(
            schema.context_projection_event.c.projection_id == projection["projection_id"]
        )
        .order_by(schema.context_projection_event.c.ordinal)
    ).mappings().all()

    if len(selected) != 3 or [int(row["ordinal"]) for row in selected] != [0, 1, 2]:
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    prior_input, prior_output, selected_current = selected
    current_seq = int(current_input["timeline_seq"])

    if selected_current["event_id"] != current_input["event_id"]:
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"
    if [int(row["timeline_seq"]) for row in selected] != [
        current_seq - 2,
        current_seq - 1,
        current_seq,
    ]:
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    if (
        prior_input["relationship_id"] != projection["relationship_id"]
        or prior_input["event_kind"] != "COUNTERPART_INPUT"
        or prior_input["actor_kind"] != "COUNTERPART"
        or prior_input["actor_ref"] != relationship["counterpart_id"]
    ):
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    if (
        prior_output["relationship_id"] != projection["relationship_id"]
        or prior_output["event_kind"] != "COMPANION_PRESENTED_OUTPUT"
        or prior_output["actor_kind"] != "COMPANION"
        or prior_output["actor_ref"] != relationship["companion_person_id"]
        or prior_output["companion_output_id"] is None
        or prior_output["reply_to_event_id"] != prior_input["event_id"]
    ):
        return "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    if prior_input["conversation_id"] != current_input["conversation_id"]:
        return "CONTEXTUAL_HISTORY_BOUNDARY_MISMATCH"

    for event in (prior_input, prior_output):
        if (
            event["surface_binding_id"] != current_input["surface_binding_id"]
            or event["channel_binding_id"] != current_input["channel_binding_id"]
        ):
            return "CONTEXTUAL_HISTORY_BOUNDARY_MISMATCH"

    return None


__all__ = ["projection_reuse_blocker"]
