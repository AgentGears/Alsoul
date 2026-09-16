from __future__ import annotations

from contextvars import ContextVar
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_cognition import (
    GeneratePersonalCalendarAnswerPlanCommand,
    PersonalCalendarGenerationResult,
)
from alsoul.services.personal_calendar_cognition import (
    PersonalCalendarCognitionServices as PersonalCalendarCognitionServicesV1,
    _aware_utc,
)
from alsoul.storage import schema

_GENERATION_ADMISSION_ACTIVE: ContextVar[bool] = ContextVar(
    "personal_calendar_generation_admission_active",
    default=False,
)


class PersonalCalendarCognitionServices(PersonalCalendarCognitionServicesV1):
    """Current F5.A cognition service with dispatch and projection-local fences.

    The first cognition implementation validates current authority before model egress.
    This current layer additionally linearizes those reads against concurrent mutable-head
    changes, serializes prospective model dispatches for one immutable projection, and
    exposes only opaque projection-local schedule-item handles to the model boundary.
    """

    def generate_answer_plan(
        self, command: GeneratePersonalCalendarAnswerPlanCommand
    ) -> PersonalCalendarGenerationResult:
        token = _GENERATION_ADMISSION_ACTIVE.set(True)
        try:
            return super().generate_answer_plan(command)
        finally:
            _GENERATION_ADMISSION_ACTIVE.reset(token)

    def _projection_occurrences(self, value: dict[str, Any]) -> list[dict[str, Any]]:
        occurrences = super()._projection_occurrences(value)
        projected: list[dict[str, Any]] = []
        for occurrence in occurrences:
            item = dict(occurrence)
            # This is the canonical projection-local schedule handle.  The provider
            # occurrence identity remains separately host-side in source_occurrence_ref.
            # A fresh opaque identifier per projection prevents a handle learned from
            # one projection from resolving inside another projection merely because
            # both schedules have the same ordinal.
            item["occurrence_ref"] = f"schedule-item:{self.ids.new()}"
            projected.append(item)
        return projected

    def _render_model_context_conn(self, conn, projection_id: UUID) -> dict[str, Any]:
        context = super()._render_model_context_conn(conn, projection_id)
        occurrences = context.get("occurrences")
        if not isinstance(occurrences, list):
            fail(
                "CALENDAR_CONTEXT_PROJECTION_INVALID",
                "personal-calendar projection occurrence context is malformed",
            )
        model_occurrences: list[dict[str, Any]] = []
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                fail(
                    "CALENDAR_CONTEXT_PROJECTION_INVALID",
                    "personal-calendar projection occurrence context is malformed",
                )
            item = dict(occurrence)
            schedule_item_ref = item.pop("occurrence_ref", None)
            if not isinstance(schedule_item_ref, str) or not schedule_item_ref.strip():
                fail(
                    "CALENDAR_CONTEXT_PROJECTION_INVALID",
                    "personal-calendar projection schedule item reference is missing",
                )
            item["schedule_item_ref"] = schedule_item_ref
            model_occurrences.append(item)
        return {**context, "occurrences": model_occurrences}

    def _load_personal_projection(self, conn, projection_id: UUID) -> dict[str, Any]:
        if _GENERATION_ADMISSION_ACTIVE.get():
            # Serialize prospective model dispatches before any generation-time read.
            # A competing transaction for the same immutable projection must wait for
            # this row fence; after it acquires the fence it re-reads durable attempts
            # and therefore observes the winning IN_PROGRESS/SUCCEEDED invocation.
            fenced = conn.execute(
                update(schema.personal_calendar_context_projection)
                .where(
                    schema.personal_calendar_context_projection.c.projection_id
                    == projection_id
                )
                .values(
                    projection_contract_version=
                    schema.personal_calendar_context_projection.c.projection_contract_version
                )
            )
            if fenced.rowcount != 1:
                fail(
                    "CALENDAR_CONTEXT_PROJECTION_NOT_FOUND",
                    "personal-calendar ContextProjection does not exist",
                )
        return super()._load_personal_projection(conn, projection_id)

    def _record_freshness_decision(
        self,
        conn,
        *,
        decision_id: UUID,
        relationship_id: UUID,
        world_result_id: UUID,
        freshness_anchor_at,
        purpose: str,
    ) -> dict[str, Any]:
        result = super()._record_freshness_decision(
            conn,
            decision_id=decision_id,
            relationship_id=relationship_id,
            world_result_id=world_result_id,
            freshness_anchor_at=freshness_anchor_at,
            purpose=purpose,
        )
        decision = conn.execute(
            select(schema.personal_calendar_freshness_decision).where(
                schema.personal_calendar_freshness_decision.c.freshness_decision_id
                == decision_id
            )
        ).mappings().one()

        # Enforce the exact elapsed interval rather than an integer-truncated age.
        elapsed = _aware_utc(decision["evaluated_at"]) - _aware_utc(
            decision["freshness_anchor_at"]
        )
        if elapsed < timedelta(0):
            fail(
                "CALENDAR_FRESHNESS_CLOCK_INVALID",
                "freshness anchor lies after the trusted evaluation clock",
            )
        if elapsed > timedelta(seconds=int(decision["max_age_seconds"])):
            fail(
                "CALENDAR_RESULT_STALE",
                "personal-calendar result is stale under the current freshness policy",
            )

        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_freshness_policy_head,
            key_column=schema.personal_calendar_freshness_policy_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=int(result["policy_revision"]),
            conflict_code="CALENDAR_FRESHNESS_POLICY_CHANGED",
        )
        return result

    def _evaluate_model_egress(
        self,
        conn,
        *,
        projection: dict[str, Any],
        permission_id: UUID,
        route_binding_id: UUID,
    ) -> dict[str, Any]:
        authority = super()._evaluate_model_egress(
            conn,
            projection=projection,
            permission_id=permission_id,
            route_binding_id=route_binding_id,
        )
        relationship_id = projection["relationship_id"]
        resource_id = projection["personal_resource_binding_id"]

        # These same-value compare-and-swap writes are the model-egress
        # linearization point. Each mutable authority head remains locked until the
        # transaction commits the exact egress decision and IN_PROGRESS invocation.
        self._cas_revision_head(
            conn,
            table=schema.personal_world_relationship_head,
            key_column=schema.personal_world_relationship_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=int(authority["relationship_authority_revision"]),
            conflict_code="CALENDAR_MODEL_EGRESS_RELATIONSHIP_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_resource_binding_head,
            key_column=schema.personal_resource_binding_head.c.personal_resource_binding_id,
            key_value=resource_id,
            expected_revision=int(authority["resource_binding_state_revision"]),
            conflict_code="CALENDAR_MODEL_EGRESS_RESOURCE_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.permission_head,
            key_column=schema.permission_head.c.permission_id,
            key_value=permission_id,
            expected_revision=int(authority["permission_state_revision"]),
            conflict_code="CALENDAR_MODEL_EGRESS_PERMISSION_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_read_policy_head,
            key_column=schema.personal_calendar_read_policy_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=int(authority["read_policy_revision"]),
            conflict_code="CALENDAR_MODEL_EGRESS_READ_POLICY_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_model_egress_policy_head,
            key_column=schema.personal_calendar_model_egress_policy_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=int(authority["egress_policy_revision"]),
            conflict_code="CALENDAR_MODEL_EGRESS_POLICY_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_model_route_head,
            key_column=schema.personal_calendar_model_route_head.c.route_binding_id,
            key_value=route_binding_id,
            expected_revision=int(authority["route_state_revision"]),
            conflict_code="CALENDAR_MODEL_ROUTE_CHANGED",
        )
        self._cas_timeline_head(
            conn,
            relationship_id=relationship_id,
            expected_frontier=int(projection["source_timeline_frontier"]),
        )
        return authority

    @staticmethod
    def _cas_revision_head(
        conn,
        *,
        table,
        key_column,
        key_value: UUID,
        expected_revision: int,
        conflict_code: str,
    ) -> None:
        changed = conn.execute(
            update(table)
            .where(
                key_column == key_value,
                table.c.current_revision == expected_revision,
            )
            .values(current_revision=expected_revision)
        )
        if changed.rowcount != 1:
            fail(
                conflict_code,
                "personal-calendar authority changed before model dispatch could linearize",
            )

    @staticmethod
    def _cas_timeline_head(
        conn,
        *,
        relationship_id: UUID,
        expected_frontier: int,
    ) -> None:
        changed = conn.execute(
            update(schema.relationship_timeline_head)
            .where(
                schema.relationship_timeline_head.c.relationship_id == relationship_id,
                schema.relationship_timeline_head.c.last_timeline_seq == expected_frontier,
            )
            .values(last_timeline_seq=expected_frontier)
        )
        if changed.rowcount != 1:
            fail(
                "CALENDAR_MODEL_EGRESS_INTERACTION_CHANGED",
                "originating interaction changed before model dispatch could linearize",
            )


__all__ = ["PersonalCalendarCognitionServices"]
