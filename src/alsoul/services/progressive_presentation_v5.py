from __future__ import annotations

from dataclasses import asdict

from alsoul.domain.errors import fail
from alsoul.domain.progressive_presentation import (
    ProgressivePresentationReceiptResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.progressive_presentation_v4 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV4,
)


_RECEIPT_SCOPE = "RecordProgressivePresentationReceipt"


class ProgressivePresentationServices(ProgressivePresentationServicesV4):
    """Current F6.A core with terminal-generation evidence fencing.

    A trusted terminal settlement proves that no additional frame beyond the settled
    extent can later become presented under that generation. Exact duplicate evidence
    that was already durable remains replayable, but a settled generation cannot admit
    new presentation evidence.
    """

    def record_presentation_receipt(
        self, command: RecordProgressivePresentationReceiptCommand
    ) -> ProgressivePresentationReceiptResult:
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECEIPT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return super().record_presentation_receipt(command)

            attempt = self._attempt(conn, command.presentation_attempt_id)
            if attempt["attempt_state"] == "SETTLED":
                existing = self._evidence_for_frame(
                    conn,
                    command.presentation_session_id,
                    command.frame_ordinal,
                )
                if (
                    existing is None
                    or existing["presentation_attempt_id"]
                    != command.presentation_attempt_id
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED",
                        "terminally settled presentation generation cannot admit new presentation evidence",
                    )

        return super().record_presentation_receipt(command)


__all__ = ["ProgressivePresentationServices"]
