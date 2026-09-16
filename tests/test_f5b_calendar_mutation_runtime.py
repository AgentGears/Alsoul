from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from alsoul.domain.personal_calendar import BindCalendarCredentialCommand
from alsoul.domain.personal_calendar_cognition import (
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
)
from alsoul.domain.personal_calendar_presentation import (
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.interaction_routing_current_v2 import classify_current_interaction_text
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_mutation_completion_v2 import (
    PersonalCalendarMutationCompletionServices,
)
from alsoul.services.personal_calendar_mutation_runtime import (
    PersonalCalendarMutationCoordinator,
)
from alsoul.services.personal_calendar_presentation_v4 import (
    PersonalCalendarPresentationServices,
)
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_approval_authority as approval_cases
import test_f5b_calendar_execution_fence as execution_cases
import test_f5b_calendar_mutation_completion as completion_cases
import test_f5b_calendar_mutation_presentation as presentation_cases
import test_f5b_calendar_mutation_transport as transport_cases


def _runtime(
    engine,
    now,
    *,
    mutation_mode="matched",
    presentation_dispatch_state="ACCEPTED",
    presentation_lookup_state="UNKNOWN",
):
    (
        ids,
        foundation,
        action_service,
        resource,
        _read_permission,
        _write_permission,
        _write_grant_event,
    ) = action_cases._bootstrap_write_authority(engine, now)
    credential = action_service.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-calendar-writer-runtime",
            secret_ref="secret-ref:calendar-write-runtime",
            provider_scopes=(action_cases._CREATE_PROVIDER_SCOPE,),
        )
    )

    completion_adapter = completion_cases._CompletionAdapter(completion_cases._valid_plan)
    completion_admin = PersonalCalendarMutationCompletionServices(
        engine,
        adapter=completion_adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    route = completion_admin.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref=completion_adapter.provider_binding_ref,
            model_ref=completion_adapter.model_ref,
            route_contract_version="calendar-mutation-runtime-route-v1",
            data_handling_contract_version="opaque-completion-ref-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    completion_admin.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="calendar-mutation-runtime-egress-v1",
            allowed_route_binding_ids=(route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )

    presentation_adapter = presentation_cases._PresentationAdapter(
        now,
        dispatch_state=presentation_dispatch_state,
        lookup_state=presentation_lookup_state,
    )
    PersonalCalendarPresentationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).set_disclosure_policy(
        SetPersonalCalendarDisclosurePolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="calendar-mutation-runtime-disclosure-v1",
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            status="ALLOW",
        )
    )

    approval_adapter = approval_cases._ApprovalAdapter()
    mutation_adapter = transport_cases._MutationAdapter(now, mode=mutation_mode)
    coordinator = PersonalCalendarMutationCoordinator(
        foundation,
        capability_contract_version=action_cases._CREATE_CAPABILITY_VERSION,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        execution_binding=execution_cases._binding(),
        approval_adapter=approval_adapter,
        mutation_adapter=mutation_adapter,
        completion_model_adapter=completion_adapter,
        presentation_adapter=presentation_adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    return {
        "ids": ids,
        "foundation": foundation,
        "resource": resource,
        "credential": credential,
        "coordinator": coordinator,
        "approval_adapter": approval_adapter,
        "mutation_adapter": mutation_adapter,
        "completion_adapter": completion_adapter,
        "presentation_adapter": presentation_adapter,
    }


def _start(ctx, now):
    request = action_cases._append_create_request(ctx["foundation"], ctx["ids"], now)
    result = ctx["coordinator"].start_create(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=request.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    return request, result


def _approve(ctx, now, challenge):
    approval_event = authority_cases._append_counterpart_event(
        ctx["foundation"], ctx["ids"], now, challenge
    )
    result = ctx["coordinator"].approve_and_execute(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    return approval_event, result


def test_exact_mutation_grammars_route_without_widening_other_interactions():
    assert classify_current_interaction_text(action_cases._CREATE_REQUEST) == (
        "PERSONAL_CALENDAR_CREATE_REQUEST"
    )
    assert classify_current_interaction_text(
        "APPROVE CALENDAR ACTION " + ("a" * 64)
    ) == "PERSONAL_CALENDAR_CREATE_APPROVAL"
    assert classify_current_interaction_text(
        "APPROVE CALENDAR ACTION not-a-digest"
    ) != "PERSONAL_CALENDAR_CREATE_APPROVAL"
    assert classify_current_interaction_text(
        "Add 'Dentist' to my calendar tomorrow."
    ) != "PERSONAL_CALENDAR_CREATE_REQUEST"


def test_create_request_stops_at_exact_approval_presentation(engine, now):
    ctx = _runtime(engine, now)
    _request, started = _start(ctx, now)

    assert started.status == "AWAITING_APPROVAL"
    assert started.approval_presentation_id is not None
    assert started.approval_challenge is not None
    prefix = "APPROVE CALENDAR ACTION "
    assert started.approval_challenge.startswith(prefix)
    digest = started.approval_challenge.removeprefix(prefix)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(character in "0123456789abcdef" for character in digest)
    assert len(ctx["approval_adapter"].calls) == 1
    assert ctx["mutation_adapter"].calls == []
    assert ctx["completion_adapter"].requests == []
    assert ctx["presentation_adapter"].payload_calls == []

    with engine.connect() as conn:
        assert conn.execute(select(schema.personal_calendar_create_execution_attempt)).first() is None
        assert conn.execute(select(schema.personal_calendar_create_effect)).first() is None


def test_exact_later_approval_executes_once_and_presents_only_confirmed_effect(engine, now):
    ctx = _runtime(engine, now)
    request, started = _start(ctx, now)
    approval_event, completed = _approve(ctx, now, started.approval_challenge)

    assert completed.status == "PRESENTED"
    assert completed.action_id == started.action_id
    assert completed.approval_id is not None
    assert completed.execution_attempt_id is not None
    assert completed.effect_id is not None
    assert completed.companion_output_id is not None
    assert completed.presentation_state == "ACCEPTED"
    assert completed.presented_event_id is not None
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["completion_adapter"].requests) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1

    provider_context = ctx["completion_adapter"].requests[0]
    assert set(provider_context) == {
        "mutation_completion_ref",
        "result_kind",
        "rendering_contract_version",
    }
    assert "Dentist" not in repr(provider_context)

    replay = ctx["coordinator"].approve_and_execute(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    assert replay == completed
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["completion_adapter"].requests) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1

    with engine.connect() as conn:
        action = conn.execute(
            select(schema.personal_calendar_create_action).where(
                schema.personal_calendar_create_action.c.action_id == completed.action_id
            )
        ).mappings().one()
        effect = conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.effect_id == completed.effect_id
            )
        ).mappings().one()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == completed.companion_output_id
            )
        ).mappings().one()
        presented = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == completed.presented_event_id
            )
        ).mappings().one()
    assert action["source_interaction_event_id"] == request.event_id
    assert effect["status"] == "CONFIRMED_EFFECT"
    assert output["content_text"].startswith('I created "Dentist"')
    assert presented["event_kind"] == "COMPANION_PRESENTED_OUTPUT"
    assert presented["reply_to_event_id"] == request.event_id


def test_unknown_mutation_outcome_never_generates_or_presents_success_and_never_resends(engine, now):
    ctx = _runtime(engine, now, mutation_mode="unknown")
    _request, started = _start(ctx, now)
    approval_event, uncertain = _approve(ctx, now, started.approval_challenge)

    assert uncertain.status == "UNKNOWN_EFFECT"
    assert uncertain.effect_id is None
    assert uncertain.companion_output_id is None
    assert len(ctx["mutation_adapter"].calls) == 1
    assert ctx["completion_adapter"].requests == []
    assert ctx["presentation_adapter"].payload_calls == []

    replay = ctx["coordinator"].approve_and_execute(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    assert replay == uncertain
    assert len(ctx["mutation_adapter"].calls) == 1

    with engine.connect() as conn:
        assert conn.execute(select(schema.personal_calendar_create_effect)).first() is None
        attempt = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_state)
            .join(
                schema.personal_calendar_create_execution_attempt_head,
                schema.personal_calendar_create_execution_attempt_head.c.execution_attempt_id
                == schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id,
            )
            .where(
                schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id
                == uncertain.execution_attempt_id,
                schema.personal_calendar_create_execution_attempt_state.c.revision
                == schema.personal_calendar_create_execution_attempt_head.c.current_revision,
            )
        ).mappings().one()
    assert attempt["status"] == "UNKNOWN_EFFECT"


def test_confirmed_effect_with_unknown_presentation_is_not_reported_as_presented_and_is_not_resent(engine, now):
    ctx = _runtime(engine, now, presentation_dispatch_state="UNKNOWN")
    _request, started = _start(ctx, now)
    approval_event, uncertain = _approve(ctx, now, started.approval_challenge)

    assert uncertain.status == "PRESENTATION_UNKNOWN"
    assert uncertain.effect_id is not None
    assert uncertain.companion_output_id is not None
    assert uncertain.presentation_state == "UNKNOWN"
    assert uncertain.presented_event_id is None
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1
    assert len(ctx["presentation_adapter"].status_calls) == 1

    replay = ctx["coordinator"].approve_and_execute(
        relationship_id=ctx["ids"].relationship_id,
        current_input_event_id=approval_event.event_id,
        surface_binding_id=ctx["ids"].surface_binding_id,
        channel_binding_id=ctx["ids"].channel_binding_id,
    )
    assert replay.status == "PRESENTATION_UNKNOWN"
    assert replay.presented_event_id is None
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1
    assert len(ctx["presentation_adapter"].status_calls) == 2


def test_terminal_nonacceptance_preserves_confirmed_effect_without_claiming_presentation(engine, now):
    ctx = _runtime(engine, now, presentation_dispatch_state="NOT_ACCEPTED")
    _request, started = _start(ctx, now)
    _approval_event, not_presented = _approve(ctx, now, started.approval_challenge)

    assert not_presented.status == "NOT_PRESENTED"
    assert not_presented.effect_id is not None
    assert not_presented.companion_output_id is not None
    assert not_presented.presentation_state == "NOT_ACCEPTED"
    assert not_presented.presented_event_id is None
    assert len(ctx["mutation_adapter"].calls) == 1
    assert len(ctx["completion_adapter"].requests) == 1
    assert len(ctx["presentation_adapter"].payload_calls) == 1

    with engine.connect() as conn:
        effect = conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.effect_id
                == not_presented.effect_id
            )
        ).mappings().one()
        assert effect["status"] == "CONFIRMED_EFFECT"
        assert conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.companion_output_id
                == not_presented.companion_output_id
            )
        ).first() is None
