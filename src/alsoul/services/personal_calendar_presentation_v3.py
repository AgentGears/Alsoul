from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_presentation import (
    PersonalCalendarPresentationResult,
    PresentPersonalCalendarOutputCommand,
    RecoverPersonalCalendarPresentationCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_presentation_v2 import (
    PersonalCalendarPresentationServices as PersonalCalendarPresentationServicesV2,
)
from alsoul.services.runtime_identity import presentation_idempotency_key
from alsoul.storage import schema

_PRESENT_SCOPE = "PresentPersonalCalendarOutput"


class PersonalCalendarPresentationServices(PersonalCalendarPresentationServicesV2):
    """Current F5.A presentation boundary with concrete sink-bound recovery."""

    def _require_adapter(self) -> None:
        super()._require_adapter()
        sink_ref = getattr(self.adapter, "sink_binding_ref", None)
        if not isinstance(sink_ref, str) or not sink_ref.strip() or len(sink_ref) > 128:
            fail(
                "CALENDAR_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation sink must expose one stable bounded binding identity",
            )

    def present_output(
        self, command: PresentPersonalCalendarOutputCommand
    ) -> PersonalCalendarPresentationResult:
        self._require_adapter()
        req = request_digest(asdict(command))

        # Idempotent replay must also repair the canonical Timeline if sink acceptance
        # was durably settled before a process loss interrupted the final append.
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PRESENT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._result_for_attempt(
                    UUID(replay["presentation_attempt_id"]),
                    commit_accepted=True,
                )
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is not None:
            if latest["sink_acceptance_state"] == "ACCEPTED":
                return self._result_for_attempt(
                    latest["presentation_attempt_id"], commit_accepted=True
                )
            if latest["sink_acceptance_state"] == "UNKNOWN":
                fail(
                    "CALENDAR_PRESENTATION_RECONCILIATION_REQUIRED",
                    "uncertain personal presentation must be reconciled content-free before another payload send",
                )

        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_PRESENT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._attempt(conn, UUID(replay["presentation_attempt_id"]))
                    return self._result_from_row(conn, row)

                # One immutable CompanionOutput is the serialization row for prospective
                # presentation generations.  This write precedes the latest-attempt
                # read so distinct operation IDs cannot both authorize one generation.
                fenced = conn.execute(
                    update(schema.personal_calendar_companion_output)
                    .where(
                        schema.personal_calendar_companion_output.c.companion_output_id
                        == command.companion_output_id
                    )
                    .values(
                        deterministic_render_digest=
                        schema.personal_calendar_companion_output.c.deterministic_render_digest
                    )
                )
                if fenced.rowcount != 1:
                    fail(
                        "CALENDAR_COMPANION_OUTPUT_NOT_FOUND",
                        "personal calendar CompanionOutput does not exist",
                    )

                lineage = super()._load_output_lineage(
                    conn, command.companion_output_id
                )
                if (
                    command.surface_binding_id
                    != lineage["source_event"]["surface_binding_id"]
                    or command.channel_binding_id
                    != lineage["source_event"]["channel_binding_id"]
                ):
                    fail(
                        "CALENDAR_PRESENTATION_ROUTE_MISMATCH",
                        "personal calendar output must use the originating first-party route",
                    )
                latest = self._latest_attempt(conn, command.companion_output_id)
                if latest is None:
                    generation = 1
                elif latest["sink_acceptance_state"] == "NOT_ACCEPTED":
                    generation = int(latest["presentation_attempt_generation"]) + 1
                elif latest["sink_acceptance_state"] == "UNKNOWN":
                    fail(
                        "CALENDAR_PRESENTATION_RECONCILIATION_REQUIRED",
                        "uncertain personal presentation must be reconciled before retry",
                    )
                else:
                    fail(
                        "CALENDAR_PRESENTATION_ALREADY_ACCEPTED",
                        "personal calendar output already has accepted presentation evidence",
                    )

                freshness_decision_id = self.ids.new()
                freshness = self._record_presentation_freshness(
                    conn,
                    decision_id=freshness_decision_id,
                    lineage=lineage,
                )
                authority = self._evaluate_disclosure_authority(
                    conn,
                    lineage=lineage,
                    permission_id=command.permission_id,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                )
                self._linearize_disclosure(
                    conn,
                    lineage=lineage,
                    permission_id=command.permission_id,
                    authority=authority,
                )

                disclosure_decision_id = self.ids.new()
                attempt_id = self.ids.new()
                fence_scope_id = self.ids.new()
                key = presentation_idempotency_key(
                    command.companion_output_id,
                    command.surface_binding_id,
                    command.channel_binding_id,
                )
                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_calendar_disclosure_decision).values(
                        disclosure_decision_id=disclosure_decision_id,
                        companion_output_id=command.companion_output_id,
                        freshness_decision_id=freshness_decision_id,
                        relationship_id=lineage["relationship"]["relationship_id"],
                        relationship_authority_revision=authority["relationship_revision"],
                        personal_resource_binding_id=lineage["resource"]["personal_resource_binding_id"],
                        resource_binding_state_revision=authority["resource_revision"],
                        permission_id=command.permission_id,
                        permission_state_revision=authority["permission_revision"],
                        read_policy_revision=authority["read_policy_revision"],
                        disclosure_policy_revision=authority["disclosure_policy_revision"],
                        source_interaction_event_id=lineage["source_event"]["event_id"],
                        source_timeline_frontier=int(lineage["source_event"]["timeline_seq"]),
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        evaluated_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_presentation_attempt).values(
                        presentation_attempt_id=attempt_id,
                        companion_output_id=command.companion_output_id,
                        presentation_key=key,
                        sink_binding_ref=self.adapter.sink_binding_ref.strip(),
                        presentation_attempt_generation=generation,
                        presentation_transport_fence_scope_id=fence_scope_id,
                        disclosure_decision_id=disclosure_decision_id,
                        freshness_decision_id=freshness_decision_id,
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        presentation_contract_version=self.adapter.presentation_contract_version,
                        status_contract_version=self.adapter.status_contract_version,
                        payload_digest=lineage["output"]["content_digest"],
                        dispatch_fenced_at=now,
                        sink_acceptance_state="UNKNOWN",
                    )
                )
                save_operation_receipt(
                    conn,
                    scope=_PRESENT_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarPresentationAttempt",
                    result_ref=attempt_id,
                    result_json={
                        "presentation_attempt_id": str(attempt_id),
                        "presentation_key": key,
                        "presentation_attempt_generation": generation,
                        "freshness_decision_id": str(freshness["freshness_decision_id"]),
                        "disclosure_decision_id": str(disclosure_decision_id),
                        "sink_binding_ref": self.adapter.sink_binding_ref.strip(),
                    },
                    committed_at=now,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_ATTEMPT_CONFLICT",
                "personal presentation generation was admitted concurrently",
            ) from exc

        try:
            status = self.adapter.present_personal(
                presentation_key=key,
                presentation_attempt_generation=generation,
                presentation_transport_fence_scope_id=fence_scope_id,
                companion_output_id=command.companion_output_id,
                surface_binding_id=command.surface_binding_id,
                channel_binding_id=command.channel_binding_id,
                content_text=lineage["output"]["content_text"],
                content_digest=lineage["output"]["content_digest"],
            )
        except (AdapterOutcomeUnknown, AdapterRejected) as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN",
                "personal presentation may have been observed by the sink; content-free reconciliation is required",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN",
                "personal presentation became uncertain after its durable dispatch fence",
            ) from exc

        self._validate_status_identity(status, attempt_id=attempt_id)
        if status.state == "UNKNOWN":
            fail(
                "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN",
                "payload dispatch did not establish terminal presentation status",
            )
        self._settle_attempt(attempt_id, status)
        return self._result_for_attempt(attempt_id, commit_accepted=True)

    def recover_presentation(
        self, command: RecoverPersonalCalendarPresentationCommand
    ) -> PersonalCalendarPresentationResult:
        self._require_adapter()
        with self.engine.connect() as conn:
            lineage = super()._load_output_lineage(
                conn, command.companion_output_id
            )
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is None:
            fail(
                "CALENDAR_PRESENTATION_ATTEMPT_NOT_FOUND",
                "no personal presentation attempt exists to reconcile",
            )
        if (
            latest["surface_binding_id"] != command.surface_binding_id
            or latest["channel_binding_id"] != command.channel_binding_id
            or lineage["source_event"]["surface_binding_id"]
            != command.surface_binding_id
            or lineage["source_event"]["channel_binding_id"]
            != command.channel_binding_id
        ):
            fail(
                "CALENDAR_PRESENTATION_ROUTE_MISMATCH",
                "presentation recovery route does not match the fenced attempt",
            )
        if latest["sink_acceptance_state"] == "ACCEPTED":
            return self._result_for_attempt(
                latest["presentation_attempt_id"], commit_accepted=True
            )
        if latest["sink_acceptance_state"] == "NOT_ACCEPTED":
            return self._result_for_attempt(latest["presentation_attempt_id"])
        if latest["sink_binding_ref"] != self.adapter.sink_binding_ref.strip():
            fail(
                "CALENDAR_PRESENTATION_SINK_MISMATCH",
                "uncertain presentation must be reconciled against the exact sink that received the fenced payload",
            )

        try:
            status = self.adapter.lookup_personal_status(
                presentation_key=latest["presentation_key"],
                presentation_attempt_generation=int(
                    latest["presentation_attempt_generation"]
                ),
                presentation_transport_fence_scope_id=latest[
                    "presentation_transport_fence_scope_id"
                ],
            )
        except AdapterOutcomeUnknown:
            return self._result_for_attempt(latest["presentation_attempt_id"])
        except AdapterRejected as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_STATUS_INVALID",
                "personal presentation status lookup returned untrusted evidence",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_STATUS_UNKNOWN",
                "personal presentation status lookup failed without terminal evidence",
            ) from exc

        self._validate_status_identity(
            status, attempt_id=latest["presentation_attempt_id"]
        )
        if status.state == "UNKNOWN":
            return self._result_for_attempt(latest["presentation_attempt_id"])
        self._settle_attempt(latest["presentation_attempt_id"], status)
        return self._result_for_attempt(
            latest["presentation_attempt_id"], commit_accepted=True
        )


__all__ = ["PersonalCalendarPresentationServices"]
