from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update

from alsoul.domain.errors import fail
from alsoul.services.personal_calendar_acquisition import (
    PersonalCalendarAcquisitionServices as PersonalCalendarAcquisitionServicesV1,
)
from alsoul.storage import schema


_RESTARTABLE_TRAVERSAL_FAILURES = frozenset(
    {
        "CALENDAR_PAGINATION_LIMIT_EXCEEDED",
        "CALENDAR_PAGINATION_TOKEN_CYCLE",
        "CALENDAR_PAGINATION_INCOMPLETE",
        "CALENDAR_PAGINATION_TERMINAL_INVALID",
        "CALENDAR_PROVIDER_RESULT_CAP_REACHED",
        "CALENDAR_SNAPSHOT_CHANGED_DURING_PAGINATION",
        "CALENDAR_SNAPSHOT_TIME_INCONSISTENT",
    }
)


class PersonalCalendarAcquisitionServices(PersonalCalendarAcquisitionServicesV1):
    """Current F5.A acquisition boundary with explicit adapter/query qualification."""

    def _qualify_contract(self) -> None:
        super()._qualify_contract()
        contract = self.capability_contract
        adapter_contract_version = getattr(
            self.adapter, "capability_contract_version", None
        )
        if adapter_contract_version != contract.contract_version:
            fail(
                "CALENDAR_ADAPTER_CAPABILITY_MISMATCH",
                "calendar adapter is not qualified for the trusted capability contract",
            )
        if contract.query_interval_semantics != "OVERLAP_COMPLETE_HALF_OPEN_WINDOW":
            fail(
                "CALENDAR_QUERY_SEMANTICS_UNTRUSTED",
                "calendar adapter contract must guarantee complete half-open interval overlap semantics",
            )
        if contract.history_compensation_mode != "PROHIBITED":
            fail(
                "CALENDAR_QUERY_SEMANTICS_UNTRUSTED",
                "calendar acquisition must not compensate with unbounded history queries",
            )
        if (
            not isinstance(contract.max_restarts, int)
            or isinstance(contract.max_restarts, bool)
            or contract.max_restarts < 0
        ):
            fail(
                "CALENDAR_RESTART_BOUND_INVALID",
                "calendar traversal restart count must be a finite non-negative integer",
            )

    def _start_attempt(self, command):
        with self.engine.connect() as conn:
            maximum_generation = conn.execute(
                select(
                    func.max(schema.personal_calendar_acquisition_attempt.c.generation)
                ).where(
                    schema.personal_calendar_acquisition_attempt.c.observation_id
                    == command.observation_id
                )
            ).scalar_one()
        if int(maximum_generation or 0) > self.capability_contract.max_restarts:
            fail(
                "CALENDAR_ACQUISITION_RESTART_LIMIT_EXCEEDED",
                "calendar acquisition exhausted the trusted traversal restart bound",
            )
        return super()._start_attempt(command)

    def _mark_failed(
        self,
        *,
        attempt_id: UUID,
        observation_id: UUID,
        investigation_id: UUID,
        failure_code: str,
    ) -> None:
        if (
            failure_code not in _RESTARTABLE_TRAVERSAL_FAILURES
            or self.capability_contract.max_restarts <= 0
        ):
            super()._mark_failed(
                attempt_id=attempt_id,
                observation_id=observation_id,
                investigation_id=investigation_id,
                failure_code=failure_code,
            )
            return

        with self.engine.connect() as conn:
            attempt = conn.execute(
                select(schema.personal_calendar_acquisition_attempt).where(
                    schema.personal_calendar_acquisition_attempt.c.acquisition_attempt_id
                    == attempt_id
                )
            ).mappings().one_or_none()
        if (
            attempt is None
            or attempt["status"] != "STARTED"
            or int(attempt["generation"]) > self.capability_contract.max_restarts
        ):
            super()._mark_failed(
                attempt_id=attempt_id,
                observation_id=observation_id,
                investigation_id=investigation_id,
                failure_code=failure_code,
            )
            return

        with self.engine.begin() as conn:
            conn.execute(
                update(schema.personal_calendar_acquisition_attempt)
                .where(
                    schema.personal_calendar_acquisition_attempt.c.acquisition_attempt_id
                    == attempt_id,
                    schema.personal_calendar_acquisition_attempt.c.status == "STARTED",
                )
                .values(
                    status="FAILED",
                    ended_at=self.clock.now(),
                    failure_code=failure_code,
                )
            )


__all__ = ["PersonalCalendarAcquisitionServices"]
