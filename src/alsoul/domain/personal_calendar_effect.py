from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


CALENDAR_CREATE_EFFECT_SCHEMA_VERSION = "CALENDAR_CREATE_EFFECT_V1"
CALENDAR_CREATE_EFFECT_SUPPORT_KIND = "SUPPORTS"


@dataclass(frozen=True, slots=True)
class AdmitPersonalCalendarCreateConfirmedEffectCommand:
    operation_id: UUID
    execution_attempt_id: UUID
    effect_evidence_id: UUID


@dataclass(frozen=True, slots=True)
class PersonalCalendarCreateConfirmedEffectResult:
    effect_id: UUID
    action_id: UUID
    execution_attempt_id: UUID
    effect_evidence_id: UUID
    status: Literal["CONFIRMED_EFFECT"] = "CONFIRMED_EFFECT"


__all__ = [
    "AdmitPersonalCalendarCreateConfirmedEffectCommand",
    "CALENDAR_CREATE_EFFECT_SCHEMA_VERSION",
    "CALENDAR_CREATE_EFFECT_SUPPORT_KIND",
    "PersonalCalendarCreateConfirmedEffectResult",
]
