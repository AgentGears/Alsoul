from __future__ import annotations

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND,
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
)
from alsoul.services.personal_calendar_presentation_v3 import (
    PersonalCalendarPresentationServices as PersonalCalendarPresentationServicesV3,
)


class PersonalCalendarPresentationServices(PersonalCalendarPresentationServicesV3):
    """Current F5.A presentation boundary with terminal-generation qualification."""

    def _require_adapter(self) -> None:
        super()._require_adapter()
        if (
            getattr(self.adapter, "terminal_negative_semantics", None)
            != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS
        ):
            fail(
                "CALENDAR_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation sink cannot prove terminal-negative settlement for an exact generation",
            )

    def _validate_status_identity(self, status, *, attempt_id) -> None:
        super()._validate_status_identity(status, attempt_id=attempt_id)
        if (
            status.state == "NOT_ACCEPTED"
            and status.terminal_proof_kind
            != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND
        ):
            fail(
                "CALENDAR_PRESENTATION_TERMINALITY_INVALID",
                "NOT_ACCEPTED evidence does not prove settled exact-generation terminality",
            )


__all__ = ["PersonalCalendarPresentationServices"]
