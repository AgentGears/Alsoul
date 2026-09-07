from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import func, select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.domain.errors import DomainError
from alsoul.services import F4CounterpartMemoryAdmission, extract_f4_memory_candidate
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.storage import schema


def _input(services, ids, now, *, text: str, key: str):
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
            conversation_id="memory-concurrency",
        )
    )


def test_instead_is_an_accepted_explicit_correction_form():
    candidate = extract_f4_memory_candidate("Instead, my machine has 32 GB RAM.")
    assert candidate is not None
    assert candidate.predicate == RAM_PREDICATE
    assert candidate.value == 32
    assert candidate.explicit_correction is True


def test_concurrent_different_initial_proposals_cannot_create_two_current_claims(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="memory-concurrency",
        external_subject="u1",
    )
    first = _input(
        services,
        ids,
        now,
        text="My machine has 16 GB RAM.",
        key="concurrent-memory-1",
    )
    second = _input(
        services,
        ids,
        now,
        text="My machine has 32 GB RAM.",
        key="concurrent-memory-2",
    )
    admission = F4CounterpartMemoryAdmission(services)

    def consider(event_id):
        try:
            return ("OK", admission.consider_event(event_id))
        except DomainError as exc:
            return (exc.code, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(consider, (first.event_id, second.event_id))
        )

    codes = sorted(code for code, _ in outcomes)
    assert codes == ["MEMORY_CHANGE_REQUIRES_EXPLICIT_CORRECTION", "OK"]

    current = services.get_current_memory_claim(
        companion_person_id=ids.companion_person_id,
        counterpart_id=ids.counterpart_id,
        relationship_id=ids.relationship_id,
        predicate=RAM_PREDICATE,
    )
    assert current is not None
    assert current["value_json"] in {16, 32}

    with services.engine.connect() as conn:
        claim_count = conn.execute(select(func.count()).select_from(schema.claim)).scalar_one()
        current_edges = conn.execute(
            select(func.count()).select_from(schema.claim_supersession)
        ).scalar_one()
    assert claim_count == 1
    assert current_edges == 0
