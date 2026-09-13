from __future__ import annotations

from uuid import uuid4

import pytest

import test_f5_personal_calendar_cognition as cognition_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    SetPersonalResourceBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.domain.personal_calendar_cognition import (
    AdoptPersonalCalendarScheduleOutputCommand,
    GeneratePersonalCalendarAnswerPlanCommand,
)


@pytest.mark.parametrize("mutation", ["relationship", "resource"])
def test_exit_relationship_or_resource_change_blocks_model_egress(
    engine, now, mutation
):
    ctx = cognition_cases._bootstrap_result(engine, now)
    adapter = cognition_cases._PlanAdapter(cognition_cases._valid_plan)
    cognition, route = cognition_cases._configure_cognition(engine, now, ctx, adapter)
    projection = cognition_cases._build_projection(cognition, ctx)

    if mutation == "relationship":
        ctx["calendar"].set_relationship_status(
            SetPersonalWorldRelationshipStatusCommand(
                operation_id=uuid4(),
                companion_person_id=ctx["ids"].companion_person_id,
                counterpart_id=ctx["ids"].counterpart_id,
                relationship_id=ctx["ids"].relationship_id,
            )
        )
    else:
        ctx["calendar"].set_resource_status(
            SetPersonalResourceBindingStatusCommand(
                operation_id=uuid4(),
                personal_resource_binding_id=ctx[
                    "resource"
                ].personal_resource_binding_id,
                status="INACTIVE",
            )
        )

    with pytest.raises(DomainError) as denied:
        cognition.generate_answer_plan(
            GeneratePersonalCalendarAnswerPlanCommand(
                operation_id=uuid4(),
                projection_id=projection.projection_id,
                permission_id=ctx["permission"].permission_id,
                route_binding_id=route.route_binding_id,
            )
        )
    assert denied.value.code == "CALENDAR_MODEL_EGRESS_DENIED"
    assert adapter.requests == []


@pytest.mark.parametrize(
    "refs",
    [
        [],
        ["schedule-item-9999"],
        ["schedule-item-0001", "schedule-item-0001"],
    ],
)
def test_exit_adoption_rejects_non_equivalent_occurrence_sets(engine, now, refs):
    ctx = cognition_cases._bootstrap_result(engine, now)
    adapter = cognition_cases._PlanAdapter(
        lambda context: cognition_cases._valid_plan(context, refs=refs)
    )
    cognition, route = cognition_cases._configure_cognition(engine, now, ctx, adapter)
    projection = cognition_cases._build_projection(cognition, ctx)
    generated = cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=projection.projection_id,
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


def test_exit_adoption_rejects_plan_lineage_mismatch(engine, now):
    ctx = cognition_cases._bootstrap_result(engine, now)

    def wrong_lineage(context):
        plan = cognition_cases._valid_plan(context)
        plan["source_world_result_id"] = str(uuid4())
        return plan

    adapter = cognition_cases._PlanAdapter(wrong_lineage)
    cognition, route = cognition_cases._configure_cognition(engine, now, ctx, adapter)
    projection = cognition_cases._build_projection(cognition, ctx)
    generated = cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=projection.projection_id,
            permission_id=ctx["permission"].permission_id,
            route_binding_id=route.route_binding_id,
        )
    )

    with pytest.raises(DomainError) as mismatch:
        cognition.adopt_schedule_output(
            AdoptPersonalCalendarScheduleOutputCommand(
                operation_id=uuid4(),
                generated_output_id=generated.generated_output_id,
            )
        )
    assert mismatch.value.code == "CALENDAR_ANSWER_PLAN_LINEAGE_MISMATCH"
