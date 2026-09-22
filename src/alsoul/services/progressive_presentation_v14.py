from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict

from sqlalchemy import insert, select, update

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
)
from alsoul.domain.progressive_personal_calendar import (
    DispatchPersonalCalendarProgressiveFrameCommand,
    OpenPersonalCalendarProgressivePresentationCommand,
)
from alsoul.domain.progressive_presentation import (
    OpenProgressivePresentationCommand,
    ProgressivePresentationFrameDispatchResult,
)
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.personal_calendar_presentation_v4 import (
    PersonalCalendarPresentationServices as PersonalCalendarPresentationServicesV4,
)
from alsoul.services.progressive_presentation import _aware_utc
from alsoul.services.progressive_presentation_v13 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV13,
)
from alsoul.storage import schema


_DISPATCH_PERSONAL_SCOPE = "DispatchPersonalCalendarProgressiveFrame"
_PERSONAL_SESSION_ADMISSION: ContextVar[bool] = ContextVar(
    "f6a_personal_calendar_progressive_session_admission",
    default=False,
)


class _F5DisclosureContractProxy:
    """Only the F5 contract identity consumed by the inherited disclosure gate."""

    presentation_contract_version = PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
    status_contract_version = PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION


class ProgressivePresentationServices(ProgressivePresentationServicesV13):
    """F6.A progressive presentation with a per-frame inherited F5 authority gate.

    Opening a durable progressive session is identity/fencing work, not a standing
    personal-data grant. Each personal-calendar frame that would cross the presentation
    boundary re-runs the current F5 freshness/disclosure gate inside the same transaction
    that durably fences that exact frame transport. Later revocation, expiry, policy
    denial, route invalidity, or freshness failure therefore blocks the next payload
    before transport without rewriting already-durable presentation evidence.
    """

    def open_personal_calendar_session(
        self, command: OpenPersonalCalendarProgressivePresentationCommand
    ):
        with self.engine.connect() as conn:
            self._require_personal_calendar_output(conn, command.companion_output_id)

        token = _PERSONAL_SESSION_ADMISSION.set(True)
        try:
            return super().open_session(
                OpenProgressivePresentationCommand(
                    operation_id=command.operation_id,
                    companion_output_id=command.companion_output_id,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                )
            )
        finally:
            _PERSONAL_SESSION_ADMISSION.reset(token)

    def _require_generic_progressive_eligibility(
        self, conn, companion_output_id
    ) -> None:
        if _PERSONAL_SESSION_ADMISSION.get():
            self._require_personal_calendar_output(conn, companion_output_id)
            return
        super()._require_generic_progressive_eligibility(conn, companion_output_id)

    def dispatch_personal_calendar_frame(
        self, command: DispatchPersonalCalendarProgressiveFrameCommand
    ) -> ProgressivePresentationFrameDispatchResult:
        self._require_adapter()
        req = request_digest(asdict(command))

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_PERSONAL_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                row = self._transport(
                    conn,
                    command.presentation_attempt_id,
                    int(replay["frame_ordinal"]),
                )
                self._require_exact_personal_authority(
                    conn,
                    command=command,
                    transport=row,
                )
                return self._dispatch_result(row)

            attempt = self._locked_attempt(conn, command.presentation_attempt_id)
            session = self._session(conn, attempt["presentation_session_id"])
            self._require_personal_calendar_output(
                conn, session["companion_output_id"]
            )
            if attempt["attempt_state"] != "OPEN":
                fail(
                    "PROGRESSIVE_PRESENTATION_ATTEMPT_NOT_OPEN",
                    "only an open presentation attempt may dispatch a frame",
                )

            frame = self._frame(
                conn, session["presentation_session_id"], command.frame_ordinal
            )
            already_presented = self._evidence_for_frame(
                conn, session["presentation_session_id"], command.frame_ordinal
            )
            if already_presented is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_FRAME_ALREADY_PRESENTED",
                    "authoritatively presented frame cannot be dispatched again",
                )
            if command.frame_ordinal > 1:
                previous = self._evidence_for_frame(
                    conn,
                    session["presentation_session_id"],
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
                self._require_exact_personal_authority(
                    conn,
                    command=command,
                    transport=existing,
                )
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

            gate = self._personal_calendar_gate()
            lineage = gate._load_output_lineage(
                conn, session["companion_output_id"]
            )
            source = lineage["source_event"]
            if (
                source["surface_binding_id"] != session["surface_binding_id"]
                or source["channel_binding_id"] != session["channel_binding_id"]
            ):
                fail(
                    "CALENDAR_PRESENTATION_ROUTE_MISMATCH",
                    "personal calendar progressive presentation must use the originating first-party route",
                )

            freshness_decision_id = self.ids.new()
            freshness = gate._record_presentation_freshness(
                conn,
                decision_id=freshness_decision_id,
                lineage=lineage,
            )
            authority = gate._evaluate_disclosure_authority(
                conn,
                lineage=lineage,
                permission_id=command.permission_id,
                surface_binding_id=session["surface_binding_id"],
                channel_binding_id=session["channel_binding_id"],
            )
            gate._linearize_disclosure(
                conn,
                lineage=lineage,
                permission_id=command.permission_id,
                authority=authority,
            )

            disclosure_decision_id = self.ids.new()
            evaluated_at = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_disclosure_decision).values(
                    disclosure_decision_id=disclosure_decision_id,
                    companion_output_id=session["companion_output_id"],
                    freshness_decision_id=freshness_decision_id,
                    relationship_id=lineage["relationship"]["relationship_id"],
                    relationship_authority_revision=authority[
                        "relationship_revision"
                    ],
                    personal_resource_binding_id=lineage["resource"][
                        "personal_resource_binding_id"
                    ],
                    resource_binding_state_revision=authority["resource_revision"],
                    permission_id=command.permission_id,
                    permission_state_revision=authority["permission_revision"],
                    read_policy_revision=authority["read_policy_revision"],
                    disclosure_policy_revision=authority[
                        "disclosure_policy_revision"
                    ],
                    source_interaction_event_id=source["event_id"],
                    source_timeline_frontier=int(source["timeline_seq"]),
                    surface_binding_id=session["surface_binding_id"],
                    channel_binding_id=session["channel_binding_id"],
                    evaluated_at=evaluated_at,
                )
            )

            conn.execute(
                insert(schema.progressive_presentation_frame_transport).values(
                    presentation_attempt_id=command.presentation_attempt_id,
                    presentation_session_id=session["presentation_session_id"],
                    frame_ordinal=command.frame_ordinal,
                    frame_digest=frame["content_digest"],
                    sink_acceptance_state="UNKNOWN",
                    dispatched_at=evaluated_at,
                )
            )
            conn.execute(
                insert(
                    schema.progressive_personal_calendar_frame_authority
                ).values(
                    presentation_attempt_id=command.presentation_attempt_id,
                    presentation_session_id=session["presentation_session_id"],
                    frame_ordinal=command.frame_ordinal,
                    attempt_generation=int(attempt["attempt_generation"]),
                    presentation_transport_fence_scope_id=attempt[
                        "presentation_transport_fence_scope_id"
                    ],
                    companion_output_id=session["companion_output_id"],
                    permission_id=command.permission_id,
                    freshness_decision_id=freshness["freshness_decision_id"],
                    disclosure_decision_id=disclosure_decision_id,
                    frame_digest=frame["content_digest"],
                    surface_binding_id=session["surface_binding_id"],
                    channel_binding_id=session["channel_binding_id"],
                    evaluated_at=evaluated_at,
                )
            )
            save_operation_receipt(
                conn,
                scope=_DISPATCH_PERSONAL_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ProgressivePersonalCalendarFrameTransport",
                result_ref=command.presentation_attempt_id,
                result_json={
                    "presentation_attempt_id": str(
                        command.presentation_attempt_id
                    ),
                    "presentation_session_id": str(
                        session["presentation_session_id"]
                    ),
                    "frame_ordinal": command.frame_ordinal,
                    "freshness_decision_id": str(
                        freshness["freshness_decision_id"]
                    ),
                    "disclosure_decision_id": str(disclosure_decision_id),
                },
                committed_at=evaluated_at,
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

    def _personal_calendar_gate(self) -> PersonalCalendarPresentationServicesV4:
        return PersonalCalendarPresentationServicesV4(
            self.engine,
            adapter=_F5DisclosureContractProxy(),
            clock=self.clock,
            ids=self.ids,
        )

    @staticmethod
    def _require_personal_calendar_output(conn, companion_output_id) -> None:
        row = conn.execute(
            select(
                schema.personal_calendar_companion_output.c.companion_output_id
            ).where(
                schema.personal_calendar_companion_output.c.companion_output_id
                == companion_output_id
            )
        ).scalar_one_or_none()
        if row is None:
            fail(
                "PERSONAL_CALENDAR_PROGRESSIVE_OUTPUT_REQUIRED",
                "specialized progressive personal-calendar presentation requires an F5 personal-calendar CompanionOutput",
            )

    def _require_exact_personal_authority(self, conn, *, command, transport) -> None:
        row = conn.execute(
            select(schema.progressive_personal_calendar_frame_authority).where(
                schema.progressive_personal_calendar_frame_authority.c.presentation_attempt_id
                == transport["presentation_attempt_id"],
                schema.progressive_personal_calendar_frame_authority.c.presentation_session_id
                == transport["presentation_session_id"],
                schema.progressive_personal_calendar_frame_authority.c.frame_ordinal
                == transport["frame_ordinal"],
            )
        ).mappings().one_or_none()
        attempt = self._attempt(conn, transport["presentation_attempt_id"])
        session = self._session(conn, transport["presentation_session_id"])
        if (
            row is None
            or row["permission_id"] != command.permission_id
            or row["frame_digest"] != transport["frame_digest"]
            or int(row["attempt_generation"]) != int(attempt["attempt_generation"])
            or row["presentation_transport_fence_scope_id"]
            != attempt["presentation_transport_fence_scope_id"]
            or row["companion_output_id"] != session["companion_output_id"]
            or row["surface_binding_id"] != session["surface_binding_id"]
            or row["channel_binding_id"] != session["channel_binding_id"]
        ):
            fail(
                "PERSONAL_CALENDAR_PROGRESSIVE_AUTHORITY_EVIDENCE_REQUIRED",
                "durable personal-calendar frame transport lacks its exact inherited authority evidence",
            )


__all__ = ["ProgressivePresentationServices"]
