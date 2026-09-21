from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    ProgressivePresentationReceiptResult,
    ProgressivePresentationReconciliationResult,
    ReconcileProgressivePresentationAttemptCommand,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v4 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV4,
)
from alsoul.storage import schema


_RECEIPT_SCOPE = "RecordProgressivePresentationReceipt"
_RECONCILE_SCOPE = "ReconcileProgressivePresentationAttempt"


class ProgressivePresentationServices(ProgressivePresentationServicesV4):
    """Current F6.A core with serialized terminal-generation evidence fencing.

    Receipt admission and terminal reconciliation lock the same durable attempt before
    their final state/evidence read. Whichever operation wins that fence determines the
    next valid state: a receipt committed first forces reconciliation to re-evaluate the
    now-larger durable extent, while a terminal settlement committed first prevents any
    new old-generation presentation evidence. Exact evidence already durable remains
    idempotently replayable.
    """

    def record_presentation_receipt(
        self, command: RecordProgressivePresentationReceiptCommand
    ) -> ProgressivePresentationReceiptResult:
        req = request_digest(asdict(command))
        if (
            command.presentation_receipt_contract_version
            != PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
                "presentation receipt contract version is unsupported",
            )
        receipt_ref = _required_text(
            command.presentation_receipt_ref,
            "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
            "presentation receipt reference must be non-empty",
        )
        presented_at = _aware_utc(command.presented_at)

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECEIPT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._receipt_evidence(
                    conn, UUID(replay["presentation_evidence_id"])
                )
                return self._receipt_result(row)

            _frame, existing = self._validate_receipt_context(
                conn,
                command=command,
                receipt_ref=receipt_ref,
                presented_at=presented_at,
                lock_attempt=False,
            )
            if existing is not None:
                self._save_receipt_operation(conn, command, req, existing)
                return self._receipt_result(existing)

        adapter = self._require_receipt_adapter()
        try:
            trusted = adapter.validate_presentation_receipt(
                presentation_key=command.presentation_key,
                attempt_generation=command.attempt_generation,
                presentation_transport_fence_scope_id=(
                    command.presentation_transport_fence_scope_id
                ),
                presentation_session_id=command.presentation_session_id,
                presentation_attempt_id=command.presentation_attempt_id,
                frame_ordinal=command.frame_ordinal,
                frame_digest=command.frame_digest,
                presentation_receipt_ref=receipt_ref,
                presented_at=presented_at,
            )
        except Exception as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED",
                "trusted first-party presentation receipt validation failed",
            ) from exc
        if trusted is not True:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED",
                "presentation receipt was not validated by the trusted first-party sink boundary",
            )

        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECEIPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._receipt_evidence(
                        conn, UUID(replay["presentation_evidence_id"])
                    )
                    return self._receipt_result(row)

                frame, existing = self._validate_receipt_context(
                    conn,
                    command=command,
                    receipt_ref=receipt_ref,
                    presented_at=presented_at,
                    lock_attempt=True,
                )
                if existing is not None:
                    self._save_receipt_operation(conn, command, req, existing)
                    return self._receipt_result(existing)

                evidence_id = self.ids.new()
                observed_at = self.clock.now()
                conn.execute(
                    insert(schema.progressive_presentation_frame_evidence).values(
                        presentation_evidence_id=evidence_id,
                        presentation_attempt_id=command.presentation_attempt_id,
                        presentation_session_id=command.presentation_session_id,
                        frame_ordinal=command.frame_ordinal,
                        presentation_key=command.presentation_key,
                        frame_digest=frame["content_digest"],
                        presentation_receipt_ref=receipt_ref,
                        presentation_receipt_contract_version=(
                            command.presentation_receipt_contract_version
                        ),
                        presented_at=presented_at,
                        observed_at=observed_at,
                    )
                )
                row = self._receipt_evidence(conn, evidence_id)
                self._save_receipt_operation(conn, command, req, row)
                return self._receipt_result(row)
        except IntegrityError as exc:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECEIPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._receipt_evidence(
                        conn, UUID(replay["presentation_evidence_id"])
                    )
                    return self._receipt_result(row)
                existing = self._evidence_for_frame(
                    conn,
                    command.presentation_session_id,
                    command.frame_ordinal,
                )
                if existing is None:
                    raise DomainError(
                        "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT",
                        "presentation evidence conflicted with durable state",
                    ) from exc
                self._require_exact_receipt(
                    existing,
                    command=command,
                    receipt_ref=receipt_ref,
                    presented_at=presented_at,
                )
                self._save_receipt_operation(conn, command, req, existing)
                return self._receipt_result(existing)

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
                row = self._status_evidence(conn, evidence_id)
                self._save_reconciliation_operation(conn, command, req, row)
                return self._reconciliation_result(row)
        except IntegrityError as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                "presentation reconciliation conflicted with durable state",
            ) from exc

    def _validate_receipt_context(
        self,
        conn,
        *,
        command: RecordProgressivePresentationReceiptCommand,
        receipt_ref: str,
        presented_at,
        lock_attempt: bool,
    ):
        session = self._session(conn, command.presentation_session_id)
        attempt = (
            self._locked_attempt(conn, command.presentation_attempt_id)
            if lock_attempt
            else self._attempt(conn, command.presentation_attempt_id)
        )
        if attempt["presentation_session_id"] != command.presentation_session_id:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID",
                "presentation receipt attempt belongs to another session",
            )
        frame = self._frame(
            conn, command.presentation_session_id, command.frame_ordinal
        )
        transport = self._transport(
            conn, command.presentation_attempt_id, command.frame_ordinal
        )
        if transport["presentation_session_id"] != command.presentation_session_id:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID",
                "presentation receipt transport belongs to another session",
            )
        if transport["sink_acceptance_state"] == "NOT_ACCEPTED":
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT",
                "terminal non-acceptance cannot be combined with presentation evidence",
            )
        if (
            command.presentation_key != session["presentation_key"]
            or command.attempt_generation != int(attempt["attempt_generation"])
            or command.presentation_transport_fence_scope_id
            != attempt["presentation_transport_fence_scope_id"]
            or command.frame_digest != frame["content_digest"]
            or transport["frame_digest"] != frame["content_digest"]
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID",
                "presentation receipt does not bind the exact session/generation/frame lineage",
            )

        existing = self._evidence_for_frame(
            conn, command.presentation_session_id, command.frame_ordinal
        )
        if existing is not None:
            self._require_exact_receipt(
                existing,
                command=command,
                receipt_ref=receipt_ref,
                presented_at=presented_at,
            )
            return frame, existing

        if attempt["attempt_state"] == "SETTLED":
            fail(
                "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED",
                "terminally settled presentation generation cannot admit new presentation evidence",
            )
        if command.frame_ordinal > 1:
            previous = self._evidence_for_frame(
                conn, command.presentation_session_id, command.frame_ordinal - 1
            )
            if previous is None:
                fail(
                    "PROGRESSIVE_PRESENTATION_RECEIPT_GAP",
                    "presentation evidence cannot create a non-contiguous presented prefix",
                )
        return frame, None

    @staticmethod
    def _require_exact_receipt(
        row,
        *,
        command: RecordProgressivePresentationReceiptCommand,
        receipt_ref: str,
        presented_at,
    ) -> None:
        if not (
            row["presentation_attempt_id"] == command.presentation_attempt_id
            and row["presentation_key"] == command.presentation_key
            and row["frame_digest"] == command.frame_digest
            and row["presentation_receipt_ref"] == receipt_ref
            and row["presentation_receipt_contract_version"]
            == command.presentation_receipt_contract_version
            and _aware_utc(row["presented_at"]) == presented_at
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT",
                "frame already has different authoritative presentation evidence",
            )

    @staticmethod
    def _receipt_evidence(conn, evidence_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_frame_evidence).where(
                schema.progressive_presentation_frame_evidence.c.presentation_evidence_id
                == evidence_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_NOT_FOUND",
                "durable presentation evidence does not exist",
            )
        return row

    def _save_receipt_operation(self, conn, command, req, row) -> None:
        save_operation_receipt(
            conn,
            scope=_RECEIPT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="ProgressivePresentationEvidence",
            result_ref=row["presentation_evidence_id"],
            result_json={
                "presentation_evidence_id": str(row["presentation_evidence_id"]),
                "presentation_session_id": str(row["presentation_session_id"]),
                "frame_ordinal": int(row["frame_ordinal"]),
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _locked_attempt(conn, attempt_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_attempt)
            .where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt_id
            )
            .with_for_update()
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_FOUND",
                "progressive presentation attempt does not exist",
            )
        return row


__all__ = ["ProgressivePresentationServices"]
