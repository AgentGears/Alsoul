from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

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
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.foundation import FoundationServices, RAM_PREDICATE, WORLD_MEMORY_REQUIREMENT_PREDICATE
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.storage import create_sqlite_engine
from alsoul.storage import schema


def test_f4_survives_process_death_and_preserves_provenance(services, db_path, now):
    ids = services.bootstrap_foundation(identity_namespace="test-user", external_subject="u1")

    first_input = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="input-1",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="thread-a",
        )
    )
    memory = services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=16,
            source_event_id=first_input.event_id,
        )
    )

    services.engine.dispose()  # complete runtime/process boundary for the service object

    later = now + timedelta(hours=1)
    engine2 = create_sqlite_engine(db_path)
    runtime2 = FoundationServices(engine2, clock=FixedClock(later), ids=UUIDGenerator())

    resolved = runtime2.resolve_inbound_identity(
        channel_namespace="alsoul.first_party",
        channel_ref="primary-text-channel",
        identity_namespace="test-user",
        external_subject="u1",
    )
    assert resolved == (ids.companion_person_id, ids.counterpart_id, ids.relationship_id)

    current_input = runtime2.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="input-2",
            content_text="Would the current software run on my machine?",
            occurred_at=later,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="thread-b",
        )
    )

    investigation = runtime2.start_investigation(
        StartInvestigationCommand(
            operation_id=uuid4(),
            initiated_by_companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            objective="Determine the current minimum memory requirement for the software.",
            conversation_id="thread-b",
        )
    )
    observation = runtime2.start_observation(
        StartObservationCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            acquisition_kind="FETCH",
            request_descriptor={"resource": "current software requirements"},
        )
    )
    world_adapter = FakeWorldAdapter(minimum_memory_gb=24)
    acquired = world_adapter.acquire(captured_at=later)
    capture = runtime2.record_observation_success(
        RecordObservationSuccessCommand(
            operation_id=uuid4(),
            observation_id=observation.observation_id,
            source_identity=acquired.source_identity,
            requested_locator=acquired.requested_locator,
            resolved_locator=acquired.resolved_locator,
            content_text=acquired.content,
            captured_at=acquired.captured_at,
        )
    )
    world = runtime2.admit_world_result(
        AdmitWorldResultCommand(
            operation_id=uuid4(),
            investigation_id=investigation.investigation_id,
            result_kind="REQUIREMENT",
            predicate=WORLD_MEMORY_REQUIREMENT_PREDICATE,
            value=24,
            support_evidence_ids=(capture.evidence_id,),
            valid_as_of=later,
        )
    )
    projection = runtime2.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current_input.event_id,
            required_personal_predicates=(RAM_PREDICATE,),
            required_world_result_ids=(world.world_result_id,),
        )
    )
    provider_context = runtime2.render_provider_context(projection.projection_id)
    draft = FakeModelAdapter().generate(provider_context)
    provider_request_digest = sha256_text(canonical_json(provider_context))
    invocation = runtime2.start_model_invocation(
        StartModelInvocationCommand(
            operation_id=uuid4(),
            context_projection_id=projection.projection_id,
            provider_binding_ref="fake-provider",
            model_ref="fake-model-v1",
            renderer_version="f4-renderer-v1",
            provider_request_digest=provider_request_digest,
        )
    )
    text = draft.render_text()
    generated = runtime2.complete_model_invocation(
        CompleteModelInvocationCommand(
            operation_id=uuid4(),
            model_invocation_id=invocation.model_invocation_id,
            content_text=text,
            content_digest=sha256_text(text),
            semantic_payload=draft.to_payload(),
            received_at=later,
        )
    )
    target = runtime2.resolve_output_target(
        ResolveOutputTargetCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            target_kind="INTERACTION_EVENT",
            target_ref=current_input.event_id,
            purpose="FINAL_RESPONSE",
        )
    )
    adopted = runtime2.adopt_companion_output(
        AdoptCompanionOutputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            output_target_id=target.output_target_id,
            origin_kind="RESPONSE_TO_EVENT",
            origin_ref=current_input.event_id,
            generated_output_id=generated.generated_output_id,
        )
    )
    presented = runtime2.present_companion_output(
        PresentCompanionOutputCommand(
            operation_id=uuid4(),
            companion_output_id=adopted.companion_output_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            presented_at=later,
        )
    )

    runtime2.engine.dispose()
    engine3 = create_sqlite_engine(db_path)
    recovery = RecoveryCoordinator(engine3).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current_input.event_id,
    )
    assert recovery.stage == "PRESENTED"
    assert recovery.presented_event_id == presented.interaction_event_id

    with engine3.connect() as conn:
        c1 = conn.execute(select(schema.claim).where(schema.claim.c.claim_id == memory.claim_id)).mappings().one()
        ce = conn.execute(select(schema.claim_evidence).where(schema.claim_evidence.c.claim_id == memory.claim_id)).mappings().one()
        e1 = conn.execute(select(schema.evidence_item).where(schema.evidence_item.c.evidence_id == ce["evidence_id"])).mappings().one()
        assert e1["source_id"] == first_input.event_id
        assert c1["value_json"] == 16

        w1 = conn.execute(select(schema.world_result).where(schema.world_result.c.world_result_id == world.world_result_id)).mappings().one()
        we = conn.execute(select(schema.world_result_evidence).where(schema.world_result_evidence.c.world_result_id == world.world_result_id)).mappings().one()
        e2 = conn.execute(select(schema.evidence_item).where(schema.evidence_item.c.evidence_id == we["evidence_id"])).mappings().one()
        s1 = conn.execute(select(schema.world_source_capture).where(schema.world_source_capture.c.source_capture_id == e2["source_id"])).mappings().one()
        o1 = conn.execute(select(schema.observation).where(schema.observation.c.observation_id == s1["observation_id"])).mappings().one()
        assert o1["investigation_id"] == w1["investigation_id"] == investigation.investigation_id

        cp_claim = conn.execute(select(schema.context_projection_personal_item).where(schema.context_projection_personal_item.c.projection_id == projection.projection_id)).mappings().one()
        cp_world = conn.execute(select(schema.context_projection_world_item).where(schema.context_projection_world_item.c.projection_id == projection.projection_id)).mappings().one()
        assert cp_claim["claim_id"] == memory.claim_id
        assert cp_claim["epistemic_basis"] == "COUNTERPART_STATED_MEMORY"
        assert cp_world["world_result_id"] == world.world_result_id
        assert cp_world["epistemic_mode"] == "CURRENT_CHECKED"

        mi = conn.execute(select(schema.model_invocation).where(schema.model_invocation.c.model_invocation_id == invocation.model_invocation_id)).mappings().one()
        go = conn.execute(select(schema.generated_output).where(schema.generated_output.c.generated_output_id == generated.generated_output_id)).mappings().one()
        co = conn.execute(select(schema.companion_output).where(schema.companion_output.c.companion_output_id == adopted.companion_output_id)).mappings().one()
        ie = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.event_id == presented.interaction_event_id)).mappings().one()
        assert mi["context_projection_id"] == projection.projection_id
        assert go["model_invocation_id"] == invocation.model_invocation_id
        assert co["source_generated_output_id"] == generated.generated_output_id
        assert ie["companion_output_id"] == adopted.companion_output_id
        assert ie["content_text"] == co["content_text"]
        assert "You told me" in ie["content_text"]
        assert "I checked" in ie["content_text"]
        assert "My take" in ie["content_text"]
