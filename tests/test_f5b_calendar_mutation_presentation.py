from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, update

from alsoul.adapters.contracts import AdapterOutcomeUnknown
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_mutation_completion import (
    AdoptPersonalCalendarMutationOutputCommand,
)
from alsoul.domain.personal_calendar_mutation_presentation import (
    PresentPersonalCalendarMutationOutputCommand,
    RecoverPersonalCalendarMutationPresentationCommand,
)
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    PersonalCalendarMutationPresentationServices,
    PersonalCalendarPresentationServices,
)
from alsoul.storage import schema

import test_f5b_calendar_mutation_completion as completion_cases


class _PresentationAdapter:
    sink_binding_ref = "surface.test/calendar-mutation-result"
    presentation_contract_version = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
    terminal_negative_semantics = PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS

    def __init__(
        self,
        now,
        *,
        dispatch_state="ACCEPTED",
        lookup_state="UNKNOWN",
        terminal_proof_kind="SETTLED_GENERATION",
    ):
        self.now = now
        self.dispatch_state = dispatch_state
        self.lookup_state = lookup_state
        self.terminal_proof_kind = terminal_proof_kind
        self.payload_calls = []
        self.status_calls = []

    def present_personal(self, **kwargs):
        self.payload_calls.append(dict(kwargs))
        if self.dispatch_state == "RAISE_UNKNOWN":
            raise AdapterOutcomeUnknown("simulated lost mutation-result acknowledgement")
        if self.dispatch_state == "UNKNOWN":
            return PersonalCalendarPresentationDispatchResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=kwargs["presentation_attempt_generation"],
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="UNKNOWN",
            )
        if self.dispatch_state == "NOT_ACCEPTED":
            return PersonalCalendarPresentationDispatchResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=kwargs["presentation_attempt_generation"],
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="NOT_ACCEPTED",
                terminal_proof_kind=self.terminal_proof_kind,
                settled_through_ref=f"settled-{kwargs['presentation_attempt_generation']}",
                proved_at=self.now,
            )
        return PersonalCalendarPresentationDispatchResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=kwargs["presentation_attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="ACCEPTED",
            receipt_ref=f"receipt-{kwargs['presentation_attempt_generation']}",
            accepted_at=self.now,
        )

    def lookup_personal_status(self, **kwargs):
        self.status_calls.append(dict(kwargs))
        if self.lookup_state == "ACCEPTED":
            return PersonalCalendarPresentationStatusResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=kwargs["presentation_attempt_generation"],
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="ACCEPTED",
                receipt_ref="recovered-mutation-result-acceptance",
                accepted_at=self.now,
            )
        if self.lookup_state == "NOT_ACCEPTED":
            return PersonalCalendarPresentationStatusResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=kwargs["presentation_attempt_generation"],
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="NOT_ACCEPTED",
                terminal_proof_kind=self.terminal_proof_kind,
                settled_through_ref="settled-recovered-generation",
                proved_at=self.now,
            )
        return PersonalCalendarPresentationStatusResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=kwargs["presentation_attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="UNKNOWN",
        )


def _adopted_mutation_output(engine, now):
    lineage, effect = completion_cases._confirmed(engine, now)
    model_adapter = completion_cases._CompletionAdapter(completion_cases._valid_plan)
    completion = completion_cases._service(engine, now, model_adapter)
    route = completion_cases._route(completion, model_adapter)
    projection = completion_cases._build(completion, effect.effect_id)
    generated = completion_cases._generate(completion, projection, route)
    adopted = completion.adopt_mutation_output(
        AdoptPersonalCalendarMutationOutputCommand(
            operation_id=uuid4(),
            generated_output_id=generated.generated_output_id,
        )
    )
    with engine.connect() as conn:
        action = conn.execute(
            select(schema.personal_calendar_create_action).where(
                schema.personal_calendar_create_action.c.action_id
                == lineage["action"].action_id
            )
        ).mappings().one()
        source = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == action["source_interaction_event_id"]
            )
        ).mappings().one()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == adopted.companion_output_id
            )
        ).mappings().one()
    return lineage, effect, adopted, dict(action), dict(source), dict(output)


def _set_disclosure(engine, now, action, source, *, status="ALLOW"):
    PersonalCalendarPresentationServices(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    ).set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=action["relationship_id"],
            policy_version="calendar-mutation-result-disclosure-v1",
            surface_binding_id=source["surface_binding_id"],
            channel_binding_id=source["channel_binding_id"],
            status=status,
        )
    )


def _service(engine, now, adapter):
    return PersonalCalendarMutationPresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _present(service, adopted, source, *, operation_id=None):
    return service.present_output(
        PresentPersonalCalendarMutationOutputCommand(
            operation_id=operation_id or uuid4(),
            companion_output_id=adopted.companion_output_id,
            surface_binding_id=source["surface_binding_id"],
            channel_binding_id=source["channel_binding_id"],
        )
    )


def test_accepted_mutation_result_presents_exact_adopted_payload_once(engine, now):
    _lineage, _effect, adopted, action, source, output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source)
    adapter = _PresentationAdapter(now)
    service = _service(engine, now, adapter)

    operation_id = uuid4()
    result = _present(service, adopted, source, operation_id=operation_id)
    replay = _present(service, adopted, source, operation_id=operation_id)

    assert result.state == "ACCEPTED"
    assert result.interaction_event_id is not None
    assert replay == result
    assert len(adapter.payload_calls) == 1
    call = adapter.payload_calls[0]
    assert call["content_text"] == output["content_text"]
    assert call["content_digest"] == output["content_digest"]
    assert call["companion_output_id"] == adopted.companion_output_id

    with engine.connect() as conn:
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == result.interaction_event_id
            )
        ).mappings().one()
        attempt = conn.execute(
            select(schema.personal_calendar_mutation_presentation_attempt).where(
                schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_id
                == result.presentation_attempt_id
            )
        ).mappings().one()
        evidence = conn.execute(
            select(schema.personal_calendar_mutation_presentation_status_evidence).where(
                schema.personal_calendar_mutation_presentation_status_evidence.c.presentation_attempt_id
                == result.presentation_attempt_id
            )
        ).mappings().one()

    assert event["event_kind"] == "COMPANION_PRESENTED_OUTPUT"
    assert event["companion_output_id"] == adopted.companion_output_id
    assert event["reply_to_event_id"] == source["event_id"]
    assert event["content_text"] == output["content_text"]
    assert attempt["sink_acceptance_state"] == "ACCEPTED"
    assert evidence["state"] == "ACCEPTED"
    assert evidence["receipt_ref"] == "receipt-1"


def test_unknown_mutation_presentation_requires_content_free_recovery(engine, now):
    _lineage, _effect, adopted, action, source, _output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source)
    adapter = _PresentationAdapter(now, dispatch_state="RAISE_UNKNOWN")
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as unknown:
        _present(service, adopted, source)
    assert unknown.value.code == "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN"
    assert len(adapter.payload_calls) == 1

    with pytest.raises(DomainError) as blocked:
        _present(service, adopted, source)
    assert (
        blocked.value.code
        == "CALENDAR_MUTATION_PRESENTATION_RECONCILIATION_REQUIRED"
    )
    assert len(adapter.payload_calls) == 1

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.companion_output_id
                == adopted.companion_output_id
            )
        ).first() is None

    adapter.lookup_state = "ACCEPTED"
    recovered = service.recover_presentation(
        RecoverPersonalCalendarMutationPresentationCommand(
            companion_output_id=adopted.companion_output_id,
            surface_binding_id=source["surface_binding_id"],
            channel_binding_id=source["channel_binding_id"],
        )
    )
    assert recovered.state == "ACCEPTED"
    assert recovered.interaction_event_id is not None
    assert len(adapter.payload_calls) == 1
    assert len(adapter.status_calls) == 1
    assert set(adapter.status_calls[0]) == {
        "presentation_key",
        "presentation_attempt_generation",
        "presentation_transport_fence_scope_id",
    }


def test_terminal_not_accepted_allows_new_generation_without_changing_semantic_key(
    engine, now
):
    _lineage, _effect, adopted, action, source, _output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source)
    adapter = _PresentationAdapter(now, dispatch_state="NOT_ACCEPTED")
    service = _service(engine, now, adapter)

    first = _present(service, adopted, source)
    assert first.state == "NOT_ACCEPTED"
    assert first.interaction_event_id is None
    assert first.presentation_attempt_generation == 1

    adapter.dispatch_state = "ACCEPTED"
    second = _present(service, adopted, source)
    assert second.state == "ACCEPTED"
    assert second.interaction_event_id is not None
    assert second.presentation_attempt_generation == 2
    assert second.presentation_key == first.presentation_key
    assert len(adapter.payload_calls) == 2


def test_current_disclosure_denial_blocks_mutation_result_payload(engine, now):
    _lineage, _effect, adopted, action, source, _output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source, status="DENY")
    adapter = _PresentationAdapter(now)
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as denied:
        _present(service, adopted, source)
    assert denied.value.code == "CALENDAR_MUTATION_DISCLOSURE_DENIED"
    assert adapter.payload_calls == []


def test_tampered_effect_lineage_cannot_be_presented_as_mutation_success(engine, now):
    _lineage, effect, adopted, action, source, _output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source)
    adapter = _PresentationAdapter(now)
    service = _service(engine, now, adapter)

    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_effect_evidence)
            .where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == effect.effect_evidence_id
            )
            .values(normalized_summary="tampered-after-adoption")
        )

    with pytest.raises(DomainError) as mismatch:
        _present(service, adopted, source)
    assert mismatch.value.code == "CALENDAR_MUTATION_EFFECT_LINEAGE_MISMATCH"
    assert adapter.payload_calls == []


def test_unsettled_negative_status_cannot_unlock_payload_retry(engine, now):
    _lineage, _effect, adopted, action, source, _output = _adopted_mutation_output(
        engine, now
    )
    _set_disclosure(engine, now, action, source)
    adapter = _PresentationAdapter(
        now,
        dispatch_state="NOT_ACCEPTED",
        terminal_proof_kind="POINT_IN_TIME_ABSENCE",
    )
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as invalid:
        _present(service, adopted, source)
    assert invalid.value.code == "CALENDAR_MUTATION_PRESENTATION_STATUS_INVALID"
    assert len(adapter.payload_calls) == 1

    with pytest.raises(DomainError) as blocked:
        _present(service, adopted, source)
    assert (
        blocked.value.code
        == "CALENDAR_MUTATION_PRESENTATION_RECONCILIATION_REQUIRED"
    )
    assert len(adapter.payload_calls) == 1
