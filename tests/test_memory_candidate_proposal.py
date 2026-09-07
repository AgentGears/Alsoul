from __future__ import annotations

from uuid import uuid4

from alsoul.services import (
    F4MemoryCandidate,
    F4MemoryProposal,
    extract_f4_memory_candidate,
    propose_f4_memory,
)
from alsoul.services.foundation import RAM_PREDICATE


def test_extracted_candidate_is_distinct_from_source_bound_memory_proposal():
    source_event_id = uuid4()
    candidate = extract_f4_memory_candidate("My machine has 16 GB RAM.")

    assert isinstance(candidate, F4MemoryCandidate)
    assert candidate.predicate == RAM_PREDICATE
    assert candidate.value == 16
    assert not hasattr(candidate, "source_event_id")

    proposal = propose_f4_memory(
        source_event_id=source_event_id,
        candidate=candidate,
    )
    assert isinstance(proposal, F4MemoryProposal)
    assert proposal.source_event_id == source_event_id
    assert proposal.predicate == candidate.predicate
    assert proposal.value == candidate.value
    assert proposal is not candidate
