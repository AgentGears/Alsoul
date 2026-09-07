from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.services.conversation_context import requires_prior_timeline_context
from alsoul.services.foundation import FoundationServices
from alsoul.services.memory_admission import extract_f4_memory_candidate
from alsoul.storage import schema

F4InteractionPurpose = Literal[
    "MEMORY_STATEMENT",
    "WORLD_QUESTION",
    "CONVERSATIONAL_RESPONSE",
    "UNSUPPORTED",
]

_WORLD_QUESTION_PATTERNS = (
    re.compile(
        r"^\s*(?:would|will|can)\s+(?:the\s+)?current\s+"
        r"(?:software|application|program)\s+(?:run|work)\s+on\s+my\s+"
        r"(?:machine|computer|laptop|pc|desktop)\s*\?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:does|do)\s+my\s+(?:machine|computer|laptop|pc|desktop)\s+"
        r"(?:meet|satisfy)\s+(?:the\s+)?current\s+"
        r"(?:software|application|program)\s+(?:memory\s+)?requirements?\s*\?\s*$",
        flags=re.IGNORECASE,
    ),
)

_CONVERSATIONAL_PATTERNS = (
    re.compile(
        r"^\s*(?:hi|hello|hey)(?:\s+there)?\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:thanks|thank\s+you)(?:\s+very\s+much)?\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*how\s+(?:are\s+you|is\s+it\s+going|are\s+things)(?:\s+today)?\s*\?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:bye|goodbye|good\s+night|see\s+you(?:\s+later)?)\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class F4InteractionClassification:
    source_event_id: UUID
    purpose: F4InteractionPurpose


class F4InteractionPurposeGate:
    """Classify one canonical F4 counterpart input into a bounded purpose.

    The gate is deterministic and provider-independent. It does not ask a model to
    infer intent and it writes no canonical state. Classification is derived from the
    immutable InteractionEvent text only after trusted ingress has already persisted
    the event. Optional expected route references fence high-level callers to the
    exact canonical event they intend to continue.
    """

    def __init__(self, services: FoundationServices) -> None:
        self.services = services

    def classify_event(
        self,
        source_event_id: UUID,
        *,
        expected_relationship_id: UUID | None = None,
        expected_surface_binding_id: UUID | None = None,
        expected_channel_binding_id: UUID | None = None,
    ) -> F4InteractionClassification:
        with self.services.engine.connect() as conn:
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == source_event_id
                )
            ).mappings().one_or_none()
            if event is None:
                fail(
                    "INTERACTION_PURPOSE_SOURCE_NOT_FOUND",
                    "interaction-purpose source event does not exist",
                )
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == event["relationship_id"]
                )
            ).mappings().one_or_none()

        if relationship is None:
            fail("RELATIONSHIP_NOT_FOUND", "interaction-purpose relationship does not exist")
        if (
            event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "INTERACTION_PURPOSE_SOURCE_INVALID",
                "interaction-purpose gate accepts only counterpart input in its relationship",
            )
        if (
            expected_relationship_id is not None
            and event["relationship_id"] != expected_relationship_id
        ):
            fail(
                "INTERACTION_PURPOSE_ROUTE_MISMATCH",
                "current input does not belong to the supplied relationship",
            )
        if (
            expected_surface_binding_id is not None
            and event["surface_binding_id"] != expected_surface_binding_id
        ):
            fail(
                "INTERACTION_PURPOSE_ROUTE_MISMATCH",
                "current input does not belong to the supplied surface binding",
            )
        if (
            expected_channel_binding_id is not None
            and event["channel_binding_id"] != expected_channel_binding_id
        ):
            fail(
                "INTERACTION_PURPOSE_ROUTE_MISMATCH",
                "current input does not belong to the supplied channel binding",
            )

        return F4InteractionClassification(
            source_event_id=source_event_id,
            purpose=classify_f4_interaction_text(event["content_text"]),
        )


def classify_f4_interaction_text(content_text: str) -> F4InteractionPurpose:
    """Classify only interaction purposes explicitly implemented by the F4 surface."""

    if extract_f4_memory_candidate(content_text) is not None:
        return "MEMORY_STATEMENT"
    if any(pattern.fullmatch(content_text) for pattern in _WORLD_QUESTION_PATTERNS):
        return "WORLD_QUESTION"
    if requires_prior_timeline_context(content_text):
        return "CONVERSATIONAL_RESPONSE"
    if any(pattern.fullmatch(content_text) for pattern in _CONVERSATIONAL_PATTERNS):
        return "CONVERSATIONAL_RESPONSE"
    return "UNSUPPORTED"


__all__ = [
    "F4InteractionClassification",
    "F4InteractionPurpose",
    "F4InteractionPurposeGate",
    "classify_f4_interaction_text",
]
