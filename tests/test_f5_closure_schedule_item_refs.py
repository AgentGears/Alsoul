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
    ctx = cognition_cases._bootstrap_result(engine, now)
    adapter = cognition_cases._PlanAdapter(cognition_cases._valid_plan)
    cognition, route = cognition_cases._configure_cognition(
        engine, now, ctx, adapter
    )
    first_projection = cognition_cases._build_projection(cognition, ctx)
    first_context = cognition.render_model_context(first_projection.projection_id)
    foreign_ref = first_context["occurrences"][0]["schedule_item_ref"]

    def cross_projection_plan(context):
        current_refs = [
            item["schedule_item_ref"] for item in context["occurrences"]
        ]
        assert foreign_ref not in current_refs
        return cognition_cases._valid_plan(
            context,
            refs=[foreign_ref, current_refs[1]],
        )

    adapter.factory = cross_projection_plan
    second_projection = cognition_cases._build_projection(cognition, ctx)
    generated = cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=second_projection.projection_id,
            permission_id=ctx["permission"].permission_id,
            route_binding_id=route.route_binding_id,
        )
    )

    with pytest.raises(DomainError) as invalid:
        cognition.adopt_schedule_output(
            AdoptPersonalCalendarScheduleOutputCommand(
                operation_id=uuid4(),
                generated_output_id=generated.generated_output_id,
            )
        )
    assert invalid.value.code == "CALENDAR_ANSWER_PLAN_OCCURRENCE_SET_INVALID"
