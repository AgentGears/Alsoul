from __future__ import annotations

from uuid import uuid4

from alsoul.adapters import FakeModelAdapter, FakeWorldAdapter
from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    PresentCompanionOutputCommand,
    RecordObservationSuccessCommand,
    ResolveOutputTargetCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.foundation import RAM_PREDICATE, WORLD_MEMORY_REQUIREMENT_PREDICATE
from alsoul.services.recovery import RecoveryCoordinator


def test_recovery_coordinator_derives_each_committed_response_stage(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(identity_namespace="recovery", external_subject="u1")
    memory_input = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "memory",
            "My machine has 16 GB RAM.",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            RAM_PREDICATE,
            16,
            memory_input.event_id,
        )
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "question",
            "Would it run?",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )

    recovery = RecoveryCoordinator(services.engine)
    assert recovery.assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    ).stage == "INPUT_ADMITTED"

    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id, "current requirement"
        )
    )
    observation = services.start_observation(
        StartObservationCommand(
            uuid4(), investigation.investigation_id, "FETCH", {"q": "requirement"}
        )
    )
    acquired = FakeWorldAdapter().acquire(captured_at=now)
    capture = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(),
            observation.observation_id,
            acquired.source_identity,
            acquired.requested_locator,
            acquired.resolved_locator,
            acquired.content,
            acquired.captured_at,
        )
    )
    world = services.admit_world_result(
        AdmitWorldResultCommand(
            uuid4(),
            investigation.investigation_id,
            "REQUIREMENT",
            WORLD_MEMORY_REQUIREMENT_PREDICATE,
            24,
            (capture.evidence_id,),
            valid_as_of=now,
        )
    )
    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            current.event_id,
            (RAM_PREDICATE,),
            (world.world_result_id,),
        )
    )

    assessment = recovery.assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "PROJECTION_READY"
    assert assessment.reusable_projection_id == projection.projection_id

    context = services.render_provider_context(projection.projection_id)
    draft = FakeModelAdapter().generate(context)
    invocation = services.start_model_invocation(
        StartModelInvocationCommand(
            uuid4(),
            projection.projection_id,
            "fake",
            "fake",
            "f4-renderer-v1",
            sha256_text(canonical_json(context)),
        )
    )
    text = draft.render_text()
    generated = services.complete_model_invocation(
        CompleteModelInvocationCommand(
            uuid4(),
            invocation.model_invocation_id,
            text,
            sha256_text(text),
            draft.to_payload(),
            now,
        )
    )

    assessment = recovery.assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "GENERATED"
    assert assessment.reusable_generated_output_id == generated.generated_output_id

    target = services.resolve_output_target(
        ResolveOutputTargetCommand(
            uuid4(),
            ids.relationship_id,
            "INTERACTION_EVENT",
            current.event_id,
            "FINAL_RESPONSE",
        )
    )
    adopted = services.adopt_companion_output(
        AdoptCompanionOutputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            target.output_target_id,
            "RESPONSE_TO_EVENT",
            current.event_id,
            generated.generated_output_id,
        )
    )

    assessment = recovery.assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "ADOPTED"
    assert assessment.output_target_id == target.output_target_id
    assert assessment.adopted_output_id == adopted.companion_output_id

    presented = services.present_companion_output(
        PresentCompanionOutputCommand(
            uuid4(),
            adopted.companion_output_id,
            ids.surface_binding_id,
            ids.channel_binding_id,
            now,
        )
    )

    assessment = recovery.assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "PRESENTED"
    assert assessment.presented_event_id == presented.interaction_event_id
