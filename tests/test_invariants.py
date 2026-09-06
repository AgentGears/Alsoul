from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import FakeWorldAdapter
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
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services.common import canonical_json, sha256_text
from alsoul.services.foundation import RAM_PREDICATE, WORLD_MEMORY_REQUIREMENT_PREDICATE
from alsoul.storage import schema


def _bootstrap_memory(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="test", external_subject="u1")
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="memory-input",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    claim = services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=16,
            source_event_id=event.event_id,
        )
    )
    return ids, event, claim


def test_memory_claim_requires_semantic_support(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="test", external_subject="u1")
    event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="bad-support",
            content_text="My machine is fairly old.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    with pytest.raises(DomainError) as exc:
        services.admit_person_memory_claim(
            AdmitPersonMemoryClaimCommand(
                operation_id=uuid4(),
                holder_companion_person_id=ids.companion_person_id,
                subject_counterpart_id=ids.counterpart_id,
                relationship_id=ids.relationship_id,
                predicate=RAM_PREDICATE,
                value=16,
                source_event_id=event.event_id,
            )
        )
    assert exc.value.code == "CLAIM_SUPPORT_SEMANTICALLY_INVALID"


def test_input_idempotency_returns_same_event(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(identity_namespace="test", external_subject="u1")
    command = AppendCounterpartInputCommand(
        operation_id=uuid4(),
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        ingress_idempotency_key="same-input",
        content_text="hello",
        occurred_at=now,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
    )
    first = services.append_counterpart_input(command)
    replay = services.append_counterpart_input(command)
    assert replay.event_id == first.event_id
    assert replay.timeline_seq == first.timeline_seq
    assert replay.idempotent_replay
    with services.engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(schema.interaction_event)).scalar_one()
    assert count == 1


def test_world_result_cannot_borrow_evidence_from_other_investigation(
    services, bootstrapper, now
):
    ids, _, _ = _bootstrap_memory(services, bootstrapper, now)
    q1 = services.start_investigation(
        StartInvestigationCommand(uuid4(), ids.companion_person_id, ids.relationship_id, "q1")
    )
    o1 = services.start_observation(
        StartObservationCommand(uuid4(), q1.investigation_id, "FETCH", {"q": 1})
    )
    acquired = FakeWorldAdapter().acquire(captured_at=now)
    cap = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(),
            o1.observation_id,
            acquired.source_identity,
            acquired.requested_locator,
            acquired.resolved_locator,
            acquired.content,
            acquired.captured_at,
        )
    )
    q2 = services.start_investigation(
        StartInvestigationCommand(uuid4(), ids.companion_person_id, ids.relationship_id, "q2")
    )
    with pytest.raises(DomainError) as exc:
        services.admit_world_result(
            AdmitWorldResultCommand(
                uuid4(),
                q2.investigation_id,
                "REQUIREMENT",
                WORLD_MEMORY_REQUIREMENT_PREDICATE,
                24,
                (cap.evidence_id,),
            )
        )
    assert exc.value.code == "WORLD_RESULT_WRONG_INVESTIGATION"


def test_correction_is_append_only_and_current_claim_is_derived(
    services, bootstrapper, now
):
    ids, _, claim1 = _bootstrap_memory(services, bootstrapper, now)
    correction_event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="correction",
            content_text="Actually, my machine has 32 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    claim2 = services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=32,
            source_event_id=correction_event.event_id,
            correction_of_claim_id=claim1.claim_id,
        )
    )
    current = services.get_current_memory_claim(
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        predicate=RAM_PREDICATE,
    )
    assert current is not None
    assert current["claim_id"] == claim2.claim_id
    assert current["value_json"] == 32
    with services.engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        relation = conn.execute(
            select(schema.claim_supersession).where(
                schema.claim_supersession.c.older_claim_id == claim1.claim_id
            )
        ).mappings().one()
    assert count == 2
    assert relation["newer_claim_id"] == claim2.claim_id
    assert relation["relation"] == "CORRECTS"


def test_generated_and_adopted_outputs_are_not_presented_history(
    services, bootstrapper, now
):
    ids, _, _ = _bootstrap_memory(services, bootstrapper, now)
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
    q = services.start_investigation(
        StartInvestigationCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id, "current requirement"
        )
    )
    o = services.start_observation(
        StartObservationCommand(uuid4(), q.investigation_id, "FETCH", {"q": "requirement"})
    )
    acquired = FakeWorldAdapter().acquire(captured_at=now)
    cap = services.record_observation_success(
        RecordObservationSuccessCommand(
            uuid4(),
            o.observation_id,
            acquired.source_identity,
            acquired.requested_locator,
            acquired.resolved_locator,
            acquired.content,
            acquired.captured_at,
        )
    )
    w = services.admit_world_result(
        AdmitWorldResultCommand(
            uuid4(),
            q.investigation_id,
            "REQUIREMENT",
            WORLD_MEMORY_REQUIREMENT_PREDICATE,
            24,
            (cap.evidence_id,),
            valid_as_of=now,
        )
    )
    cp = services.build_context_projection(
        BuildContextProjectionCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            current.event_id,
            (RAM_PREDICATE,),
            (w.world_result_id,),
        )
    )
    ctx = services.render_provider_context(cp.projection_id)
    personal = ctx["personal_context"][0]
    world = ctx["world_context"][0]
    draft = FoundationResponseDraft(
        (
            FoundationResponseSegment(
                "REMEMBERED_COUNTERPART_STATEMENT",
                "You told me your machine has 16 GB RAM.",
                __import__("uuid").UUID(personal["claim_id"]),
            ),
            FoundationResponseSegment(
                "CURRENT_CHECKED_WORLD",
                "I checked the current requirement; it is 24 GB RAM.",
                __import__("uuid").UUID(world["world_result_id"]),
            ),
            FoundationResponseSegment(
                "COMPANION_INTERPRETATION",
                "My take is that it does not meet the requirement.",
                None,
            ),
        )
    )
    inv = services.start_model_invocation(
        StartModelInvocationCommand(
            uuid4(), cp.projection_id, "fake", "fake", "r1", sha256_text(canonical_json(ctx))
        )
    )
    text = draft.render_text()
    g = services.complete_model_invocation(
        CompleteModelInvocationCommand(
            uuid4(), inv.model_invocation_id, text, sha256_text(text), draft.to_payload(), now
        )
    )
    with services.engine.connect() as conn:
        before = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT")
        ).scalar_one()
    assert before == 0
    ot = services.resolve_output_target(
        ResolveOutputTargetCommand(
            uuid4(), ids.relationship_id, "INTERACTION_EVENT", current.event_id, "FINAL_RESPONSE"
        )
    )
    co = services.adopt_companion_output(
        AdoptCompanionOutputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            ot.output_target_id,
            "RESPONSE_TO_EVENT",
            current.event_id,
            g.generated_output_id,
        )
    )
    with services.engine.connect() as conn:
        after_adopt = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT")
        ).scalar_one()
    assert after_adopt == 0
    p = services.present_companion_output(
        PresentCompanionOutputCommand(
            uuid4(),
            co.companion_output_id,
            ids.surface_binding_id,
            ids.channel_binding_id,
            now,
        )
    )
    replay = services.present_companion_output(
        PresentCompanionOutputCommand(
            uuid4(),
            co.companion_output_id,
            ids.surface_binding_id,
            ids.channel_binding_id,
            now,
        )
    )
    assert replay.interaction_event_id == p.interaction_event_id
    with services.engine.connect() as conn:
        final_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT")
        ).scalar_one()
    assert final_count == 1
