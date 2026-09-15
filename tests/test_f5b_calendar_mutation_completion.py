from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_cognition import (
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarModelRouteStatusCommand,
)
from alsoul.domain.personal_calendar_mutation_completion import (
    AdoptPersonalCalendarMutationOutputCommand,
    BuildPersonalCalendarMutationCompletionProjectionCommand,
    GeneratePersonalCalendarMutationResultPlanCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar_mutation_completion import (
    PersonalCalendarMutationCompletionServices,
)
from alsoul.storage import schema

import test_f5b_calendar_confirmed_effect as effect_cases


class _CompletionAdapter:
    provider_binding_ref = "model.test/calendar-mutation-completion"
    model_ref = "calendar-mutation-completion-v1"

    def __init__(self, factory):
        self.factory = factory
        self.requests = []

    def generate_plan(self, context):
        self.requests.append(dict(context))
        return self.factory(context)


def _valid_plan(context):
    return dict(context)


def _confirmed(engine, now):
    lineage, _adapter, _transport, evidence = effect_cases._matched_transport(engine, now)
    effect = effect_cases._admit(
        effect_cases._effect_service(engine, now),
        lineage["attempt"],
        evidence.effect_evidence_id,
    )
    return lineage, effect


def _service(engine, now, adapter):
    return PersonalCalendarMutationCompletionServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _route(service, adapter):
    return service.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=adapter.provider_binding_ref,
            model_ref=adapter.model_ref,
            route_contract_version="calendar-mutation-result-route-v1",
            data_handling_contract_version="opaque-completion-ref-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )


def _build(service, effect_id, *, operation_id=None):
    return service.build_completion_projection(
        BuildPersonalCalendarMutationCompletionProjectionCommand(
            operation_id=operation_id or uuid4(),
            effect_id=effect_id,
        )
    )


def _generate(service, projection, route, *, operation_id=None):
    return service.generate_result_plan(
        GeneratePersonalCalendarMutationResultPlanCommand(
            operation_id=operation_id or uuid4(),
            projection_id=projection.projection_id,
            route_binding_id=route.route_binding_id,
        )
    )


def test_confirmed_effect_projects_only_opaque_completion_context_and_renders_facts_host_side(
    engine, now
):
    lineage, effect = _confirmed(engine, now)
    adapter = _CompletionAdapter(_valid_plan)
    service = _service(engine, now, adapter)
    route = _route(service, adapter)
    projection = _build(service, effect.effect_id)

    generated = _generate(service, projection, route)
    adopted = service.adopt_mutation_output(
        AdoptPersonalCalendarMutationOutputCommand(
            operation_id=uuid4(),
            generated_output_id=generated.generated_output_id,
        )
    )

    assert len(adapter.requests) == 1
    assert set(adapter.requests[0]) == {
        "mutation_completion_ref",
        "result_kind",
        "rendering_contract_version",
    }
    serialized = repr(adapter.requests[0])
    assert str(lineage["action"].action_id) not in serialized
    assert str(effect.effect_id) not in serialized
    assert lineage["action"].summary not in serialized
    assert lineage["action"].start_text not in serialized
    assert lineage["action"].end_text not in serialized
    assert "provider-event" not in serialized
    assert "provider-receipt" not in serialized
    assert adapter.requests[0]["result_kind"] == "CREATED"
    assert adapter.requests[0]["rendering_contract_version"] == "CALENDAR_CREATE_RESULT_V1"

    with engine.connect() as conn:
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == adopted.companion_output_id
            )
        ).mappings().one()
        specialized = conn.execute(
            select(schema.personal_calendar_mutation_adoption).where(
                schema.personal_calendar_mutation_adoption.c.companion_output_id
                == adopted.companion_output_id
            )
        ).mappings().one()

    assert output["content_text"] == (
        f'I created "{lineage["action"].summary}" on your calendar from '
        f'{lineage["action"].start_text} to {lineage["action"].end_text}.'
    )
    assert output["semantic_payload_json"]["result_kind"] == "CREATED"
    assert "action_id" not in output["semantic_payload_json"]
    assert "effect_id" not in output["semantic_payload_json"]
    assert specialized["action_id"] == lineage["action"].action_id
    assert specialized["effect_id"] == effect.effect_id
    assert specialized["effect_evidence_id"] == effect.effect_evidence_id


def test_projection_generation_and_adoption_replay_are_idempotent(engine, now):
    _lineage, effect = _confirmed(engine, now)
    adapter = _CompletionAdapter(_valid_plan)
    service = _service(engine, now, adapter)
    route = _route(service, adapter)

    build_operation = uuid4()
    projection = _build(service, effect.effect_id, operation_id=build_operation)
    assert _build(service, effect.effect_id, operation_id=build_operation) == projection
    assert _build(service, effect.effect_id).projection_id == projection.projection_id

    generate_operation = uuid4()
    generated = _generate(
        service, projection, route, operation_id=generate_operation
    )
    replayed = _generate(
        service, projection, route, operation_id=generate_operation
    )
    assert replayed == generated
    assert len(adapter.requests) == 1

    adopt_operation = uuid4()
    command = AdoptPersonalCalendarMutationOutputCommand(
        operation_id=adopt_operation,
        generated_output_id=generated.generated_output_id,
    )
    adopted = service.adopt_mutation_output(command)
    assert service.adopt_mutation_output(command) == adopted


def test_model_cannot_supply_calendar_facts_or_cross_completion_reference(engine, now):
    _lineage, effect = _confirmed(engine, now)

    extra = _CompletionAdapter(
        lambda context: {**context, "summary": "model-authored fact"}
    )
    service = _service(engine, now, extra)
    projection = _build(service, effect.effect_id)
    route = _route(service, extra)
    with pytest.raises(DomainError) as invalid:
        _generate(service, projection, route)
    assert invalid.value.code == "CALENDAR_MUTATION_RESULT_PLAN_INVALID"

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_mutation_generated_output).where(
                schema.personal_calendar_mutation_generated_output.c.projection_id
                == projection.projection_id
            )
        ).first() is None

    forged = _CompletionAdapter(
        lambda context: {**context, "mutation_completion_ref": str(uuid4())}
    )
    second_service = _service(engine, now, forged)
    with pytest.raises(DomainError) as mismatch:
        _generate(second_service, projection, route)
    assert mismatch.value.code == "CALENDAR_MUTATION_RESULT_PLAN_MISMATCH"


def test_only_confirmed_effect_can_enter_mutation_completion(engine, now):
    adapter = _CompletionAdapter(_valid_plan)
    service = _service(engine, now, adapter)
    with pytest.raises(DomainError) as missing:
        _build(service, uuid4())
    assert missing.value.code == "CALENDAR_MUTATION_CONFIRMED_EFFECT_NOT_FOUND"


def test_revoked_or_mismatched_route_blocks_model_transport(engine, now):
    _lineage, effect = _confirmed(engine, now)
    adapter = _CompletionAdapter(_valid_plan)
    service = _service(engine, now, adapter)
    projection = _build(service, effect.effect_id)
    route = _route(service, adapter)
    service.set_model_route_status(
        SetPersonalCalendarModelRouteStatusCommand(
            operation_id=uuid4(),
            route_binding_id=route.route_binding_id,
            status="REVOKED",
        )
    )
    with pytest.raises(DomainError) as revoked:
        _generate(service, projection, route)
    assert revoked.value.code == "CALENDAR_MUTATION_MODEL_ROUTE_REVOKED"
    assert adapter.requests == []

    other = _CompletionAdapter(_valid_plan)
    other.provider_binding_ref = "model.test/other-route"
    other_service = _service(engine, now, other)
    active_route = _route(other_service, other)
    mismatched_adapter = _CompletionAdapter(_valid_plan)
    mismatched_service = _service(engine, now, mismatched_adapter)
    with pytest.raises(DomainError) as mismatch:
        _generate(mismatched_service, projection, active_route)
    assert mismatch.value.code == "CALENDAR_MUTATION_MODEL_ROUTE_MISMATCH"
    assert mismatched_adapter.requests == []


def test_adoption_revalidates_effect_evidence_semantics(engine, now):
    lineage, effect = _confirmed(engine, now)
    adapter = _CompletionAdapter(_valid_plan)
    service = _service(engine, now, adapter)
    route = _route(service, adapter)
    projection = _build(service, effect.effect_id)
    generated = _generate(service, projection, route)

    from sqlalchemy import update

    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_effect_evidence)
            .where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == effect.effect_evidence_id
            )
            .values(normalized_summary=f"tampered:{lineage['action'].summary}")
        )

    with pytest.raises(DomainError) as mismatch:
        service.adopt_mutation_output(
            AdoptPersonalCalendarMutationOutputCommand(
                operation_id=uuid4(),
                generated_output_id=generated.generated_output_id,
            )
        )
    assert mismatch.value.code == "CALENDAR_MUTATION_EFFECT_LINEAGE_MISMATCH"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_mutation_adoption).where(
                schema.personal_calendar_mutation_adoption.c.generated_output_id
                == generated.generated_output_id
            )
        ).first() is None
