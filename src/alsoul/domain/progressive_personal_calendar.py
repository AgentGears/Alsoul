from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OpenPersonalCalendarProgressivePresentationCommand:
    operation_id: UUID
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class DispatchPersonalCalendarProgressiveFrameCommand:
    operation_id: UUID
    presentation_attempt_id: UUID
    frame_ordinal: int
    permission_id: UUID


__all__ = [
    "DispatchPersonalCalendarProgressiveFrameCommand",
    "OpenPersonalCalendarProgressivePresentationCommand",
]
