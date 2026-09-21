from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    FenceProgressivePresentationAttemptCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    ProgressivePresentationAttemptResult,
    ProgressivePresentationReceiptResult,
    ProgressivePresentationSessionResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v2 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV2,
)
from alsoul.storage import schema


_FENCE_SCOPE = "FenceProgressivePresentationAttempt"
_RECEIPT_SCOPE = "RecordProgressivePresentationReceipt"


class ProgressivePresentationServices(ProgressivePresentationServicesV2):
    """Current bounded F6.A progressive-presentation core.

    The current layer adds fail-closed route and receipt boundaries and permits a new
    fenced generation only when the prior generation has durable terminal
    non-acceptance. Unknown transport outcomes remain blocked for later content-free
    reconciliation; they are never retried speculatively.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        with self.engine.connect() as conn:
            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == command.companion_output_id
                )
            ).mappings().one_or_none()
            if output is not None:
                target = conn.execute(
                    select(schema.output_target).where(
                        schema.output_target.c.output_target_id
                        == output["output_target_id"]
                    )
                ).mappings().one_or_none()
                source_event = None
                if target is not None and target["target_kind"] == "INTERACTION_EVENT":
                    source_event = conn.execute(
                        select(schema.interaction_event).where(
                            schema.interaction_event.c.event_id == target["target_ref"]
                        )
                    ).mappings().one_or_none()
                if (
                    target is None
                    or target["relationship_id"] != output["relationship_id"]
                    or target["target_kind"] != "INTERACTION_EVENT"
                    or source_event is None
                    or source_event["relationship_id"] != output["relationship_id"]
                    or source_event["surface_binding_id"] != command.surface_binding_id
                    or source_event["channel_binding_id"] != command.channel_binding_id
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_ROUTE_INVALID",
                        "progressive presentation must use the CompanionOutput's exact canonical interaction route",
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

    def _require_adapter(self) -> None:
        super()._require_adapter()
        self._require_receipt_adapter()

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

        adapter = self._require_receipt_adapter()
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
            return super().record_presentation_receipt(command)
        except IntegrityError as exc:
            with self.engine.connect() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECEIPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                existing = self._evidence_for_frame(
                    conn,
                    command.presentation_session_id,
                    command.frame_ordinal,
                )
            if replay:
                return super().record_presentation_receipt(command)
            if existing is None:
                raise exc
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
                return super().record_presentation_receipt(command)
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_CONFLICT",
                "frame already has different authoritative presentation evidence",
            )

    def _require_receipt_adapter(self):
        adapter = self.adapter
        if (
            adapter is None
            or getattr(adapter, "receipt_contract_version", None)
            != PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
            or not callable(getattr(adapter, "validate_presentation_receipt", None))
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE",
                "progressive presentation requires the exact trusted presentation-receipt contract",
            )
        return adapter


__all__ = ["ProgressivePresentationServices"]
