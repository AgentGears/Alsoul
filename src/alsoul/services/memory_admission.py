from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.errors import fail
from alsoul.services.foundation import FoundationServices, RAM_PREDICATE
from alsoul.storage import schema

MemoryAdmissionDisposition = Literal[
    "NO_CANDIDATE",
    "ADMITTED",
    "CORRECTED",
    "UNCHANGED",
]

_CORRECTION_SIGNAL = re.compile(
    r"\b(?:actually|correction|to correct that|i was wrong|instead)\b",
    flags=re.IGNORECASE,
)

_PRIMARY_MACHINE_RAM_PATTERNS = (
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong|instead)\s*[,;:]?\s*)?"
        r"my\s+(?:machine|computer|laptop|pc|desktop)\s+"
        r"(?:(?:currently|now)\s+)?(?:has|contains|comes\s+with)\s+"
        r"(?P<value>\d{1,5})\s*gb(?:\s+of)?\s+(?:ram|memory)\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong|instead)\s*[,;:]?\s*)?"
        r"my\s+(?:machine|computer|laptop|pc|desktop)(?:'s)?\s+"
        r"(?:ram|memory)\s+(?:is|=)\s+(?P<value>\d{1,5})\s*gb\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong|instead)\s*[,;:]?\s*)?"
        r"my\s+(?:ram|memory)\s+(?:is|=)\s+(?P<value>\d{1,5})\s*gb\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class F4MemoryCandidate:
    """Non-authoritative semantic candidate extracted from statement text."""

    predicate: str
    value: int
    explicit_correction: bool


@dataclass(frozen=True, slots=True)
class F4MemoryProposal:
    """Non-authoritative proposal binding one candidate to canonical evidence."""

    source_event_id: UUID
    predicate: str
    value: int
    explicit_correction: bool


@dataclass(frozen=True, slots=True)
class F4MemoryAdmissionResult:
    source_event_id: UUID
    disposition: MemoryAdmissionDisposition
    predicate: str | None = None
    value: int | None = None
    claim_id: UUID | None = None
    corrected_claim_id: UUID | None = None


class F4CounterpartMemoryAdmission:
    """Admit the one bounded F4 personal-memory predicate from trusted history.

    Source history, extraction, proposal, current-claim validation, and admission
    remain distinct stages. The write path serializes claim admission per F4
    relationship before re-reading current claim state, so concurrent proposals
    cannot create two unsuperseded current claims for the singleton predicate.
    """

    def __init__(self, services: FoundationServices) -> None:
        self.services = services

    def consider_event(self, source_event_id: UUID) -> F4MemoryAdmissionResult:
        # The first read allows exact already-admitted replay to return without taking
        # the relationship write fence. Every path that may write rechecks after the
        # fence, so this optimization is not authoritative for admission.
        with self.services.engine.connect() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            existing = self._claim_from_source_event(
                conn,
                source_event_id=source_event_id,
                companion_person_id=relationship["companion_person_id"],
                counterpart_id=relationship["counterpart_id"],
                relationship_id=relationship["relationship_id"],
            )
            if existing is not None:
                return self._existing_result(conn, source_event_id, existing)

        candidate = extract_f4_memory_candidate(event["content_text"])
        if candidate is None:
            return F4MemoryAdmissionResult(
                source_event_id=source_event_id,
                disposition="NO_CANDIDATE",
            )
        proposal = propose_f4_memory(
            source_event_id=source_event_id,
            candidate=candidate,
        )

        # In F4 the memory predicate is relationship-scoped and singleton. A no-op
        # update of the durable relationship Timeline head is used only as a database
        # write fence: SQLite serializes writers and row-locking databases serialize
        # this relationship row. The Timeline sequence value itself is not changed.
        # Current claim state is then resolved *inside the same transaction* before
        # any Claim/Evidence rows are inserted.
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            fenced = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == relationship["relationship_id"]
                )
                .values(
                    last_timeline_seq=schema.relationship_timeline_head.c.last_timeline_seq
                )
            )
            if fenced.rowcount != 1:
                fail(
                    "MEMORY_ADMISSION_FENCE_UNAVAILABLE",
                    "relationship memory-admission fence is unavailable",
                )

            # Another worker may have admitted this source while this worker waited
            # for the fence. Recover that exact result rather than creating state.
            existing = self._claim_from_source_event(
                conn,
                source_event_id=source_event_id,
                companion_person_id=relationship["companion_person_id"],
                counterpart_id=relationship["counterpart_id"],
                relationship_id=relationship["relationship_id"],
            )
            if existing is not None:
                return self._existing_result(conn, source_event_id, existing)

            current_resolved = self.services._resolve_current_claim(
                conn,
                relationship["companion_person_id"],
                relationship["counterpart_id"],
                relationship["relationship_id"],
                proposal.predicate,
            )
            current = current_resolved[0] if current_resolved is not None else None

            if current is not None and current["value_json"] == proposal.value:
                return F4MemoryAdmissionResult(
                    source_event_id=source_event_id,
                    disposition="UNCHANGED",
                    predicate=proposal.predicate,
                    value=proposal.value,
                    claim_id=current["claim_id"],
                )

            correction_of_claim_id: UUID | None = None
            disposition: MemoryAdmissionDisposition = "ADMITTED"
            if current is not None:
                if not proposal.explicit_correction:
                    fail(
                        "MEMORY_CHANGE_REQUIRES_EXPLICIT_CORRECTION",
                        "a different current memory value requires an explicit counterpart correction",
                    )
                correction_of_claim_id = current["claim_id"]
                disposition = "CORRECTED"

            # Revalidate the exact canonical source while holding the fence. The
            # bounded candidate is necessary but never sufficient by itself.
            if (
                event["relationship_id"] != relationship["relationship_id"]
                or event["actor_ref"] != relationship["counterpart_id"]
                or event["event_kind"] != "COUNTERPART_INPUT"
                or event["actor_kind"] != "COUNTERPART"
            ):
                fail(
                    "MEMORY_SOURCE_EVENT_INVALID",
                    "memory source is not a counterpart statement in the target relationship",
                )
            candidate_under_fence = extract_f4_memory_candidate(event["content_text"])
            if (
                candidate_under_fence is None
                or candidate_under_fence.predicate != proposal.predicate
                or candidate_under_fence.value != proposal.value
                or candidate_under_fence.explicit_correction
                != proposal.explicit_correction
            ):
                fail(
                    "MEMORY_PROPOSAL_SOURCE_MISMATCH",
                    "canonical source no longer matches the bounded memory proposal",
                )

            evidence_id = self.services.ids.new()
            claim_id = self.services.ids.new()
            now = self.services.clock.now()
            conn.execute(
                insert(schema.evidence_item).values(
                    evidence_id=evidence_id,
                    origin_kind="COUNTERPART_STATEMENT",
                    source_type="INTERACTION_EVENT",
                    source_id=source_event_id,
                    source_actor_ref=relationship["counterpart_id"],
                    recorded_at=now,
                )
            )
            conn.execute(
                insert(schema.claim).values(
                    claim_id=claim_id,
                    holder_companion_person_id=relationship["companion_person_id"],
                    subject_counterpart_id=relationship["counterpart_id"],
                    memory_scope_kind="RELATIONSHIP",
                    memory_scope_ref=relationship["relationship_id"],
                    claim_domain="PERSON",
                    claim_kind="FACTUAL",
                    predicate=proposal.predicate,
                    value_json=proposal.value,
                    valid_from=event["occurred_at"],
                    admitted_at=now,
                )
            )
            conn.execute(
                insert(schema.claim_evidence).values(
                    claim_id=claim_id,
                    evidence_id=evidence_id,
                    relation="SUPPORTS",
                )
            )
            if correction_of_claim_id is not None:
                conn.execute(
                    insert(schema.claim_supersession).values(
                        newer_claim_id=claim_id,
                        older_claim_id=correction_of_claim_id,
                        relation="CORRECTS",
                        created_at=now,
                    )
                )

            return F4MemoryAdmissionResult(
                source_event_id=source_event_id,
                disposition=disposition,
                predicate=proposal.predicate,
                value=proposal.value,
                claim_id=claim_id,
                corrected_claim_id=correction_of_claim_id,
            )

    def _load_source(self, conn, source_event_id: UUID):
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == source_event_id
            )
        ).mappings().one_or_none()
        if event is None:
            fail("MEMORY_SOURCE_EVENT_NOT_FOUND", "memory source event does not exist")
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == event["relationship_id"]
            )
        ).mappings().one_or_none()
        if relationship is None:
            fail("RELATIONSHIP_NOT_FOUND", "memory source relationship does not exist")
        if (
            event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "MEMORY_SOURCE_EVENT_INVALID",
                "memory admission accepts only counterpart input in its bound relationship",
            )
        return event, relationship

    def _existing_result(self, conn, source_event_id: UUID, existing):
        correction = conn.execute(
            select(schema.claim_supersession).where(
                schema.claim_supersession.c.newer_claim_id == existing["claim_id"],
                schema.claim_supersession.c.relation == "CORRECTS",
            )
        ).mappings().one_or_none()
        return F4MemoryAdmissionResult(
            source_event_id=source_event_id,
            disposition="CORRECTED" if correction is not None else "ADMITTED",
            predicate=existing["predicate"],
            value=int(existing["value_json"]),
            claim_id=existing["claim_id"],
            corrected_claim_id=(
                correction["older_claim_id"] if correction is not None else None
            ),
        )

    def _claim_from_source_event(
        self,
        conn,
        *,
        source_event_id: UUID,
        companion_person_id: UUID,
        counterpart_id: UUID,
        relationship_id: UUID,
    ):
        rows = conn.execute(
            select(schema.claim)
            .select_from(
                schema.claim.join(
                    schema.claim_evidence,
                    schema.claim.c.claim_id == schema.claim_evidence.c.claim_id,
                ).join(
                    schema.evidence_item,
                    schema.claim_evidence.c.evidence_id
                    == schema.evidence_item.c.evidence_id,
                )
            )
            .where(
                schema.claim.c.holder_companion_person_id == companion_person_id,
                schema.claim.c.subject_counterpart_id == counterpart_id,
                schema.claim.c.memory_scope_kind == "RELATIONSHIP",
                schema.claim.c.memory_scope_ref == relationship_id,
                schema.claim.c.predicate == RAM_PREDICATE,
                schema.claim_evidence.c.relation == "SUPPORTS",
                schema.evidence_item.c.origin_kind == "COUNTERPART_STATEMENT",
                schema.evidence_item.c.source_type == "INTERACTION_EVENT",
                schema.evidence_item.c.source_id == source_event_id,
            )
        ).mappings().all()
        if len(rows) > 1:
            fail(
                "MEMORY_ADMISSION_INCONSISTENT",
                "one counterpart source event supports multiple admitted F4 memory claims",
            )
        return rows[0] if rows else None


def extract_f4_memory_candidate(content_text: str) -> F4MemoryCandidate | None:
    """Extract only an explicit primary-machine RAM semantic candidate.

    A number followed by ``GB`` is intentionally insufficient. The statement must
    explicitly bind the value to the counterpart's primary machine/computer memory.
    Questions, storage capacity, third-party machines, and unrelated quantities do
    not become candidates.
    """

    for pattern in _PRIMARY_MACHINE_RAM_PATTERNS:
        match = pattern.fullmatch(content_text)
        if match is None:
            continue
        value = int(match.group("value"))
        if value <= 0:
            return None
        return F4MemoryCandidate(
            predicate=RAM_PREDICATE,
            value=value,
            explicit_correction=bool(_CORRECTION_SIGNAL.search(content_text)),
        )
    return None


def propose_f4_memory(
    *, source_event_id: UUID, candidate: F4MemoryCandidate
) -> F4MemoryProposal:
    """Bind a non-authoritative extracted candidate to one canonical source event."""

    return F4MemoryProposal(
        source_event_id=source_event_id,
        predicate=candidate.predicate,
        value=candidate.value,
        explicit_correction=candidate.explicit_correction,
    )


def extract_f4_memory_proposal(
    *, source_event_id: UUID, content_text: str
) -> F4MemoryProposal | None:
    """Compatibility helper that still crosses candidate and proposal explicitly."""

    candidate = extract_f4_memory_candidate(content_text)
    if candidate is None:
        return None
    return propose_f4_memory(source_event_id=source_event_id, candidate=candidate)


__all__ = [
    "F4CounterpartMemoryAdmission",
    "F4MemoryAdmissionResult",
    "F4MemoryCandidate",
    "F4MemoryProposal",
    "MemoryAdmissionDisposition",
    "extract_f4_memory_candidate",
    "extract_f4_memory_proposal",
    "propose_f4_memory",
]
