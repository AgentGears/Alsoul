from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, update

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_effect import (
    AdmitPersonalCalendarCreateConfirmedEffectCommand,
    CALENDAR_CREATE_EFFECT_SCHEMA_VERSION,
    CALENDAR_CREATE_EFFECT_SUPPORT_KIND,
)
from alsoul.domain.personal_calendar_execution import (
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_effect import PersonalCalendarEffectServices
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_execution_fence as execution_cases
import test_f5b_calendar_mutation_transport as transport_cases


def _effect_service(engine, now):
    return PersonalCalendarEffectServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _matched_transport(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    adapter = transport_cases._MutationAdapter(now)
    transport = transport_cases._service(engine, now, adapter)
    evidence = transport_cases._dispatch(transport, lineage["attempt"])
    assert evidence.status == "MATCHED_EFFECT_EVIDENCE"
    assert evidence.effect_evidence_id is not None
    return lineage, adapter, transport, evidence


def _admit(service, attempt, evidence_id, *, operation_id=None):
    return service.admit_confirmed_effect(
        AdmitPersonalCalendarCreateConfirmedEffectCommand(
            operation_id=operation_id or uuid4(),
            execution_attempt_id=attempt.execution_attempt_id,
            effect_evidence_id=evidence_id,
        )
    )


def test_matched_durable_evidence_admits_exactly_one_terminal_effect_with_support(
    engine, now
):
    lineage, adapter, transport, evidence = _matched_transport(engine, now)
    service = _effect_service(engine, now)
    operation_id = uuid4()

    confirmed = _admit(
        service,
        lineage["attempt"],
        evidence.effect_evidence_id,
        operation_id=operation_id,
    )
    replay = _admit(
        service,
        lineage["attempt"],
        evidence.effect_evidence_id,
        operation_id=operation_id,
    )
    another_operation = _admit(
        service,
        lineage["attempt"],
        evidence.effect_evidence_id,
    )

    assert replay == confirmed
    assert another_operation == confirmed
    assert confirmed.status == "CONFIRMED_EFFECT"
    assert confirmed.action_id == lineage["action"].action_id
    assert confirmed.execution_attempt_id == lineage["attempt"].execution_attempt_id
    assert confirmed.effect_evidence_id == evidence.effect_evidence_id

    with engine.connect() as conn:
        effect = conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.effect_id == confirmed.effect_id
            )
        ).mappings().one()
        support = conn.execute(
            select(schema.personal_calendar_create_effect_support).where(
                schema.personal_calendar_create_effect_support.c.effect_id
                == confirmed.effect_id
            )
        ).mappings().one()

    assert effect["status"] == "CONFIRMED_EFFECT"
    assert effect["effect_schema_version"] == CALENDAR_CREATE_EFFECT_SCHEMA_VERSION
    assert effect["execution_attempt_id"] == lineage["attempt"].execution_attempt_id
    assert support["effect_evidence_id"] == evidence.effect_evidence_id
    assert support["support_kind"] == CALENDAR_CREATE_EFFECT_SUPPORT_KIND

    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "CONFIRMED_EFFECT"
    assert guard["status"] == "CONFIRMED_EFFECT"

    with pytest.raises(DomainError) as locked:
        execution_cases._prepare(
            lineage["execution_service"],
            lineage["action"],
            lineage["approval"],
            lineage["credential"],
        )
    assert locked.value.code == "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED"

    recovered_transport = transport_cases._dispatch(transport, lineage["attempt"])
    assert recovered_transport == evidence
    assert len(adapter.calls) == 1


def test_matched_evidence_can_terminalize_attempt_after_conservative_unknown_recovery(
    engine, now
):
    lineage, _, transport, evidence = _matched_transport(engine, now)
    recovered = transport.recover_fenced_attempt(
        RecoverPersonalCalendarCreateFencedAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=lineage["attempt"].execution_attempt_id,
        )
    )
    assert recovered.status == "UNKNOWN_EFFECT"

    confirmed = _admit(
        _effect_service(engine, now),
        lineage["attempt"],
        evidence.effect_evidence_id,
    )
    assert confirmed.status == "CONFIRMED_EFFECT"
    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "CONFIRMED_EFFECT"
    assert guard["status"] == "CONFIRMED_EFFECT"


def test_divergent_evidence_cannot_admit_confirmed_effect(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    adapter = transport_cases._MutationAdapter(now, mode="divergent-resource")
    transport = transport_cases._service(engine, now, adapter)
    evidence = transport_cases._dispatch(transport, lineage["attempt"])
    assert evidence.status == "DIVERGENT_EFFECT_EVIDENCE"
    assert evidence.effect_evidence_id is not None

    with pytest.raises(DomainError) as insufficient:
        _admit(
            _effect_service(engine, now),
            lineage["attempt"],
            evidence.effect_evidence_id,
        )
    assert insufficient.value.code == "CALENDAR_CREATE_EFFECT_EVIDENCE_NOT_SUFFICIENT"

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None
    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"


def test_effect_admission_revalidates_semantics_instead_of_trusting_match_label(
    engine, now
):
    lineage, _, _, evidence = _matched_transport(engine, now)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_effect_evidence)
            .where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == evidence.effect_evidence_id
            )
            .values(normalized_summary="tampered-summary")
        )

    with pytest.raises(DomainError) as mismatch:
        _admit(
            _effect_service(engine, now),
            lineage["attempt"],
            evidence.effect_evidence_id,
        )
    assert mismatch.value.code == "CALENDAR_CREATE_EFFECT_SEMANTIC_MISMATCH"

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None


def test_effect_admission_revalidates_unique_action_correlation(engine, now):
    lineage, _, _, evidence = _matched_transport(engine, now)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_effect_evidence)
            .where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == evidence.effect_evidence_id
            )
            .values(correlation_key="calendar-create:tampered")
        )

    with pytest.raises(DomainError) as mismatch:
        _admit(
            _effect_service(engine, now),
            lineage["attempt"],
            evidence.effect_evidence_id,
        )
    assert mismatch.value.code == "CALENDAR_CREATE_EFFECT_CORRELATION_MISMATCH"

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None
