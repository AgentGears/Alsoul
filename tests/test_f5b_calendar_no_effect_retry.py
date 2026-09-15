from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_approval import (
    RevokePersonalCalendarCreateApprovalCommand,
)
from alsoul.domain.personal_calendar_execution import (
    CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
    CalendarCreateExecutionBinding,
    FencePersonalCalendarCreateExecutionAttemptCommand,
    PreparePersonalCalendarCreateExecutionAttemptCommand,
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.domain.personal_calendar_no_effect import (
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION,
    CalendarCreateNegativeConfirmationContract,
    PersonalCalendarCreateTerminalNoEffectObservation,
    PreparePersonalCalendarCreateRetryAttemptCommand,
    ReconcilePersonalCalendarCreateNoEffectCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_execution import PersonalCalendarExecutionServices
from alsoul.services.personal_calendar_reconciliation import (
    PersonalCalendarReconciliationServices,
)
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_approval_authority as approval_cases
import test_f5b_calendar_execution_fence as execution_cases
import test_f5b_calendar_mutation_transport as transport_cases
import test_f5b_calendar_reconciliation as reconciliation_cases


class _TerminalNoEffectAdapter:
    adapter_binding_ref = "calendar-reconcile:test-adapter"
    adapter_version = "calendar-reconcile.adapter.v2"
    read_capability_contract_version = authority_cases._CAPABILITY_VERSION
    correlation_contract_version = CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION
    negative_confirmation_contract_version = (
        CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
    )
    external_system_ref = "calendar.test"

    def __init__(self, now, *, mode="terminal"):
        self.now = now
        self.mode = mode
        self.calls = []

    def lookup_create_effect(self, request):
        raise AssertionError("positive reconciliation path must not be used")

    def lookup_terminal_no_effect(self, request):
        self.calls.append(request)
        if self.mode == "inconclusive":
            return PersonalCalendarCreateTerminalNoEffectObservation(
                status="INCONCLUSIVE",
                correlation_key=request.correlation_key,
                observed_at=self.now,
                intended_effect_absent=False,
                terminal_non_application=False,
                terminality_scope="EXACT_EXECUTION_ATTEMPT",
                operation_status="PENDING",
            )
        terminal = self.mode != "weak-terminal"
        return PersonalCalendarCreateTerminalNoEffectObservation(
            status="TERMINAL_NO_EFFECT",
            correlation_key=request.correlation_key,
            observed_at=self.now,
            intended_effect_absent=True,
            terminal_non_application=terminal,
            terminality_scope="EXACT_EXECUTION_ATTEMPT",
            operation_status="TERMINAL_NOT_APPLIED",
            terminality_proof_ref="provider-operation:terminal-1",
            absence_proof_ref="provider-correlation:absent-1",
        )


def _supported_binding():
    return CalendarCreateExecutionBinding(
        adapter_binding_ref="calendar-create:test-adapter",
        adapter_contract_version="calendar-create.adapter.v1",
        executor_contract_version="calendar-create.executor.v1",
        correlation_contract_version=CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
        negative_confirmation_contract_version=(
            CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
        ),
        capability_contract_version=action_cases._CREATE_CAPABILITY_VERSION,
        external_system_ref="calendar.test",
    )


def _negative_contract():
    return CalendarCreateNegativeConfirmationContract(
        read_capability_contract_version=authority_cases._CAPABILITY_VERSION,
        correlation_contract_version=CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
    )


def _unknown_mutation(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    adapter = transport_cases._MutationAdapter(now, mode="unknown")
    transport = transport_cases._service(
        engine,
        now,
        adapter,
        binding=_supported_binding(),
    )
    result = transport_cases._dispatch(transport, lineage["attempt"])
    assert result.status == "UNKNOWN_EFFECT"
    assert len(adapter.calls) == 1
    return lineage, adapter


def _read_authority(lineage, now):
    return reconciliation_cases._read_authority(lineage, now)


def _service(engine, now, adapter):
    return PersonalCalendarReconciliationServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        reconciliation_contract=reconciliation_cases._contract(),
        reconciliation_adapter=adapter,
        negative_confirmation_contract=_negative_contract(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _reconcile_no_effect(
    service, attempt, permission, credential, *, operation_id=None
):
    return service.reconcile_confirmed_no_effect(
        ReconcilePersonalCalendarCreateNoEffectCommand(
            operation_id=operation_id or uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )


def _confirm_no_effect(engine, now):
    lineage, mutation_adapter = _unknown_mutation(engine, now)
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now)
    service = _service(engine, now, adapter)
    result = _reconcile_no_effect(
        service, lineage["attempt"], permission, read_credential
    )
    assert result.status == "CONFIRMED_NO_EFFECT"
    return lineage, mutation_adapter, permission, read_credential, adapter, result


def _retry_service(engine, now):
    return PersonalCalendarExecutionServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        execution_binding=_supported_binding(),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def test_terminal_negative_proof_atomically_confirms_no_effect_and_replays(engine, now):
    lineage, mutation_adapter = _unknown_mutation(engine, now)
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now)
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    first = _reconcile_no_effect(
        service,
        lineage["attempt"],
        permission,
        read_credential,
        operation_id=operation_id,
    )
    replay = _reconcile_no_effect(
        service,
        lineage["attempt"],
        permission,
        read_credential,
        operation_id=operation_id,
    )

    assert replay == first
    assert first.status == "CONFIRMED_NO_EFFECT"
    assert first.no_effect_id is not None
    assert first.no_effect_evidence_id is not None
    assert len(adapter.calls) == 1
    assert len(mutation_adapter.calls) == 1

    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "CONFIRMED_NO_EFFECT"
    assert guard["status"] == "CONFIRMED_NO_EFFECT"

    with engine.connect() as conn:
        evidence = conn.execute(
            select(schema.personal_calendar_create_no_effect_evidence).where(
                schema.personal_calendar_create_no_effect_evidence.c.no_effect_evidence_id
                == first.no_effect_evidence_id
            )
        ).mappings().one()
        support = conn.execute(
            select(schema.personal_calendar_create_no_effect_support).where(
                schema.personal_calendar_create_no_effect_support.c.no_effect_id
                == first.no_effect_id
            )
        ).mappings().one()
        probe = conn.execute(
            select(schema.personal_calendar_create_reconciliation_probe).where(
                schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                == first.reconciliation_probe_id
            )
        ).mappings().one()
        claim = conn.execute(
            select(schema.personal_calendar_create_no_effect_operation_claim).where(
                schema.personal_calendar_create_no_effect_operation_claim.c.operation_id
                == operation_id
            )
        ).mappings().one()
    assert evidence["operation_status"] == "TERMINAL_NOT_APPLIED"
    assert evidence["terminality_scope"] == "EXACT_EXECUTION_ATTEMPT"
    assert evidence["intended_effect_absent"] is True
    assert evidence["terminal_non_application"] is True
    assert support["support_kind"] == "SUPPORTS"
    assert probe["status"] == "NOT_FOUND"
    assert claim["status"] == "COMPLETED"


def test_inconclusive_terminal_reconciliation_stays_unknown(engine, now):
    lineage, _ = _unknown_mutation(engine, now)
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now, mode="inconclusive")

    result = _reconcile_no_effect(
        _service(engine, now, adapter),
        lineage["attempt"],
        permission,
        read_credential,
    )
    assert result.status == "UNKNOWN_EFFECT"
    assert result.no_effect_id is None
    assert result.no_effect_evidence_id is None
    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"


def test_absence_without_terminal_non_application_cannot_confirm_no_effect(engine, now):
    lineage, _ = _unknown_mutation(engine, now)
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now, mode="weak-terminal")

    with pytest.raises(DomainError) as weak:
        _reconcile_no_effect(
            _service(engine, now, adapter),
            lineage["attempt"],
            permission,
            read_credential,
        )
    assert weak.value.code == "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_NOT_TERMINAL"
    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_no_effect)
        ).first() is None


def test_terminal_no_effect_requires_supported_contract_pinned_before_mutation(engine, now):
    lineage, _, _ = reconciliation_cases._unknown_mutation(engine, now)
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now)

    with pytest.raises(DomainError) as mismatch:
        _reconcile_no_effect(
            _service(engine, now, adapter),
            lineage["attempt"],
            permission,
            read_credential,
        )
    assert mismatch.value.code == "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_FENCE_MISMATCH"
    assert adapter.calls == []


def test_terminal_no_effect_requires_actual_one_shot_mutation_dispatch_claim(engine, now):
    ids, foundation, resource, write_permission, action = approval_cases._prepared_action(
        engine, now
    )
    execution_service = execution_cases._service(
        engine,
        now,
        binding=_supported_binding(),
        approval_adapter=approval_cases._ApprovalAdapter(),
    )
    presentation = approval_cases._present(execution_service, action)
    approval_event = authority_cases._append_counterpart_event(
        foundation,
        ids,
        now,
        approval_cases._approval_text(action),
    )
    approval = approval_cases._admit(
        execution_service, presentation, approval_event
    )
    credential = execution_service.bind_credential(
        execution_cases.BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-calendar-writer",
            secret_ref="secret-ref:calendar-write",
            provider_scopes=(action_cases._CREATE_PROVIDER_SCOPE,),
        )
    )
    attempt = execution_cases._prepare(
        execution_service, action, approval, credential
    )
    execution_service.fence_execution_attempt(
        FencePersonalCalendarCreateExecutionAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )
    execution_service.recover_fenced_attempt(
        RecoverPersonalCalendarCreateFencedAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
        )
    )
    lineage = {
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
    permission, read_credential = _read_authority(lineage, now)
    adapter = _TerminalNoEffectAdapter(now)

    with pytest.raises(DomainError) as missing:
        _reconcile_no_effect(
            _service(engine, now, adapter),
            attempt,
            permission,
            read_credential,
        )
    assert missing.value.code == "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_DISPATCH_CLAIM_MISSING"
    assert adapter.calls == []


def test_confirmed_no_effect_retry_is_explicit_single_consumption_with_fresh_authority(
    engine, now
):
    lineage, _, _, _, _, no_effect = _confirm_no_effect(engine, now)
    retry_service = _retry_service(engine, now)

    with pytest.raises(DomainError) as ordinary_locked:
        retry_service.prepare_execution_attempt(
            PreparePersonalCalendarCreateExecutionAttemptCommand(
                operation_id=uuid4(),
                action_id=lineage["action"].action_id,
                approval_id=lineage["approval"].approval_id,
                credential_binding_id=lineage["credential"].credential_binding_id,
            )
        )
    assert ordinary_locked.value.code == "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED"

    operation_id = uuid4()
    command = PreparePersonalCalendarCreateRetryAttemptCommand(
        operation_id=operation_id,
        prior_execution_attempt_id=lineage["attempt"].execution_attempt_id,
        approval_id=lineage["approval"].approval_id,
        credential_binding_id=lineage["credential"].credential_binding_id,
    )
    retry = retry_service.prepare_retry_attempt(command)
    replay = retry_service.prepare_retry_attempt(command)
    assert replay == retry
    assert retry.status == "PREPARED"
    assert retry.attempt_generation == lineage["attempt"].attempt_generation + 1
    assert retry.correlation_key == lineage["attempt"].correlation_key
    assert retry.no_effect_id == no_effect.no_effect_id

    with engine.connect() as conn:
        claim = conn.execute(
            select(schema.personal_calendar_create_retry_claim).where(
                schema.personal_calendar_create_retry_claim.c.prior_execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).mappings().one()
    assert claim["new_execution_attempt_id"] == retry.execution_attempt_id

    with pytest.raises(DomainError) as second:
        retry_service.prepare_retry_attempt(
            PreparePersonalCalendarCreateRetryAttemptCommand(
                operation_id=uuid4(),
                prior_execution_attempt_id=lineage["attempt"].execution_attempt_id,
                approval_id=lineage["approval"].approval_id,
                credential_binding_id=lineage["credential"].credential_binding_id,
            )
        )
    assert second.value.code == "CALENDAR_CREATE_RETRY_NOT_ELIGIBLE"


def test_retry_rechecks_current_approval_before_consuming_no_effect(engine, now):
    lineage, _, _, _, _, _ = _confirm_no_effect(engine, now)
    retry_service = _retry_service(engine, now)
    retry_service.revoke_create_approval(
        RevokePersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(),
            approval_id=lineage["approval"].approval_id,
        )
    )

    with pytest.raises(DomainError) as revoked:
        retry_service.prepare_retry_attempt(
            PreparePersonalCalendarCreateRetryAttemptCommand(
                operation_id=uuid4(),
                prior_execution_attempt_id=lineage["attempt"].execution_attempt_id,
                approval_id=lineage["approval"].approval_id,
                credential_binding_id=lineage["credential"].credential_binding_id,
            )
        )
    assert revoked.value.code == "CALENDAR_CREATE_EXECUTION_APPROVAL_INVALID"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_retry_claim)
        ).first() is None
