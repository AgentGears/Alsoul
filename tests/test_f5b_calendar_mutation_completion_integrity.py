from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_mutation_completion import (
    GeneratePersonalCalendarMutationResultPlanCommand,
)
from alsoul.storage import schema

import test_f5b_calendar_mutation_completion as completion_cases


def test_projection_cannot_substitute_another_effect_evidence(engine, now):
    _lineage_a, effect_a = completion_cases._confirmed(engine, now)
    _lineage_b, effect_b = completion_cases._confirmed(engine, now)
    adapter = completion_cases._CompletionAdapter(completion_cases._valid_plan)
    service = completion_cases._service(engine, now, adapter)
    projection = completion_cases._build(service, effect_a.effect_id)
    route = completion_cases._route(service, adapter)

    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_mutation_completion_projection)
            .where(
                schema.personal_calendar_mutation_completion_projection.c.projection_id
                == projection.projection_id
            )
            .values(effect_evidence_id=effect_b.effect_evidence_id)
        )

    with pytest.raises(DomainError) as mismatch:
        service.generate_result_plan(
            GeneratePersonalCalendarMutationResultPlanCommand(
                operation_id=uuid4(),
                projection_id=projection.projection_id,
                route_binding_id=route.route_binding_id,
            )
        )
    assert (
        mismatch.value.code
        == "CALENDAR_MUTATION_COMPLETION_PROJECTION_LINEAGE_MISMATCH"
    )
    assert adapter.requests == []


def test_generic_context_manifest_tampering_blocks_model_dispatch(engine, now):
    _lineage, effect = completion_cases._confirmed(engine, now)
    adapter = completion_cases._CompletionAdapter(completion_cases._valid_plan)
    service = completion_cases._service(engine, now, adapter)
    projection = completion_cases._build(service, effect.effect_id)
    route = completion_cases._route(service, adapter)

    with engine.begin() as conn:
        conn.execute(
            update(schema.context_projection)
            .where(schema.context_projection.c.projection_id == projection.projection_id)
            .values(manifest_digest="0" * 64)
        )

    with pytest.raises(DomainError) as mismatch:
        service.generate_result_plan(
            GeneratePersonalCalendarMutationResultPlanCommand(
                operation_id=uuid4(),
                projection_id=projection.projection_id,
                route_binding_id=route.route_binding_id,
            )
        )
    assert mismatch.value.code == "CALENDAR_MUTATION_COMPLETION_CONTEXT_MISMATCH"
    assert adapter.requests == []
