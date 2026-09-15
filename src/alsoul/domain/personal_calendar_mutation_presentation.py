from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from alsoul.domain.personal_calendar_presentation import (
    PersonalCalendarPresentationAdapter,
    PersonalCalendarPresentationResult,
)


@dataclass(frozen=True, slots=True)
class PresentPersonalCalendarMutationOutputCommand:
    operation_id: UUID
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class RecoverPersonalCalendarMutationPresentationCommand:
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


__all__ = [
    "PersonalCalendarPresentationAdapter",
    "PersonalCalendarPresentationResult",
    "PresentPersonalCalendarMutationOutputCommand",
    "RecoverPersonalCalendarMutationPresentationCommand",
]
