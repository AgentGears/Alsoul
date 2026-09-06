from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from alsoul.adapters import FakeWorldAdapter
from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    ResolveOutputTargetCommand,
    RecordObservationSuccessCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.foundation import (
    RAM_PREDICATE,
    WORLD_MEMORY_REQUIREMENT_PREDICATE,
)


def _bootstrap_memory(services, now):
    ids = services.bootstrap_foundation(identity_namespace="review", external_subject="u1")
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(), ids.companion_person_id, ids.counterpart_id,
            ids.relationship_id, "memory", "My machine has 16 GB RAM.", now,
            ids.surface_binding_id, ids.channel_binding_id,
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            uuid4(), ids.companion_person_id, ids.counterpart_id,
            ids.relationship_id, RAM_PREDICATE, 16, event.event_id,
        )
    )
    return ids


def _prepare_current_world(
    services, now, ids, *, captured_at=None, valid_as_of=None, minimum_memory_gb=24
):
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(), ids.companion_person_id, ids.counterpart_id,
            ids.relationship_id, f"question-{uuid4()}", "Would it run?", now,
            ids.surface_binding_id, ids.channel_binding_id,
        )
    )
    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id,
            "current requirement",
        )
    )
    observation = services.start_observation(
        StartObservationCommand(
            uuid4(), investigation.investigation_id, "FETCH", {"q": "requirement"}
        )
    )
    acquired = FakeWorldAdapter(minimum_memory_gb=minimum_memory_gb).acquire(
        captured_at=captured_at or now
    )
    capture = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(), observation.observation_id, acquired.source_identity,
            acquired.requested_locator, acquired.resolved_locator,
            acquired.content, acquired.captured_at,
        )
    )
    world = services.admit_world_result(
        AdmitWorldResultCommand(
            uuid4(), investigation.investigation_id, "REQUIREMENT",
            WORLD_MEMORY_REQUIREMENT_PREDICATE, minimum_memory_gb,
            (capture.evidence_id,), valid_as_of=valid_as_of,
        )
    )
    return current, world


def test_current_checked_rejects_capture_older_than_current_input(services, now):
    ids = _bootstrap_memory(services, now)
    current, world = _prepare_current_world(
        services, now, ids,
        captured_at=now - timedelta(minutes=5),
        valid_as_of=now,
    )
    with pytest.raises(DomainError) as exc:
        services.build_context_projection(
            BuildContextProjectionCommand(
                uuid4(), ids.companion_person_id, ids.relationship_id,
                current.event_id, (RAM_PREDICATE,), (world.world_result_id,),
            )
        )
    assert exc.value.code == "PROJECTION_FRESHNESS_REQUIREMENT_FAILED"


def test_current_checked_rejects_explicitly_stale_valid_as_of(services, now):
    ids = _bootstrap_memory(services, now)
    current, world = _prepare_current_world(
        services, now, ids,
        captured_at=now,
        valid_as_of=now - timedelta(minutes=5),
    )
    with pytest.raises(DomainError) as exc:
        services.build_context_projection(
            BuildContextProjectionCommand(
                uuid4(), ids.companion_person_id, ids.relationship_id,
                current.event_id, (RAM_PREDICATE,), (world.world_result_id,),
            )
        )
    assert exc.value.code == "PROJECTION_FRESHNESS_REQUIREMENT_FAILED"


def test_investigation_relationship_must_belong_to_initiator(services):
    ids1 = services.bootstrap_foundation(
        identity_namespace="review", external_subject="u1",
        surface_ref="surface-1", channel_ref="channel-1",
    )
    ids2 = services.bootstrap_foundation(
        identity_namespace="review", external_subject="u2",
        surface_ref="surface-2", channel_ref="channel-2",
    )
    with pytest.raises(DomainError) as exc:
        services.start_investigation(
            StartInvestigationCommand(
                uuid4(), ids2.companion_person_id, ids1.relationship_id,
                "cross-person investigation",
            )
        )
    assert exc.value.code == "INVESTIGATION_RELATIONSHIP_MISMATCH"


def test_world_result_rejects_cross_investigation_contradiction(services, now):
    ids = _bootstrap_memory(services, now)

    q1 = services.start_investigation(
        StartInvestigationCommand(uuid4(), ids.companion_person_id, ids.relationship_id, "q1")
    )
    o1 = services.start_observation(
        StartObservationCommand(uuid4(), q1.investigation_id, "FETCH", {"q": 1})
    )
    source1 = FakeWorldAdapter(minimum_memory_gb=24).acquire(captured_at=now)
    cap1 = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(), o1.observation_id, source1.source_identity,
            source1.requested_locator, source1.resolved_locator,
            source1.content, source1.captured_at,
        )
    )

    q2 = services.start_investigation(
        StartInvestigationCommand(uuid4(), ids.companion_person_id, ids.relationship_id, "q2")
    )
    o2 = services.start_observation(
        StartObservationCommand(uuid4(), q2.investigation_id, "FETCH", {"q": 2})
    )
    source2 = FakeWorldAdapter(minimum_memory_gb=32).acquire(captured_at=now)
    cap2 = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(), o2.observation_id, source2.source_identity,
            source2.requested_locator, source2.resolved_locator,
            source2.content, source2.captured_at,
        )
    )

    with pytest.raises(DomainError) as exc:
        services.admit_world_result(
            AdmitWorldResultCommand(
                uuid4(), q1.investigation_id, "REQUIREMENT",
                WORLD_MEMORY_REQUIREMENT_PREDICATE, 24,
                (cap1.evidence_id,), contradiction_evidence_ids=(cap2.evidence_id,),
            )
        )
    assert exc.value.code == "WORLD_RESULT_WRONG_INVESTIGATION"


def test_adoption_rejects_text_not_matching_semantic_payload(services, now):
    ids = _bootstrap_memory(services, now)
    current, world = _prepare_current_world(
        services, now, ids, captured_at=now, valid_as_of=now
    )
    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id,
            current.event_id, (RAM_PREDICATE,), (world.world_result_id,),
        )
    )
    context = services.render_provider_context(projection.projection_id)
    claim_ref = UUID(context["personal_context"][0]["claim_id"])
    world_ref = UUID(context["world_context"][0]["world_result_id"])
    draft = FoundationResponseDraft((
        FoundationResponseSegment(
            "REMEMBERED_COUNTERPART_STATEMENT",
            "You told me your machine has 16 GB RAM.", claim_ref,
        ),
        FoundationResponseSegment(
            "CURRENT_CHECKED_WORLD",
            "I checked the current requirement; it is 24 GB RAM.", world_ref,
        ),
        FoundationResponseSegment(
            "COMPANION_INTERPRETATION",
            "My take is that it does not meet the requirement.", None,
        ),
    ))
    invocation = services.start_model_invocation(
        StartModelInvocationCommand(
            uuid4(), projection.projection_id, "fake", "fake", "r1",
            sha256_text(canonical_json(context)),
        )
    )
    malicious_text = "Everything is definitely fine."
    generated = services.complete_model_invocation(
        CompleteModelInvocationCommand(
            uuid4(), invocation.model_invocation_id, malicious_text,
            sha256_text(malicious_text), draft.to_payload(), now,
        )
    )
    target = services.resolve_output_target(
        ResolveOutputTargetCommand(
            uuid4(), ids.relationship_id, "INTERACTION_EVENT",
            current.event_id, "FINAL_RESPONSE",
        )
    )
    with pytest.raises(DomainError) as exc:
        services.adopt_companion_output(
            AdoptCompanionOutputCommand(
                uuid4(), ids.companion_person_id, ids.relationship_id,
                target.output_target_id, "RESPONSE_TO_EVENT", current.event_id,
                generated.generated_output_id,
            )
        )
    assert exc.value.code == "OUTPUT_CONTENT_POLICY_REJECTED"
