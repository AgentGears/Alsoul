from __future__ import annotations

from dataclasses import asdict
from uuid import UUID, uuid5

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    CommitProgressivePresentationHistoryCommand,
    DispatchProgressivePresentationFrameCommand,
    FenceProgressivePresentationAttemptCommand,
    InterruptProgressivePresentationCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION,
    ProgressivePresentationAttemptResult,
    ProgressivePresentationFrameDispatchResult,
    ProgressivePresentationHistoryResult,
    ProgressivePresentationInterruptionResult,
    ProgressivePresentationSessionResult,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.progressive_presentation import _aware_utc
from alsoul.services.progressive_presentation_v7 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV7,
)
from alsoul.storage import schema


_FENCE_SCOPE = "FenceProgressivePresentationAttempt"
_DISPATCH_SCOPE = "DispatchProgressivePresentationFrame"
_INTERRUPT_SCOPE = "InterruptProgressivePresentationAttempt"
_HISTORY_SCOPE = "CommitProgressivePresentationHistory"
_INTERRUPTION_NAMESPACE = UUID("f42496d8-357f-4e81-87a9-b35abdd5d971")


class ProgressivePresentationServices(ProgressivePresentationServicesV7):
    """Current F6.A core with canonical interruption and exact Timeline truth.

    A counterpart interruption becomes authoritative only after the input already exists
    as a canonical counterpart Timeline event. Interruption and frame authorization use
    the same durable attempt write fence, so a frame is either authorized before the
    interrupt fence (and then reconciled as in-flight) or rejected after it. An
    interrupted session can never open a later generation for its unpresented remainder.

    Canonical ``COMPANION_PRESENTED_OUTPUT`` history is committed only from terminal
    presentation evidence. Full presentation records the complete CompanionOutput;
    interrupted partial presentation records only the authoritative contiguous prefix;
    zero presented frames record no companion Timeline event.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        with self.engine.connect() as conn:
            existing_session = conn.execute(
                select(schema.progressive_presentation_session.c.presentation_session_id)
                .where(
                    schema.progressive_presentation_session.c.companion_output_id
                    == command.companion_output_id
                )
                .limit(1)
            ).scalar_one_or_none()
            existing_history = conn.execute(
                select(schema.interaction_event.c.event_id)
                .where(
                    schema.interaction_event.c.companion_output_id
                    == command.companion_output_id,
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT",
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing_session is None and existing_history is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_OUTPUT_ALREADY_PRESENTED",
                    "already-presented CompanionOutput cannot enter a new progressive presentation session",
                )
        return super().open_session(command)

    def fence_attempt(
        self, command: FenceProgressivePresentationAttemptCommand
    ) -> ProgressivePresentationAttemptResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_FENCE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._attempt(conn, UUID(replay["presentation_attempt_id"]))
                    return self._attempt_result(row)

                self._session(conn, command.presentation_session_id)
                latest = conn.execute(
                    select(schema.progressive_presentation_attempt)
                    .where(
                        schema.progressive_presentation_attempt.c.presentation_session_id
                        == command.presentation_session_id
                    )
                    .order_by(
                        schema.progressive_presentation_attempt.c.attempt_generation.desc()
                    )
                    .limit(1)
                ).mappings().one_or_none()

                if latest is not None:
                    latest = self._locked_attempt(
                        conn, latest["presentation_attempt_id"]
                    )

                interrupted = conn.execute(
                    select(schema.progressive_presentation_interruption.c.interruption_id)
                    .where(
                        schema.progressive_presentation_interruption.c.presentation_session_id
                        == command.presentation_session_id
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if interrupted is not None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_INTERRUPTED_REMAINDER_REQUIRES_NEW_OUTPUT",
                        "an interrupted presentation session cannot automatically resume its unpresented remainder",
                    )

                committed_history = conn.execute(
                    select(
                        schema.progressive_presentation_timeline_lineage.c.interaction_event_id
                    ).where(
                        schema.progressive_presentation_timeline_lineage.c.presentation_session_id
                        == command.presentation_session_id
                    )
                ).scalar_one_or_none()
                if committed_history is not None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_HISTORY_ALREADY_COMMITTED",
                        "presentation session with canonical Timeline history cannot open another generation",
                    )

                generation = 1
                if latest is not None:
                    generation = int(latest["attempt_generation"]) + 1
                    if latest["attempt_state"] == "OPEN":
                        terminal_nonacceptance = conn.execute(
                            select(
                                schema.progressive_presentation_frame_transport.c.frame_ordinal
                            ).where(
                                schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                                == latest["presentation_attempt_id"],
                                schema.progressive_presentation_frame_transport.c.sink_acceptance_state
                                == "NOT_ACCEPTED",
                            )
                        ).first()
                        if terminal_nonacceptance is None:
                            fail(
                                "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLEMENT_REQUIRED",
                                "a later presentation generation requires terminal settlement of the prior generation",
                            )
                        settled = conn.execute(
                            update(schema.progressive_presentation_attempt)
                            .where(
                                schema.progressive_presentation_attempt.c.presentation_attempt_id
                                == latest["presentation_attempt_id"],
                                schema.progressive_presentation_attempt.c.attempt_state
                                == "OPEN",
                            )
                            .values(attempt_state="SETTLED")
                        )
                        if settled.rowcount != 1:
                            fail(
                                "PROGRESSIVE_PRESENTATION_ATTEMPT_CONFLICT",
                                "presentation attempt settlement changed concurrently",
                            )
                    elif latest["attempt_state"] != "SETTLED":
                        fail(
                            "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLEMENT_REQUIRED",
                            "a later presentation generation requires terminal settlement of the prior generation",
                        )

                attempt_id = self.ids.new()
                fence_scope_id = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.progressive_presentation_attempt).values(
                        presentation_attempt_id=attempt_id,
                        presentation_session_id=command.presentation_session_id,
                        attempt_generation=generation,
                        presentation_transport_fence_scope_id=fence_scope_id,
                        attempt_state="OPEN",
                        opened_at=now,
                    )
                )
                save_operation_receipt(
                    conn,
                    scope=_FENCE_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="ProgressivePresentationAttempt",
                    result_ref=attempt_id,
                    result_json={
                        "presentation_attempt_id": str(attempt_id),
                        "presentation_session_id": str(command.presentation_session_id),
                        "attempt_generation": generation,
                        "presentation_transport_fence_scope_id": str(fence_scope_id),
                    },
                    committed_at=now,
                )
                return ProgressivePresentationAttemptResult(
                    presentation_attempt_id=attempt_id,
                    presentation_session_id=command.presentation_session_id,
                    attempt_generation=generation,
                    presentation_transport_fence_scope_id=fence_scope_id,
                    state="OPEN",
                )
        except IntegrityError as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_ATTEMPT_CONFLICT",
                "presentation attempt generation changed concurrently",
            ) from exc

    def dispatch_frame(
        self, command: DispatchProgressivePresentationFrameCommand
    ) -> ProgressivePresentationFrameDispatchResult:
        self._require_adapter()
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._transport(
                    conn,
                    UUID(replay["presentation_attempt_id"]),
                    int(replay["frame_ordinal"]),
                )
                return self._dispatch_result(row)

            attempt = self._locked_attempt(conn, command.presentation_attempt_id)
            session = self._session(conn, attempt["presentation_session_id"])
            self._require_generic_progressive_eligibility(
                conn, session["companion_output_id"]
            )
            if attempt["attempt_state"] != "OPEN":
                fail(
                    "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_OPEN",
                    "only an open presentation attempt may dispatch a frame",
                )
            frame = self._frame(
                conn, attempt["presentation_session_id"], command.frame_ordinal
            )
            already_presented = self._evidence_for_frame(
                conn, attempt["presentation_session_id"], command.frame_ordinal
            )
            if already_presented is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_FRAME_ALREADY_PRESENTED",
                    "authoritatively presented frame cannot be dispatched again",
                )
            if command.frame_ordinal > 1:
                previous = self._evidence_for_frame(
                    conn,
                    attempt["presentation_session_id"],
                    command.frame_ordinal - 1,
                )
                if previous is None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_FRAME_ORDER_INVALID",
                        "next frame cannot dispatch before the prior frame is authoritatively presented",
                    )

            existing = conn.execute(
                select(schema.progressive_presentation_frame_transport).where(
                    schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                    == command.presentation_attempt_id,
                    schema.progressive_presentation_frame_transport.c.frame_ordinal
                    == command.frame_ordinal,
                )
            ).mappings().one_or_none()
            if existing is not None:
                return self._dispatch_result(existing)

            interrupted = conn.execute(
                select(schema.progressive_presentation_interruption.c.interruption_id)
                .where(
                    schema.progressive_presentation_interruption.c.presentation_attempt_id
                    == command.presentation_attempt_id
                )
            ).scalar_one_or_none()
            if interrupted is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_INTERRUPTED",
                    "canonical counterpart interruption blocks authorization of new presentation frames",
                )

            dispatched_at = self.clock.now()
            conn.execute(
                insert(schema.progressive_presentation_frame_transport).values(
                    presentation_attempt_id=command.presentation_attempt_id,
                    presentation_session_id=attempt["presentation_session_id"],
                    frame_ordinal=command.frame_ordinal,
                    frame_digest=frame["content_digest"],
                    sink_acceptance_state="UNKNOWN",
                    dispatched_at=dispatched_at,
                )
            )
            save_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ProgressivePresentationFrameTransport",
                result_ref=command.presentation_attempt_id,
                result_json={
                    "presentation_attempt_id": str(command.presentation_attempt_id),
                    "presentation_session_id": str(attempt["presentation_session_id"]),
                    "frame_ordinal": command.frame_ordinal,
                },
                committed_at=dispatched_at,
            )

        try:
            status = self.adapter.dispatch_frame(
                presentation_key=session["presentation_key"],
                attempt_generation=int(attempt["attempt_generation"]),
                presentation_transport_fence_scope_id=attempt[
                    "presentation_transport_fence_scope_id"
                ],
                presentation_session_id=session["presentation_session_id"],
                presentation_attempt_id=attempt["presentation_attempt_id"],
                frame_ordinal=command.frame_ordinal,
                frame_digest=frame["content_digest"],
                content_text=frame["content_text"],
            )
        except (AdapterOutcomeUnknown, AdapterRejected) as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_OUTCOME_UNKNOWN",
                "frame transport may have crossed the presentation boundary; content-free reconciliation is required",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_OUTCOME_UNKNOWN",
                "frame transport became uncertain after its durable dispatch fence",
            ) from exc

        self._validate_transport_status(
            status=status,
            session=session,
            attempt=attempt,
            frame=frame,
        )
        if status.acceptance_state == "UNKNOWN":
            fail(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_OUTCOME_UNKNOWN",
                "frame transport did not establish terminal transport acceptance",
            )

        with self.engine.begin() as conn:
            accepted_at = (
                _aware_utc(status.accepted_at)
                if status.acceptance_state == "ACCEPTED"
                else None
            )
            conn.execute(
                update(schema.progressive_presentation_frame_transport)
                .where(
                    schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                    == command.presentation_attempt_id,
                    schema.progressive_presentation_frame_transport.c.frame_ordinal
                    == command.frame_ordinal,
                    schema.progressive_presentation_frame_transport.c.sink_acceptance_state
                    == "UNKNOWN",
                )
                .values(
                    sink_acceptance_state=status.acceptance_state,
                    acceptance_ref=status.acceptance_ref,
                    accepted_at=accepted_at,
                )
            )
            row = self._transport(
                conn, command.presentation_attempt_id, command.frame_ordinal
            )
            return self._dispatch_result(row)

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

                attempt = self._locked_attempt(conn, command.presentation_attempt_id)
                session = self._session(conn, attempt["presentation_session_id"])
                event = self._canonical_interrupt_event(
                    conn, session, command.interrupting_event_id
                )
                existing = self._interruption_for_attempt(
                    conn, command.presentation_attempt_id
                )
                if existing is not None:
                    if existing["interrupting_event_id"] != command.interrupting_event_id:
                        fail(
                            "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                            "presentation attempt is already fenced by another canonical interruption",
                        )
                    interruption = existing
                else:
                    if attempt["attempt_state"] == "SETTLED":
                        fail(
                            "PROGRESSIVE_PRESENTATION_INTERRUPTION_TOO_LATE",
                            "terminally settled presentation attempt cannot be newly interrupted",
                        )
                    interruption_id = self.ids.new()
                    now = self.clock.now()
                    conn.execute(
                        insert(schema.progressive_presentation_interruption).values(
                            interruption_id=interruption_id,
                            presentation_attempt_id=attempt["presentation_attempt_id"],
                            presentation_session_id=session["presentation_session_id"],
                            presentation_key=session["presentation_key"],
                            attempt_generation=int(attempt["attempt_generation"]),
                            presentation_transport_fence_scope_id=attempt[
                                "presentation_transport_fence_scope_id"
                            ],
                            interrupting_event_id=event["event_id"],
                            interrupting_timeline_seq=int(event["timeline_seq"]),
                            interruption_key=self._interruption_key(
                                attempt["presentation_attempt_id"], event["event_id"]
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

        request_state = interruption["cancellation_request_state"]
        if request_state != "REQUESTED":
            adapter = self._cancellation_adapter_or_none()
            acknowledged = False
            if adapter is not None:
                try:
                    acknowledged = (
                        adapter.request_presentation_cancellation(
                            presentation_key=interruption["presentation_key"],
                            attempt_generation=int(interruption["attempt_generation"]),
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
            current_attempt = self._locked_attempt(
                conn, command.presentation_attempt_id
            )
            current = self._interruption_for_attempt(
                conn, command.presentation_attempt_id
            )
            if current is None or current["interrupting_event_id"] != command.interrupting_event_id:
                fail(
                    "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                    "canonical interruption lineage changed before cancellation state could be recorded",
                )
            if (
                current["attempt_generation"] != current_attempt["attempt_generation"]
                or current["presentation_transport_fence_scope_id"]
                != current_attempt["presentation_transport_fence_scope_id"]
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_INTERRUPTION_CONFLICT",
                    "canonical interruption no longer binds the exact presentation generation",
                )
            if current["cancellation_request_state"] != "REQUESTED":
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
            return self._interruption_result(row)

    def commit_presentation_history(
        self, command: CommitProgressivePresentationHistoryCommand
    ) -> ProgressivePresentationHistoryResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_HISTORY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._history_result_from_receipt(replay, idempotent=True)

            attempt = self._locked_attempt(conn, command.presentation_attempt_id)
            if attempt["attempt_state"] != "SETTLED":
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_SETTLEMENT_REQUIRED",
                    "canonical presentation history requires a terminally settled generation",
                )
            session = self._session(conn, attempt["presentation_session_id"])
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
                    "PROGRESSIVE_PRESENTATION_HISTORY_STALE_GENERATION",
                    "canonical presentation history must use the latest presentation generation",
                )

            status = self._latest_terminal_status(
                conn, attempt["presentation_attempt_id"]
            )
            if status is None:
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_TERMINAL_PROOF_REQUIRED",
                    "canonical presentation history requires terminal presentation-status evidence",
                )
            extent = int(status["last_authoritatively_presented_frame"])
            known_extent = self._contiguous_presented_extent(
                conn, session["presentation_session_id"]
            )
            if extent != known_extent:
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_EVIDENCE_MISMATCH",
                    "terminal status does not match authoritative durable presentation extent",
                )
            frame_count = int(
                conn.execute(
                    select(func.count())
                    .select_from(schema.progressive_presentation_frame)
                    .where(
                        schema.progressive_presentation_frame.c.presentation_session_id
                        == session["presentation_session_id"]
                    )
                ).scalar_one()
            )
            interruption = conn.execute(
                select(schema.progressive_presentation_interruption)
                .where(
                    schema.progressive_presentation_interruption.c.presentation_session_id
                    == session["presentation_session_id"]
                )
                .order_by(
                    schema.progressive_presentation_interruption.c.observed_at.desc()
                )
                .limit(1)
            ).mappings().one_or_none()
            if extent < frame_count and (
                interruption is None
                or interruption["presentation_attempt_id"]
                != attempt["presentation_attempt_id"]
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_PARTIAL_REQUIRES_INTERRUPTION",
                    "partial canonical presentation history requires the exact canonical interruption that finalized the generation",
                )

            existing_lineage = conn.execute(
                select(schema.progressive_presentation_timeline_lineage).where(
                    schema.progressive_presentation_timeline_lineage.c.presentation_session_id
                    == session["presentation_session_id"]
                )
            ).mappings().one_or_none()
            if existing_lineage is not None:
                self._require_exact_history_lineage(
                    existing_lineage,
                    attempt=attempt,
                    status=status,
                    extent=extent,
                )
                event = conn.execute(
                    select(schema.interaction_event).where(
                        schema.interaction_event.c.event_id
                        == existing_lineage["interaction_event_id"]
                    )
                ).mappings().one()
                result = ProgressivePresentationHistoryResult(
                    presentation_session_id=session["presentation_session_id"],
                    presentation_attempt_id=attempt["presentation_attempt_id"],
                    interaction_event_id=event["event_id"],
                    timeline_seq=int(event["timeline_seq"]),
                    last_presented_frame=extent,
                    presented_content_digest=existing_lineage[
                        "presented_content_digest"
                    ],
                    idempotent_replay=True,
                )
                self._save_history_operation(conn, command, req, result)
                return result

            if extent == 0:
                if (
                    interruption is None
                    or interruption["presentation_attempt_id"]
                    != attempt["presentation_attempt_id"]
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_HISTORY_ZERO_REQUIRES_INTERRUPTION",
                        "zero-frame finalization requires a canonical interruption",
                    )
                result = ProgressivePresentationHistoryResult(
                    presentation_session_id=session["presentation_session_id"],
                    presentation_attempt_id=attempt["presentation_attempt_id"],
                    interaction_event_id=None,
                    timeline_seq=None,
                    last_presented_frame=0,
                    presented_content_digest=None,
                )
                self._save_history_operation(conn, command, req, result)
                return result

            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == session["companion_output_id"]
                )
            ).mappings().one()
            prior_event = conn.execute(
                select(schema.interaction_event.c.event_id)
                .where(
                    schema.interaction_event.c.companion_output_id
                    == session["companion_output_id"],
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT",
                )
                .limit(1)
            ).scalar_one_or_none()
            if prior_event is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_CONFLICT",
                    "CompanionOutput already has canonical presentation history outside this progressive session",
                )

            frames = conn.execute(
                select(schema.progressive_presentation_frame)
                .where(
                    schema.progressive_presentation_frame.c.presentation_session_id
                    == session["presentation_session_id"],
                    schema.progressive_presentation_frame.c.frame_ordinal <= extent,
                )
                .order_by(schema.progressive_presentation_frame.c.frame_ordinal)
            ).mappings().all()
            evidence = conn.execute(
                select(schema.progressive_presentation_frame_evidence)
                .where(
                    schema.progressive_presentation_frame_evidence.c.presentation_session_id
                    == session["presentation_session_id"],
                    schema.progressive_presentation_frame_evidence.c.frame_ordinal
                    <= extent,
                )
                .order_by(
                    schema.progressive_presentation_frame_evidence.c.frame_ordinal
                )
            ).mappings().all()
            expected_ordinals = list(range(1, extent + 1))
            if (
                [int(row["frame_ordinal"]) for row in frames] != expected_ordinals
                or [int(row["frame_ordinal"]) for row in evidence]
                != expected_ordinals
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_EVIDENCE_GAP",
                    "canonical presentation history requires an authoritative contiguous presented prefix",
                )
            content_text = "".join(row["content_text"] for row in frames)
            content_digest = sha256_text(content_text)
            if extent == frame_count and (
                content_text != output["content_text"]
                or content_digest != output["content_digest"]
            ):
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_CONTENT_MISMATCH",
                    "full progressive presentation does not reconstruct the canonical CompanionOutput",
                )

            target = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.output_target_id == output["output_target_id"]
                )
            ).mappings().one()
            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == output["relationship_id"]
                )
            ).mappings().one()
            next_seq = int(timeline["last_timeline_seq"]) + 1
            event_id = self.ids.new()
            recorded_at = self.clock.now()
            occurred_at = _aware_utc(evidence[-1]["presented_at"])
            conn.execute(
                insert(schema.interaction_event).values(
                    event_id=event_id,
                    relationship_id=output["relationship_id"],
                    timeline_seq=next_seq,
                    actor_kind="COMPANION",
                    actor_ref=output["companion_person_id"],
                    event_kind="COMPANION_PRESENTED_OUTPUT",
                    content_text=content_text,
                    occurred_at=occurred_at,
                    recorded_at=recorded_at,
                    surface_binding_id=session["surface_binding_id"],
                    channel_binding_id=session["channel_binding_id"],
                    companion_output_id=session["companion_output_id"],
                    reply_to_event_id=target["target_ref"],
                )
            )
            changed = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == output["relationship_id"],
                    schema.relationship_timeline_head.c.last_timeline_seq
                    == timeline["last_timeline_seq"],
                )
                .values(last_timeline_seq=next_seq)
            )
            if changed.rowcount != 1:
                fail(
                    "TIMELINE_SEQUENCE_CONFLICT",
                    "relationship Timeline advanced concurrently",
                )
            conn.execute(
                insert(schema.progressive_presentation_timeline_lineage).values(
                    interaction_event_id=event_id,
                    companion_output_id=session["companion_output_id"],
                    presentation_session_id=session["presentation_session_id"],
                    terminal_presentation_attempt_id=attempt[
                        "presentation_attempt_id"
                    ],
                    terminal_status_evidence_id=status[
                        "presentation_status_evidence_id"
                    ],
                    interrupting_event_id=(
                        interruption["interrupting_event_id"]
                        if interruption is not None
                        else None
                    ),
                    first_presented_frame=1,
                    last_presented_frame=extent,
                    frame_contract_version=session["frame_contract_version"],
                    presented_content_digest=content_digest,
                    committed_at=recorded_at,
                )
            )
            result = ProgressivePresentationHistoryResult(
                presentation_session_id=session["presentation_session_id"],
                presentation_attempt_id=attempt["presentation_attempt_id"],
                interaction_event_id=event_id,
                timeline_seq=next_seq,
                last_presented_frame=extent,
                presented_content_digest=content_digest,
            )
            self._save_history_operation(conn, command, req, result)
            return result

    def _canonical_interrupt_event(self, conn, session, event_id: UUID):
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == event_id
            )
        ).mappings().one_or_none()
        if event is None:
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_EVENT_INVALID",
                "interrupting counterpart input is not durably present in the canonical Timeline",
            )
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == session["relationship_id"]
            )
        ).mappings().one()
        timeline_head = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id
                == session["relationship_id"]
            )
        ).mappings().one()
        if (
            event["relationship_id"] != session["relationship_id"]
            or event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
            or event["ingress_idempotency_key"] is None
            or event["surface_binding_id"] is None
            or event["channel_binding_id"] is None
            or int(event["timeline_seq"]) > int(timeline_head["last_timeline_seq"])
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_EVENT_INVALID",
                "interruption requires a canonical counterpart input admitted through the normal ingress boundary",
            )
        return event

    def _cancellation_adapter_or_none(self):
        adapter = self.adapter
        if (
            adapter is None
            or getattr(adapter, "cancellation_contract_version", None)
            != PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION
            or not callable(getattr(adapter, "request_presentation_cancellation", None))
        ):
            return None
        return adapter

    @staticmethod
    def _interruption_for_attempt(conn, attempt_id: UUID):
        return conn.execute(
            select(schema.progressive_presentation_interruption).where(
                schema.progressive_presentation_interruption.c.presentation_attempt_id
                == attempt_id
            )
        ).mappings().one_or_none()

    @staticmethod
    def _interruption(conn, interruption_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_interruption).where(
                schema.progressive_presentation_interruption.c.interruption_id
                == interruption_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_NOT_FOUND",
                "durable progressive presentation interruption does not exist",
            )
        return row

    @staticmethod
    def _interruption_result(row) -> ProgressivePresentationInterruptionResult:
        return ProgressivePresentationInterruptionResult(
            interruption_id=row["interruption_id"],
            presentation_attempt_id=row["presentation_attempt_id"],
            presentation_session_id=row["presentation_session_id"],
            interrupting_event_id=row["interrupting_event_id"],
            cancellation_request_state=row["cancellation_request_state"],
        )

    @staticmethod
    def _interruption_key(attempt_id: UUID, event_id: UUID) -> str:
        return str(uuid5(_INTERRUPTION_NAMESPACE, f"{attempt_id}:{event_id}"))

    @staticmethod
    def _require_exact_history_lineage(row, *, attempt, status, extent: int) -> None:
        if not (
            row["terminal_presentation_attempt_id"]
            == attempt["presentation_attempt_id"]
            and row["presentation_session_id"] == attempt["presentation_session_id"]
            and row["terminal_status_evidence_id"]
            == status["presentation_status_evidence_id"]
            and int(row["last_presented_frame"]) == extent
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_HISTORY_CONFLICT",
                "presentation session already has different canonical Timeline lineage",
            )

    def _save_history_operation(self, conn, command, req, result) -> None:
        save_operation_receipt(
            conn,
            scope=_HISTORY_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind=(
                "InteractionEvent"
                if result.interaction_event_id is not None
                else "ProgressivePresentationHistoryNoEvent"
            ),
            result_ref=(
                result.interaction_event_id
                if result.interaction_event_id is not None
                else result.presentation_session_id
            ),
            result_json={
                "presentation_session_id": str(result.presentation_session_id),
                "presentation_attempt_id": str(result.presentation_attempt_id),
                "interaction_event_id": (
                    str(result.interaction_event_id)
                    if result.interaction_event_id is not None
                    else None
                ),
                "timeline_seq": result.timeline_seq,
                "last_presented_frame": result.last_presented_frame,
                "presented_content_digest": result.presented_content_digest,
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _history_result_from_receipt(
        replay, *, idempotent: bool
    ) -> ProgressivePresentationHistoryResult:
        return ProgressivePresentationHistoryResult(
            presentation_session_id=UUID(replay["presentation_session_id"]),
            presentation_attempt_id=UUID(replay["presentation_attempt_id"]),
            interaction_event_id=(
                UUID(replay["interaction_event_id"])
                if replay.get("interaction_event_id")
                else None
            ),
            timeline_seq=(
                int(replay["timeline_seq"])
                if replay.get("timeline_seq") is not None
                else None
            ),
            last_presented_frame=int(replay["last_presented_frame"]),
            presented_content_digest=replay.get("presented_content_digest"),
            idempotent_replay=idempotent,
        )


__all__ = ["ProgressivePresentationServices"]
