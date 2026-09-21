from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    FenceProgressivePresentationAttemptCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    ProgressivePresentationAdapter,
    ProgressivePresentationAttemptResult,
    ProgressivePresentationFrameDispatchResult,
    ProgressivePresentationFrameTransportResult,
    ProgressivePresentationReceiptResult,
    ProgressivePresentationSessionResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.storage import schema


_OPEN_SCOPE = "OpenProgressivePresentation"
_FENCE_SCOPE = "FenceProgressivePresentationAttempt"
_DISPATCH_SCOPE = "DispatchProgressivePresentationFrame"
_RECEIPT_SCOPE = "RecordProgressivePresentationReceipt"
_PRESENTATION_NAMESPACE = UUID("4759a9e7-8cc1-4d77-a72d-fad5cf85c65f")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        fail("PROGRESSIVE_PRESENTATION_TIME_INVALID", "presentation time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_text(value: Any, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(code, message)
    return value.strip()


class ProgressivePresentationServices:
    """F6.A durable progressive-presentation identity and evidence core.

    The service deliberately keeps transport acceptance distinct from presentation
    evidence. It does not yet commit partial presentation to the relationship Timeline;
    that later step must consume only the authoritative contiguous evidence recorded
    here.
    """

    def __init__(
        self,
        engine,
        *,
        adapter: ProgressivePresentationAdapter | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.adapter = adapter
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_OPEN_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._session(conn, UUID(replay["presentation_session_id"]))
                return self._session_result(conn, row)

            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == command.companion_output_id
                )
            ).mappings().one_or_none()
            if output is None:
                fail(
                    "PROGRESSIVE_PRESENTATION_OUTPUT_NOT_FOUND",
                    "CompanionOutput does not exist",
                )
            self._require_route(
                conn,
                companion_person_id=output["companion_person_id"],
                surface_binding_id=command.surface_binding_id,
                channel_binding_id=command.channel_binding_id,
            )
            if sha256_text(output["content_text"]) != output["content_digest"]:
                fail(
                    "PROGRESSIVE_PRESENTATION_OUTPUT_DIGEST_MISMATCH",
                    "CompanionOutput content digest is invalid",
                )

            key = self._presentation_key(
                command.companion_output_id,
                command.surface_binding_id,
                command.channel_binding_id,
            )
            existing = conn.execute(
                select(schema.progressive_presentation_session).where(
                    schema.progressive_presentation_session.c.presentation_key == key
                )
            ).mappings().one_or_none()
            if existing is not None:
                if (
                    existing["companion_output_id"] != command.companion_output_id
                    or existing["surface_binding_id"] != command.surface_binding_id
                    or existing["channel_binding_id"] != command.channel_binding_id
                    or existing["source_content_digest"] != output["content_digest"]
                    or existing["presentation_contract_version"]
                    != PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
                    or existing["frame_contract_version"]
                    != PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_SESSION_CONFLICT",
                        "presentation key resolves to conflicting durable lineage",
                    )
                self._save_open_receipt(conn, command, req, existing)
                return self._session_result(conn, existing)

            session_id = self.ids.new()
            now = self.clock.now()
            frames = self._render_frames(output["content_text"])
            try:
                conn.execute(
                    insert(schema.progressive_presentation_session).values(
                        presentation_session_id=session_id,
                        companion_output_id=command.companion_output_id,
                        relationship_id=output["relationship_id"],
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        presentation_key=key,
                        presentation_contract_version=PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
                        frame_contract_version=PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
                        source_content_digest=output["content_digest"],
                        opened_at=now,
                    )
                )
                for frame in frames:
                    conn.execute(
                        insert(schema.progressive_presentation_frame).values(
                            presentation_session_id=session_id,
                            **frame,
                        )
                    )
            except IntegrityError as exc:
                raise DomainError(
                    "PROGRESSIVE_PRESENTATION_SESSION_CONFLICT",
                    "progressive presentation session was created concurrently",
                ) from exc

            row = self._session(conn, session_id)
            self._save_open_receipt(conn, command, req, row)
            return self._session_result(conn, row)

    def fence_attempt(
        self, command: FenceProgressivePresentationAttemptCommand
    ) -> ProgressivePresentationAttemptResult:
        req = request_digest(asdict(command))
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
                    attempt_generation=1,
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
                    "attempt_generation": 1,
                    "presentation_transport_fence_scope_id": str(fence_scope_id),
                },
                committed_at=now,
            )
            return ProgressivePresentationAttemptResult(
                presentation_attempt_id=attempt_id,
                presentation_session_id=command.presentation_session_id,
                attempt_generation=1,
                presentation_transport_fence_scope_id=fence_scope_id,
                state="OPEN",
            )

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

            attempt = self._attempt(conn, command.presentation_attempt_id)
            if attempt["attempt_state"] != "OPEN":
                fail(
                    "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_OPEN",
                    "only an open presentation attempt may dispatch a frame",
                )
            session = self._session(conn, attempt["presentation_session_id"])
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

    def record_presentation_receipt(
        self, command: RecordProgressivePresentationReceiptCommand
    ) -> ProgressivePresentationReceiptResult:
        req = request_digest(asdict(command))
        receipt_ref = _required_text(
            command.presentation_receipt_ref,
            "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
            "presentation receipt reference must be non-empty",
        )
        if (
            command.presentation_receipt_contract_version
            != PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
                "presentation receipt contract version is unsupported",
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
                row = conn.execute(
                    select(schema.progressive_presentation_frame_evidence).where(
                        schema.progressive_presentation_frame_evidence.c.presentation_evidence_id
                        == UUID(replay["presentation_evidence_id"])
                    )
                ).mappings().one()
                return self._receipt_result(row)

            session = self._session(conn, command.presentation_session_id)
            attempt = self._attempt(conn, command.presentation_attempt_id)
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
            if command.frame_ordinal > 1:
                previous = self._evidence_for_frame(
                    conn, command.presentation_session_id, command.frame_ordinal - 1
                )
                if previous is None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_RECEIPT_GAP",
                        "presentation evidence cannot create a non-contiguous presented prefix",
                    )

            existing = self._evidence_for_frame(
                conn, command.presentation_session_id, command.frame_ordinal
            )
            if existing is not None:
                if (
                    existing["presentation_attempt_id"]
                    == command.presentation_attempt_id
                    and existing["presentation_key"] == command.presentation_key
                    and existing["frame_digest"] == command.frame_digest
                    and existing["presentation_receipt_ref"] == receipt_ref
                    and existing["presentation_receipt_contract_version"]
                    == command.presentation_receipt_contract_version
                    and _aware_utc(existing["presented_at"]) == presented_at
                ):
                    save_operation_receipt(
                        conn,
                        scope=_RECEIPT_SCOPE,
                        operation_id=command.operation_id,
                        req_digest=req,
                        result_kind="ProgressivePresentationEvidence",
                        result_ref=existing["presentation_evidence_id"],
                        result_json={
                            "presentation_evidence_id": str(
                                existing["presentation_evidence_id"]
                            ),
                            "presentation_session_id": str(
                                command.presentation_session_id
                            ),
                            "frame_ordinal": command.frame_ordinal,
                        },
                        committed_at=self.clock.now(),
                    )
                    return self._receipt_result(existing)
                fail(
                    "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT",
                    "frame already has different authoritative presentation evidence",
                )

            evidence_id = self.ids.new()
            observed_at = self.clock.now()
            conn.execute(
                insert(schema.progressive_presentation_frame_evidence).values(
                    presentation_evidence_id=evidence_id,
                    presentation_attempt_id=command.presentation_attempt_id,
                    presentation_session_id=command.presentation_session_id,
                    frame_ordinal=command.frame_ordinal,
                    presentation_key=command.presentation_key,
                    frame_digest=command.frame_digest,
                    presentation_receipt_ref=receipt_ref,
                    presentation_receipt_contract_version=command.presentation_receipt_contract_version,
                    presented_at=presented_at,
                    observed_at=observed_at,
                )
            )
            save_operation_receipt(
                conn,
                scope=_RECEIPT_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ProgressivePresentationEvidence",
                result_ref=evidence_id,
                result_json={
                    "presentation_evidence_id": str(evidence_id),
                    "presentation_session_id": str(command.presentation_session_id),
                    "frame_ordinal": command.frame_ordinal,
                },
                committed_at=observed_at,
            )
            row = conn.execute(
                select(schema.progressive_presentation_frame_evidence).where(
                    schema.progressive_presentation_frame_evidence.c.presentation_evidence_id
                    == evidence_id
                )
            ).mappings().one()
            return self._receipt_result(row)

    def _require_adapter(self) -> None:
        adapter = self.adapter
        if (
            adapter is None
            or adapter.presentation_contract_version
            != PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
            or adapter.frame_contract_version
            != PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
            or adapter.transport_contract_version
            != PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION
            or not callable(getattr(adapter, "dispatch_frame", None))
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE",
                "progressive presentation requires the exact trusted frame transport contract",
            )

    def _validate_transport_status(
        self, *, status, session, attempt, frame
    ) -> None:
        if not isinstance(status, ProgressivePresentationFrameTransportResult):
            fail(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_STATUS_INVALID",
                "frame transport returned material outside the trusted contract",
            )
        if (
            status.transport_contract_version
            != PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION
            or status.presentation_key != session["presentation_key"]
            or status.attempt_generation != int(attempt["attempt_generation"])
            or status.presentation_transport_fence_scope_id
            != attempt["presentation_transport_fence_scope_id"]
            or status.frame_ordinal != int(frame["frame_ordinal"])
            or status.frame_digest != frame["content_digest"]
            or status.acceptance_state not in {"UNKNOWN", "ACCEPTED", "NOT_ACCEPTED"}
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_STATUS_INVALID",
                "frame transport status does not match exact fenced frame lineage",
            )
        if status.acceptance_state == "ACCEPTED":
            _required_text(
                status.acceptance_ref,
                "PROGRESSIVE_PRESENTATION_TRANSPORT_STATUS_INVALID",
                "accepted frame transport requires an acceptance reference",
            )
            _aware_utc(status.accepted_at)
        elif status.accepted_at is not None:
            fail(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_STATUS_INVALID",
                "non-accepted transport cannot carry accepted-at evidence",
            )

    def _require_route(
        self,
        conn,
        *,
        companion_person_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> None:
        surface = conn.execute(
            select(schema.surface_binding).where(
                schema.surface_binding.c.surface_binding_id == surface_binding_id
            )
        ).mappings().one_or_none()
        channel = conn.execute(
            select(schema.channel_binding).where(
                schema.channel_binding.c.channel_binding_id == channel_binding_id
            )
        ).mappings().one_or_none()
        if (
            surface is None
            or channel is None
            or surface["companion_person_id"] != companion_person_id
            or channel["companion_person_id"] != companion_person_id
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ROUTE_INVALID",
                "surface/channel binding does not belong to the CompanionPerson",
            )

    def _save_open_receipt(self, conn, command, req, row) -> None:
        save_operation_receipt(
            conn,
            scope=_OPEN_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="ProgressivePresentationSession",
            result_ref=row["presentation_session_id"],
            result_json={
                "presentation_session_id": str(row["presentation_session_id"]),
                "presentation_key": row["presentation_key"],
            },
            committed_at=self.clock.now(),
        )

    def _session(self, conn, session_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_session).where(
                schema.progressive_presentation_session.c.presentation_session_id
                == session_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_SESSION_NOT_FOUND",
                "progressive presentation session does not exist",
            )
        return row

    def _attempt(self, conn, attempt_id: UUID):
        row = conn.execute(
            select(schema.progressive_presentation_attempt).where(
                schema.progressive_presentation_attempt.c.presentation_attempt_id
                == attempt_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_FOUND",
                "progressive presentation attempt does not exist",
            )
        return row

    def _frame(self, conn, session_id: UUID, frame_ordinal: int):
        if not isinstance(frame_ordinal, int) or isinstance(frame_ordinal, bool) or frame_ordinal < 1:
            fail(
                "PROGRESSIVE_PRESENTATION_FRAME_INVALID",
                "frame ordinal must be a positive integer",
            )
        row = conn.execute(
            select(schema.progressive_presentation_frame).where(
                schema.progressive_presentation_frame.c.presentation_session_id
                == session_id,
                schema.progressive_presentation_frame.c.frame_ordinal == frame_ordinal,
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_FRAME_NOT_FOUND",
                "progressive presentation frame does not exist",
            )
        return row

    def _transport(self, conn, attempt_id: UUID, frame_ordinal: int):
        row = conn.execute(
            select(schema.progressive_presentation_frame_transport).where(
                schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                == attempt_id,
                schema.progressive_presentation_frame_transport.c.frame_ordinal
                == frame_ordinal,
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "PROGRESSIVE_PRESENTATION_TRANSPORT_NOT_FOUND",
                "frame has no durable transport record",
            )
        return row

    def _evidence_for_frame(self, conn, session_id: UUID, frame_ordinal: int):
        return conn.execute(
            select(schema.progressive_presentation_frame_evidence).where(
                schema.progressive_presentation_frame_evidence.c.presentation_session_id
                == session_id,
                schema.progressive_presentation_frame_evidence.c.frame_ordinal
                == frame_ordinal,
            )
        ).mappings().one_or_none()

    def _session_result(self, conn, row) -> ProgressivePresentationSessionResult:
        frame_count = conn.execute(
            select(func.count())
            .select_from(schema.progressive_presentation_frame)
            .where(
                schema.progressive_presentation_frame.c.presentation_session_id
                == row["presentation_session_id"]
            )
        ).scalar_one()
        return ProgressivePresentationSessionResult(
            presentation_session_id=row["presentation_session_id"],
            companion_output_id=row["companion_output_id"],
            presentation_key=row["presentation_key"],
            frame_count=int(frame_count),
            presentation_contract_version=row["presentation_contract_version"],
            frame_contract_version=row["frame_contract_version"],
        )

    @staticmethod
    def _attempt_result(row) -> ProgressivePresentationAttemptResult:
        return ProgressivePresentationAttemptResult(
            presentation_attempt_id=row["presentation_attempt_id"],
            presentation_session_id=row["presentation_session_id"],
            attempt_generation=int(row["attempt_generation"]),
            presentation_transport_fence_scope_id=row[
                "presentation_transport_fence_scope_id"
            ],
            state=row["attempt_state"],
        )

    @staticmethod
    def _dispatch_result(row) -> ProgressivePresentationFrameDispatchResult:
        return ProgressivePresentationFrameDispatchResult(
            presentation_attempt_id=row["presentation_attempt_id"],
            presentation_session_id=row["presentation_session_id"],
            frame_ordinal=int(row["frame_ordinal"]),
            acceptance_state=row["sink_acceptance_state"],
            acceptance_ref=row["acceptance_ref"],
        )

    @staticmethod
    def _receipt_result(row) -> ProgressivePresentationReceiptResult:
        return ProgressivePresentationReceiptResult(
            presentation_evidence_id=row["presentation_evidence_id"],
            presentation_session_id=row["presentation_session_id"],
            frame_ordinal=int(row["frame_ordinal"]),
            presented_through_frame=int(row["frame_ordinal"]),
        )

    @staticmethod
    def _render_frames(content_text: str) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        if content_text == "":
            return [
                {
                    "frame_ordinal": 1,
                    "source_start": 0,
                    "source_end": 0,
                    "content_text": "",
                    "content_digest": sha256_text(""),
                }
            ]
        start = 0
        ordinal = 1
        while start < len(content_text):
            end = min(
                len(content_text),
                start + PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT,
            )
            frame_text = content_text[start:end]
            frames.append(
                {
                    "frame_ordinal": ordinal,
                    "source_start": start,
                    "source_end": end,
                    "content_text": frame_text,
                    "content_digest": sha256_text(frame_text),
                }
            )
            start = end
            ordinal += 1
        return frames

    @staticmethod
    def _presentation_key(
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> str:
        return str(
            uuid5(
                _PRESENTATION_NAMESPACE,
                (
                    f"{companion_output_id}:{surface_binding_id}:{channel_binding_id}:"
                    f"{PROGRESSIVE_PRESENTATION_CONTRACT_VERSION}"
                ),
            )
        )


__all__ = ["ProgressivePresentationServices"]
