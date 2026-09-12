from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import (
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    PresentCompanionOutputCommand,
    ResolveOutputTargetCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    GrantCalendarReadPermissionCommand,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    SetCalendarReadPolicyCommand,
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
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.services.common import sha256_text
from alsoul.services.personal_calendar import (
    CALENDAR_READ_PERMISSION_GRANT_TEXT,
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
)
from alsoul.services.personal_calendar_acquisition import PersonalCalendarAcquisitionServices
from alsoul.services.personal_calendar_cognition import PersonalCalendarCognitionServices
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
            conversation_id="f5-calendar-generic-guard-test",
        )
    )


class _CalendarAdapter:
    adapter_binding_ref = "calendar.test/read"
    adapter_version = "calendar-test-adapter-generic-guard-v1"

    def __init__(self, page):
        self.page = page
        self.calls = 0

    def read_page(self, request):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("single-page fixture transported more than once")
        return self.page


class _PlanAdapter:
    provider_binding_ref = "model.test/calendar-plan-guard"
    model_ref = "calendar-plan-guard-v1"

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


def _bootstrap_result(engine, now):
    ids = FoundationBootstrapper(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    ).bootstrap(
        identity_namespace="f5-calendar-generic-guard-test",
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
            secret_ref="secret://calendar/generic-guard-test",
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
            objective="Exercise the F5 generic-path guards.",
            conversation_id="f5-calendar-generic-guard-test",
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
                occurrence_ref="provider-occurrence-guard-1",
                title="Guarded schedule item",
                start_at=prepared.window.window_start + timedelta(hours=9),
                end_at=prepared.window.window_start + timedelta(hours=10),
                all_day=False,
            ),
        ),
        snapshot_ref="snapshot-generic-guard-1",
        snapshot_as_of=now,
        next_page_token=None,
        terminal=True,
    )
    acquisition = PersonalCalendarAcquisitionServices(
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
    )
    acquired = acquisition.acquire(
        AcquirePersonalCalendarObservationCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            permission_id=permission.permission_id,
            credential_binding_id=credential.credential_binding_id,
        )
    )
    return {
        "ids": ids,
        "foundation": foundation,
        "permission": permission,
        "source_event": source_event,
        "world_result_id": acquired.world_result_id,
    }


def _configure_cognition(engine, now, ctx, adapter):
    cognition = PersonalCalendarCognitionServices(
        engine, adapter=adapter, clock=FixedClock(now), ids=UUIDGenerator()
    )
    cognition.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-freshness-guard-v1",
            max_age_seconds=3600,
        )
    )
    route = cognition.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=adapter.provider_binding_ref,
            model_ref=adapter.model_ref,
            route_contract_version="calendar-plan-guard-route-v1",
            data_handling_contract_version="personal-data-guard-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            policy_version="calendar-egress-guard-v1",
            allowed_route_binding_ids=(route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    projection = cognition.build_projection(
        BuildPersonalCalendarProjectionCommand(
            operation_id=uuid4(),
            world_result_id=ctx["world_result_id"],
            current_input_event_id=ctx["source_event"].event_id,
        )
    )
    return cognition, route, projection


def test_current_foundation_generic_paths_cannot_bypass_f5_calendar_boundaries(engine, now):
    ctx = _bootstrap_result(engine, now)
    foundation = FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())

    with pytest.raises(DomainError) as generic_projection:
        foundation.build_context_projection(
            BuildContextProjectionCommand(
                operation_id=uuid4(),
                companion_person_id=ctx["ids"].companion_person_id,
                relationship_id=ctx["ids"].relationship_id,
                current_input_event_id=ctx["source_event"].event_id,
                required_personal_predicates=(),
                required_world_result_ids=(ctx["world_result_id"],),
            )
        )
    _assert_code(
        generic_projection, "PERSONAL_CALENDAR_SPECIALIZED_PROJECTION_REQUIRED"
    )

    adapter = _PlanAdapter()
    cognition, route, projection = _configure_cognition(engine, now, ctx, adapter)

    with pytest.raises(DomainError) as generic_render:
        foundation.render_provider_context(projection.projection_id)
    _assert_code(generic_render, "PERSONAL_CALENDAR_SPECIALIZED_RENDERER_REQUIRED")

    with pytest.raises(DomainError) as generic_start:
        foundation.start_model_invocation(
            StartModelInvocationCommand(
                operation_id=uuid4(),
                context_projection_id=projection.projection_id,
                provider_binding_ref=adapter.provider_binding_ref,
                model_ref=adapter.model_ref,
                renderer_version="generic-renderer-v1",
                provider_request_digest="0" * 64,
            )
        )
    _assert_code(generic_start, "PERSONAL_CALENDAR_MODEL_EGRESS_REQUIRED")

    generated = cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=uuid4(),
            projection_id=projection.projection_id,
            permission_id=ctx["permission"].permission_id,
            route_binding_id=route.route_binding_id,
        )
    )

    with pytest.raises(DomainError) as generic_complete:
        foundation.complete_model_invocation(
            CompleteModelInvocationCommand(
                operation_id=uuid4(),
                model_invocation_id=generated.model_invocation_id,
                content_text="generic free-form replacement",
                content_digest=sha256_text("generic free-form replacement"),
                semantic_payload={"segments": []},
                received_at=now,
            )
        )
    _assert_code(
        generic_complete, "PERSONAL_CALENDAR_STRUCTURED_GENERATION_REQUIRED"
    )

    output_target = foundation.resolve_output_target(
        ResolveOutputTargetCommand(
            operation_id=uuid4(),
            relationship_id=ctx["ids"].relationship_id,
            target_kind="INTERACTION_EVENT",
            target_ref=ctx["source_event"].event_id,
            purpose="RESPOND_TO_INTERACTION",
        )
    )
    with pytest.raises(DomainError) as generic_adoption:
        foundation.adopt_companion_output(
            AdoptCompanionOutputCommand(
                operation_id=uuid4(),
                companion_person_id=ctx["ids"].companion_person_id,
                relationship_id=ctx["ids"].relationship_id,
                output_target_id=output_target.output_target_id,
                origin_kind="MODEL_GENERATED_RESPONSE",
                origin_ref=ctx["source_event"].event_id,
                generated_output_id=generated.generated_output_id,
            )
        )
    _assert_code(
        generic_adoption, "PERSONAL_CALENDAR_DETERMINISTIC_ADOPTION_REQUIRED"
    )

    adopted = cognition.adopt_schedule_output(
        AdoptPersonalCalendarScheduleOutputCommand(
            operation_id=uuid4(), generated_output_id=generated.generated_output_id
        )
    )
    with pytest.raises(DomainError) as generic_presentation:
        foundation.present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=uuid4(),
                companion_output_id=adopted.companion_output_id,
                surface_binding_id=ctx["ids"].surface_binding_id,
                channel_binding_id=ctx["ids"].channel_binding_id,
                presented_at=now,
            )
        )
    _assert_code(
        generic_presentation, "PERSONAL_CALENDAR_PRESENTATION_AUTHORITY_REQUIRED"
    )

    with engine.connect() as conn:
        presented = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == adopted.companion_output_id
            )
        ).scalar_one()
    assert presented == 0
