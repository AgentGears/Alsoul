from __future__ import annotations

from typing import Any

from sqlalchemy import select

from alsoul.services.conversation_context import requires_prior_timeline_context
from alsoul.storage import schema


def projection_reuse_blocker(conn, projection: dict[str, Any]) -> str | None:
    """Return why one reactive ContextProjection must not be reused.

    F4 retries may reuse an immutable projection only while the canonical state it
    fenced is still current. A stale projection remains durable history; it simply
    stops being eligible for another provider invocation.

    Contextual conversation adds a stronger compatibility fence: if the immutable
    current input now requires bounded prior-Timeline context, a legacy projection
    containing only that input is historical but not reusable. Recovery must build
    a new projection under the current exact-selection contract rather than silently
    treating the legacy provider context as equivalent.
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

    if requires_prior_timeline_context(current_input["content_text"]):
        contextual_blocker = _contextual_selection_blocker(
            conn,
            projection=projection,
            current_input=dict(current_input),
        )
        if contextual_blocker is not None:
            return contextual_blocker

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


def _contextual_selection_blocker(
    conn,
    *,
    projection: dict[str, Any],
    current_input: dict[str, Any],
) -> str | None:
    """Validate the exact F4 contextual event set for projection reuse."""

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

    # Conversation identity is carried by the triggering counterpart input. The
    # presented output is causally bound to that input through reply_to_event_id;
    # F4 presentation rows do not duplicate conversation_id.
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
