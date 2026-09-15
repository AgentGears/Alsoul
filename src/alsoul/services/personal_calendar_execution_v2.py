from __future__ import annotations

from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.domain.errors import DomainError
from alsoul.services.personal_calendar_execution import (
    PersonalCalendarExecutionServices as PersonalCalendarExecutionServicesV1,
)


_TRANSITION_CONFLICT_CODE = "CALENDAR_CREATE_EXECUTION_TRANSITION_CONFLICT"
_TRANSITION_CONFLICT_MESSAGE = (
    "calendar-create execution transition conflicted with a concurrent durable state advance"
)


class PersonalCalendarExecutionServices(PersonalCalendarExecutionServicesV1):
    """Current calendar-create state boundary with deterministic transition conflicts."""

    def prepare_execution_attempt(self, command):
        try:
            return super().prepare_execution_attempt(command)
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
                "calendar-create Action dispatch eligibility was claimed concurrently",
            ) from exc

    def fence_execution_attempt(self, command):
        try:
            return super().fence_execution_attempt(command)
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_EXECUTION_FENCE_CONFLICT",
                "calendar-create execution fence conflicted with current durable state",
            ) from exc

    def abandon_prepared_attempt(self, command):
        try:
            return super().abandon_prepared_attempt(command)
        except IntegrityError as exc:
            raise DomainError(_TRANSITION_CONFLICT_CODE, _TRANSITION_CONFLICT_MESSAGE) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(_TRANSITION_CONFLICT_CODE, _TRANSITION_CONFLICT_MESSAGE) from exc

    def recover_fenced_attempt(self, command):
        try:
            return super().recover_fenced_attempt(command)
        except IntegrityError as exc:
            raise DomainError(_TRANSITION_CONFLICT_CODE, _TRANSITION_CONFLICT_MESSAGE) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(_TRANSITION_CONFLICT_CODE, _TRANSITION_CONFLICT_MESSAGE) from exc


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = ["PersonalCalendarExecutionServices"]
