from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_transport import (
    DispatchPersonalCalendarCreateMutationCommand,
    PersonalCalendarCreateMutationResponse,
)
from alsoul.storage import schema

import test_f5b_calendar_mutation_transport as transport_cases


class _WrongCorrelationAdapter(transport_cases._MutationAdapter):
    def create_event(self, request):
        self.calls.append(request)
        return PersonalCalendarCreateMutationResponse(
            correlation_key="calendar-create:unrelated",
            external_effect_ref="provider-event:uncorrelated",
            external_system_ref=request.external_system_ref,
            external_resource_ref=request.external_resource_ref,
            summary=request.summary,
            normalized_start_at=request.normalized_start_at,
            normalized_end_at=request.normalized_end_at,
            receipt_ref="provider-receipt:uncorrelated",
            observed_at=self.now,
        )


def test_uncorrelated_provider_response_is_not_admitted_as_effect_evidence(engine, now):
    lineage = transport_cases._prepared_action(engine, now)
    adapter = _WrongCorrelationAdapter(now)
    service = transport_cases._service(engine, now, adapter)

    with pytest.raises(DomainError) as mismatch:
        service.dispatch_create_mutation(
            DispatchPersonalCalendarCreateMutationCommand(
                operation_id=uuid4(),
                execution_attempt_id=lineage["attempt"].execution_attempt_id,
            )
        )
    assert mismatch.value.code == "CALENDAR_CREATE_MUTATION_CORRELATION_MISMATCH"
    assert len(adapter.calls) == 1

    attempt_state, guard = transport_cases._current_attempt_and_guard(
        engine, lineage["attempt"]
    )
    assert attempt_state["status"] == "UNKNOWN_EFFECT"
    assert guard["status"] == "UNKNOWN_EFFECT"
    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                == lineage["attempt"].execution_attempt_id
            )
        ).first() is None
