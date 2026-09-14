from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.storage import schema


def select_model_route(engine, *, relationship_id: UUID, model_adapter) -> UUID:
    with engine.connect() as conn:
        head = conn.execute(
            select(schema.personal_calendar_model_egress_policy_head).where(
                schema.personal_calendar_model_egress_policy_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_EGRESS_POLICY_MISSING",
                "calendar interaction requires a current model-egress policy",
            )
        policy = conn.execute(
            select(schema.personal_calendar_model_egress_policy_revision).where(
                schema.personal_calendar_model_egress_policy_revision.c.relationship_id
                == relationship_id,
                schema.personal_calendar_model_egress_policy_revision.c.revision
                == head["current_revision"],
            )
        ).mappings().one()
        if policy["status"] != "ALLOW":
            fail(
                "PERSONAL_CALENDAR_RUNTIME_EGRESS_POLICY_DENIED",
                "current personal-calendar model-egress policy denies processing",
            )
        matches: list[UUID] = []
        for value in policy["allowed_route_binding_ids_json"]:
            route_id = UUID(str(value))
            route = conn.execute(
                select(schema.personal_calendar_model_route_binding).where(
                    schema.personal_calendar_model_route_binding.c.route_binding_id
                    == route_id,
                    schema.personal_calendar_model_route_binding.c.provider_binding_ref
                    == model_adapter.provider_binding_ref,
                    schema.personal_calendar_model_route_binding.c.model_ref
                    == model_adapter.model_ref,
                )
            ).mappings().one_or_none()
            if route is None:
                continue
            route_head = conn.execute(
                select(schema.personal_calendar_model_route_head).where(
                    schema.personal_calendar_model_route_head.c.route_binding_id
                    == route_id
                )
            ).mappings().one_or_none()
            if route_head is None:
                continue
            state = conn.execute(
                select(schema.personal_calendar_model_route_state).where(
                    schema.personal_calendar_model_route_state.c.route_binding_id
                    == route_id,
                    schema.personal_calendar_model_route_state.c.revision
                    == route_head["current_revision"],
                )
            ).mappings().one_or_none()
            if state is not None and state["status"] == "ACTIVE":
                matches.append(route_id)
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_MODEL_ROUTE_AMBIGUOUS",
                "calendar interaction requires exactly one current authorized model route matching the configured adapter",
            )
        return matches[0]


__all__ = ["select_model_route"]
