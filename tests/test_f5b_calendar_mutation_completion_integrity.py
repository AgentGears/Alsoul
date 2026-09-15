from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_mutation_completion import (
    GeneratePersonalCalendarMutationResultPlanCommand,
)
from alsoul.storage import schema

import test_f5b_calendar_mutation_completion as completion_cases


def test_projection_cannot_substitute_another_effect_evidence(engine, now):
    lineage, effect = completion_cases._confirmed(engine, now)
    adapter = completion_cases._CompletionAdapter(completion_cases._valid_plan)
    service = completion_cases._service(engine, now, adapter)
    projection = completion_cases._build(service, effect.effect_id)
    route = completion_cases._route(service, adapter)

    alternate_attempt_id = uuid4()
    alternate_evidence_id = uuid4()
    with engine.begin() as conn:
        original_evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == effect.effect_evidence_id
            )
        ).mappings().one()
        conn.execute(
            insert(schema.personal_calendar_create_execution_attempt).values(
                execution_attempt_id=alternate_attempt_id,
                action_id=lineage["action"].action_id,
                attempt_generation=int(lineage["attempt"].attempt_generation) + 100,
                approval_id=lineage["approval"].approval_id,
                credential_binding_id=lineage["credential"].credential_binding_id,
                correlation_key=lineage["attempt"].correlation_key,
                correlation_contract_version=(
                    lineage["attempt"].correlation_key
                    and "CALENDAR_CREATE_ACTION_CORRELATION_V1"
                ),
                prepared_at=now,
            )
        )
        conn.execute(
            insert(schema.personal_calendar_create_mutation_dispatch).values(
                execution_attempt_id=alternate_attempt_id,
                action_id=lineage["action"].action_id,
                request_contract_version="CALENDAR_CREATE_MUTATION_REQUEST_V1",
                started_at=now,
            )
        )
        conn.execute(
            insert(schema.personal_calendar_create_effect_evidence).values(
                effect_evidence_id=alternate_evidence_id,
                execution_attempt_id=alternate_attempt_id,
                action_id=lineage["action"].action_id,
                validation_kind=original_evidence["validation_kind"],
                correlation_key=original_evidence["correlation_key"],
                external_effect_ref="provider-event:alternate-valid-row",
                external_system_ref=original_evidence["external_system_ref"],
                external_resource_ref=original_evidence["external_resource_ref"],
                normalized_summary=original_evidence["normalized_summary"],
                normalized_start_at=original_evidence["normalized_start_at"],
                normalized_end_at=original_evidence["normalized_end_at"],
                provider_status=original_evidence["provider_status"],
                receipt_ref="provider-receipt:alternate-valid-row",
                observed_at=original_evidence["observed_at"],
                evidence_schema_version=original_evidence["evidence_schema_version"],
                committed_at=now,
            )
        )
        conn.execute(
            update(schema.personal_calendar_mutation_completion_projection)
            .where(
                schema.personal_calendar_mutation_completion_projection.c.projection_id
                == projection.projection_id
            )
            .values(effect_evidence_id=alternate_evidence_id)
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
