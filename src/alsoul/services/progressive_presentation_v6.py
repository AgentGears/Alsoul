from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    ProgressivePresentationReceiptResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v5 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV5,
)
from alsoul.storage import schema


_RECEIPT_SCOPE = "RecordProgressivePresentationReceipt"


class ProgressivePresentationServices(ProgressivePresentationServicesV5):
    """Current F6.A receipt boundary with durable replay and terminal fencing.

    Durable evidence already admitted may replay without consulting the sink, but the
    replay request must still bind the exact durable attempt generation and transport
    fence. A genuinely new receipt, including one with nonexistent caller-provided
    lineage, must first pass the trusted first-party receipt validator; final evidence
    admission is then serialized against terminal reconciliation by the attempt fence.
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

            existing = self._evidence_for_frame(
                conn,
                command.presentation_session_id,
                command.frame_ordinal,
            )
            if existing is not None:
                self._require_exact_receipt(
                    existing,
                    command=command,
                    receipt_ref=receipt_ref,
                    presented_at=presented_at,
                )
                attempt = self._attempt(conn, existing["presentation_attempt_id"])
                if (
                    command.attempt_generation != int(attempt["attempt_generation"])
                    or command.presentation_transport_fence_scope_id
                    != attempt["presentation_transport_fence_scope_id"]
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID",
                        "durable presentation receipt replay does not bind the exact attempt generation/fence",
                    )
                self._save_receipt_operation(conn, command, req, existing)
                return self._receipt_result(existing)

            attempt = conn.execute(
                select(schema.progressive_presentation_attempt).where(
                    schema.progressive_presentation_attempt.c.presentation_attempt_id
                    == command.presentation_attempt_id
                )
            ).mappings().one_or_none()
            if attempt is not None and attempt["attempt_state"] == "SETTLED":
                fail(
                    "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED",
                    "terminally settled presentation generation cannot admit new presentation evidence",
                )

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
                attempt = self._attempt(conn, existing["presentation_attempt_id"])
                if (
                    command.attempt_generation != int(attempt["attempt_generation"])
                    or command.presentation_transport_fence_scope_id
                    != attempt["presentation_transport_fence_scope_id"]
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECEIPT_LINEAGE_INVALID",
                        "durable presentation receipt replay does not bind the exact attempt generation/fence",
                    )
                self._save_receipt_operation(conn, command, req, existing)
                return self._receipt_result(existing)


__all__ = ["ProgressivePresentationServices"]
