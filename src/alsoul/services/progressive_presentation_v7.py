from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEPTION_KIND,
    ProgressivePresentationReceptionResult,
    RecordProgressivePresentationReceptionCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v6 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV6,
)
from alsoul.storage import schema


_RECEPTION_SCOPE = "RecordProgressivePresentationReception"


class ProgressivePresentationServices(ProgressivePresentationServicesV6):
    """Current F6.A core with one portable generation-settlement write fence.

    SQLite does not implement row-level ``SELECT ... FOR UPDATE`` locking. Receipt,
    reception, and terminal reconciliation therefore acquire a real write fence by
    issuing a semantic no-op update against the exact attempt row before their final
    state/evidence read. This serializes competing writers on SQLite and also locks the
    row on databases with row-level update locking.
    """

    def record_reception_receipt(
        self, command: RecordProgressivePresentationReceptionCommand
    ) -> ProgressivePresentationReceptionResult:
        req = request_digest(asdict(command))
        received_through = self._positive_frame_ordinal(command.received_through_frame)
        if command.reception_kind != PROGRESSIVE_PRESENTATION_RECEPTION_KIND:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_INVALID",
                "reception evidence uses an unsupported reception kind",
            )
        if (
            command.reception_contract_version
            != PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_INVALID",
                "reception evidence uses an unsupported contract version",
            )
        receipt_ref = _required_text(
            command.reception_receipt_ref,
            "PROGRESSIVE_PRESENTATION_RECEPTION_INVALID",
            "reception receipt reference must be non-empty",
        )
        received_at = _aware_utc(command.received_at)

        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECEPTION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._reception_evidence(
                    conn, UUID(replay["reception_evidence_id"])
                )
                return self._reception_result(row)

        adapter = self._require_reception_adapter()
        try:
            trusted = adapter.validate_reception_receipt(
                presentation_key=command.presentation_key,
                attempt_generation=command.attempt_generation,
                presentation_transport_fence_scope_id=(
                    command.presentation_transport_fence_scope_id
                ),
                presentation_session_id=command.presentation_session_id,
                presentation_attempt_id=command.presentation_attempt_id,
                received_through_frame=received_through,
                reception_receipt_ref=receipt_ref,
                received_at=received_at,
                reception_kind=command.reception_kind,
            )
        except Exception as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECEPTION_UNTRUSTED",
                "trusted first-party reception receipt validation failed",
            ) from exc
        if trusted is not True:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_UNTRUSTED",
                "reception receipt was not validated by the trusted first-party sink boundary",
            )

        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECEPTION_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._reception_evidence(
                        conn, UUID(replay["reception_evidence_id"])
                    )
                    return self._reception_result(row)

                attempt = self._locked_attempt(conn, command.presentation_attempt_id)
                self._validate_reception_lineage(conn, command, received_through)
                existing = self._reception_by_ref(
                    conn, command.presentation_key, receipt_ref
                )
                if existing is not None:
                    self._require_exact_reception(
                        existing,
                        command=command,
                        receipt_ref=receipt_ref,
                        received_at=received_at,
                    )
                    self._save_reception_operation(conn, command, req, existing)
                    return self._reception_result(existing)
                if attempt["attempt_state"] == "SETTLED":
                    fail(
                        "PROGRESSIVE_PRESENTATION_ATTEMPT_SETTLED",
                        "terminally settled presentation generation cannot admit new reception evidence",
                    )

                evidence_id = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.progressive_presentation_reception_evidence).values(
                        reception_evidence_id=evidence_id,
                        presentation_attempt_id=command.presentation_attempt_id,
                        presentation_session_id=command.presentation_session_id,
                        attempt_generation=command.attempt_generation,
                        presentation_transport_fence_scope_id=(
                            command.presentation_transport_fence_scope_id
                        ),
                        presentation_key=command.presentation_key,
                        received_through_frame=received_through,
                        reception_kind=command.reception_kind,
                        reception_receipt_ref=receipt_ref,
                        reception_contract_version=command.reception_contract_version,
                        received_at=received_at,
                        observed_at=now,
                    )
                )
                row = self._reception_evidence(conn, evidence_id)
                self._save_reception_operation(conn, command, req, row)
                return self._reception_result(row)
        except IntegrityError as exc:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECEPTION_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._reception_evidence(
                        conn, UUID(replay["reception_evidence_id"])
                    )
                    return self._reception_result(row)
                existing = self._reception_by_ref(
                    conn, command.presentation_key, receipt_ref
                )
                if existing is None:
                    raise DomainError(
                        "PROGRESSIVE_PRESENTATION_RECEPTION_CONFLICT",
                        "reception evidence conflicted with durable state",
                    ) from exc
                self._require_exact_reception(
                    existing,
                    command=command,
                    receipt_ref=receipt_ref,
                    received_at=received_at,
                )
                self._save_reception_operation(conn, command, req, existing)
                return self._reception_result(existing)

    @staticmethod
    def _locked_attempt(conn, attempt_id: UUID):
        fenced = conn.execute(
            update(schema.progressive_presentation_attempt)
            .where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt_id
            )
            .values(
                attempt_state=schema.progressive_presentation_attempt.c.attempt_state
            )
        )
        if fenced.rowcount != 1:
            fail(
                "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_FOUND",
                "progressive presentation attempt does not exist",
            )
        row = conn.execute(
            schema.progressive_presentation_attempt.select().where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt_id
            )
        ).mappings().one()
        return row


__all__ = ["ProgressivePresentationServices"]
