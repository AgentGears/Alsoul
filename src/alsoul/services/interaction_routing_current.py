from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from alsoul.services.interaction_routing import (
    F4InteractionPurposeGate,
    classify_f4_interaction_text,
)
from alsoul.storage import schema

CurrentInteractionPurpose = Literal[
    "MEMORY_STATEMENT",
    "WORLD_QUESTION",
    "CONVERSATIONAL_RESPONSE",
    "PERSONAL_CALENDAR_QUESTION",
    "UNSUPPORTED",
]

_PERSONAL_CALENDAR_QUESTION = re.compile(
    r"^(?:What's on my calendar on|What do I have on my calendar on) "
    r"\d{4}-\d{2}-\d{2}\?$"
)


@dataclass(frozen=True, slots=True)
class CurrentInteractionClassification:
    source_event_id: UUID
    purpose: CurrentInteractionPurpose


class CurrentInteractionPurposeGate(F4InteractionPurposeGate):
    """Extend the deterministic interaction gate with the exact F5.A grammar."""

    def classify_event(self, source_event_id: UUID, **kwargs) -> CurrentInteractionClassification:
        base = super().classify_event(source_event_id, **kwargs)
        if base.purpose != "UNSUPPORTED":
            return CurrentInteractionClassification(base.source_event_id, base.purpose)
        with self.services.engine.connect() as conn:
            text = conn.execute(
                select(schema.interaction_event.c.content_text).where(
                    schema.interaction_event.c.event_id == source_event_id
                )
            ).scalar_one()
        return CurrentInteractionClassification(
            source_event_id,
            classify_current_interaction_text(text),
        )


def classify_current_interaction_text(content_text: str) -> CurrentInteractionPurpose:
    if _PERSONAL_CALENDAR_QUESTION.fullmatch(content_text):
        return "PERSONAL_CALENDAR_QUESTION"
    return classify_f4_interaction_text(content_text)


__all__ = [
    "CurrentInteractionClassification",
    "CurrentInteractionPurpose",
    "CurrentInteractionPurposeGate",
    "classify_current_interaction_text",
]
