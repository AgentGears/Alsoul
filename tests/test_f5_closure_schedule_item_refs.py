from __future__ import annotations

from uuid import uuid4

import pytest

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_cognition import (
    AdoptPersonalCalendarScheduleOutputCommand,
    GeneratePersonalCalendarAnswerPlanCommand,
)

import test_f5_personal_calendar_cognition as cognition_cases


def test_schedule_item_ref_is_projection_local_and_cross_projection_ref_fails_adoption(
    engine, now
):
    first_ctx = cognition_cases._bootstrap_result(engine, now)
    first_adapter = cognition_cases._PlanAdapter(cognition_cases._valid_plan)
    first_cognition, _first_route = cognition_cases._configure_cognition(
        engine, now, first_ctx, first_adapter
    )
    first_projection = cognition_cases._build_projection(first_cognition, first_ctx)
    first_context = first_cognition.render_model_context(first_projection.projection_id)
    foreign_ref = first_context["occurrences"][0]["schedule_item_ref"]

    second_ctx = cognition_cases._bootstrap_result(engine, now)

    def cross_projection_plan(context):
        current_refs = [
            item["schedule_item_ref"] for item in context["occurrences"]
        ]
        assert foreign_ref not in current_refs
        return cognition_cases._valid_plan(
            context,
            refs=[foreign_ref, current_refs[1]],
        )

    second_adapter = cognition_cases._PlanAdapter(cross_projection_plan)
    second_cognition, second_route = cognition_cases._configure_cognition(
        engine, now, second_ctx, second_adapter
    )
    second_projection = cognition_cases._build_projection(second_cognition, second_ctx)
    generated = second_cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=second_projection.projection_id,
            permission_id=second_ctx["permission"].permission_id,
            route_binding_id=second_route.route_binding_id,
        )
    )

    with pytest.raises(DomainError) as invalid:
        second_cognition.adopt_schedule_output(
            AdoptPersonalCalendarScheduleOutputCommand(
                operation_id=uuid4(),
                generated_output_id=generated.generated_output_id,
            )
        )
    assert invalid.value.code == "CALENDAR_ANSWER_PLAN_OCCURRENCE_SET_INVALID"
