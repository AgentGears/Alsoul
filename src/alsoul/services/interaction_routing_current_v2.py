from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from alsoul.services.interaction_routing_current import (
    CurrentInteractionClassification as CurrentInteractionClassificationV1,
    CurrentInteractionPurposeGate as CurrentInteractionPurposeGateV1,
    classify_current_interaction_text as classify_current_interaction_text_v1,
)
from alsoul.storage import schema

CurrentInteractionPurpose = Literal[
    "MEMORY_STATEMENT",
    "WORLD_QUESTION",
    "CONVERSATIONAL_RESPONSE",
    "PERSONAL_CALENDAR_QUESTION",
    "PERSONAL_CALENDAR_CREATE_REQUEST",
    "PERSONAL_CALENDAR_CREATE_APPROVAL",
    "UNSUPPORTED",
]

_CREATE_REQUEST = re.compile(
    r"^Add '[^'\n]+' to my calendar from "
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}) to "
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})\.$"
)
_APPROVAL = re.compile(r"^APPROVE CALENDAR ACTION [0-9a-f]{64}$")

CurrentInteractionClassification = CurrentInteractionClassificationV1


class CurrentInteractionPurposeGate(CurrentInteractionPurposeGateV1):
    """Route only the exact bounded F5.B mutation grammars ahead of F5.A/F4."""

    def classify_event(self, source_event_id: UUID, **kwargs) -> CurrentInteractionClassification:
        with self.services.engine.connect() as conn:
            text = conn.execute(
                select(schema.interaction_event.c.content_text).where(
                    schema.interaction_event.c.event_id == source_event_id
                )
            ).scalar_one()
        mutation = classify_mutation_interaction_text(text)
        if mutation is not None:
            # Reuse the inherited source/relationship/route validation before admitting
            # the specialized purpose. Its textual classification result is ignored.
            validated = super().classify_event(source_event_id, **kwargs)
            return CurrentInteractionClassification(validated.source_event_id, mutation)
        return super().classify_event(source_event_id, **kwargs)


def classify_mutation_interaction_text(content_text: str):
    if _CREATE_REQUEST.fullmatch(content_text):
        return "PERSONAL_CALENDAR_CREATE_REQUEST"
    if _APPROVAL.fullmatch(content_text):
        return "PERSONAL_CALENDAR_CREATE_APPROVAL"
    return None


def classify_current_interaction_text(content_text: str) -> CurrentInteractionPurpose:
    mutation = classify_mutation_interaction_text(content_text)
    if mutation is not None:
        return mutation
    return classify_current_interaction_text_v1(content_text)


__all__ = [
    "CurrentInteractionClassification",
    "CurrentInteractionPurpose",
    "CurrentInteractionPurposeGate",
    "classify_current_interaction_text",
    "classify_mutation_interaction_text",
]
