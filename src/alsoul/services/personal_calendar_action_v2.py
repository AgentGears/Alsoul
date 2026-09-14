from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError
from alsoul.services.personal_calendar_action import (
    PersonalCalendarActionServices as PersonalCalendarActionServicesV1,
)


class PersonalCalendarActionServices(PersonalCalendarActionServicesV1):
    """Current F5.B Action boundary with deterministic revision-conflict errors."""

    def set_create_policy(self, command):
        try:
            return super().set_create_policy(command)
        except IntegrityError as exc:
            # The base transaction has already unwound and rolled back here. A
            # concurrent writer may have claimed either the same next revision or
            # the first head before this operation committed.
            raise DomainError(
                "CALENDAR_CREATE_POLICY_CONFLICT",
                "calendar-create policy revision was claimed concurrently",
            ) from exc

    def set_create_permission_status(self, command):
        try:
            return super().set_create_permission_status(command)
        except IntegrityError as exc:
            # Translate an append collision only after the transaction context has
            # rolled back, so callers never inherit a failed database transaction.
            raise DomainError(
                "CALENDAR_CREATE_PERMISSION_STATE_CONFLICT",
                "calendar-create Permission state advanced concurrently",
            ) from exc


__all__ = ["PersonalCalendarActionServices"]
