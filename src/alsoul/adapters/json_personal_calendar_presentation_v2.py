from __future__ import annotations

import hashlib
from dataclasses import dataclass

from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
)
from alsoul.adapters.json_personal_calendar_presentation import (
    JsonPersonalCalendarPresentationAdapter as JsonPersonalCalendarPresentationAdapterV1,
)


@dataclass(frozen=True, slots=True)
class JsonPersonalCalendarPresentationAdapter(
    JsonPersonalCalendarPresentationAdapterV1
):
    """Qualified sink with immutable exact-generation terminal-negative semantics."""

    terminal_negative_semantics: str = PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.terminal_negative_semantics != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS:
            raise ValueError("unsupported personal presentation terminal-negative semantics")

    @property
    def sink_binding_ref(self) -> str:
        material = "\n".join(
            (
                super().sink_binding_ref,
                self.terminal_negative_semantics,
            )
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(material).hexdigest()}"


__all__ = ["JsonPersonalCalendarPresentationAdapter"]
