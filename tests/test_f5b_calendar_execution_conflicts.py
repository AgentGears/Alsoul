from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_execution import (
    AbandonPersonalCalendarCreateExecutionAttemptCommand,
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_execution import PersonalCalendarExecutionServices
from alsoul.services.personal_calendar_execution_v2 import (
    PersonalCalendarExecutionServicesV1,
)

import test_f5_personal_calendar_authority as authority_cases


def _service(engine, now):
    return PersonalCalendarExecutionServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def test_abandon_append_collision_is_translated_after_transaction_unwinds(
    engine, now, monkeypatch
):
    def collide(self, command):
        raise IntegrityError(
            "insert execution transition",
            {},
            Exception("duplicate state revision"),
        )

    monkeypatch.setattr(
        PersonalCalendarExecutionServicesV1,
        "abandon_prepared_attempt",
        collide,
    )
    service = _service(engine, now)

    with pytest.raises(DomainError) as conflict:
        service.abandon_prepared_attempt(
            AbandonPersonalCalendarCreateExecutionAttemptCommand(
                operation_id=uuid4(),
                execution_attempt_id=uuid4(),
            )
        )

    assert conflict.value.code == "CALENDAR_CREATE_EXECUTION_TRANSITION_CONFLICT"


def test_recovery_sqlite_lock_collision_is_translated_after_transaction_unwinds(
    engine, now, monkeypatch
):
    def collide(self, command):
        raise OperationalError(
            "insert execution transition",
            {},
            Exception("database is locked"),
        )

    monkeypatch.setattr(
        PersonalCalendarExecutionServicesV1,
        "recover_fenced_attempt",
        collide,
    )
    service = _service(engine, now)

    with pytest.raises(DomainError) as conflict:
        service.recover_fenced_attempt(
            RecoverPersonalCalendarCreateFencedAttemptCommand(
                operation_id=uuid4(),
                execution_attempt_id=uuid4(),
            )
        )

    assert conflict.value.code == "CALENDAR_CREATE_EXECUTION_TRANSITION_CONFLICT"


def test_non_lock_operational_error_is_not_misclassified_as_transition_conflict(
    engine, now, monkeypatch
):
    def fail_storage(self, command):
        raise OperationalError(
            "select execution transition",
            {},
            Exception("disk I/O error"),
        )

    monkeypatch.setattr(
        PersonalCalendarExecutionServicesV1,
        "recover_fenced_attempt",
        fail_storage,
    )
    service = _service(engine, now)

    with pytest.raises(OperationalError):
        service.recover_fenced_attempt(
            RecoverPersonalCalendarCreateFencedAttemptCommand(
                operation_id=uuid4(),
                execution_attempt_id=uuid4(),
            )
        )
