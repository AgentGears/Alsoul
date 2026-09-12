from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_presentation as presentation_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import SetPermissionStatusCommand
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PersonalCalendarPresentationDispatchResult,
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import PersonalCalendarPresentationServices
from alsoul.storage import schema


def _code(exc: pytest.ExceptionInfo[DomainError]) -> str:
    return exc.value.code


class _FenceInspectingPresentationAdapter(presentation_cases._PresentationAdapter):
    sink_binding_ref = "presentation.test/exit-audit-fence"

    def __init__(self, engine, now):
        super().__init__(now, dispatch_state="ACCEPTED", lookup_state="UNKNOWN")
        self.engine = engine
        self.fence_seen = False

    def present_personal(self, **kwargs):
        with self.engine.connect() as conn:
            attempt = conn.execute(
                select(schema.personal_calendar_presentation_attempt).where(
                    schema.personal_calendar_presentation_attempt.c.presentation_transport_fence_scope_id
                    == kwargs["presentation_transport_fence_scope_id"]
                )
            ).mappings().one()
            disclosure = conn.execute(
                select(schema.personal_calendar_disclosure_decision).where(
                    schema.personal_calendar_disclosure_decision.c.disclosure_decision_id
                    == attempt["disclosure_decision_id"]
                )
            ).mappings().one()
            freshness = conn.execute(
                select(schema.personal_calendar_presentation_freshness_decision).where(
                    schema.personal_calendar_presentation_freshness_decision.c.freshness_decision_id
                    == attempt["freshness_decision_id"]
                )
            ).mappings().one()
        assert attempt["sink_acceptance_state"] == "UNKNOWN"
        assert attempt["presentation_key"] == kwargs["presentation_key"]
        assert int(attempt["presentation_attempt_generation"]) == kwargs[
            "presentation_attempt_generation"
        ]
        assert disclosure["freshness_decision_id"] == freshness["freshness_decision_id"]
        self.fence_seen = True
        return super().present_personal(**kwargs)


def test_exit_presentation_is_fenced_before_payload_and_history_survives_later_denial(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    adapter = _FenceInspectingPresentationAdapter(engine, now)
    service = presentation_cases._presentation_service(engine, now, ctx, adapter)
    accepted = service.present_output(presentation_cases._present_command(ctx))
    assert adapter.fence_seen
    assert accepted.state == "ACCEPTED"
    assert accepted.interaction_event_id is not None
    assert len(adapter.payload_calls) == 1

    ctx["calendar"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(),
            permission_id=ctx["permission"].permission_id,
        )
    )
    service.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-disclosure-denied-after-accept-v2",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
            status="DENY",
        )
    )
    recovered = service.recover_presentation(presentation_cases._recover_command(ctx))
    assert recovered.interaction_event_id == accepted.interaction_event_id
    assert recovered.state == "ACCEPTED"
    assert len(adapter.payload_calls) == 1

    with engine.connect() as conn:
        event_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one()
        provenance = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope
                == "BindPersonalCalendarPresentedEventProvenance",
                schema.operation_receipt.c.operation_id == accepted.interaction_event_id,
            )
        ).mappings().one()
    assert event_count == 1
    assert provenance["result_json"]["presentation_attempt_id"] == str(
        accepted.presentation_attempt_id
    )
    assert provenance["result_json"]["presentation_attempt_generation"] == 1


class _NoStatusLookupSink:
    sink_binding_ref = "presentation.test/no-status-lookup"
    presentation_contract_version = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION

    def present_personal(self, **_kwargs):
        raise AssertionError("ineligible sink must not receive payload")


def test_exit_sink_without_content_free_lookup_is_ineligible_before_payload(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    sink = _NoStatusLookupSink()
    service = PersonalCalendarPresentationServices(
        engine, adapter=sink, clock=FixedClock(now), ids=UUIDGenerator()
    )
    service.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-disclosure-exit-audit-v1",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    with pytest.raises(DomainError) as ineligible:
        service.present_output(presentation_cases._present_command(ctx))
    assert _code(ineligible) == "CALENDAR_PRESENTATION_ADAPTER_INELIGIBLE"
    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(schema.personal_calendar_presentation_attempt)
        ).scalar_one() == 0


class _WeakNegativeSink(presentation_cases._PresentationAdapter):
    sink_binding_ref = "presentation.test/weak-negative"

    def __init__(self, now):
        super().__init__(now, dispatch_state="ACCEPTED", lookup_state="UNKNOWN")

    def present_personal(self, **kwargs):
        self.payload_calls.append(dict(kwargs))
        return PersonalCalendarPresentationDispatchResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=kwargs["presentation_attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="NOT_ACCEPTED",
        )


def test_exit_point_in_time_negative_without_terminal_proof_remains_uncertain(engine, now):
    ctx = presentation_cases._adopted_calendar_output(engine, now)
    sink = _WeakNegativeSink(now)
    service = presentation_cases._presentation_service(engine, now, ctx, sink)

    with pytest.raises(DomainError) as weak:
        service.present_output(presentation_cases._present_command(ctx))
    assert _code(weak) == "CALENDAR_PRESENTATION_TERMINALITY_INVALID"
    with engine.connect() as conn:
        attempt = conn.execute(
            select(schema.personal_calendar_presentation_attempt)
        ).mappings().one()
        evidence_count = conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_presentation_status_evidence
            )
        ).scalar_one()
    assert attempt["sink_acceptance_state"] == "UNKNOWN"
    assert evidence_count == 0
    assert len(sink.payload_calls) == 1
