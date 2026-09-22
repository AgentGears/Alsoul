from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    InterruptProgressivePresentationCommand,
    ProgressivePresentationInterruptionResult,
)
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.progressive_presentation import _aware_utc
from alsoul.services.progressive_presentation_v11 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV11,
)
from alsoul.storage import schema


_INTERRUPT_SCOPE = "InterruptProgressivePresentationAttempt"


class ProgressivePresentationServices(ProgressivePresentationServicesV11):
    """Current F6.A service with durable ordering for interruption/settlement races.

    Interruption admission acquires the same durable attempt write fence used by frame
    authorization and terminal reconciliation before deciding whether the generation is
    still active. If reconciliation has already settled the exact generation, a
    counterpart input that was canonically admitted before terminal status observation
    may still be recorded as the interruption boundary with
    ``NOT_REQUIRED_TERMINAL``. Input admitted only after terminal observation is never
    retroactively promoted into an interruption.
    """

    def interrupt_attempt(
        self, command: InterruptProgressivePresentationCommand
    ) -> ProgressivePresentationInterruptionResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_INTERRUPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._interruption(
                        conn, UUID(replay["interruption_id"])
                    )
                    return self._interruption_result(row)

                attempt = self._locked_attempt(
                    conn, command.presentation_attempt_id
                )
                session = self._session(conn, attempt["presentation_session_id"])
                event = self._canonical_interrupt_event(
                    conn, session, command.interrupting_event_id
                )
                existing = self._interruption_for_attempt(
                    conn, command.presentation_attempt_id
                )
                if existing is not None:
                    if existing["interrupting_event_id"] != event["event_id"]:
                        fail(
                            "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                            "presentation attempt is already fenced by another canonical interruption",
                        )
                    if (
                        existing["cancellation_request_state"]
                        == "NOT_REQUIRED_TERMINAL"
                    ):
                        self._save_interrupt_operation(
                            conn, command, req, existing
                        )
                        return self._interruption_result(existing)
                    interruption = existing
                else:
                    if attempt["attempt_state"] == "SETTLED":
                        self._require_terminal_race_eligibility(
                            conn,
                            attempt=attempt,
                            session=session,
                            event=event,
                        )
                        interruption_id = self.ids.new()
                        now = self.clock.now()
                        conn.execute(
                            insert(schema.progressive_presentation_interruption).values(
                                interruption_id=interruption_id,
                                presentation_attempt_id=attempt[
                                    "presentation_attempt_id"
                                ],
                                presentation_session_id=session[
                                    "presentation_session_id"
                                ],
                                presentation_key=session["presentation_key"],
                                attempt_generation=int(
                                    attempt["attempt_generation"]
                                ),
                                presentation_transport_fence_scope_id=attempt[
                                    "presentation_transport_fence_scope_id"
                                ],
                                interrupting_event_id=event["event_id"],
                                interrupting_timeline_seq=int(
                                    event["timeline_seq"]
                                ),
                                interruption_key=self._interruption_key(
                                    attempt["presentation_attempt_id"],
                                    event["event_id"],
                                ),
                                cancellation_request_state="NOT_REQUIRED_TERMINAL",
                                interrupted_at=_aware_utc(event["recorded_at"]),
                                observed_at=now,
                            )
                        )
                        row = self._interruption(conn, interruption_id)
                        self._save_interrupt_operation(
                            conn, command, req, row
                        )
                        return self._interruption_result(row)

                    if attempt["attempt_state"] not in {"OPEN", "UNKNOWN"}:
                        fail(
                            "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                            "presentation attempt cannot accept a new canonical interruption from its current state",
                        )

                    interruption_id = self.ids.new()
                    now = self.clock.now()
                    conn.execute(
                        insert(schema.progressive_presentation_interruption).values(
                            interruption_id=interruption_id,
                            presentation_attempt_id=attempt[
                                "presentation_attempt_id"
                            ],
                            presentation_session_id=session[
                                "presentation_session_id"
                            ],
                            presentation_key=session["presentation_key"],
                            attempt_generation=int(
                                attempt["attempt_generation"]
                            ),
                            presentation_transport_fence_scope_id=attempt[
                                "presentation_transport_fence_scope_id"
                            ],
                            interrupting_event_id=event["event_id"],
                            interrupting_timeline_seq=int(event["timeline_seq"]),
                            interruption_key=self._interruption_key(
                                attempt["presentation_attempt_id"],
                                event["event_id"],
                            ),
                            cancellation_request_state="PENDING",
                            interrupted_at=_aware_utc(event["recorded_at"]),
                            observed_at=now,
                        )
                    )
                    interruption = self._interruption(conn, interruption_id)
        except IntegrityError as exc:
            with self.engine.connect() as conn:
                interruption = self._interruption_for_attempt(
                    conn, command.presentation_attempt_id
                )
                if (
                    interruption is None
                    or interruption["interrupting_event_id"]
                    != command.interrupting_event_id
                ):
                    raise DomainError(
                        "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                        "canonical interruption conflicted with durable state",
                    ) from exc
                if (
                    interruption["cancellation_request_state"]
                    == "NOT_REQUIRED_TERMINAL"
                ):
                    terminal_interruption_id = interruption["interruption_id"]
                else:
                    terminal_interruption_id = None
            if terminal_interruption_id is not None:
                with self.engine.begin() as conn:
                    replay = load_operation_receipt(
                        conn,
                        scope=_INTERRUPT_SCOPE,
                        operation_id=command.operation_id,
                        expected_request_digest=req,
                    )
                    if replay:
                        row = self._interruption(
                            conn, UUID(replay["interruption_id"])
                        )
                        return self._interruption_result(row)
                    row = self._interruption(conn, terminal_interruption_id)
                    if (
                        row["interrupting_event_id"]
                        != command.interrupting_event_id
                        or row["cancellation_request_state"]
                        != "NOT_REQUIRED_TERMINAL"
                    ):
                        fail(
                            "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                            "terminal interruption lineage changed before idempotent replay",
                        )
                    self._save_interrupt_operation(conn, command, req, row)
                    return self._interruption_result(row)

        request_state = interruption["cancellation_request_state"]
        if request_state != "REQUESTED":
            adapter = self._cancellation_adapter_or_none()
            acknowledged = False
            if adapter is not None:
                try:
                    acknowledged = (
                        adapter.request_presentation_cancellation(
                            presentation_key=interruption["presentation_key"],
                            attempt_generation=int(
                                interruption["attempt_generation"]
                            ),
                            presentation_transport_fence_scope_id=interruption[
                                "presentation_transport_fence_scope_id"
                            ],
                            presentation_session_id=interruption[
                                "presentation_session_id"
                            ],
                            presentation_attempt_id=interruption[
                                "presentation_attempt_id"
                            ],
                            interruption_key=interruption["interruption_key"],
                            interrupting_event_id=interruption[
                                "interrupting_event_id"
                            ],
                        )
                        is True
                    )
                except Exception:
                    acknowledged = False
            request_state = "REQUESTED" if acknowledged else "UNKNOWN"

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_INTERRUPT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._interruption(
                    conn, UUID(replay["interruption_id"])
                )
                return self._interruption_result(row)

            current_attempt = self._locked_attempt(
                conn, command.presentation_attempt_id
            )
            current = self._interruption_for_attempt(
                conn, command.presentation_attempt_id
            )
            if (
                current is None
                or current["interrupting_event_id"]
                != command.interrupting_event_id
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                    "canonical interruption lineage changed before cancellation state could be recorded",
                )
            if (
                current["attempt_generation"]
                != current_attempt["attempt_generation"]
                or current["presentation_transport_fence_scope_id"]
                != current_attempt["presentation_transport_fence_scope_id"]
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                    "canonical interruption no longer binds the exact presentation generation",
                )
            if current["cancellation_request_state"] not in {
                "REQUESTED",
                "NOT_REQUIRED_TERMINAL",
            }:
                values = {"cancellation_request_state": request_state}
                if request_state == "REQUESTED":
                    values["cancellation_requested_at"] = self.clock.now()
                conn.execute(
                    update(schema.progressive_presentation_interruption)
                    .where(
                        schema.progressive_presentation_interruption.c.interruption_id
                        == current["interruption_id"]
                    )
                    .values(**values)
                )
            row = self._interruption(conn, current["interruption_id"])
            self._save_interrupt_operation(conn, command, req, row)
            return self._interruption_result(row)

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
        if _aware_utc(event["recorded_at"]) > _aware_utc(terminal["observed_at"]):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                "counterpart input was canonically admitted only after terminal presentation status was observed",
            )

    def _save_interrupt_operation(self, conn, command, req, row) -> None:
        save_operation_receipt(
            conn,
            scope=_INTERRUPT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="ProgressivePresentationInterruption",
            result_ref=row["interruption_id"],
            result_json={"interruption_id": str(row["interruption_id"])},
            committed_at=self.clock.now(),
        )


__all__ = ["ProgressivePresentationServices"]
