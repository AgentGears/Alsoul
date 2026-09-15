from __future__ import annotations

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.services.personal_calendar_mutation_completion import (
    PersonalCalendarMutationCompletionServices as PersonalCalendarMutationCompletionServicesV1,
)
from alsoul.storage import schema


class PersonalCalendarMutationCompletionServices(
    PersonalCalendarMutationCompletionServicesV1
):
    """Current mutation-completion service with exact projection-context lineage checks."""

    def build_completion_projection(self, command):
        result = super().build_completion_projection(command)
        with self.engine.connect() as conn:
            projection = super()._load_completion_projection(conn, result.projection_id)
            lineage = super()._load_confirmed_completion(conn, projection["effect_id"])
            self._validate_projection_context(conn, projection, lineage)
        return result

    def _load_completion_projection(self, conn, projection_id, *, serialize=False):
        projection = super()._load_completion_projection(
            conn, projection_id, serialize=serialize
        )
        lineage = super()._load_confirmed_completion(conn, projection["effect_id"])
        self._validate_projection_context(conn, projection, lineage)
        return projection

    def _validate_projection_context(self, conn, projection, lineage) -> None:
        action = lineage["action"]
        effect = lineage["effect"]
        support = lineage["support"]
        relationship = lineage["relationship"]
        if (
            projection["action_id"] != action["action_id"]
            or projection["effect_id"] != effect["effect_id"]
            or projection["effect_evidence_id"] != support["effect_evidence_id"]
        ):
            fail(
                "CALENDAR_MUTATION_COMPLETION_PROJECTION_LINEAGE_MISMATCH",
                "mutation completion projection does not resolve to its exact Action/Effect/evidence lineage",
            )

        generic = conn.execute(
            select(schema.context_projection).where(
                schema.context_projection.c.projection_id == projection["projection_id"]
            )
        ).mappings().one_or_none()
        if generic is None:
            fail(
                "CALENDAR_MUTATION_COMPLETION_CONTEXT_MISSING",
                "mutation completion projection lacks its generic ContextProjection",
            )
        expected_manifest = super()._projection_result(projection).manifest_digest
        if (
            int(generic["projection_schema_version"]) != 3
            or generic["purpose"] != "CALENDAR_MUTATION_COMPLETION"
            or generic["companion_person_id"] != relationship["companion_person_id"]
            or generic["relationship_id"] != action["relationship_id"]
            or generic["current_input_event_id"] != action["source_interaction_event_id"]
            or int(generic["source_timeline_frontier"])
            != int(action["source_timeline_frontier"])
            or generic["manifest_digest"] != expected_manifest
        ):
            fail(
                "CALENDAR_MUTATION_COMPLETION_CONTEXT_MISMATCH",
                "mutation completion ContextProjection does not match the exact durable completion mapping",
            )

        events = conn.execute(
            select(schema.context_projection_event)
            .where(
                schema.context_projection_event.c.projection_id
                == projection["projection_id"]
            )
            .order_by(schema.context_projection_event.c.ordinal)
        ).mappings().all()
        if (
            len(events) != 1
            or int(events[0]["ordinal"]) != 0
            or events[0]["event_id"] != action["source_interaction_event_id"]
        ):
            fail(
                "CALENDAR_MUTATION_COMPLETION_CONTEXT_EVENT_MISMATCH",
                "mutation completion context must contain only the exact Action source interaction",
            )


__all__ = ["PersonalCalendarMutationCompletionServices"]
