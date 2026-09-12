from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_cognition as cognition_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_cognition import (
    BuildPersonalCalendarProjectionCommand,
    GeneratePersonalCalendarAnswerPlanCommand,
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarCognitionServices
from alsoul.storage import schema


def _code(exc: pytest.ExceptionInfo[DomainError]) -> str:
    return exc.value.code


def test_exit_tightened_freshness_invalidates_recovered_result_before_projection(engine, now):
    ctx = cognition_cases._bootstrap_result(engine, now)
    initial = PersonalCalendarCognitionServices(
        engine, adapter=None, clock=FixedClock(now), ids=UUIDGenerator()
    )
    initial.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-freshness-wide-v1",
            max_age_seconds=3600,
        )
    )
    tightened_at = now + timedelta(seconds=1)
    tightened = PersonalCalendarCognitionServices(
        engine, adapter=None, clock=FixedClock(tightened_at), ids=UUIDGenerator()
    )
    tightened.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-freshness-zero-v2",
            max_age_seconds=0,
        )
    )
    with pytest.raises(DomainError) as stale:
        tightened.build_projection(
            BuildPersonalCalendarProjectionCommand(
                operation_id=uuid4(),
                world_result_id=ctx["world_result_id"],
                current_input_event_id=ctx["source_event"].event_id,
            )
        )
    assert _code(stale) == "CALENDAR_RESULT_STALE"
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.context_projection)
        ).scalar_one() == 0
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_world_result)
        ).scalar_one() == 1


def test_exit_model_route_change_requires_new_gate_and_records_full_invocation_provenance(engine, now):
    ctx = cognition_cases._bootstrap_result(engine, now)
    original_adapter = cognition_cases._PlanAdapter(cognition_cases._valid_plan)
    cognition, old_route = cognition_cases._configure_cognition(
        engine, now, ctx, original_adapter
    )
    projection = cognition_cases._build_projection(cognition, ctx)

    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-egress-deny-exit-v2",
            allowed_route_binding_ids=(old_route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
            status="DENY",
        )
    )
    with pytest.raises(DomainError) as denied:
        cognition.generate_answer_plan(
            GeneratePersonalCalendarAnswerPlanCommand(
                operation_id=uuid4(),
                projection_id=projection.projection_id,
                permission_id=ctx["permission"].permission_id,
                route_binding_id=old_route.route_binding_id,
            )
        )
    assert _code(denied) == "CALENDAR_MODEL_EGRESS_DENIED"
    assert original_adapter.requests == []

    new_provider = "model.test/calendar-plan-exit-v2"
    new_model = "calendar-plan-exit-v2"
    new_route = cognition.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=new_provider,
            model_ref=new_model,
            route_contract_version="calendar-plan-route-exit-v2",
            data_handling_contract_version="personal-data-route-exit-v2",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-egress-new-route-v3",
            allowed_route_binding_ids=(new_route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    with pytest.raises(DomainError) as old_denied:
        cognition.generate_answer_plan(
            GeneratePersonalCalendarAnswerPlanCommand(
                operation_id=uuid4(),
                projection_id=projection.projection_id,
                permission_id=ctx["permission"].permission_id,
                route_binding_id=old_route.route_binding_id,
            )
        )
    assert _code(old_denied) == "CALENDAR_MODEL_EGRESS_DENIED"

    new_adapter = cognition_cases._PlanAdapter(cognition_cases._valid_plan)
    new_adapter.provider_binding_ref = new_provider
    new_adapter.model_ref = new_model
    recomposed = PersonalCalendarCognitionServices(
        engine, adapter=new_adapter, clock=FixedClock(now), ids=UUIDGenerator()
    )
    generated = recomposed.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=projection.projection_id,
            permission_id=ctx["permission"].permission_id,
            route_binding_id=new_route.route_binding_id,
        )
    )
    assert len(new_adapter.requests) == 1

    with engine.connect() as conn:
        egress = conn.execute(
            select(schema.personal_calendar_model_egress_decision).where(
                schema.personal_calendar_model_egress_decision.c.egress_decision_id
                == generated.egress_decision_id
            )
        ).mappings().one()
        invocation = conn.execute(
            select(schema.personal_calendar_model_invocation).where(
                schema.personal_calendar_model_invocation.c.model_invocation_id
                == generated.model_invocation_id
            )
        ).mappings().one()
        generic = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id
                == generated.model_invocation_id
            )
        ).mappings().one()
        freshness = conn.execute(
            select(schema.personal_calendar_freshness_decision).where(
                schema.personal_calendar_freshness_decision.c.freshness_decision_id
                == egress["freshness_decision_id"]
            )
        ).mappings().one()
    assert egress["projection_id"] == projection.projection_id
    assert egress["permission_id"] == ctx["permission"].permission_id
    assert egress["route_binding_id"] == new_route.route_binding_id
    assert int(egress["relationship_authority_revision"]) >= 1
    assert int(egress["resource_binding_state_revision"]) >= 1
    assert int(egress["permission_state_revision"]) >= 1
    assert int(egress["read_policy_revision"]) >= 1
    assert int(egress["egress_policy_revision"]) >= 1
    assert int(egress["route_state_revision"]) >= 1
    assert invocation["projection_id"] == projection.projection_id
    assert invocation["egress_decision_id"] == generated.egress_decision_id
    assert invocation["route_binding_id"] == new_route.route_binding_id
    assert generic["provider_binding_ref"] == new_provider
    assert generic["model_ref"] == new_model
    assert freshness["decision_purpose"] == "MODEL_EGRESS"
