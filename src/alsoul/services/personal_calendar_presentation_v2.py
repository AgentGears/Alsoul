from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_presentation import (
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
    PresentPersonalCalendarOutputCommand,
)
from alsoul.services.personal_calendar_presentation import (
    PersonalCalendarPresentationServices as PersonalCalendarPresentationServicesV1,
    _required_text,
)
from alsoul.storage import schema

_PRESENTATION_ADMISSION_ACTIVE: ContextVar[bool] = ContextVar(
    "personal_calendar_presentation_admission_active",
    default=False,
)


class PersonalCalendarPresentationServices(PersonalCalendarPresentationServicesV1):
    """Current F5.A presentation service with output/generation serialization fences."""

    def present_output(self, command: PresentPersonalCalendarOutputCommand):
        token = _PRESENTATION_ADMISSION_ACTIVE.set(True)
        try:
            return super().present_output(command)
        finally:
            _PRESENTATION_ADMISSION_ACTIVE.reset(token)

    def _load_output_lineage(self, conn, companion_output_id: UUID):
        if _PRESENTATION_ADMISSION_ACTIVE.get():
            # Serialize prospective payload-bearing attempts for one immutable output
            # before reading the latest generation.  A competing transaction waits on
            # this row; after the winner commits UNKNOWN/terminal attempt state the
            # loser re-reads that state and cannot dispatch the same next generation.
            fenced = conn.execute(
                update(schema.personal_calendar_companion_output)
                .where(
                    schema.personal_calendar_companion_output.c.companion_output_id
                    == companion_output_id
                )
                .values(
                    deterministic_render_digest=
                    schema.personal_calendar_companion_output.c.deterministic_render_digest
                )
            )
            if fenced.rowcount != 1:
                fail(
                    "CALENDAR_COMPANION_OUTPUT_NOT_FOUND",
                    "personal calendar CompanionOutput does not exist",
                )
        return super()._load_output_lineage(conn, companion_output_id)

    def _settle_attempt(
        self,
        attempt_id: UUID,
        status: PersonalCalendarPresentationDispatchResult
        | PersonalCalendarPresentationStatusResult,
    ) -> None:
        with self.engine.begin() as conn:
            # Serialize terminal settlement before inserting the unique evidence row.
            # If another reconciler wins, re-read its terminal state rather than
            # surfacing a storage uniqueness error or admitting contradictory proof.
            fenced = conn.execute(
                update(schema.personal_calendar_presentation_attempt)
                .where(
                    schema.personal_calendar_presentation_attempt.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_presentation_attempt.c.sink_acceptance_state
                    == "UNKNOWN",
                )
                .values(sink_acceptance_state="UNKNOWN")
            )
            if fenced.rowcount != 1:
                attempt = self._attempt(conn, attempt_id)
                if attempt["sink_acceptance_state"] == status.state:
                    return
                fail(
                    "CALENDAR_PRESENTATION_SETTLEMENT_CONFLICT",
                    "presentation attempt already has a different terminal state",
                )

            if status.state == "ACCEPTED":
                receipt_ref = _required_text(
                    status.receipt_ref,
                    "CALENDAR_PRESENTATION_ACCEPTANCE_INVALID",
                    "accepted presentation requires a sink receipt",
                )
                accepted_at = status.accepted_at
                proof_kind = None
                settled_ref = None
                proved_at = None
            elif status.state == "NOT_ACCEPTED":
                receipt_ref = None
                proof_kind = _required_text(
                    status.terminal_proof_kind,
                    "CALENDAR_PRESENTATION_TERMINALITY_INVALID",
                    "NOT_ACCEPTED requires terminal proof kind",
                )
                settled_ref = _required_text(
                    status.settled_through_ref,
                    "CALENDAR_PRESENTATION_TERMINALITY_INVALID",
                    "NOT_ACCEPTED requires settled-through evidence",
                )
                accepted_at = None
                proved_at = status.proved_at or self.clock.now()
            else:
                fail(
                    "CALENDAR_PRESENTATION_STATUS_INVALID",
                    "only terminal presentation status can settle an attempt",
                )

            observed_at = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_presentation_status_evidence).values(
                    status_evidence_id=self.ids.new(),
                    presentation_attempt_id=attempt_id,
                    state=status.state,
                    receipt_ref=receipt_ref,
                    terminal_proof_kind=proof_kind,
                    settled_through_ref=settled_ref,
                    status_contract_version=status.status_contract_version,
                    accepted_at=accepted_at,
                    proved_at=proved_at,
                    observed_at=observed_at,
                )
            )
            changed = conn.execute(
                update(schema.personal_calendar_presentation_attempt)
                .where(
                    schema.personal_calendar_presentation_attempt.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_presentation_attempt.c.sink_acceptance_state
                    == "UNKNOWN",
                )
                .values(sink_acceptance_state=status.state, settled_at=observed_at)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_PRESENTATION_SETTLEMENT_CONFLICT",
                    "presentation attempt changed during terminal settlement",
                )


__all__ = ["PersonalCalendarPresentationServices"]
