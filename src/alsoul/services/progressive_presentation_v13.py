from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    ProgressivePresentationReconciliationResult,
    ReconcileProgressivePresentationAttemptCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.progressive_presentation import _aware_utc
from alsoul.services.progressive_presentation_v12 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV12,
)
from alsoul.storage import schema


_RECONCILE_SCOPE = "ReconcileProgressivePresentationAttempt"


class ProgressivePresentationServices(ProgressivePresentationServicesV12):
    """Current F6.A service with durable terminal Timeline ordering.

    Terminal reconciliation and canonical counterpart-input admission share the durable
    relationship Timeline write fence. Every newly committed terminal status therefore
    records the exact Timeline frontier observed while holding that fence. Retroactive
    interruption eligibility is decided from that monotonic frontier rather than wall
    clock timestamps, so equal/coarse timestamps can neither invent nor erase ordering.
    """

    def reconcile_attempt(
        self, command: ReconcileProgressivePresentationAttemptCommand
    ) -> ProgressivePresentationReconciliationResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECONCILE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._status_evidence(
                    conn, UUID(replay["presentation_status_evidence_id"])
                )
                return self._reconciliation_result(row)

            attempt = self._attempt(conn, command.presentation_attempt_id)
            session = self._session(conn, attempt["presentation_session_id"])
            settled = self._latest_terminal_status(
                conn, command.presentation_attempt_id
            )
            if attempt["attempt_state"] == "SETTLED" and settled is not None:
                self._save_reconciliation_operation(conn, command, req, settled)
                return self._reconciliation_result(settled)
            if attempt["attempt_state"] not in {"OPEN", "UNKNOWN"}:
                fail(
                    "PROGRESSIVE_PRESENTATION_RECONCILIATION_INVALID",
                    "presentation attempt cannot be reconciled from its current state",
                )
            known_presented = self._contiguous_presented_extent(
                conn, session["presentation_session_id"]
            )
            known_received = self._known_received_extent(
                conn, session["presentation_session_id"]
            )

        adapter = self._require_status_adapter()
        try:
            status = adapter.reconcile_presentation_status(
                presentation_key=session["presentation_key"],
                attempt_generation=int(attempt["attempt_generation"]),
                presentation_transport_fence_scope_id=attempt[
                    "presentation_transport_fence_scope_id"
                ],
                presentation_session_id=session["presentation_session_id"],
                presentation_attempt_id=attempt["presentation_attempt_id"],
            )
        except Exception as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECONCILIATION_UNAVAILABLE",
                "trusted first-party presentation status reconciliation failed",
            ) from exc

        self._validate_reconciliation_status(
            status,
            session=session,
            attempt=attempt,
            known_presented=known_presented,
            known_received=known_received,
        )

        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECONCILE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._status_evidence(
                        conn, UUID(replay["presentation_status_evidence_id"])
                    )
                    return self._reconciliation_result(row)

                current_attempt = self._locked_attempt(
                    conn, command.presentation_attempt_id
                )
                current_session = self._session(
                    conn, current_attempt["presentation_session_id"]
                )
                settled = self._latest_terminal_status(
                    conn, command.presentation_attempt_id
                )
                if current_attempt["attempt_state"] == "SETTLED":
                    if settled is not None:
                        self._save_reconciliation_operation(
                            conn, command, req, settled
                        )
                        return self._reconciliation_result(settled)
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                        "presentation attempt settled without matching terminal status evidence",
                    )
                if current_attempt["attempt_state"] not in {"OPEN", "UNKNOWN"}:
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                        "presentation attempt state changed before reconciliation could settle",
                    )

                current_presented = self._contiguous_presented_extent(
                    conn, current_session["presentation_session_id"]
                )
                current_received = self._known_received_extent(
                    conn, current_session["presentation_session_id"]
                )
                self._validate_reconciliation_status(
                    status,
                    session=current_session,
                    attempt=current_attempt,
                    known_presented=current_presented,
                    known_received=current_received,
                )
                existing = self._status_by_ref(
                    conn, current_session["presentation_key"], status.status_ref
                )
                if existing is not None:
                    self._require_exact_status(existing, status)
                    self._save_reconciliation_operation(conn, command, req, existing)
                    return self._reconciliation_result(existing)

                terminal_timeline_frontier = None
                if status.settlement_state == "TERMINAL":
                    terminal_timeline_frontier = self._lock_timeline_frontier(
                        conn, current_session
                    )

                evidence_id = self.ids.new()
                observed_at = self.clock.now()
                conn.execute(
                    insert(schema.progressive_presentation_status_evidence).values(
                        presentation_status_evidence_id=evidence_id,
                        presentation_attempt_id=current_attempt[
                            "presentation_attempt_id"
                        ],
                        presentation_session_id=current_session[
                            "presentation_session_id"
                        ],
                        attempt_generation=int(current_attempt["attempt_generation"]),
                        presentation_transport_fence_scope_id=current_attempt[
                            "presentation_transport_fence_scope_id"
                        ],
                        presentation_key=current_session["presentation_key"],
                        settlement_state=status.settlement_state,
                        status_ref=status.status_ref,
                        last_authoritatively_presented_frame=(
                            status.last_authoritatively_presented_frame
                        ),
                        last_authoritatively_received_frame=(
                            status.last_authoritatively_received_frame
                        ),
                        settled_through_ref=status.settled_through_ref,
                        status_contract_version=status.status_contract_version,
                        settled_at=(
                            _aware_utc(status.settled_at)
                            if status.settled_at is not None
                            else None
                        ),
                        observed_at=observed_at,
                    )
                )
                target_state = (
                    "SETTLED"
                    if status.settlement_state == "TERMINAL"
                    else "UNKNOWN"
                )
                changed = conn.execute(
                    update(schema.progressive_presentation_attempt)
                    .where(
                        schema.progressive_presentation_attempt.c.presentation_attempt_id
                        == command.presentation_attempt_id,
                        schema.progressive_presentation_attempt.c.attempt_state.in_(
                            ("OPEN", "UNKNOWN")
                        ),
                    )
                    .values(attempt_state=target_state)
                )
                if changed.rowcount != 1:
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                        "presentation attempt state changed before reconciliation could settle",
                    )

                if terminal_timeline_frontier is not None:
                    conn.execute(
                        insert(
                            schema.progressive_presentation_terminal_timeline_frontier
                        ).values(
                            presentation_status_evidence_id=evidence_id,
                            presentation_attempt_id=current_attempt[
                                "presentation_attempt_id"
                            ],
                            presentation_session_id=current_session[
                                "presentation_session_id"
                            ],
                            relationship_id=current_session["relationship_id"],
                            observed_timeline_frontier=terminal_timeline_frontier,
                            recorded_at=observed_at,
                        )
                    )

                row = self._status_evidence(conn, evidence_id)
                self._save_reconciliation_operation(conn, command, req, row)
                return self._reconciliation_result(row)
        except IntegrityError as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                "presentation reconciliation conflicted with durable state",
            ) from exc

    def _require_terminal_race_eligibility(
        self, conn, *, attempt, session, event
    ) -> None:
        latest_attempt_id = conn.execute(
            select(schema.progressive_presentation_attempt.c.presentation_attempt_id)
            .where(
                schema.progressive_presentation_attempt.c.presentation_session_id
                == session["presentation_session_id"]
            )
            .order_by(
                schema.progressive_presentation_attempt.c.attempt_generation.desc()
            )
            .limit(1)
        ).scalar_one()
        if latest_attempt_id != attempt["presentation_attempt_id"]:
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "a canonical input cannot retroactively interrupt a superseded presentation generation",
            )

        existing_history = conn.execute(
            select(
                schema.progressive_presentation_timeline_lineage.c.interaction_event_id
            ).where(
                schema.progressive_presentation_timeline_lineage.c.presentation_session_id
                == session["presentation_session_id"]
            )
        ).scalar_one_or_none()
        if existing_history is not None:
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "canonical presentation history was already committed before interruption admission",
            )

        terminal = self._latest_terminal_status(
            conn, attempt["presentation_attempt_id"]
        )
        if terminal is None:
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "settled attempt without terminal status evidence cannot be retroactively interrupted",
            )

        frontier = conn.execute(
            select(schema.progressive_presentation_terminal_timeline_frontier).where(
                schema.progressive_presentation_terminal_timeline_frontier.c.presentation_status_evidence_id
                == terminal["presentation_status_evidence_id"]
            )
        ).mappings().one_or_none()
        if (
            frontier is None
            or frontier["presentation_attempt_id"]
            != attempt["presentation_attempt_id"]
            or frontier["presentation_session_id"]
            != session["presentation_session_id"]
            or frontier["relationship_id"] != session["relationship_id"]
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "terminal status lacks an exact durable Timeline observation frontier",
            )
        if int(event["timeline_seq"]) > int(frontier["observed_timeline_frontier"]):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "counterpart input was canonically admitted only after terminal presentation status was observed",
            )

    @staticmethod
    def _lock_timeline_frontier(conn, session) -> int:
        fenced = conn.execute(
            update(schema.relationship_timeline_head)
            .where(
                schema.relationship_timeline_head.c.relationship_id
                == session["relationship_id"]
            )
            .values(
                last_timeline_seq=schema.relationship_timeline_head.c.last_timeline_seq
            )
        )
        if fenced.rowcount != 1:
            fail(
                "RELATIONSHIP_NOT_FOUND",
                "presentation relationship Timeline head is missing during terminal reconciliation",
            )
        return int(
            conn.execute(
                select(schema.relationship_timeline_head.c.last_timeline_seq).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == session["relationship_id"]
                )
            ).scalar_one()
        )


__all__ = ["ProgressivePresentationServices"]
