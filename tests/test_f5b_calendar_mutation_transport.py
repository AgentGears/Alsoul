from __future__ import annotations

from dataclasses import fields
from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.adapters.contracts import AdapterOutcomeUnknown
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_execution import (
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
    CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION,
    DispatchPersonalCalendarCreateMutationCommand,
    PersonalCalendarCreateMutationRequest,
    PersonalCalendarCreateMutationResponse,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_transport import (
    PersonalCalendarMutationTransportServices,
)
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_execution_fence as execution_cases


class _MutationAdapter:
    adapter_binding_ref = "calendar-create:test-adapter"
    adapter_contract_version = "calendar-create.adapter.v1"
    capability_contract_version = action_cases._CREATE_CAPABILITY_VERSION
    external_system_ref = "calendar.test"

    def __init__(self, now, *, mode="matched"):
        self.now = now
        self.mode = mode
        self.calls = []

    def create_event(self, request):
        self.calls.append(request)
        if self.mode == "unknown":
            raise AdapterOutcomeUnknown("provider outcome unavailable")
        if self.mode == "invalid":
            return {"raw": "provider-response"}

        resource_ref = request.external_resource_ref
        summary = request.summary
        if self.mode == "divergent-resource":
            resource_ref = "provider-calendar:wrong"
        elif self.mode == "divergent-summary":
            summary = f"wrong:{request.summary}"

        return PersonalCalendarCreateMutationResponse(
            correlation_key=request.correlation_key,
            external_effect_ref="provider-event:created-1",
            external_system_ref=request.external_system_ref,
            external_resource_ref=resource_ref,
            summary=summary,
            normalized_start_at=request.normalized_start_at,
            normalized_end_at=request.normalized_end_at,
            receipt_ref="provider-receipt:create-1",
            observed_at=self.now,
        )


class _ReplacementMutationAdapter(_MutationAdapter):
    adapter_binding_ref = "calendar-create:replacement-adapter"


def _service(engine, now, adapter, *, binding=None):
    return PersonalCalendarMutationTransportServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        mutation_adapter=adapter,
        execution_binding=binding or execution_cases._binding(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _prepared_action(engine, now):
    (
        ids,
        foundation,
        resource,
        write_permission,
        action,
        approval,
        credential,
        execution_service,
    ) = execution_cases._approved_action(engine, now)
    attempt = execution_cases._prepare(
        execution_service, action, approval, credential
    )
    return {
        "ids": ids,
        "foundation": foundation,
        "resource": resource,
        "write_permission": write_permission,
        "action": action,
        "approval": approval,
        "credential": credential,
        "execution_service": execution_service,
        "attempt": attempt,
    }


def _fenced_action(engine, now):
    lineage = _prepared_action(engine, now)
    lineage["fence"] = execution_cases._fence(
        lineage["execution_service"], lineage["attempt"]
    )
    return lineage


def _dispatch(service, attempt, *, operation_id=None):
    return service.dispatch_create_mutation(
        DispatchPersonalCalendarCreateMutationCommand(
            operation_id=operation_id or uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )


def _current_attempt_and_guard(engine, attempt):
    with engine.connect() as conn:
        attempt_state = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_state)
            .join(
                schema.personal_calendar_create_execution_attempt_head,
                schema.personal_calendar_create_execution_attempt_head.c.execution_attempt_id
                == schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id,
            )
            .where(
                schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id
                == attempt.execution_attempt_id,
                schema.personal_calendar_create_execution_attempt_state.c.revision
                == schema.personal_calendar_create_execution_attempt_head.c.current_revision,
            )
        ).mappings().one()
        guard = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_state)
            .join(
                schema.personal_calendar_create_action_dispatch_head,
                schema.personal_calendar_create_action_dispatch_head.c.action_id
                == schema.personal_calendar_create_action_dispatch_state.c.action_id,
            )
            .where(
                schema.personal_calendar_create_action_dispatch_state.c.action_id
                == attempt.action_id,
                schema.personal_calendar_create_action_dispatch_state.c.revision
                == schema.personal_calendar_create_action_dispatch_head.c.current_revision,
            )
        ).mappings().one()
    return attempt_state, guard


def _fence_row(engine, attempt):
    with engine.connect() as conn:
        return conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == attempt.execution_attempt_id
            )
        ).mappings().one_or_none()


def test_prepared_action_is_fenced_and_crosses_exact_adapter_once_with_minimized_evidence(
    engine, now
):
    lineage = _prepared_action(engine, now)
    adapter = _MutationAdapter(now)
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    result = _dispatch(service, lineage["attempt"], operation_id=operation_id)
    replay = _dispatch(service, lineage["attempt"], operation_id=operation_id)
    second_operation = _dispatch(service, lineage["attempt"])

    assert replay == result
    assert second_operation == result
    assert result.status == "MATCHED_EFFECT_EVIDENCE"
    assert result.effect_evidence_id is not None
    assert len(adapter.calls) == 1

    fence = _fence_row(engine, lineage["attempt"])
    assert fence is not None
    request = adapter.calls[0]
    assert isinstance(request, PersonalCalendarCreateMutationRequest)
    assert {field.name for field in fields(request)} == {
        "execution_attempt_id",
        "action_id",
        "external_system_ref",
        "external_resource_ref",
        "summary",
        "normalized_start_at",
        "normalized_end_at",
        "correlation_key",
        "credential_secret_ref",
        "capability_contract_version",
        "adapter_contract_version",
        "request_contract_version",
    }
    assert request.execution_attempt_id == lineage["attempt"].execution_attempt_id
    assert request.action_id == lineage["action"].action_id
    assert request.summary == lineage["action"].summary
    assert request.correlation_key == fence["correlation_key"]
    assert request.credential_secret_ref == "secret-ref:calendar-write"
    assert request.request_contract_version == CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION

    with engine.connect() as conn:
        dispatch = conn.execute(
            select(schema.personal_calendar_create_mutation_dispatch).where(
                schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).mappings().one()
        evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == result.effect_evidence_id
            )
        ).mappings().one()

    assert set(dispatch) == {
        "execution_attempt_id",
        "action_id",
        "request_contract_version",
        "started_at",
    }
    assert dispatch["request_contract_version"] == CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION
    assert evidence["validation_kind"] == "SEMANTIC_MATCH"
    assert evidence["correlation_key"] == fence["correlation_key"]
    assert evidence["normalized_summary"] == lineage["action"].summary
    assert evidence["provider_status"] == "CREATED"
    assert evidence["evidence_schema_version"] == CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION
    assert "credential_secret_ref" not in evidence

    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "DISPATCH_FENCED"
    assert guard["status"] == "DISPATCH_FENCED"


def test_unknown_adapter_outcome_is_durable_and_never_blindly_redispatched(engine, now):
    lineage = _prepared_action(engine, now)
    adapter = _MutationAdapter(now, mode="unknown")
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    result = _dispatch(service, lineage["attempt"], operation_id=operation_id)
    replay = _dispatch(service, lineage["attempt"], operation_id=operation_id)
    another_operation = _dispatch(service, lineage["attempt"])

    assert result.status == "UNKNOWN_EFFECT"
    assert replay == result
    assert another_operation == result
    assert result.effect_evidence_id is None
    assert len(adapter.calls) == 1

    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None


def test_surviving_fence_is_not_reusable_transport_authority(engine, now):
    lineage = _fenced_action(engine, now)
    adapter = _MutationAdapter(now)
    service = _service(engine, now, adapter)

    result = _dispatch(service, lineage["attempt"])

    assert result.status == "UNKNOWN_EFFECT"
    assert len(adapter.calls) == 0
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_mutation_dispatch).where(
                schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None
    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"


def test_surviving_one_shot_dispatch_claim_without_evidence_recovers_unknown_without_call(
    engine, now
):
    lineage = _fenced_action(engine, now)
    with engine.begin() as conn:
        conn.execute(
            schema.personal_calendar_create_mutation_dispatch.insert().values(
                execution_attempt_id=lineage["attempt"].execution_attempt_id,
                action_id=lineage["action"].action_id,
                request_contract_version=CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION,
                started_at=now,
            )
        )

    adapter = _MutationAdapter(now)
    service = _service(engine, now, adapter)
    result = _dispatch(service, lineage["attempt"])

    assert result.status == "UNKNOWN_EFFECT"
    assert len(adapter.calls) == 0
    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"


def test_correlated_semantic_divergence_is_evidence_but_not_effect_truth(engine, now):
    lineage = _prepared_action(engine, now)
    adapter = _MutationAdapter(now, mode="divergent-resource")
    service = _service(engine, now, adapter)

    result = _dispatch(service, lineage["attempt"])

    assert result.status == "DIVERGENT_EFFECT_EVIDENCE"
    assert result.effect_evidence_id is not None
    assert len(adapter.calls) == 1
    with engine.connect() as conn:
        evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == result.effect_evidence_id
            )
        ).mappings().one()
    assert evidence["validation_kind"] == "SEMANTIC_DIVERGENCE"
    assert evidence["external_resource_ref"] == "provider-calendar:wrong"

    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"

    with pytest.raises(DomainError) as locked:
        execution_cases._prepare(
            lineage["execution_service"],
            lineage["action"],
            lineage["approval"],
            lineage["credential"],
        )
    assert locked.value.code == "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED"


def test_wrong_adapter_fails_before_fence_or_transport_claim(engine, now):
    lineage = _prepared_action(engine, now)
    adapter = _ReplacementMutationAdapter(now)
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as mismatch:
        _dispatch(service, lineage["attempt"])
    assert mismatch.value.code == "CALENDAR_CREATE_MUTATION_ADAPTER_MISMATCH"
    assert len(adapter.calls) == 0
    assert _fence_row(engine, lineage["attempt"]) is None

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_mutation_dispatch).where(
                schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None


def test_invalid_normalized_response_marks_attempt_unknown_and_keeps_raw_material_out(
    engine, now
):
    lineage = _prepared_action(engine, now)
    adapter = _MutationAdapter(now, mode="invalid")
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    with pytest.raises(DomainError) as invalid:
        _dispatch(service, lineage["attempt"], operation_id=operation_id)
    assert invalid.value.code == "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID"
    assert len(adapter.calls) == 1

    attempt_state, guard = _current_attempt_and_guard(engine, lineage["attempt"])
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None

    replay = _dispatch(service, lineage["attempt"], operation_id=operation_id)
    assert replay.status == "UNKNOWN_EFFECT"
    assert len(adapter.calls) == 1


def test_recovery_after_matched_evidence_remains_conservative_without_redispatch(engine, now):
    lineage = _prepared_action(engine, now)
    adapter = _MutationAdapter(now)
    service = _service(engine, now, adapter)
    matched = _dispatch(service, lineage["attempt"])
    assert matched.status == "MATCHED_EFFECT_EVIDENCE"

    recovered = service.recover_fenced_attempt(
        RecoverPersonalCalendarCreateFencedAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=lineage["attempt"].execution_attempt_id,
        )
    )
    assert recovered.status == "UNKNOWN_EFFECT"

    second = _dispatch(service, lineage["attempt"])
    assert second == matched
    assert len(adapter.calls) == 1
