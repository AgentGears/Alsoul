from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from alsoul.domain.progressive_presentation import (
    OpenProgressivePresentationCommand,
    ProgressivePresentationSessionResult,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.progressive_presentation_v10 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV10,
)


_OPEN_SCOPE = "OpenProgressivePresentation"


class ProgressivePresentationServices(ProgressivePresentationServicesV10):
    """Current F6.A service with exact session-open operation replay typing.

    Operation receipts store UUIDs as canonical JSON strings. The current boundary
    converts the durable presentation-session reference back to UUID before querying
    the UUID-typed session key, preserving exact idempotent replay on every backend.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_OPEN_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._session(conn, UUID(replay["presentation_session_id"]))
                self._require_session_frontier(conn, row)
                return self._session_result(conn, row)
        return super().open_session(command)


__all__ = ["ProgressivePresentationServices"]
