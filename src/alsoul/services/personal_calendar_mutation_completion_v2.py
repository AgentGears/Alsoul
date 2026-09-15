from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict

from sqlalchemy import select, update

from alsoul.domain.errors import fail
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.personal_calendar_mutation_completion import (
    PersonalCalendarMutationCompletionServices as PersonalCalendarMutationCompletionServicesV1,
    _ADOPT_SCOPE,
    _BUILD_SCOPE,
    _GENERATE_SCOPE,
)
from alsoul.storage import schema


_BUILD_RECHECK: ContextVar[tuple[object, str] | None] = ContextVar(
    "calendar_mutation_completion_build_recheck", default=None
)
_GENERATE_RECHECK: ContextVar[tuple[object, str] | None] = ContextVar(
    "calendar_mutation_completion_generate_recheck", default=None
)
_ADOPT_RECHECK: ContextVar[tuple[object, str] | None] = ContextVar(
    "calendar_mutation_completion_adopt_recheck", default=None
)


class _BuildReplay(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class _GenerationReplay(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class _AdoptionReplay(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class PersonalCalendarMutationCompletionServices(
    PersonalCalendarMutationCompletionServicesV1
):
    """Current mutation completion with exact lineage and serialized operation replay."""

    def build_completion_projection(self, command):
        req = request_digest(asdict(command))
        token = _BUILD_RECHECK.set((command, req))
        try:
            try:
                result = super().build_completion_projection(command)
            except _BuildReplay as replay:
                result = replay.result
        finally:
            _BUILD_RECHECK.reset(token)
        with self.engine.connect() as conn:
            projection = super()._load_completion_projection(conn, result.projection_id)
            lineage = super()._load_confirmed_completion(conn, projection["effect_id"])
            self._validate_projection_context(conn, projection, lineage)
        return result

    def generate_result_plan(self, command):
        req = request_digest(asdict(command))
        token = _GENERATE_RECHECK.set((command, req))
        try:
            try:
                return super().generate_result_plan(command)
            except _GenerationReplay as replay:
                return replay.result
        finally:
            _GENERATE_RECHECK.reset(token)

    def adopt_mutation_output(self, command):
        req = request_digest(asdict(command))
        token = _ADOPT_RECHECK.set((command, req))
        try:
            try:
                return super().adopt_mutation_output(command)
            except _AdoptionReplay as replay:
                return replay.result
        finally:
            _ADOPT_RECHECK.reset(token)

    def _load_confirmed_completion(self, conn, effect_id):
        build = _BUILD_RECHECK.get()
        if build is not None:
            command, req = build
            locked = conn.execute(
                update(schema.personal_calendar_create_effect)
                .where(schema.personal_calendar_create_effect.c.effect_id == effect_id)
                .values(status=schema.personal_calendar_create_effect.c.status)
            )
            if locked.rowcount == 1:
                replay = load_operation_receipt(
                    conn,
                    scope=_BUILD_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    raise _BuildReplay(self._projection_result_from_json(replay))
        return super()._load_confirmed_completion(conn, effect_id)

    def _load_completion_projection(self, conn, projection_id, *, serialize=False):
        projection = super()._load_completion_projection(
            conn, projection_id, serialize=serialize
        )
        if serialize:
            generation = _GENERATE_RECHECK.get()
            if generation is not None:
                command, req = generation
                replay = load_operation_receipt(
                    conn,
                    scope=_GENERATE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    raise _GenerationReplay(
                        self._recover_generation_replay(conn, replay)
                    )
            adoption = _ADOPT_RECHECK.get()
            if adoption is not None:
                command, req = adoption
                replay = load_operation_receipt(
                    conn,
                    scope=_ADOPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    raise _AdoptionReplay(self._adoption_result_from_json(replay))

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
