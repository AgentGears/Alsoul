from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    SetCredentialBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.domain.personal_calendar_approval import (
    RevokePersonalCalendarCreateApprovalCommand,
)
from alsoul.domain.personal_calendar_execution import (
    AbandonPersonalCalendarCreateExecutionAttemptCommand,
    CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION,
    CalendarCreateExecutionBinding,
    FencePersonalCalendarCreateExecutionAttemptCommand,
    PreparePersonalCalendarCreateExecutionAttemptCommand,
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_execution import PersonalCalendarExecutionServices
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_approval_authority as approval_cases


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _binding(*, adapter_binding_ref="calendar-create:test-adapter"):
    return CalendarCreateExecutionBinding(
        adapter_binding_ref=adapter_binding_ref,
        adapter_contract_version="calendar-create.adapter.v1",
        executor_contract_version="calendar-create.executor.v1",
        correlation_contract_version=CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
        negative_confirmation_contract_version=(
            CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION
        ),
        capability_contract_version=action_cases._CREATE_CAPABILITY_VERSION,
        external_system_ref="calendar.test",
    )


def _service(engine, now, *, binding=None, approval_adapter=None):
    return PersonalCalendarExecutionServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        execution_binding=binding,
        approval_adapter=approval_adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _approved_action(engine, now, *, binding=None):
    ids, foundation, resource, write_permission, action = approval_cases._prepared_action(
        engine, now
    )
    service = _service(
        engine,
        now,
        binding=binding or _binding(),
        approval_adapter=approval_cases._ApprovalAdapter(),
    )
    presentation = approval_cases._present(service, action)
    approval_event = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        approval_cases._approval_text(action),
    )
    approval = approval_cases._admit(service, presentation, approval_event)
    credential = service.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-calendar-writer",
            secret_ref="secret-ref:calendar-write",
            provider_scopes=(action_cases._CREATE_PROVIDER_SCOPE,),
        )
    )
    return (
        ids,
        foundation,
        resource,
        write_permission,
        action,
        approval,
        credential,
        service,
    )


def _prepare(service, action, approval, credential, *, operation_id=None):
    return service.prepare_execution_attempt(
        PreparePersonalCalendarCreateExecutionAttemptCommand(
            operation_id=operation_id or uuid4(),
            action_id=action.action_id,
            approval_id=approval.approval_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )


def _fence(service, attempt, *, operation_id=None):
    return service.fence_execution_attempt(
        FencePersonalCalendarCreateExecutionAttemptCommand(
            operation_id=operation_id or uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )


def test_one_action_has_one_dispatch_eligible_attempt_and_stable_action_correlation(
    engine, now
):
    _, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    operation_id = uuid4()
    first = _prepare(
        service,
        action,
        approval,
        credential,
        operation_id=operation_id,
    )
    replay = _prepare(
        service,
        action,
        approval,
        credential,
        operation_id=operation_id,
    )

    assert replay == first
    assert first.attempt_generation == 1
    assert first.status == "PREPARED"
    assert first.correlation_key.startswith("calendar-create:")
    assert first.correlation_key != action.action_digest

    with pytest.raises(DomainError) as locked:
        _prepare(service, action, approval, credential)
    _assert_code(locked, "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED")

    with engine.connect() as conn:
        attempts = conn.execute(
            select(schema.personal_calendar_create_execution_attempt).where(
                schema.personal_calendar_create_execution_attempt.c.action_id
                == action.action_id
            )
        ).mappings().all()
        guard = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_state)
            .join(
                schema.personal_calendar_create_action_dispatch_head,
                schema.personal_calendar_create_action_dispatch_head.c.action_id
                == schema.personal_calendar_create_action_dispatch_state.c.action_id,
            )
            .where(
                schema.personal_calendar_create_action_dispatch_state.c.action_id
                == action.action_id,
                schema.personal_calendar_create_action_dispatch_state.c.revision
                == schema.personal_calendar_create_action_dispatch_head.c.current_revision,
            )
        ).mappings().one()
    assert len(attempts) == 1
    assert guard["status"] == "PREPARED"
    assert guard["execution_attempt_id"] == first.execution_attempt_id


def test_prepared_attempt_can_be_abandoned_before_fence_then_new_generation_claims(
    engine, now
):
    _, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    first = _prepare(service, action, approval, credential)

    abandoned = service.abandon_prepared_attempt(
        AbandonPersonalCalendarCreateExecutionAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=first.execution_attempt_id,
        )
    )
    assert abandoned.status == "ABANDONED"

    second = _prepare(service, action, approval, credential)
    assert second.execution_attempt_id != first.execution_attempt_id
    assert second.attempt_generation == 2
    assert second.correlation_key == first.correlation_key

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == first.execution_attempt_id
            )
        ).first() is None


def test_dispatch_fence_rechecks_authority_and_pins_exact_execution_semantics(
    engine, now
):
    ids, _, resource, write_permission, action, approval, credential, service = (
        _approved_action(engine, now)
    )
    attempt = _prepare(service, action, approval, credential)
    operation_id = uuid4()
    fenced = _fence(service, attempt, operation_id=operation_id)
    replay = _fence(service, attempt, operation_id=operation_id)

    assert replay == fenced
    assert fenced.status == "DISPATCH_FENCED"
    assert fenced.adapter_binding_ref == "calendar-create:test-adapter"
    assert fenced.correlation_key == attempt.correlation_key

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == attempt.execution_attempt_id
            )
        ).mappings().one()
        state = conn.execute(
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

    assert row["relationship_id"] == ids.relationship_id
    assert row["personal_resource_binding_id"] == resource.personal_resource_binding_id
    assert row["write_permission_id"] == write_permission.permission_id
    assert row["approval_id"] == approval.approval_id
    assert row["approval_state_revision"] == 1
    assert row["credential_binding_id"] == credential.credential_binding_id
    assert row["credential_binding_state_revision"] == 1
    assert row["provider_scope_snapshot_json"] == [action_cases._CREATE_PROVIDER_SCOPE]
    assert row["capability_semantic_operation"] == "calendar.event.create"
    assert row["capability_contract_version"] == action_cases._CREATE_CAPABILITY_VERSION
    assert row["ai_policy_version"] == "calendar-create-policy-v1"
    assert row["resource_scope_version"] == "calendar-create-resource-scope-v1"
    assert row["adapter_contract_version"] == "calendar-create.adapter.v1"
    assert row["executor_contract_version"] == "calendar-create.executor.v1"
    assert row["correlation_contract_version"] == CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION
    assert (
        row["negative_confirmation_contract_version"]
        == CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION
    )
    assert "secret_ref" not in row
    assert state["status"] == "DISPATCH_FENCED"


def test_authority_reduction_after_prepare_blocks_fence_without_creating_fence(
    engine, now
):
    ids, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    attempt = _prepare(service, action, approval, credential)
    service.set_relationship_status(
        SetPersonalWorldRelationshipStatusCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
        )
    )

    with pytest.raises(DomainError) as ended:
        _fence(service, attempt)
    _assert_code(ended, "RELATIONSHIP_NOT_ACTIVE")

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == attempt.execution_attempt_id
            )
        ).first() is None


def test_approval_revocation_after_prepare_blocks_fence_and_prepared_attempt_can_release(
    engine, now
):
    _, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    attempt = _prepare(service, action, approval, credential)
    service.revoke_create_approval(
        RevokePersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            approval_id=approval.approval_id,
        )
    )

    with pytest.raises(DomainError) as revoked:
        _fence(service, attempt)
    _assert_code(revoked, "CALENDAR_CREATE_EXECUTION_APPROVAL_INVALID")

    released = service.abandon_prepared_attempt(
        AbandonPersonalCalendarCreateExecutionAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )
    assert released.status == "ABANDONED"


def test_credential_revocation_after_prepare_blocks_fence(engine, now):
    _, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    attempt = _prepare(service, action, approval, credential)
    service.set_credential_status(
        SetCredentialBindingStatusCommand(
            operation_id=uuid4(),
            credential_binding_id=credential.credential_binding_id,
        )
    )

    with pytest.raises(DomainError) as revoked:
        _fence(service, attempt)
    _assert_code(revoked, "CALENDAR_CREATE_EXECUTION_CREDENTIAL_INVALID")


def test_fenced_attempt_recovers_unknown_with_original_pins_and_blocks_new_attempt(
    engine, now
):
    _, _, _, _, action, approval, credential, service = _approved_action(engine, now)
    attempt = _prepare(service, action, approval, credential)
    fenced = _fence(service, attempt)

    replacement = _service(
        engine,
        now,
        binding=_binding(adapter_binding_ref="calendar-create:replacement-adapter"),
    )
    recovered = replacement.recover_fenced_attempt(
        RecoverPersonalCalendarCreateFencedAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )
    assert recovered.status == "UNKNOWN_EFFECT"
    assert recovered.adapter_binding_ref == fenced.adapter_binding_ref
    assert recovered.adapter_binding_ref != "calendar-create:replacement-adapter"
    assert recovered.correlation_key == fenced.correlation_key

    with pytest.raises(DomainError) as locked:
        _prepare(replacement, action, approval, credential)
    _assert_code(locked, "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED")

    with engine.connect() as conn:
        guard = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_state)
            .join(
                schema.personal_calendar_create_action_dispatch_head,
                schema.personal_calendar_create_action_dispatch_head.c.action_id
                == schema.personal_calendar_create_action_dispatch_state.c.action_id,
            )
            .where(
                schema.personal_calendar_create_action_dispatch_state.c.action_id
                == action.action_id,
                schema.personal_calendar_create_action_dispatch_state.c.revision
                == schema.personal_calendar_create_action_dispatch_head.c.current_revision,
            )
        ).mappings().one()
    assert guard["status"] == "UNKNOWN_EFFECT"
    assert guard["execution_attempt_id"] == attempt.execution_attempt_id


def test_unqualified_or_wrong_execution_binding_fails_before_attempt_claim(engine, now):
    _, _, _, _, action, approval, credential, _ = _approved_action(engine, now)
    missing = _service(engine, now, binding=None)
    with pytest.raises(DomainError) as no_binding:
        _prepare(missing, action, approval, credential)
    _assert_code(no_binding, "CALENDAR_CREATE_EXECUTION_BINDING_MISSING")

    wrong = CalendarCreateExecutionBinding(
        adapter_binding_ref="calendar-create:test-adapter",
        adapter_contract_version="calendar-create.adapter.v1",
        executor_contract_version="calendar-create.executor.v1",
        correlation_contract_version=CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
        negative_confirmation_contract_version=(
            CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION
        ),
        capability_contract_version="calendar.event.create.v999",
        external_system_ref="calendar.test",
    )
    mismatched = _service(engine, now, binding=wrong)
    with pytest.raises(DomainError) as mismatch:
        _prepare(mismatched, action, approval, credential)
    _assert_code(mismatch, "CALENDAR_CREATE_EXECUTION_BINDING_INVALID")

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_execution_attempt).where(
                schema.personal_calendar_create_execution_attempt.c.action_id
                == action.action_id
            )
        ).first() is None
