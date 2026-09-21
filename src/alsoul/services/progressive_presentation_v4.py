from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEPTION_KIND,
    PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION,
    ProgressivePresentationReceptionResult,
    ProgressivePresentationReconciliationResult,
    ProgressivePresentationReconciliationStatus,
    ReconcileProgressivePresentationAttemptCommand,
    RecordProgressivePresentationReceptionCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v3 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV3,
)
from alsoul.storage import schema


_RECEPTION_SCOPE = "RecordProgressivePresentationReception"
_RECONCILE_SCOPE = "ReconcileProgressivePresentationAttempt"


class ProgressivePresentationServices(ProgressivePresentationServicesV3):
    """Current F6.A core with reception evidence and content-free reconciliation.

    Reception evidence is stronger than presentation evidence but never implies human
    attention or understanding. Reconciliation may settle an uncertain generation only
    against presentation/reception evidence that Alsoul already durably knows; a status
    lookup cannot manufacture a missing presented prefix. Unknown status stays unknown
    and blocks unsafe payload replay.
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

            self._validate_reception_lineage(conn, command, received_through)
            existing = self._reception_by_ref(conn, command.presentation_key, receipt_ref)
            if existing is not None:
                self._require_exact_reception(
                    existing,
                    command=command,
                    receipt_ref=receipt_ref,
                    received_at=received_at,
                )
                self._save_reception_operation(conn, command, req, existing)
                return self._reception_result(existing)

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

                current_attempt = self._attempt(conn, command.presentation_attempt_id)
                current_session = self._session(
                    conn, current_attempt["presentation_session_id"]
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

    def _validate_reception_lineage(
        self,
        conn,
        command: RecordProgressivePresentationReceptionCommand,
        received_through: int,
    ) -> None:
        session = self._session(conn, command.presentation_session_id)
        attempt = self._attempt(conn, command.presentation_attempt_id)
        if (
            attempt["presentation_session_id"] != command.presentation_session_id
            or session["presentation_key"] != command.presentation_key
            or int(attempt["attempt_generation"]) != command.attempt_generation
            or attempt["presentation_transport_fence_scope_id"]
            != command.presentation_transport_fence_scope_id
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_LINEAGE_INVALID",
                "reception evidence does not bind the exact presentation lineage",
            )
        self._frame(conn, command.presentation_session_id, received_through)
        presented_through = self._contiguous_presented_extent(
            conn, command.presentation_session_id
        )
        if received_through > presented_through:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_EXCEEDS_PRESENTED_EXTENT",
                "reception evidence cannot exceed authoritative presented extent",
            )

    def _validate_reconciliation_status(
        self,
        status: Any,
        *,
        session,
        attempt,
        known_presented: int,
        known_received: int,
    ) -> None:
        if not isinstance(status, ProgressivePresentationReconciliationStatus):
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                "presentation status material is outside the trusted reconciliation contract",
            )
        status_ref = _required_text(
            status.status_ref,
            "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
            "presentation status reference must be non-empty",
        )
        if status_ref != status.status_ref:
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                "presentation status reference must already be canonical",
            )
        for value in (
            status.last_authoritatively_presented_frame,
            status.last_authoritatively_received_frame,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                fail(
                    "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                    "presentation status extents must be non-negative integers",
                )
        if (
            status.status_contract_version
            != PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION
            or status.presentation_key != session["presentation_key"]
            or status.presentation_session_id != session["presentation_session_id"]
            or status.presentation_attempt_id != attempt["presentation_attempt_id"]
            or status.attempt_generation != int(attempt["attempt_generation"])
            or status.presentation_transport_fence_scope_id
            != attempt["presentation_transport_fence_scope_id"]
            or status.settlement_state not in {
                "TERMINAL",
                "UNKNOWN_PRESENTATION_EXTENT",
            }
            or status.last_authoritatively_received_frame
            > status.last_authoritatively_presented_frame
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                "presentation status does not match exact fenced generation lineage",
            )
        if (
            status.last_authoritatively_presented_frame != known_presented
            or status.last_authoritatively_received_frame != known_received
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_EVIDENCE_INCOMPLETE",
                "content-free status cannot manufacture or discard durable presentation/reception evidence",
            )
        if status.settlement_state == "TERMINAL":
            _required_text(
                status.settled_through_ref,
                "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                "terminal presentation status requires a settlement proof reference",
            )
            _aware_utc(status.settled_at)
        elif status.settled_through_ref is not None or status.settled_at is not None:
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_INVALID",
                "unknown presentation status cannot claim terminal settlement proof",
            )

    def _contiguous_presented_extent(self, conn, session_id: UUID) -> int:
        count, minimum, maximum = conn.execute(
            select(
                func.count(),
                func.min(schema.progressive_presentation_frame_evidence.c.frame_ordinal),
                func.max(schema.progressive_presentation_frame_evidence.c.frame_ordinal),
            ).where(
                schema.progressive_presentation_frame_evidence.c.presentation_session_id
                == session_id
            )
        ).one()
        if int(count) == 0:
            return 0
        if int(minimum) != 1 or int(count) != int(maximum):
            fail(
                "PROGRESSIVE_PRESENTATION_EVIDENCE_GAP",
                "durable presentation evidence does not form a contiguous prefix",
            )
        return int(maximum)

    @staticmethod
    def _known_received_extent(conn, session_id: UUID) -> int:
        value = conn.execute(
            select(
                func.max(
                    schema.progressive_presentation_reception_evidence.c.received_through_frame
                )
            ).where(
                schema.progressive_presentation_reception_evidence.c.presentation_session_id
                == session_id
            )
        ).scalar_one()
        return 0 if value is None else int(value)

    def _require_reception_adapter(self):
        adapter = self.adapter
        if (
            adapter is None
            or getattr(adapter, "reception_contract_version", None)
            != PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION
            or not callable(getattr(adapter, "validate_reception_receipt", None))
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE",
                "progressive reception requires the exact trusted reception contract",
            )
        return adapter

    def _require_status_adapter(self):
        adapter = self.adapter
        if (
            adapter is None
            or getattr(adapter, "status_contract_version", None)
            != PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION
            or not callable(getattr(adapter, "reconcile_presentation_status", None))
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation reconciliation requires the exact trusted status contract",
            )
        return adapter

    @staticmethod
    def _positive_frame_ordinal(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_INVALID",
                "received-through frame must be a positive integer",
            )
        return value

    @staticmethod
    def _reception_by_ref(conn, presentation_key: str, receipt_ref: str):
        return conn.execute(
            select(schema.progressive_presentation_reception_evidence).where(
                schema.progressive_presentation_reception_evidence.c.presentation_key
                == presentation_key,
                schema.progressive_presentation_reception_evidence.c.reception_receipt_ref
                == receipt_ref,
            )
        ).mappings().one_or_none()

    @staticmethod
    def _reception_evidence(conn, evidence_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_reception_evidence).where(
                schema.progressive_presentation_reception_evidence.c.reception_evidence_id
                == evidence_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_NOT_FOUND",
                "durable reception evidence does not exist",
            )
        return row

    @staticmethod
    def _status_by_ref(conn, presentation_key: str, status_ref: str):
        return conn.execute(
            select(schema.progressive_presentation_status_evidence).where(
                schema.progressive_presentation_status_evidence.c.presentation_key
                == presentation_key,
                schema.progressive_presentation_status_evidence.c.status_ref == status_ref,
            )
        ).mappings().one_or_none()

    @staticmethod
    def _status_evidence(conn, evidence_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_status_evidence).where(
                schema.progressive_presentation_status_evidence.c.presentation_status_evidence_id
                == evidence_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_STATUS_NOT_FOUND",
                "durable presentation status evidence does not exist",
            )
        return row

    @staticmethod
    def _latest_terminal_status(conn, attempt_id: UUID):
        return conn.execute(
            select(schema.progressive_presentation_status_evidence)
            .where(
                schema.progressive_presentation_status_evidence.c.presentation_attempt_id
                == attempt_id,
                schema.progressive_presentation_status_evidence.c.settlement_state
                == "TERMINAL",
            )
            .order_by(
                schema.progressive_presentation_status_evidence.c.observed_at.desc()
            )
            .limit(1)
        ).mappings().one_or_none()

    @staticmethod
    def _require_exact_reception(
        row,
        *,
        command: RecordProgressivePresentationReceptionCommand,
        receipt_ref: str,
        received_at,
    ) -> None:
        if not (
            row["presentation_attempt_id"] == command.presentation_attempt_id
            and row["presentation_session_id"] == command.presentation_session_id
            and int(row["attempt_generation"]) == command.attempt_generation
            and row["presentation_transport_fence_scope_id"]
            == command.presentation_transport_fence_scope_id
            and row["presentation_key"] == command.presentation_key
            and int(row["received_through_frame"])
            == command.received_through_frame
            and row["reception_kind"] == command.reception_kind
            and row["reception_receipt_ref"] == receipt_ref
            and row["reception_contract_version"]
            == command.reception_contract_version
            and _aware_utc(row["received_at"]) == received_at
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEPTION_CONFLICT",
                "reception receipt reference conflicts with durable reception evidence",
            )

    @staticmethod
    def _require_exact_status(row, status: ProgressivePresentationReconciliationStatus):
        settled_at = (
            _aware_utc(status.settled_at) if status.settled_at is not None else None
        )
        row_settled_at = (
            _aware_utc(row["settled_at"]) if row["settled_at"] is not None else None
        )
        if not (
            row["presentation_attempt_id"] == status.presentation_attempt_id
            and row["presentation_session_id"] == status.presentation_session_id
            and int(row["attempt_generation"]) == status.attempt_generation
            and row["presentation_transport_fence_scope_id"]
            == status.presentation_transport_fence_scope_id
            and row["presentation_key"] == status.presentation_key
            and row["settlement_state"] == status.settlement_state
            and row["status_ref"] == status.status_ref
            and int(row["last_authoritatively_presented_frame"])
            == status.last_authoritatively_presented_frame
            and int(row["last_authoritatively_received_frame"])
            == status.last_authoritatively_received_frame
            and row["settled_through_ref"] == status.settled_through_ref
            and row["status_contract_version"] == status.status_contract_version
            and row_settled_at == settled_at
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECONCILIATION_CONFLICT",
                "presentation status reference conflicts with durable status evidence",
            )

    def _save_reception_operation(self, conn, command, req, row) -> None:
        save_operation_receipt(
            conn,
            scope=_RECEPTION_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="ProgressivePresentationReceptionEvidence",
            result_ref=row["reception_evidence_id"],
            result_json={
                "reception_evidence_id": str(row["reception_evidence_id"]),
                "presentation_session_id": str(row["presentation_session_id"]),
                "received_through_frame": int(row["received_through_frame"]),
            },
            committed_at=self.clock.now(),
        )

    def _save_reconciliation_operation(self, conn, command, req, row) -> None:
        save_operation_receipt(
            conn,
            scope=_RECONCILE_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="ProgressivePresentationStatusEvidence",
            result_ref=row["presentation_status_evidence_id"],
            result_json={
                "presentation_status_evidence_id": str(
                    row["presentation_status_evidence_id"]
                ),
                "presentation_attempt_id": str(row["presentation_attempt_id"]),
                "presentation_session_id": str(row["presentation_session_id"]),
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _reception_result(row) -> ProgressivePresentationReceptionResult:
        return ProgressivePresentationReceptionResult(
            reception_evidence_id=row["reception_evidence_id"],
            presentation_session_id=row["presentation_session_id"],
            received_through_frame=int(row["received_through_frame"]),
        )

    @staticmethod
    def _reconciliation_result(row) -> ProgressivePresentationReconciliationResult:
        return ProgressivePresentationReconciliationResult(
            presentation_status_evidence_id=row["presentation_status_evidence_id"],
            presentation_attempt_id=row["presentation_attempt_id"],
            presentation_session_id=row["presentation_session_id"],
            state=row["settlement_state"],
            last_authoritatively_presented_frame=int(
                row["last_authoritatively_presented_frame"]
            ),
            last_authoritatively_received_frame=int(
                row["last_authoritatively_received_frame"]
            ),
        )


__all__ = ["ProgressivePresentationServices"]
