from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters.contracts import AdapterOutcomeUnknown
from alsoul.domain.commands import (
    AppendCounterpartInputCommand,
    StartInvestigationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    GrantCalendarReadPermissionCommand,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    SetCalendarReadPolicyCommand,
    SetPermissionStatusCommand,
)
from alsoul.domain.personal_calendar_acquisition import (
    AcquirePersonalCalendarObservationCommand,
    CalendarReadCapabilityContract,
    NormalizedCalendarEvent,
    PersonalCalendarReadPage,
)
from alsoul.domain.personal_calendar_cognition import (
    CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
    CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
    AdoptPersonalCalendarScheduleOutputCommand,
    BuildPersonalCalendarProjectionCommand,
    GeneratePersonalCalendarAnswerPlanCommand,
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
)
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
    PresentPersonalCalendarOutputCommand,
    RecoverPersonalCalendarPresentationCommand,
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    FoundationBootstrapper,
    FoundationServices,
    PersonalCalendarCognitionServices,
    PersonalCalendarPresentationServices,
)
from alsoul.services.personal_calendar import (
    CALENDAR_READ_PERMISSION_GRANT_TEXT,
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
)
from alsoul.services.personal_calendar_acquisition import PersonalCalendarAcquisitionServices
from alsoul.storage import schema

_RULES_VERSION = "test-tzdb-v1"
_CAPABILITY_VERSION = "calendar.events.read.v1"
_GRANT_POLICY_VERSION = "first-party-grant-v1"
_PROVIDER_SCOPE = "calendar.read"


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _append_counterpart(foundation, ids, now, text: str):
    return foundation.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text=text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="f5-calendar-presentation-test",
        )
    )


class _CalendarAdapter:
    adapter_binding_ref = "calendar.test/read"
    adapter_version = "calendar-test-adapter-presentation-v1"

    def __init__(self, page):
        self.page = page
        self.calls = 0

    def read_page(self, request):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("single-page presentation fixture transported more than once")
        return self.page


class _PlanAdapter:
    provider_binding_ref = "model.test/calendar-presentation-plan"
    model_ref = "calendar-presentation-plan-v1"

    def generate_plan(self, context):
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
    presentation_contract_version = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION

    def __init__(self, now, *, dispatch_state="ACCEPTED", lookup_state="UNKNOWN"):
        self.now = now
        self.dispatch_state = dispatch_state
        self.lookup_state = lookup_state
        self.payload_calls = []
        self.status_calls = []
        self.lookup_generation_delta = 0

    def present_personal(self, **kwargs):
        self.payload_calls.append(dict(kwargs))
        if self.dispatch_state == "UNKNOWN":
            raise AdapterOutcomeUnknown("simulated lost presentation acknowledgement")
        if self.dispatch_state == "NOT_ACCEPTED":
            return PersonalCalendarPresentationDispatchResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=kwargs["presentation_attempt_generation"],
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="NOT_ACCEPTED",
                terminal_proof_kind="SETTLED_GENERATION",
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
        generation = kwargs["presentation_attempt_generation"] + self.lookup_generation_delta
        if self.lookup_state == "ACCEPTED":
            return PersonalCalendarPresentationStatusResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=generation,
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="ACCEPTED",
                receipt_ref="recovered-acceptance",
                accepted_at=self.now,
            )
        if self.lookup_state == "NOT_ACCEPTED":
            return PersonalCalendarPresentationStatusResult(
                presentation_key=kwargs["presentation_key"],
                presentation_attempt_generation=generation,
                presentation_transport_fence_scope_id=kwargs[
                    "presentation_transport_fence_scope_id"
                ],
                state="NOT_ACCEPTED",
                terminal_proof_kind="SETTLED_GENERATION",
                settled_through_ref="settled-recovered-generation",
                proved_at=self.now,
            )
        return PersonalCalendarPresentationStatusResult(
            presentation_key=kwargs["presentation_key"],
            presentation_attempt_generation=generation,
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            state="UNKNOWN",
        )


def _adopted_calendar_output(engine, now):
    ids = FoundationBootstrapper(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    ).bootstrap(
        identity_namespace="f5-calendar-presentation-test",
        external_subject=str(uuid4()),
    )
    foundation = FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())
    calendar = PersonalCalendarReadServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    external_system_ref = f"calendar.test.{uuid4()}"
    resource = calendar.register_calendar_resource(
        RegisterPersonalCalendarResourceCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            external_system_ref=external_system_ref,
            external_resource_ref="primary",
            calendar_timezone="UTC",
            timezone_rules_version=_RULES_VERSION,
        )
    )
    credential = calendar.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref=external_system_ref,
            external_principal_ref="counterpart-account",
            secret_ref="secret://calendar/presentation-test",
            provider_scopes=(_PROVIDER_SCOPE,),
        )
    )
    grant_event = _append_counterpart(
        foundation, ids, now, CALENDAR_READ_PERMISSION_GRANT_TEXT
    )
    permission = calendar.grant_read_permission(
        GrantCalendarReadPermissionCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            personal_resource_binding_id=resource.personal_resource_binding_id,
            capability_contract_version=_CAPABILITY_VERSION,
            grant_policy_version=_GRANT_POLICY_VERSION,
            source_interaction_event_id=grant_event.event_id,
        )
    )
    calendar.set_read_policy(
        SetCalendarReadPolicyCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            capability_contract_version=_CAPABILITY_VERSION,
            ai_policy_version="personal-calendar-read-v1",
            resource_scope_version="calendar-scope-v1",
            required_provider_scope=_PROVIDER_SCOPE,
            permission_grant_policy_version=_GRANT_POLICY_VERSION,
            allowed_resource_binding_ids=(resource.personal_resource_binding_id,),
        )
    )
    source_event = _append_counterpart(
        foundation, ids, now, "What's on my calendar on 2026-09-12?"
    )
    investigation = foundation.start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            objective="Produce one bounded personal-calendar answer.",
            conversation_id="f5-calendar-presentation-test",
        )
    )
    observation = foundation.start_observation(
        StartObservationCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            acquisition_kind="PERSONAL_CALENDAR_READ",
            request_descriptor={"purpose": "calendar.events.read"},
        )
    )
    prepared = calendar.prepare_observation(
        PreparePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            source_interaction_event_id=source_event.event_id,
        )
    )
    page = PersonalCalendarReadPage(
        events=(
            NormalizedCalendarEvent(
                occurrence_ref="provider-occurrence-presentation-1",
                title="Presentation boundary meeting",
                start_at=prepared.window.window_start + timedelta(hours=9),
                end_at=prepared.window.window_start + timedelta(hours=10),
                all_day=False,
            ),
        ),
        snapshot_ref="snapshot-presentation-1",
        snapshot_as_of=now,
        next_page_token=None,
        terminal=True,
    )
    acquired = PersonalCalendarAcquisitionServices(
        engine,
        capability_contract=CalendarReadCapabilityContract(
            contract_version=_CAPABILITY_VERSION,
            pagination_contract_version="calendar.cursor.v1",
            snapshot_contract_version="calendar.snapshot.v1",
            normalization_schema_version="calendar.normalized-event.v1",
            field_minimization_contract_version="calendar.minimized-event.v1",
            freshness_policy_version="calendar-freshness-v1",
            max_pages=2,
            max_events=10,
            max_events_per_page=10,
        ),
        adapter=_CalendarAdapter(page),
        time_resolver=ZoneInfoCalendarTimeResolver(rules_version=_RULES_VERSION),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).acquire(
        AcquirePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )

    plan_adapter = _PlanAdapter()
    cognition = PersonalCalendarCognitionServices(
        engine, adapter=plan_adapter, clock=FixedClock(now), ids=UUIDGenerator()
    )
    cognition.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="calendar-freshness-presentation-v1",
            max_age_seconds=3600,
        )
    )
    route = cognition.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=plan_adapter.provider_binding_ref,
            model_ref=plan_adapter.model_ref,
            route_contract_version="calendar-plan-presentation-route-v1",
            data_handling_contract_version="personal-data-presentation-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="calendar-egress-presentation-v1",
            allowed_route_binding_ids=(route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    projection = cognition.build_projection(
        BuildPersonalCalendarProjectionCommand(
            operation_id=uuid4(),
            world_result_id=acquired.world_result_id,
            current_input_event_id=source_event.event_id,
        )
    )
    generated = cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=projection.projection_id,
            permission_id=permission.permission_id,
            route_binding_id=route.route_binding_id,
        )
    )
    adopted = cognition.adopt_schedule_output(
        AdoptPersonalCalendarScheduleOutputCommand(
            operation_id=uuid4(), generated_output_id=generated.generated_output_id
        )
    )
    return {
        "ids": ids,
        "calendar": calendar,
        "permission": permission,
        "resource": resource,
        "source_event": source_event,
        "adopted": adopted,
    }


def _presentation_service(engine, now, ctx, adapter):
    service = PersonalCalendarPresentationServices(
        engine, adapter=adapter, clock=FixedClock(now), ids=UUIDGenerator()
    )
    service.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-disclosure-v1",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    return service


def _present_command(ctx, operation_id=None):
    return PresentPersonalCalendarOutputCommand(
        operation_id=operation_id or uuid4(),
        companion_output_id=ctx["adopted"].companion_output_id,
        permission_id=ctx["permission"].permission_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )


def _recover_command(ctx):
    return RecoverPersonalCalendarPresentationCommand(
        companion_output_id=ctx["adopted"].companion_output_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )


def test_accepted_first_presentation_commits_exactly_one_timeline_event(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now)
    service = _presentation_service(engine, now, ctx, adapter)
    operation_id = uuid4()

    first = service.present_output(_present_command(ctx, operation_id))
    replay = service.present_output(_present_command(ctx, operation_id))

    assert first.state == "ACCEPTED"
    assert first.presentation_attempt_generation == 1
    assert first.interaction_event_id is not None
    assert replay.presentation_attempt_id == first.presentation_attempt_id
    assert replay.interaction_event_id == first.interaction_event_id
    assert len(adapter.payload_calls) == 1
    assert not adapter.status_calls

    with engine.connect() as conn:
        event_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one()
        attempt = conn.execute(
            select(schema.personal_calendar_presentation_attempt).where(
                schema.personal_calendar_presentation_attempt.c.presentation_attempt_id
                == first.presentation_attempt_id
            )
        ).mappings().one()
        evidence_count = conn.execute(
            select(func.count())
            .select_from(schema.personal_calendar_presentation_status_evidence)
            .where(
                schema.personal_calendar_presentation_status_evidence.c.presentation_attempt_id
                == first.presentation_attempt_id
            )
        ).scalar_one()
    assert event_count == 1
    assert attempt["sink_acceptance_state"] == "ACCEPTED"
    assert evidence_count == 1


def test_unknown_dispatch_recovers_accepted_content_free_after_permission_revocation(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now, dispatch_state="UNKNOWN", lookup_state="ACCEPTED")
    service = _presentation_service(engine, now, ctx, adapter)

    with pytest.raises(DomainError) as uncertain:
        service.present_output(_present_command(ctx))
    _assert_code(uncertain, "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN")
    assert len(adapter.payload_calls) == 1

    ctx["calendar"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(), permission_id=ctx["permission"].permission_id
        )
    )
    recovered = service.recover_presentation(_recover_command(ctx))

    assert recovered.state == "ACCEPTED"
    assert recovered.interaction_event_id is not None
    assert len(adapter.payload_calls) == 1
    assert len(adapter.status_calls) == 1
    assert set(adapter.status_calls[0]) == {
        "presentation_key",
        "presentation_attempt_generation",
        "presentation_transport_fence_scope_id",
    }


def test_unknown_lookup_never_resends_payload_or_fabricates_presentation(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now, dispatch_state="UNKNOWN", lookup_state="UNKNOWN")
    service = _presentation_service(engine, now, ctx, adapter)

    with pytest.raises(DomainError):
        service.present_output(_present_command(ctx))
    recovered = service.recover_presentation(_recover_command(ctx))

    assert recovered.state == "UNKNOWN"
    assert recovered.interaction_event_id is None
    assert len(adapter.payload_calls) == 1
    assert len(adapter.status_calls) == 1
    with pytest.raises(DomainError) as retry:
        service.present_output(_present_command(ctx))
    _assert_code(retry, "CALENDAR_PRESENTATION_RECONCILIATION_REQUIRED")
    assert len(adapter.payload_calls) == 1


def test_terminal_not_accepted_allows_new_generation_with_same_semantic_key(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now, dispatch_state="NOT_ACCEPTED")
    service = _presentation_service(engine, now, ctx, adapter)

    first = service.present_output(_present_command(ctx))
    assert first.state == "NOT_ACCEPTED"
    assert first.interaction_event_id is None

    adapter.dispatch_state = "ACCEPTED"
    second = service.present_output(_present_command(ctx))
    assert second.state == "ACCEPTED"
    assert second.presentation_attempt_generation == 2
    assert second.presentation_key == first.presentation_key
    assert second.interaction_event_id is not None
    assert len(adapter.payload_calls) == 2
    assert adapter.payload_calls[0]["presentation_transport_fence_scope_id"] != adapter.payload_calls[1]["presentation_transport_fence_scope_id"]


def test_terminal_not_accepted_does_not_bypass_later_permission_revocation(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now, dispatch_state="NOT_ACCEPTED")
    service = _presentation_service(engine, now, ctx, adapter)
    first = service.present_output(_present_command(ctx))
    assert first.state == "NOT_ACCEPTED"

    ctx["calendar"].set_permission_status(
        SetPermissionStatusCommand(
            operation_id=uuid4(), permission_id=ctx["permission"].permission_id
        )
    )
    adapter.dispatch_state = "ACCEPTED"
    with pytest.raises(DomainError) as denied:
        service.present_output(_present_command(ctx))
    _assert_code(denied, "CALENDAR_DISCLOSURE_DENIED")
    assert len(adapter.payload_calls) == 1


def test_stale_output_and_disclosure_denial_block_payload_before_attempt(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now)
    service = _presentation_service(engine, now, ctx, adapter)
    service.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-disclosure-deny-v2",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
            status="DENY",
        )
    )
    with pytest.raises(DomainError) as disclosure_denied:
        service.present_output(_present_command(ctx))
    _assert_code(disclosure_denied, "CALENDAR_DISCLOSURE_DENIED")
    assert not adapter.payload_calls

    service.set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-disclosure-allow-v3",
            surface_binding_id=ctx["ids"].surface_binding_id,
            channel_binding_id=ctx["ids"].channel_binding_id,
        )
    )
    stale = PersonalCalendarPresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now + timedelta(hours=2)),
        ids=UUIDGenerator(),
    )
    with pytest.raises(DomainError) as stale_output:
        stale.present_output(_present_command(ctx))
    _assert_code(stale_output, "CALENDAR_RESULT_STALE")
    assert not adapter.payload_calls

    with engine.connect() as conn:
        attempts = conn.execute(
            select(func.count()).select_from(schema.personal_calendar_presentation_attempt)
        ).scalar_one()
    assert attempts == 0


def test_mismatched_status_generation_cannot_settle_unknown_attempt(engine, now):
    ctx = _adopted_calendar_output(engine, now)
    adapter = _PresentationAdapter(now, dispatch_state="UNKNOWN", lookup_state="ACCEPTED")
    service = _presentation_service(engine, now, ctx, adapter)
    with pytest.raises(DomainError):
        service.present_output(_present_command(ctx))
    adapter.lookup_generation_delta = 1

    with pytest.raises(DomainError) as invalid:
        service.recover_presentation(_recover_command(ctx))
    _assert_code(invalid, "CALENDAR_PRESENTATION_STATUS_INVALID")
    with engine.connect() as conn:
        state = conn.execute(
            select(schema.personal_calendar_presentation_attempt.c.sink_acceptance_state)
        ).scalar_one()
        presented = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id
            )
        ).scalar_one()
    assert state == "UNKNOWN"
    assert presented == 0
