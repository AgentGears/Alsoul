from __future__ import annotations

from typing import Any

from sqlalchemy import select

from alsoul.storage import schema


def projection_reuse_blocker(conn, projection: dict[str, Any]) -> str | None:
    """Return why one reactive ContextProjection must not be reused.

    F4 retries may reuse an immutable projection only while the canonical state it
    fenced is still current. A stale projection remains durable history; it simply
    stops being eligible for another provider invocation.
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


__all__ = ["projection_reuse_blocker"]
