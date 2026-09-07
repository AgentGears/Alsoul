from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid5

from sqlalchemy import select

from alsoul.domain.commands import AdmitPersonMemoryClaimCommand
from alsoul.domain.errors import fail
from alsoul.services.foundation import FoundationServices, RAM_PREDICATE
from alsoul.storage import schema

_MEMORY_ADMISSION_NAMESPACE = UUID("58cc7115-f208-42ed-96ef-a7c7f6a99808")

MemoryAdmissionDisposition = Literal[
    "NO_CANDIDATE",
    "ADMITTED",
    "CORRECTED",
    "UNCHANGED",
]

_CORRECTION_SIGNAL = re.compile(
    r"\b(?:actually|correction|to correct that|i was wrong)\b",
    flags=re.IGNORECASE,
)

_PRIMARY_MACHINE_RAM_PATTERNS = (
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong)\s*[,;:]?\s*)?"
        r"my\s+(?:machine|computer|laptop|pc|desktop)\s+"
        r"(?:(?:currently|now)\s+)?(?:has|contains|comes\s+with)\s+"
        r"(?P<value>\d{1,5})\s*gb(?:\s+of)?\s+(?:ram|memory)\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong)\s*[,;:]?\s*)?"
        r"my\s+(?:machine|computer|laptop|pc|desktop)(?:'s)?\s+"
        r"(?:ram|memory)\s+(?:is|=)\s+(?P<value>\d{1,5})\s*gb\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:(?:actually|correction|to correct that|i was wrong)\s*[,;:]?\s*)?"
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

    This service deliberately separates source history, extraction, proposal, and
    admission. Extraction is deterministic and narrow; it never asks a model to
    decide what to remember. The existing FoundationServices transaction remains
    the authoritative Claim/Evidence admission boundary.
    """

    def __init__(self, services: FoundationServices) -> None:
        self.services = services

    def consider_event(self, source_event_id: UUID) -> F4MemoryAdmissionResult:
        with self.services.engine.connect() as conn:
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

            existing = self._claim_from_source_event(
                conn,
                source_event_id=source_event_id,
                companion_person_id=relationship["companion_person_id"],
                counterpart_id=relationship["counterpart_id"],
                relationship_id=relationship["relationship_id"],
            )
            if existing is not None:
                correction = conn.execute(
                    select(schema.claim_supersession).where(
                        schema.claim_supersession.c.newer_claim_id
                        == existing["claim_id"],
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

        current = self.services.get_current_memory_claim(
            companion_person_id=relationship["companion_person_id"],
            counterpart_id=relationship["counterpart_id"],
            relationship_id=relationship["relationship_id"],
            predicate=proposal.predicate,
        )
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

        result = self.services.admit_person_memory_claim(
            AdmitPersonMemoryClaimCommand(
                operation_id=uuid5(
                    _MEMORY_ADMISSION_NAMESPACE,
                    f"{source_event_id}:{proposal.predicate}",
                ),
                holder_companion_person_id=relationship["companion_person_id"],
                subject_counterpart_id=relationship["counterpart_id"],
                relationship_id=relationship["relationship_id"],
                predicate=proposal.predicate,
                value=proposal.value,
                source_event_id=source_event_id,
                correction_of_claim_id=correction_of_claim_id,
                valid_from=event["occurred_at"],
            )
        )
        return F4MemoryAdmissionResult(
            source_event_id=source_event_id,
            disposition=disposition,
            predicate=proposal.predicate,
            value=proposal.value,
            claim_id=result.claim_id,
            corrected_claim_id=result.corrected_claim_id,
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
