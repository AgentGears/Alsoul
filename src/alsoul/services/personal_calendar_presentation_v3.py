from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update
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
_EVENT_PROVENANCE_SCOPE = "BindPersonalCalendarPresentedEventProvenance"


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
        adapter = self.adapter
        assert adapter is not None
        sink_binding_ref = adapter.sink_binding_ref.strip()
        presentation_contract_version = adapter.presentation_contract_version
        status_contract_version = adapter.status_contract_version
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
                # presentation generations. This write precedes the latest-attempt read
                # so distinct operation IDs cannot both authorize one generation.
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
                        sink_binding_ref=sink_binding_ref,
                        presentation_attempt_generation=generation,
                        presentation_transport_fence_scope_id=fence_scope_id,
                        disclosure_decision_id=disclosure_decision_id,
                        freshness_decision_id=freshness_decision_id,
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        presentation_contract_version=presentation_contract_version,
                        status_contract_version=status_contract_version,
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
                        "sink_binding_ref": sink_binding_ref,
                    },
                    committed_at=now,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_PRESENTATION_ATTEMPT_CONFLICT",
                "personal presentation generation was admitted concurrently",
            ) from exc

        # The adapter object and all identity-bearing values above were snapshotted
        # before the durable fence. The qualified JSON adapter is immutable, so the
        # object used here cannot silently change endpoints between fence and dispatch.
        if (
            adapter.sink_binding_ref.strip() != sink_binding_ref
            or adapter.presentation_contract_version != presentation_contract_version
            or adapter.status_contract_version != status_contract_version
        ):
            raise DomainError(
                "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN",
                "presentation adapter identity changed after the durable dispatch fence",
            )

        try:
            status = adapter.present_personal(
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
        adapter = self.adapter
        assert adapter is not None
        sink_binding_ref = adapter.sink_binding_ref.strip()
        status_contract_version = adapter.status_contract_version
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
        if latest["sink_binding_ref"] != sink_binding_ref:
            fail(
                "CALENDAR_PRESENTATION_SINK_MISMATCH",
                "uncertain presentation must be reconciled against the exact sink that received the fenced payload",
            )
        if adapter.status_contract_version != status_contract_version:
            fail(
                "CALENDAR_PRESENTATION_SINK_MISMATCH",
                "presentation status adapter changed before content-free reconciliation",
            )

        try:
            status = adapter.lookup_personal_status(
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

    def _commit_accepted_presentation(self, attempt_id: UUID) -> None:
        """Commit historical Timeline truth and bind it to exact acceptance evidence."""

        super()._commit_accepted_presentation(attempt_id)
        with self.engine.begin() as conn:
            attempt = self._attempt(conn, attempt_id)
            evidence = conn.execute(
                select(schema.personal_calendar_presentation_status_evidence).where(
                    schema.personal_calendar_presentation_status_evidence.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_presentation_status_evidence.c.state
                    == "ACCEPTED",
                )
            ).mappings().one_or_none()
            event_id = conn.execute(
                select(schema.interaction_event.c.event_id).where(
                    schema.interaction_event.c.companion_output_id
                    == attempt["companion_output_id"]
                )
            ).scalar_one_or_none()
            if evidence is None or event_id is None:
                fail(
                    "CALENDAR_PRESENTATION_PROVENANCE_INVALID",
                    "accepted presentation lacks canonical event or sink evidence",
                )

            provenance = {
                "interaction_event_id": str(event_id),
                "presentation_attempt_id": str(attempt_id),
                "presentation_attempt_generation": int(
                    attempt["presentation_attempt_generation"]
                ),
                "presentation_transport_fence_scope_id": str(
                    attempt["presentation_transport_fence_scope_id"]
                ),
                "presentation_key": attempt["presentation_key"],
                "sink_binding_ref": attempt["sink_binding_ref"],
                "status_evidence_id": str(evidence["status_evidence_id"]),
                "receipt_ref": evidence["receipt_ref"],
                "accepted_at": (
                    evidence["accepted_at"].isoformat()
                    if evidence["accepted_at"] is not None
                    else None
                ),
            }
            provenance_digest = request_digest(provenance)
            replay = load_operation_receipt(
                conn,
                scope=_EVENT_PROVENANCE_SCOPE,
                operation_id=event_id,
                expected_request_digest=provenance_digest,
            )
            if replay:
                return
            save_operation_receipt(
                conn,
                scope=_EVENT_PROVENANCE_SCOPE,
                operation_id=event_id,
                req_digest=provenance_digest,
                result_kind="PersonalCalendarPresentedEventProvenance",
                result_ref=event_id,
                result_json=provenance,
                committed_at=self.clock.now(),
            )


__all__ = ["PersonalCalendarPresentationServices"]
