from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_reconciliation import (
    PersonalCalendarCreateReconciliationResult,
    ReconcilePersonalCalendarCreateUnknownEffectCommand,
)
from alsoul.storage import schema

import test_f5b_calendar_mutation_transport as transport_cases
import test_f5b_calendar_reconciliation as reconciliation_cases


def test_second_replay_check_returns_completed_operation_without_provider_recall(
    engine, now
):
    lineage, _, _ = reconciliation_cases._unknown_mutation(engine, now)
    permission, credential = reconciliation_cases._read_authority(lineage, now)
    adapter = reconciliation_cases._ReconciliationAdapter(now, lineage["action"])
    service = reconciliation_cases._service(engine, now, adapter)
    expected = PersonalCalendarCreateReconciliationResult(
        reconciliation_probe_id=uuid4(),
        execution_attempt_id=lineage["attempt"].execution_attempt_id,
        action_id=lineage["action"].action_id,
        status="UNKNOWN_EFFECT",
        effect_evidence_id=None,
    )
    service._qualify_contract = lambda: None
    service._start_probe = lambda command, req_digest: {"replay": expected}

    result = service.reconcile_unknown_effect(
        ReconcilePersonalCalendarCreateUnknownEffectCommand(
            operation_id=uuid4(),
            execution_attempt_id=lineage["attempt"].execution_attempt_id,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )

    assert result == expected
    assert adapter.calls == []


def test_positive_reconciliation_without_one_shot_dispatch_claim_is_rejected(
    engine, now
):
    lineage = transport_cases._fenced_action(engine, now)
    mutation_adapter = transport_cases._MutationAdapter(now)
    mutation_service = transport_cases._service(engine, now, mutation_adapter)
    unknown = transport_cases._dispatch(mutation_service, lineage["attempt"])
    assert unknown.status == "UNKNOWN_EFFECT"
    assert mutation_adapter.calls == []

    permission, credential = reconciliation_cases._read_authority(lineage, now)
    adapter = reconciliation_cases._ReconciliationAdapter(now, lineage["action"])
    service = reconciliation_cases._service(engine, now, adapter)

    with pytest.raises(DomainError) as impossible:
        reconciliation_cases._reconcile(
            service,
            lineage["attempt"],
            permission,
            credential,
        )
    assert (
        impossible.value.code
        == "CALENDAR_CREATE_RECONCILIATION_FOUND_WITHOUT_DISPATCH_CLAIM"
    )
    assert len(adapter.calls) == 1

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
