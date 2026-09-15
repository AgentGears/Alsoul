from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    GrantCalendarReadPermissionCommand,
    SetCalendarReadPolicyCommand,
    SetPermissionStatusCommand,
)
from alsoul.domain.personal_calendar_execution import (
    CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
)
from alsoul.domain.personal_calendar_reconciliation import (
    CalendarCreateReconciliationContract,
    PersonalCalendarCreateReconciliationObservation,
    ReconcilePersonalCalendarCreateUnknownEffectCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import (
    CALENDAR_READ_PERMISSION_GRANT_TEXT,
    ZoneInfoCalendarTimeResolver,
)
from alsoul.services.personal_calendar_effect import PersonalCalendarEffectServices
from alsoul.services.personal_calendar_reconciliation import (
    PersonalCalendarReconciliationServices,
)
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_confirmed_effect as effect_cases
import test_f5b_calendar_execution_fence as execution_cases
import test_f5b_calendar_mutation_transport as transport_cases


class _ReconciliationAdapter:
    adapter_binding_ref = "calendar-reconcile:test-adapter"
    adapter_version = "calendar-reconcile.adapter.v1"
    read_capability_contract_version = authority_cases._CAPABILITY_VERSION
    correlation_contract_version = CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION
    external_system_ref = "calendar.test"

    def __init__(self, now, action, *, mode="found"):
        self.now = now
        self.action = action
        self.mode = mode
        self.calls = []

    def lookup_create_effect(self, request):
        self.calls.append(request)
        if self.mode == "unknown":
            raise AdapterOutcomeUnknown("reconciliation outcome unavailable")
        if self.mode == "rejected":
            raise AdapterRejected("reconciliation lookup rejected")
        if self.mode == "not-found":
            return PersonalCalendarCreateReconciliationObservation(
                status="NOT_FOUND",
                correlation_key=request.correlation_key,
                observed_at=self.now,
            )

        correlation_key = request.correlation_key
        summary = self.action.summary
        if self.mode == "wrong-correlation":
            correlation_key = "calendar-create:unrelated"
        elif self.mode == "divergent-summary":
            summary = f"wrong:{summary}"
        return PersonalCalendarCreateReconciliationObservation(
            status="FOUND",
            correlation_key=correlation_key,
            observed_at=self.now,
            external_effect_ref="provider-event:reconciled-1",
            external_system_ref=request.external_system_ref,
            external_resource_ref=request.external_resource_ref,
            summary=summary,
            normalized_start_at=self.action.normalized_start_at,
            normalized_end_at=self.action.normalized_end_at,
            provider_status="CREATED",
            receipt_ref="provider-reconcile:receipt-1",
        )


def _contract(*, max_probes=3):
    return CalendarCreateReconciliationContract(
        read_capability_contract_version=authority_cases._CAPABILITY_VERSION,
        correlation_contract_version=CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
        max_probes=max_probes,
    )


def _service(engine, now, adapter, *, max_probes=3):
    return PersonalCalendarReconciliationServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        reconciliation_contract=_contract(max_probes=max_probes),
        reconciliation_adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _unknown_mutation(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    mutation_adapter = transport_cases._MutationAdapter(now, mode="unknown")
    transport = transport_cases._service(engine, now, mutation_adapter)
    result = transport_cases._dispatch(transport, lineage["attempt"])
    assert result.status == "UNKNOWN_EFFECT"
    assert result.effect_evidence_id is None
    return lineage, mutation_adapter, transport


def _read_authority(lineage, now):
    service = lineage["execution_service"]
    grant_event = authority_cases._append_counterpart_event(
        lineage["foundation"],
        lineage["ids"],
        now,
        CALENDAR_READ_PERMISSION_GRANT_TEXT,
    )
    permission = service.grant_read_permission(
        GrantCalendarReadPermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=lineage["ids"].companion_person_id,
            counterpart_id=lineage["ids"].counterpart_id,
            relationship_id=lineage["ids"].relationship_id,
            personal_resource_binding_id=(
                lineage["resource"].personal_resource_binding_id
            ),
            capability_contract_version=authority_cases._CAPABILITY_VERSION,
            grant_policy_version=authority_cases._GRANT_POLICY_VERSION,
            source_interaction_event_id=grant_event.event_id,
        )
    )
    service.set_read_policy(
        SetCalendarReadPolicyCommand(
            operation_id=uuid4(),
            companion_person_id=lineage["ids"].companion_person_id,
            counterpart_id=lineage["ids"].counterpart_id,
            relationship_id=lineage["ids"].relationship_id,
            capability_contract_version=authority_cases._CAPABILITY_VERSION,
            ai_policy_version="personal-calendar-read-v1",
            resource_scope_version="calendar-scope-v1",
            required_provider_scope=authority_cases._PROVIDER_SCOPE,
            permission_grant_policy_version=authority_cases._GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(
                lineage["resource"].personal_resource_binding_id,
            ),
        )
    )
    credential = service.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-calendar-reader",
            secret_ref="secret-ref:calendar-read",
            provider_scopes=(authority_cases._PROVIDER_SCOPE,),
        )
    )
    return permission, credential


def _reconcile(service, attempt, permission, credential, *, operation_id=None):
    return service.reconcile_unknown_effect(
        ReconcilePersonalCalendarCreateUnknownEffectCommand(
            operation_id=operation_id or uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )


def test_current_authorized_reconciliation_recovers_matched_evidence_then_effect(
    engine, now
):
    lineage, mutation_adapter, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"])
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    reconciled = _reconcile(
        service,
        lineage["attempt"],
        permission,
        credential,
        operation_id=operation_id,
    )
    replay = _reconcile(
        service,
        lineage["attempt"],
        permission,
        credential,
        operation_id=operation_id,
    )

    assert replay == reconciled
    assert reconciled.status == "MATCHED_EFFECT_EVIDENCE"
    assert reconciled.effect_evidence_id is not None
    assert len(adapter.calls) == 1
    assert len(mutation_adapter.calls) == 1
    request = adapter.calls[0]
    assert request.correlation_key == lineage["attempt"].correlation_key
    assert request.external_resource_ref == "primary"
    assert request.credential_secret_ref == "secret-ref:calendar-read"

    with engine.connect() as conn:
        probe = conn.execute(
            select(schema.personal_calendar_create_reconciliation_probe).where(
                schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                == reconciled.reconciliation_probe_id
            )
        ).mappings().one()
        evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == reconciled.effect_evidence_id
            )
        ).mappings().one()
    assert probe["status"] == "MATCHED_EFFECT_EVIDENCE"
    assert probe["permission_id"] == permission.permission_id
    assert probe["permission_state_revision"] == 1
    assert probe["credential_binding_id"] == credential.credential_binding_id
    assert probe["read_policy_revision"] == 2
    assert evidence["validation_kind"] == "SEMANTIC_MATCH"
    assert evidence["correlation_key"] == lineage["attempt"].correlation_key

    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"

    effect = effect_cases._admit(
        PersonalCalendarEffectServices(
            engine,
            time_resolver=ZoneInfoCalendarTimeResolver(
                rules_version=authority_cases._RULES_VERSION
            ),
            clock=FixedClock(now),
            ids=UUIDGenerator(),
        ),
        lineage["attempt"],
        reconciled.effect_evidence_id,
    )
    assert effect.status == "CONFIRMED_EFFECT"
    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "CONFIRMED_EFFECT"
    assert guard["status"] == "CONFIRMED_EFFECT"


def test_not_found_reconciliation_remains_unknown_and_never_unlocks_retry(engine, now):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"], mode="not-found")
    service = _service(engine, now, adapter)

    result = _reconcile(service, lineage["attempt"], permission, credential)

    assert result.status == "UNKNOWN_EFFECT"
    assert result.effect_evidence_id is None
    with engine.connect() as conn:
        probe = conn.execute(
            select(schema.personal_calendar_create_reconciliation_probe).where(
                schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                == result.reconciliation_probe_id
            )
        ).mappings().one()
        assert probe["status"] == "NOT_FOUND"
        assert conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None

    with pytest.raises(DomainError) as locked:
        execution_cases._prepare(
            lineage["execution_service"],
            lineage["action"],
            lineage["approval"],
            lineage["credential"],
        )
    assert locked.value.code == "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED"


def test_reconciliation_requires_fresh_current_read_authority(engine, now):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    lineage["execution_service"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=permission.permission_id,
        )
    )
    adapter = _ReconciliationAdapter(now, lineage["action"])

    with pytest.raises(DomainError) as revoked:
        _reconcile(
            _service(engine, now, adapter),
            lineage["attempt"],
            permission,
            credential,
        )
    assert revoked.value.code == "CALENDAR_READ_PERMISSION_REVOKED"
    assert adapter.calls == []


def test_uncorrelated_reconciliation_response_is_never_admitted_as_effect_evidence(
    engine, now
):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"], mode="wrong-correlation")
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as mismatch:
        _reconcile(service, lineage["attempt"], permission, credential)
    assert mismatch.value.code == "CALENDAR_CREATE_RECONCILIATION_CORRELATION_MISMATCH"

    with engine.connect() as conn:
        probe = conn.execute(
            select(schema.personal_calendar_create_reconciliation_probe).where(
                schema.personal_calendar_create_reconciliation_probe.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).mappings().one()
        assert probe["status"] == "UNKNOWN"
        assert conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None


def test_correlated_reconciliation_divergence_is_durable_but_not_terminal_effect(
    engine, now
):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"], mode="divergent-summary")
    result = _reconcile(
        _service(engine, now, adapter),
        lineage["attempt"],
        permission,
        credential,
    )

    assert result.status == "DIVERGENT_EFFECT_EVIDENCE"
    assert result.effect_evidence_id is not None
    with pytest.raises(DomainError) as rejected:
        effect_cases._admit(
            effect_cases._effect_service(engine, now),
            lineage["attempt"],
            result.effect_evidence_id,
        )
    assert rejected.value.code == "CALENDAR_CREATE_EFFECT_EVIDENCE_NOT_SUFFICIENT"


def test_unknown_or_rejected_probe_remains_unknown_and_operation_replay_does_not_recall(
    engine, now
):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"], mode="unknown")
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    result = _reconcile(
        service,
        lineage["attempt"],
        permission,
        credential,
        operation_id=operation_id,
    )
    replay = _reconcile(
        service,
        lineage["attempt"],
        permission,
        credential,
        operation_id=operation_id,
    )
    assert result.status == "UNKNOWN_EFFECT"
    assert replay == result
    assert len(adapter.calls) == 1


def test_reconciliation_probe_count_is_explicitly_bounded(engine, now):
    lineage, _, _ = _unknown_mutation(engine, now)
    permission, credential = _read_authority(lineage, now)
    adapter = _ReconciliationAdapter(now, lineage["action"], mode="not-found")
    service = _service(engine, now, adapter, max_probes=1)

    first = _reconcile(service, lineage["attempt"], permission, credential)
    assert first.status == "UNKNOWN_EFFECT"
    with pytest.raises(DomainError) as exhausted:
        _reconcile(service, lineage["attempt"], permission, credential)
    assert exhausted.value.code == "CALENDAR_CREATE_RECONCILIATION_PROBE_LIMIT_EXCEEDED"
    assert len(adapter.calls) == 1
