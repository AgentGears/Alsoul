from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.services import F4CounterpartMemoryAdmission, extract_f4_memory_proposal
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.storage import schema


def _input(services, ids, now, text: str, key: str):
    return services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=key,
            content_text=text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="memory-admission",
        )
    )


def test_bounded_extractor_requires_explicit_primary_machine_ram_statement():
    source = uuid4()
    proposal = extract_f4_memory_proposal(
        source_event_id=source,
        content_text="My machine has 16 GB RAM.",
    )
    assert proposal is not None
    assert proposal.source_event_id == source
    assert proposal.predicate == RAM_PREDICATE
    assert proposal.value == 16
    assert proposal.explicit_correction is False

    correction = extract_f4_memory_proposal(
        source_event_id=source,
        content_text="Actually, my machine has 32 GB RAM.",
    )
    assert correction is not None
    assert correction.value == 32
    assert correction.explicit_correction is True

    assert (
        extract_f4_memory_proposal(
            source_event_id=source,
            content_text="My USB drive has 16 GB RAM.",
        )
        is None
    )
    assert (
        extract_f4_memory_proposal(
            source_event_id=source,
            content_text="Does my machine have 16 GB RAM?",
        )
        is None
    )
    assert (
        extract_f4_memory_proposal(
            source_event_id=source,
            content_text="Their machine has 16 GB RAM.",
        )
        is None
    )


def test_memory_admission_creates_claim_and_replays_same_source_idempotently(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="memory-admission",
        external_subject="u1",
    )
    event = _input(
        services,
        ids,
        now,
        "My machine has 16 GB RAM.",
        "memory-event-1",
    )
    admission = F4CounterpartMemoryAdmission(services)

    first = admission.consider_event(event.event_id)
    replay = admission.consider_event(event.event_id)

    assert first.disposition == "ADMITTED"
    assert first.claim_id is not None
    assert replay.disposition == "ADMITTED"
    assert replay.claim_id == first.claim_id
    assert replay.corrected_claim_id is None

    current = services.get_current_memory_claim(
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        predicate=RAM_PREDICATE,
    )
    assert current is not None
    assert current["claim_id"] == first.claim_id
    assert current["value_json"] == 16

    with services.engine.connect() as conn:
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        evidence_count = conn.execute(
            select(func.count()).select_from(schema.evidence_item)
        ).scalar_one()
    assert claim_count == 1
    assert evidence_count == 1


def test_explicit_correction_supersedes_current_claim(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="memory-correction",
        external_subject="u1",
    )
    admission = F4CounterpartMemoryAdmission(services)

    first_event = _input(
        services,
        ids,
        now,
        "My machine has 16 GB RAM.",
        "memory-correction-1",
    )
    first = admission.consider_event(first_event.event_id)

    correction_event = _input(
        services,
        ids,
        now,
        "Actually, my machine has 32 GB RAM.",
        "memory-correction-2",
    )
    corrected = admission.consider_event(correction_event.event_id)

    assert corrected.disposition == "CORRECTED"
    assert corrected.claim_id is not None
    assert corrected.claim_id != first.claim_id
    assert corrected.corrected_claim_id == first.claim_id

    current = services.get_current_memory_claim(
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        predicate=RAM_PREDICATE,
    )
    assert current is not None
    assert current["claim_id"] == corrected.claim_id
    assert current["value_json"] == 32

    with services.engine.connect() as conn:
        edge = conn.execute(
            select(schema.claim_supersession).where(
                schema.claim_supersession.c.newer_claim_id == corrected.claim_id,
                schema.claim_supersession.c.older_claim_id == first.claim_id,
                schema.claim_supersession.c.relation == "CORRECTS",
            )
        ).mappings().one()
    assert edge["older_claim_id"] == first.claim_id


def test_different_value_without_explicit_correction_fails_closed(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="memory-conflict",
        external_subject="u1",
    )
    admission = F4CounterpartMemoryAdmission(services)
    first = _input(
        services,
        ids,
        now,
        "My machine has 16 GB RAM.",
        "memory-conflict-1",
    )
    admission.consider_event(first.event_id)

    conflicting = _input(
        services,
        ids,
        now,
        "My machine has 32 GB RAM.",
        "memory-conflict-2",
    )
    with pytest.raises(DomainError) as exc:
        admission.consider_event(conflicting.event_id)
    assert exc.value.code == "MEMORY_CHANGE_REQUIRES_EXPLICIT_CORRECTION"

    current = services.get_current_memory_claim(
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        predicate=RAM_PREDICATE,
    )
    assert current is not None
    assert current["value_json"] == 16


def test_repeated_same_value_is_not_a_second_memory_admission(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="memory-repeat",
        external_subject="u1",
    )
    admission = F4CounterpartMemoryAdmission(services)
    first = _input(
        services,
        ids,
        now,
        "My machine has 16 GB RAM.",
        "memory-repeat-1",
    )
    admitted = admission.consider_event(first.event_id)

    repeated = _input(
        services,
        ids,
        now,
        "My computer has 16 GB of memory.",
        "memory-repeat-2",
    )
    unchanged = admission.consider_event(repeated.event_id)

    assert unchanged.disposition == "UNCHANGED"
    assert unchanged.claim_id == admitted.claim_id
    with services.engine.connect() as conn:
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
    assert claim_count == 1
