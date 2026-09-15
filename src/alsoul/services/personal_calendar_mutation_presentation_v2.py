from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
)
from alsoul.services.personal_calendar_mutation_presentation import (
    PersonalCalendarMutationPresentationServices as PersonalCalendarMutationPresentationServicesV1,
    _is_transient_lock_collision,
    _required_text,
)
from alsoul.services.runtime_identity import presentation_idempotency_key
from alsoul.storage import schema


class PersonalCalendarMutationPresentationServices(
    PersonalCalendarMutationPresentationServicesV1
):
    """Current mutation-result presentation with exact attempt integrity and serialized settlement."""

    def _attempt(self, conn, attempt_id: UUID):
        attempt = super()._attempt(conn, attempt_id)
        decision = conn.execute(
            select(schema.personal_calendar_mutation_disclosure_decision).where(
                schema.personal_calendar_mutation_disclosure_decision.c.disclosure_decision_id
                == attempt["disclosure_decision_id"]
            )
        ).mappings().one_or_none()
        adoption = conn.execute(
            select(schema.personal_calendar_mutation_adoption).where(
                schema.personal_calendar_mutation_adoption.c.companion_output_id
                == attempt["companion_output_id"]
            )
        ).mappings().one_or_none()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == attempt["companion_output_id"]
            )
        ).mappings().one_or_none()
        expected_key = presentation_idempotency_key(
            attempt["companion_output_id"],
            attempt["surface_binding_id"],
            attempt["channel_binding_id"],
        )
        if (
            decision is None
            or adoption is None
            or output is None
            or decision["companion_output_id"] != attempt["companion_output_id"]
            or decision["action_id"] != adoption["action_id"]
            or decision["effect_id"] != adoption["effect_id"]
            or decision["effect_evidence_id"] != adoption["effect_evidence_id"]
            or decision["surface_binding_id"] != attempt["surface_binding_id"]
            or decision["channel_binding_id"] != attempt["channel_binding_id"]
            or decision["relationship_id"] != output["relationship_id"]
            or attempt["payload_digest"] != output["content_digest"]
            or attempt["presentation_key"] != expected_key
            or attempt["presentation_contract_version"]
            != PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
            or attempt["status_contract_version"]
            != PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
        ):
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ATTEMPT_LINEAGE_MISMATCH",
                "mutation-result presentation attempt does not match its exact disclosure/adoption/output lineage",
            )
        return attempt

    def _settle_attempt(
        self,
        attempt_id: UUID,
        status: PersonalCalendarPresentationDispatchResult
        | PersonalCalendarPresentationStatusResult,
    ) -> None:
        try:
            with self.engine.begin() as conn:
                # Serialize terminal settlement before inserting the unique evidence
                # row. A competing reconciler that already settled the same terminal
                # truth becomes an idempotent replay rather than a storage error.
                fenced = conn.execute(
                    update(schema.personal_calendar_mutation_presentation_attempt)
                    .where(
                        schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_id
                        == attempt_id,
                        schema.personal_calendar_mutation_presentation_attempt.c.sink_acceptance_state
                        == "UNKNOWN",
                    )
                    .values(sink_acceptance_state="UNKNOWN")
                )
                if fenced.rowcount != 1:
                    attempt = self._attempt(conn, attempt_id)
                    if attempt["sink_acceptance_state"] == status.state:
                        return
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                        "mutation-result presentation attempt already has a different terminal state",
                    )

                # Revalidate the exact disclosure/adoption/output binding under the
                # same write transaction that owns terminal settlement.
                self._attempt(conn, attempt_id)

                if status.state == "ACCEPTED":
                    receipt_ref = _required_text(
                        status.receipt_ref,
                        "CALENDAR_MUTATION_PRESENTATION_ACCEPTANCE_INVALID",
                        "accepted mutation-result presentation requires a sink receipt",
                    )
                    accepted_at = status.accepted_at
                    proof_kind = None
                    settled_ref = None
                    proved_at = None
                elif status.state == "NOT_ACCEPTED":
                    receipt_ref = None
                    proof_kind = _required_text(
                        status.terminal_proof_kind,
                        "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                        "NOT_ACCEPTED requires exact-generation terminal proof",
                    )
                    if proof_kind != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND:
                        fail(
                            "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                            "NOT_ACCEPTED evidence does not prove settled exact-generation terminality",
                        )
                    settled_ref = _required_text(
                        status.settled_through_ref,
                        "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                        "NOT_ACCEPTED requires settled-through evidence",
                    )
                    accepted_at = None
                    proved_at = status.proved_at or self.clock.now()
                else:
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_STATUS_INVALID",
                        "only terminal presentation status can settle an attempt",
                    )

                observed_at = self.clock.now()
                conn.execute(
                    insert(
                        schema.personal_calendar_mutation_presentation_status_evidence
                    ).values(
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
                    update(schema.personal_calendar_mutation_presentation_attempt)
                    .where(
                        schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_id
                        == attempt_id,
                        schema.personal_calendar_mutation_presentation_attempt.c.sink_acceptance_state
                        == "UNKNOWN",
                    )
                    .values(
                        sink_acceptance_state=status.state,
                        settled_at=observed_at,
                    )
                )
                if changed.rowcount != 1:
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                        "mutation-result presentation attempt changed during terminal settlement",
                    )
        except DomainError:
            raise
        except IntegrityError as exc:
            # A uniqueness collision here is necessarily another terminal settlement
            # racing this exact attempt; never expose raw storage semantics.
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                "mutation-result presentation terminal evidence conflicted with concurrent settlement",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                "mutation-result presentation terminal settlement conflicted with concurrent state",
            ) from exc


__all__ = ["PersonalCalendarMutationPresentationServices"]
