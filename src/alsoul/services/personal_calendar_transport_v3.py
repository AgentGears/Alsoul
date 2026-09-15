from __future__ import annotations

from alsoul.services.personal_calendar_execution_v3 import (
    require_current_calendar_create_execution_binding,
)
from alsoul.services.personal_calendar_transport_v2 import (
    PersonalCalendarMutationTransportServices as PersonalCalendarMutationTransportServicesV2,
)


class PersonalCalendarMutationTransportServices(
    PersonalCalendarMutationTransportServicesV2
):
    """Current mutation transport with trusted terminal-negative fence semantics."""

    def _require_execution_binding(self, *, action, resource):
        return require_current_calendar_create_execution_binding(
            self, action=action, resource=resource
        )


__all__ = ["PersonalCalendarMutationTransportServices"]
