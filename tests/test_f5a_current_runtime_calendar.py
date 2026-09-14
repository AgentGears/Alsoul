from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from alsoul.domain.personal_calendar_acquisition import (
    CalendarReadCapabilityContract,
    NormalizedCalendarEvent,
    PersonalCalendarReadPage,
)
from alsoul.domain.personal_calendar_cognition import (
    CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
    CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
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
    ConfiguredFoundationRuntime,
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PersonalCalendarCognitionServices,
    PersonalCalendarPresentationServices,
    PersonalCalendarResponseCoordinator,
    PresentationRuntimeConfig,
    WorldRuntimeConfig,
)
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver

import test_f5_personal_calendar_authority as authority_cases


class _ReadAdapter:
    adapter_binding_ref = "calendar.test/runtime-read"
    adapter_version = "runtime-read-v1"
    capability_contract_version = authority_cases._CAPABILITY_VERSION

    def __init__(self, now):
        self.now = now
        self.requests = []

    def read_page(self, request):
        self.requests.append(request)
        return PersonalCalendarReadPage(
            events=(
                NormalizedCalendarEvent(
                    occurrence_ref="runtime-occurrence-1",
                    title="Runtime integration review",
                    start_at=request.window_start + timedelta(hours=9),
                    end_at=request.window_start + timedelta(hours=10),
                    all_day=False,
                ),
            ),
            snapshot_ref="runtime-snapshot-1",
            snapshot_as_of=self.now,
            next_page_token=None,
            terminal=True,
        )


class _PlanAdapter:
    provider_binding_ref = "model.test/runtime-calendar"
    model_ref = "runtime-calendar-plan-v1"

    def __init__(self):
        self.requests = []

    def generate_plan(self, context):
        self.requests.append(context)
        return {
            "plan_schema_version": CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
            "source_context_projection_id": context["source_context_projection_id"],
            "source_world_result_id": context["source_world_result_id"],
            "requested_date": context["requested_date"],
            "ordered_occurrence_refs": [
                item["occurrence_ref"] for item in context["occurrences"]
            ],
            "rendering_contract_version": CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
            "framing_mode": "NEUTRAL",
        }


class _PresentationAdapter:
    sink_binding_ref = "presentation.test/runtime-calendar"
    presentation_contract_version = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
    terminal_negative_semantics = PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS

    def __init__(self, now):
        self.now = now
        self.payload_calls = []
        self.status_calls = []

    def present_personal(self, **kwargs):
        self.payload_calls.append(dict(kwargs))
        return PersonalCalendarPresentationDispatchResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=kwargs["presentation_attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="ACCEPTED",
            receipt_ref="runtime-receipt-1",
            accepted_at=self.now,
        )

    def lookup_personal_status(self, **kwargs):
        self.status_calls.append(dict(kwargs))
        return PersonalCalendarPresentationStatusResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=kwargs["presentation_attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="ACCEPTED",
            receipt_ref="runtime-receipt-1",
            accepted_at=self.now,
        )


def _configured_runtime(engine, now):
    (
        ids,
        foundation,
        _calendar,
        _observation,
        _resource,
        _credential,
        _permission,
        _prepared,
        source_event,
        _grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)
    read_adapter = _ReadAdapter(now)
    plan_adapter = _PlanAdapter()
    presentation_adapter = _PresentationAdapter(now)
    contract = CalendarReadCapabilityContract(
        contract_version=authority_cases._CAPABILITY_VERSION,
        pagination_contract_version="calendar.cursor.runtime.v1",
        snapshot_contract_version="calendar.snapshot.runtime.v1",
        normalization_schema_version="calendar.normalized.runtime.v1",
        field_minimization_contract_version="calendar.minimized.runtime.v1",
        freshness_policy_version="calendar.freshness.runtime.v1",
        max_pages=2,
        max_events=10,
        max_events_per_page=10,
    )
    cognition = PersonalCalendarCognitionServices(
        engine, adapter=plan_adapter, clock=FixedClock(now), ids=UUIDGenerator()
    )
    cognition.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="runtime-freshness-v1",
            max_age_seconds=3600,
        )
    )
    route = cognition.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=plan_adapter.provider_binding_ref,
            model_ref=plan_adapter.model_ref,
            route_contract_version="runtime-route-v1",
            data_handling_contract_version="runtime-data-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="runtime-egress-v1",
            allowed_route_binding_ids=(route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    presentation = PersonalCalendarPresentationServices(
        engine,
        adapter=presentation_adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    presentation.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="runtime-disclosure-v1",
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    coordinator = PersonalCalendarResponseCoordinator(
        foundation,
        capability_contract=contract,
        read_adapter=read_adapter,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        model_adapter=plan_adapter,
        presentation_adapter=presentation_adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    runtime = ConfiguredFoundationRuntime(
        foundation,
        config=FoundationRuntimeConfig(
            world=WorldRuntimeConfig(locator="https://world.invalid/f4"),
            model=ModelRuntimeConfig(
                endpoint="https://model.invalid/generate",
                provider_binding_ref="model.test/f4",
                model_ref="f4-model",
            ),
            presentation=PresentationRuntimeConfig(
                endpoint="https://presentation.invalid/accept"
            ),
        ),
        personal_calendar_coordinator=coordinator,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    return ids, source_event, runtime, read_adapter, plan_adapter, presentation_adapter


def test_current_runtime_executes_and_recovers_f5a_without_redispatch(engine, now):
    ids, source, runtime, read_adapter, plan_adapter, sink = _configured_runtime(engine, now)

    first = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )
    replay = runtime.interact(
        relationship_id=ids.relationship_id,
        current_input_event_id=source.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        after_process_loss=True,
    )

    assert first.interaction_purpose == "PERSONAL_CALENDAR_QUESTION"
    assert replay.interaction_purpose == "PERSONAL_CALENDAR_QUESTION"
    assert replay.response == first.response
    assert first.response.presentation_state == "ACCEPTED"
    assert first.response.presented_event_id is not None
    assert len(read_adapter.requests) == 1
    assert len(plan_adapter.requests) == 1
    assert len(sink.payload_calls) == 1
    assert sink.status_calls == []
