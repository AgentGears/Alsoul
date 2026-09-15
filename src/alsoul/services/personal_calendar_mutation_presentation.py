from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_mutation_presentation import (
    PersonalCalendarPresentationAdapter,
    PersonalCalendarPresentationResult,
    PresentPersonalCalendarMutationOutputCommand,
    RecoverPersonalCalendarMutationPresentationCommand,
)
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND,
    PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationStatusResult,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar_mutation_completion_v2 import (
    PersonalCalendarMutationCompletionServices,
)
from alsoul.services.runtime_identity import presentation_idempotency_key
from alsoul.storage import schema


_PRESENT_SCOPE = "PresentPersonalCalendarMutationOutput"
_TIMELINE_COMMIT_SCOPE = "CommitPersonalCalendarMutationAcceptedPresentation"
_EVENT_PROVENANCE_SCOPE = "BindPersonalCalendarMutationPresentedEventProvenance"
_PRESENTATION_NAMESPACE = UUID("81121e1e-f602-4fbb-b620-163e751c76e2")


def _required_text(value: Any, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(code, message)
    return value.strip()


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


class PersonalCalendarMutationPresentationServices:
    """First-party presentation for an adopted evidence-backed calendar mutation result.

    The payload is immutable historical Effect-completion truth rather than a fresh
    current-state calendar observation, so no read/freshness authority is manufactured.
    Every payload send still requires current relationship/resource association and the
    current first-party disclosure policy, linearized in the same transaction as the
    presentation fence. Recovery is content-free and uses only exact sink generation
    identity.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        adapter: PersonalCalendarPresentationAdapter | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.adapter = adapter
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def present_output(
        self, command: PresentPersonalCalendarMutationOutputCommand
    ) -> PersonalCalendarPresentationResult:
        self._require_adapter()
        adapter = self.adapter
        assert adapter is not None
        sink_binding_ref = adapter.sink_binding_ref.strip()
        presentation_contract_version = adapter.presentation_contract_version
        status_contract_version = adapter.status_contract_version
        terminal_negative_semantics = adapter.terminal_negative_semantics
        req = request_digest(asdict(command))

        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PRESENT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._result_for_attempt(
                    UUID(replay["presentation_attempt_id"]), commit_accepted=True
                )
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is not None:
            if latest["sink_acceptance_state"] == "ACCEPTED":
                return self._result_for_attempt(
                    latest["presentation_attempt_id"], commit_accepted=True
                )
            if latest["sink_acceptance_state"] == "UNKNOWN":
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_RECONCILIATION_REQUIRED",
                    "uncertain mutation-result presentation must be reconciled content-free before another payload send",
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

                # The immutable adoption is the serialization row for prospective
                # presentation generations of this one CompanionOutput.
                locked = conn.execute(
                    update(schema.personal_calendar_mutation_adoption)
                    .where(
                        schema.personal_calendar_mutation_adoption.c.companion_output_id
                        == command.companion_output_id
                    )
                    .values(
                        deterministic_render_digest=(
                            schema.personal_calendar_mutation_adoption.c.deterministic_render_digest
                        )
                    )
                )
                if locked.rowcount != 1:
                    fail(
                        "CALENDAR_MUTATION_COMPANION_OUTPUT_NOT_FOUND",
                        "adopted calendar mutation CompanionOutput does not exist",
                    )

                lineage = self._load_output_lineage(conn, command.companion_output_id)
                source = lineage["source_event"]
                if (
                    source["surface_binding_id"] != command.surface_binding_id
                    or source["channel_binding_id"] != command.channel_binding_id
                ):
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_ROUTE_MISMATCH",
                        "mutation result must use the originating first-party route",
                    )

                latest = self._latest_attempt(conn, command.companion_output_id)
                if latest is None:
                    generation = 1
                elif latest["sink_acceptance_state"] == "NOT_ACCEPTED":
                    generation = int(latest["presentation_attempt_generation"]) + 1
                elif latest["sink_acceptance_state"] == "UNKNOWN":
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_RECONCILIATION_REQUIRED",
                        "uncertain mutation-result presentation must be reconciled before retry",
                    )
                else:
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_ALREADY_ACCEPTED",
                        "calendar mutation result already has accepted presentation evidence",
                    )

                authority = self._evaluate_disclosure_authority(
                    conn,
                    lineage=lineage,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                )
                self._linearize_disclosure(conn, lineage=lineage, authority=authority)

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
                    insert(schema.personal_calendar_mutation_disclosure_decision).values(
                        disclosure_decision_id=disclosure_decision_id,
                        companion_output_id=command.companion_output_id,
                        action_id=lineage["action"]["action_id"],
                        effect_id=lineage["effect"]["effect_id"],
                        effect_evidence_id=lineage["support"]["effect_evidence_id"],
                        relationship_id=lineage["relationship"]["relationship_id"],
                        relationship_authority_revision=authority[
                            "relationship_revision"
                        ],
                        personal_resource_binding_id=lineage["resource"][
                            "personal_resource_binding_id"
                        ],
                        resource_binding_state_revision=authority["resource_revision"],
                        disclosure_policy_revision=authority[
                            "disclosure_policy_revision"
                        ],
                        source_interaction_event_id=source["event_id"],
                        source_timeline_frontier=int(
                            lineage["action"]["source_timeline_frontier"]
                        ),
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        evaluated_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_mutation_presentation_attempt).values(
                        presentation_attempt_id=attempt_id,
                        companion_output_id=command.companion_output_id,
                        presentation_key=key,
                        sink_binding_ref=sink_binding_ref,
                        presentation_attempt_generation=generation,
                        presentation_transport_fence_scope_id=fence_scope_id,
                        disclosure_decision_id=disclosure_decision_id,
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
                    result_kind="PersonalCalendarMutationPresentationAttempt",
                    result_ref=attempt_id,
                    result_json={
                        "presentation_attempt_id": str(attempt_id),
                        "presentation_key": key,
                        "presentation_attempt_generation": generation,
                        "disclosure_decision_id": str(disclosure_decision_id),
                        "sink_binding_ref": sink_binding_ref,
                    },
                    committed_at=now,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_ATTEMPT_CONFLICT",
                "mutation-result presentation generation was admitted concurrently",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_ATTEMPT_CONFLICT",
                "mutation-result presentation conflicted with concurrent state",
            ) from exc

        # Adapter identity and transport semantics are snapshotted before the fence.
        if (
            adapter.sink_binding_ref.strip() != sink_binding_ref
            or adapter.presentation_contract_version != presentation_contract_version
            or adapter.status_contract_version != status_contract_version
            or adapter.terminal_negative_semantics != terminal_negative_semantics
        ):
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN",
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
                "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN",
                "mutation-result presentation may have been observed; content-free reconciliation is required",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN",
                "mutation-result presentation became uncertain after its durable dispatch fence",
            ) from exc

        self._validate_status_identity(status, attempt_id=attempt_id)
        if status.state == "UNKNOWN":
            fail(
                "CALENDAR_MUTATION_PRESENTATION_OUTCOME_UNKNOWN",
                "payload dispatch did not establish terminal presentation status",
            )
        self._settle_attempt(attempt_id, status)
        return self._result_for_attempt(attempt_id, commit_accepted=True)

    def recover_presentation(
        self, command: RecoverPersonalCalendarMutationPresentationCommand
    ) -> PersonalCalendarPresentationResult:
        self._require_adapter()
        adapter = self.adapter
        assert adapter is not None
        sink_binding_ref = adapter.sink_binding_ref.strip()

        with self.engine.connect() as conn:
            lineage = self._load_output_lineage(conn, command.companion_output_id)
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is None:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ATTEMPT_NOT_FOUND",
                "no mutation-result presentation attempt exists to reconcile",
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
                "CALENDAR_MUTATION_PRESENTATION_ROUTE_MISMATCH",
                "mutation-result presentation recovery route does not match the fenced attempt",
            )
        if latest["sink_acceptance_state"] == "ACCEPTED":
            return self._result_for_attempt(
                latest["presentation_attempt_id"], commit_accepted=True
            )
        if latest["sink_acceptance_state"] == "NOT_ACCEPTED":
            return self._result_for_attempt(latest["presentation_attempt_id"])
        if latest["sink_binding_ref"] != sink_binding_ref:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_SINK_MISMATCH",
                "uncertain mutation-result presentation must be reconciled against the exact fenced sink",
            )
        if latest["status_contract_version"] != adapter.status_contract_version:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_SINK_MISMATCH",
                "presentation status contract changed before content-free reconciliation",
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
                "CALENDAR_MUTATION_PRESENTATION_STATUS_INVALID",
                "mutation-result presentation status lookup returned untrusted evidence",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "CALENDAR_MUTATION_PRESENTATION_STATUS_UNKNOWN",
                "mutation-result presentation status lookup failed without terminal evidence",
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

    def _load_output_lineage(self, conn, companion_output_id: UUID) -> dict[str, Any]:
        adoption = conn.execute(
            select(schema.personal_calendar_mutation_adoption).where(
                schema.personal_calendar_mutation_adoption.c.companion_output_id
                == companion_output_id
            )
        ).mappings().one_or_none()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id == companion_output_id
            )
        ).mappings().one_or_none()
        if adoption is None or output is None:
            fail(
                "CALENDAR_MUTATION_COMPANION_OUTPUT_NOT_FOUND",
                "adopted calendar mutation CompanionOutput does not exist",
            )

        completion = PersonalCalendarMutationCompletionServices(
            self.engine, adapter=None, clock=self.clock, ids=self.ids
        )
        projection = completion._load_completion_projection(
            conn, adoption["projection_id"]
        )
        effect_lineage = completion._load_confirmed_completion(
            conn, adoption["effect_id"]
        )
        completion._validate_projection_context(conn, projection, effect_lineage)

        generated = conn.execute(
            select(schema.personal_calendar_mutation_generated_output).where(
                schema.personal_calendar_mutation_generated_output.c.generated_output_id
                == adoption["generated_output_id"]
            )
        ).mappings().one_or_none()
        base_generated = conn.execute(
            select(schema.generated_output).where(
                schema.generated_output.c.generated_output_id
                == adoption["generated_output_id"]
            )
        ).mappings().one_or_none()
        target = conn.execute(
            select(schema.output_target).where(
                schema.output_target.c.output_target_id == output["output_target_id"]
            )
        ).mappings().one_or_none()
        action = effect_lineage["action"]
        relationship = effect_lineage["relationship"]
        resource = effect_lineage["resource"]
        source = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == action["source_interaction_event_id"]
            )
        ).mappings().one_or_none()
        expected_payload = completion._provider_context(projection)
        expected_text = completion._render_created(action)

        if (
            generated is None
            or base_generated is None
            or target is None
            or source is None
            or adoption["action_id"] != action["action_id"]
            or adoption["effect_id"] != effect_lineage["effect"]["effect_id"]
            or adoption["effect_evidence_id"]
            != effect_lineage["support"]["effect_evidence_id"]
            or adoption["generated_output_id"] != output["source_generated_output_id"]
            or adoption["projection_id"] != projection["projection_id"]
            or adoption["deterministic_render_digest"] != output["content_digest"]
            or generated["projection_id"] != projection["projection_id"]
            or generated["action_id"] != action["action_id"]
            or generated["effect_id"] != effect_lineage["effect"]["effect_id"]
            or base_generated["semantic_payload_json"] != expected_payload
            or output["semantic_payload_json"] != expected_payload
            or output["origin_kind"] != "PERSONAL_CALENDAR_MUTATION_RESULT"
            or output["origin_ref"] != effect_lineage["effect"]["effect_id"]
            or output["relationship_id"] != action["relationship_id"]
            or output["companion_person_id"] != relationship["companion_person_id"]
            or output["content_text"] != expected_text
            or sha256_text(output["content_text"]) != output["content_digest"]
            or target["relationship_id"] != action["relationship_id"]
            or target["target_kind"] != "PERSONAL_CALENDAR_CREATE_ACTION"
            or target["target_ref"] != action["action_id"]
            or target["purpose"] != "REPORT_CALENDAR_MUTATION_RESULT"
            or source["relationship_id"] != action["relationship_id"]
            or source["event_kind"] != "COUNTERPART_INPUT"
            or source["actor_kind"] != "COUNTERPART"
            or source["actor_ref"] != relationship["counterpart_id"]
            or resource["relationship_id"] != action["relationship_id"]
            or resource["counterpart_id"] != relationship["counterpart_id"]
        ):
            fail(
                "CALENDAR_MUTATION_PRESENTATION_LINEAGE_INVALID",
                "mutation-result presentation lineage is incomplete or inconsistent",
            )

        return {
            "adoption": dict(adoption),
            "output": dict(output),
            "projection": dict(projection),
            "generated": dict(generated),
            "base_generated": dict(base_generated),
            "target": dict(target),
            "source_event": dict(source),
            **effect_lineage,
        }

    def _evaluate_disclosure_authority(
        self,
        conn,
        *,
        lineage: dict[str, Any],
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> dict[str, int]:
        relationship = lineage["relationship"]
        relationship_id = relationship["relationship_id"]
        relationship_head = conn.execute(
            select(schema.personal_world_relationship_head).where(
                schema.personal_world_relationship_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if relationship_head is None:
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_DENIED",
                "personal-world relationship authority is missing",
            )
        relationship_revision = int(relationship_head["current_revision"])
        relationship_state = conn.execute(
            select(schema.personal_world_relationship_state).where(
                schema.personal_world_relationship_state.c.relationship_id
                == relationship_id,
                schema.personal_world_relationship_state.c.revision
                == relationship_revision,
            )
        ).mappings().one_or_none()
        if relationship_state is None or relationship_state["status"] != "ACTIVE":
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_DENIED",
                "personal-world relationship is not active",
            )

        resource_id = lineage["resource"]["personal_resource_binding_id"]
        resource_head = conn.execute(
            select(schema.personal_resource_binding_head).where(
                schema.personal_resource_binding_head.c.personal_resource_binding_id
                == resource_id
            )
        ).mappings().one_or_none()
        if resource_head is None:
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_DENIED",
                "calendar resource state is missing",
            )
        resource_revision = int(resource_head["current_revision"])
        resource_state = conn.execute(
            select(schema.personal_resource_binding_state).where(
                schema.personal_resource_binding_state.c.personal_resource_binding_id
                == resource_id,
                schema.personal_resource_binding_state.c.revision == resource_revision,
            )
        ).mappings().one_or_none()
        if resource_state is None or resource_state["status"] != "ACTIVE":
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_DENIED",
                "calendar resource is no longer active",
            )

        disclosure_head = conn.execute(
            select(schema.personal_calendar_disclosure_policy_head).where(
                schema.personal_calendar_disclosure_policy_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if disclosure_head is None:
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_POLICY_MISSING",
                "current personal-calendar disclosure policy is missing",
            )
        disclosure_revision = int(disclosure_head["current_revision"])
        disclosure = conn.execute(
            select(schema.personal_calendar_disclosure_policy_revision).where(
                schema.personal_calendar_disclosure_policy_revision.c.relationship_id
                == relationship_id,
                schema.personal_calendar_disclosure_policy_revision.c.revision
                == disclosure_revision,
            )
        ).mappings().one_or_none()
        if (
            disclosure is None
            or disclosure["status"] != "ALLOW"
            or disclosure["surface_binding_id"] != surface_binding_id
            or disclosure["channel_binding_id"] != channel_binding_id
            or disclosure["presentation_contract_version"]
            != self.adapter.presentation_contract_version
            or disclosure["status_contract_version"]
            != self.adapter.status_contract_version
        ):
            fail(
                "CALENDAR_MUTATION_DISCLOSURE_DENIED",
                "current disclosure policy denies this mutation-result route",
            )
        self._require_first_party_route(
            conn,
            relationship=relationship,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        return {
            "relationship_revision": relationship_revision,
            "resource_revision": resource_revision,
            "disclosure_policy_revision": disclosure_revision,
        }

    def _linearize_disclosure(
        self, conn, *, lineage: dict[str, Any], authority: dict[str, int]
    ) -> None:
        relationship_id = lineage["relationship"]["relationship_id"]
        resource_id = lineage["resource"]["personal_resource_binding_id"]
        self._cas_revision_head(
            conn,
            table=schema.personal_world_relationship_head,
            key_column=schema.personal_world_relationship_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=authority["relationship_revision"],
            conflict_code="CALENDAR_MUTATION_DISCLOSURE_RELATIONSHIP_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_resource_binding_head,
            key_column=schema.personal_resource_binding_head.c.personal_resource_binding_id,
            key_value=resource_id,
            expected_revision=authority["resource_revision"],
            conflict_code="CALENDAR_MUTATION_DISCLOSURE_RESOURCE_CHANGED",
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_disclosure_policy_head,
            key_column=schema.personal_calendar_disclosure_policy_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=authority["disclosure_policy_revision"],
            conflict_code="CALENDAR_MUTATION_DISCLOSURE_POLICY_CHANGED",
        )

    def _require_adapter(self) -> None:
        adapter = self.adapter
        if adapter is None:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ADAPTER_UNAVAILABLE",
                "qualified first-party presentation adapter is required",
            )
        if (
            getattr(adapter, "presentation_contract_version", None)
            != PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
            or getattr(adapter, "status_contract_version", None)
            != PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
            or getattr(adapter, "terminal_negative_semantics", None)
            != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_SEMANTICS
            or not callable(getattr(adapter, "present_personal", None))
            or not callable(getattr(adapter, "lookup_personal_status", None))
        ):
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation sink lacks exact payload, status, and terminal-generation semantics",
            )
        sink_ref = getattr(adapter, "sink_binding_ref", None)
        if not isinstance(sink_ref, str) or not sink_ref.strip() or len(sink_ref) > 128:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation sink must expose one stable bounded binding identity",
            )

    def _validate_status_identity(
        self,
        status: PersonalCalendarPresentationDispatchResult
        | PersonalCalendarPresentationStatusResult,
        *,
        attempt_id: UUID,
    ) -> None:
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
        if (
            status.presentation_key != attempt["presentation_key"]
            or status.presentation_attempt_generation
            != int(attempt["presentation_attempt_generation"])
            or status.presentation_transport_fence_scope_id
            != attempt["presentation_transport_fence_scope_id"]
            or status.status_contract_version != attempt["status_contract_version"]
            or status.state not in {"UNKNOWN", "ACCEPTED", "NOT_ACCEPTED"}
            or (
                status.state == "NOT_ACCEPTED"
                and status.terminal_proof_kind
                != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND
            )
        ):
            fail(
                "CALENDAR_MUTATION_PRESENTATION_STATUS_INVALID",
                "sink status does not bind the exact mutation-result presentation generation/fence",
            )

    def _settle_attempt(
        self,
        attempt_id: UUID,
        status: PersonalCalendarPresentationDispatchResult
        | PersonalCalendarPresentationStatusResult,
    ) -> None:
        with self.engine.begin() as conn:
            attempt = self._attempt(conn, attempt_id)
            if attempt["sink_acceptance_state"] != "UNKNOWN":
                if attempt["sink_acceptance_state"] == status.state:
                    return
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                    "mutation-result presentation attempt already has a different terminal state",
                )
            if status.state == "ACCEPTED":
                receipt_ref = _required_text(
                    status.receipt_ref,
                    "CALENDAR_MUTATION_PRESENTATION_ACCEPTANCE_INVALID",
                    "accepted mutation-result presentation requires a sink receipt",
                )
                accepted_at = status.accepted_at
                proof_kind = None
                settled_ref = None
                proved_at = None
            elif status.state == "NOT_ACCEPTED":
                receipt_ref = None
                proof_kind = _required_text(
                    status.terminal_proof_kind,
                    "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                    "NOT_ACCEPTED requires exact-generation terminal proof",
                )
                if proof_kind != PERSONAL_CALENDAR_TERMINAL_NEGATIVE_PROOF_KIND:
                    fail(
                        "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                        "NOT_ACCEPTED evidence does not prove settled exact-generation terminality",
                    )
                settled_ref = _required_text(
                    status.settled_through_ref,
                    "CALENDAR_MUTATION_PRESENTATION_TERMINALITY_INVALID",
                    "NOT_ACCEPTED requires settled-through evidence",
                )
                accepted_at = None
                proved_at = status.proved_at or self.clock.now()
            else:
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_STATUS_INVALID",
                    "only terminal presentation status can settle an attempt",
                )
            observed_at = self.clock.now()
            conn.execute(
                insert(
                    schema.personal_calendar_mutation_presentation_status_evidence
                ).values(
                    status_evidence_id=self.ids.new(),
                    presentation_attempt_id=attempt_id,
                    state=status.state,
                    receipt_ref=receipt_ref,
                    terminal_proof_kind=proof_kind,
                    settled_through_ref=settled_ref,
                    status_contract_version=status.status_contract_version,
                    accepted_at=accepted_at,
                    proved_at=proved_at,
                    observed_at=observed_at,
                )
            )
            changed = conn.execute(
                update(schema.personal_calendar_mutation_presentation_attempt)
                .where(
                    schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_mutation_presentation_attempt.c.sink_acceptance_state
                    == "UNKNOWN",
                )
                .values(sink_acceptance_state=status.state, settled_at=observed_at)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_SETTLEMENT_CONFLICT",
                    "mutation-result presentation attempt settled concurrently",
                )

    def _result_for_attempt(
        self, attempt_id: UUID, *, commit_accepted: bool = False
    ) -> PersonalCalendarPresentationResult:
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
        if commit_accepted and attempt["sink_acceptance_state"] == "ACCEPTED":
            self._commit_accepted_presentation(attempt_id)
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
            return self._result_from_row(conn, attempt)

    def _result_from_row(self, conn, attempt) -> PersonalCalendarPresentationResult:
        event_id = conn.execute(
            select(schema.interaction_event.c.event_id).where(
                schema.interaction_event.c.companion_output_id
                == attempt["companion_output_id"]
            )
        ).scalar_one_or_none()
        return PersonalCalendarPresentationResult(
            companion_output_id=attempt["companion_output_id"],
            presentation_attempt_id=attempt["presentation_attempt_id"],
            presentation_attempt_generation=int(
                attempt["presentation_attempt_generation"]
            ),
            presentation_key=attempt["presentation_key"],
            state=attempt["sink_acceptance_state"],
            interaction_event_id=event_id,
        )

    def _commit_accepted_presentation(self, attempt_id: UUID) -> None:
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
            if attempt["sink_acceptance_state"] != "ACCEPTED":
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_NOT_ACCEPTED",
                    "cannot commit Timeline presentation without acceptance evidence",
                )
            evidence = conn.execute(
                select(
                    schema.personal_calendar_mutation_presentation_status_evidence
                ).where(
                    schema.personal_calendar_mutation_presentation_status_evidence.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_mutation_presentation_status_evidence.c.state
                    == "ACCEPTED",
                )
            ).mappings().one_or_none()
            if evidence is None:
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_ACCEPTANCE_INVALID",
                    "accepted mutation-result attempt lacks durable sink evidence",
                )
            lineage = self._load_output_lineage(
                conn, attempt["companion_output_id"]
            )
            presented_at = evidence["accepted_at"] or evidence["observed_at"]

        operation_id = uuid5(
            _PRESENTATION_NAMESPACE,
            f"{attempt['companion_output_id']}:calendar-mutation-presentation-commit-v1",
        )
        commit_payload = {
            "companion_output_id": str(attempt["companion_output_id"]),
            "presentation_attempt_id": str(attempt_id),
            "presentation_attempt_generation": int(
                attempt["presentation_attempt_generation"]
            ),
            "surface_binding_id": str(attempt["surface_binding_id"]),
            "channel_binding_id": str(attempt["channel_binding_id"]),
            "reply_to_event_id": str(lineage["source_event"]["event_id"]),
            "presented_at": presented_at.isoformat(),
        }
        commit_digest = request_digest(commit_payload)
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_TIMELINE_COMMIT_SCOPE,
                operation_id=operation_id,
                expected_request_digest=commit_digest,
            )
            if replay:
                event_id = UUID(replay["interaction_event_id"])
            else:
                existing = conn.execute(
                    select(schema.interaction_event).where(
                        schema.interaction_event.c.companion_output_id
                        == attempt["companion_output_id"]
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    if (
                        existing["relationship_id"]
                        != lineage["relationship"]["relationship_id"]
                        or existing["actor_kind"] != "COMPANION"
                        or existing["actor_ref"]
                        != lineage["relationship"]["companion_person_id"]
                        or existing["event_kind"] != "COMPANION_PRESENTED_OUTPUT"
                        or existing["content_text"] != lineage["output"]["content_text"]
                        or existing["surface_binding_id"]
                        != attempt["surface_binding_id"]
                        or existing["channel_binding_id"]
                        != attempt["channel_binding_id"]
                        or existing["reply_to_event_id"]
                        != lineage["source_event"]["event_id"]
                    ):
                        fail(
                            "CALENDAR_MUTATION_PRESENTATION_TIMELINE_CONFLICT",
                            "existing Timeline presentation does not match the accepted mutation result",
                        )
                    event_id = existing["event_id"]
                else:
                    timeline = conn.execute(
                        select(schema.relationship_timeline_head).where(
                            schema.relationship_timeline_head.c.relationship_id
                            == lineage["relationship"]["relationship_id"]
                        )
                    ).mappings().one_or_none()
                    if timeline is None:
                        fail(
                            "CALENDAR_MUTATION_PRESENTATION_TIMELINE_MISSING",
                            "relationship Timeline head is missing",
                        )
                    next_seq = int(timeline["last_timeline_seq"]) + 1
                    event_id = self.ids.new()
                    conn.execute(
                        insert(schema.interaction_event).values(
                            event_id=event_id,
                            relationship_id=lineage["relationship"][
                                "relationship_id"
                            ],
                            timeline_seq=next_seq,
                            actor_kind="COMPANION",
                            actor_ref=lineage["relationship"][
                                "companion_person_id"
                            ],
                            event_kind="COMPANION_PRESENTED_OUTPUT",
                            content_text=lineage["output"]["content_text"],
                            occurred_at=presented_at,
                            recorded_at=self.clock.now(),
                            surface_binding_id=attempt["surface_binding_id"],
                            channel_binding_id=attempt["channel_binding_id"],
                            companion_output_id=attempt["companion_output_id"],
                            reply_to_event_id=lineage["source_event"]["event_id"],
                        )
                    )
                    changed = conn.execute(
                        update(schema.relationship_timeline_head)
                        .where(
                            schema.relationship_timeline_head.c.relationship_id
                            == lineage["relationship"]["relationship_id"],
                            schema.relationship_timeline_head.c.last_timeline_seq
                            == timeline["last_timeline_seq"],
                        )
                        .values(last_timeline_seq=next_seq)
                    )
                    if changed.rowcount != 1:
                        fail(
                            "CALENDAR_MUTATION_PRESENTATION_TIMELINE_CONFLICT",
                            "relationship Timeline advanced concurrently",
                        )
                save_operation_receipt(
                    conn,
                    scope=_TIMELINE_COMMIT_SCOPE,
                    operation_id=operation_id,
                    req_digest=commit_digest,
                    result_kind="PersonalCalendarMutationPresentedInteractionEvent",
                    result_ref=event_id,
                    result_json={"interaction_event_id": str(event_id)},
                    committed_at=self.clock.now(),
                )

        # Bind historical Timeline truth to exact sink acceptance evidence. This can
        # be repaired after process loss without redisclosing the payload.
        with self.engine.begin() as conn:
            attempt = self._attempt(conn, attempt_id)
            evidence = conn.execute(
                select(
                    schema.personal_calendar_mutation_presentation_status_evidence
                ).where(
                    schema.personal_calendar_mutation_presentation_status_evidence.c.presentation_attempt_id
                    == attempt_id,
                    schema.personal_calendar_mutation_presentation_status_evidence.c.state
                    == "ACCEPTED",
                )
            ).mappings().one_or_none()
            event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == event_id
                )
            ).mappings().one_or_none()
            if evidence is None or event is None:
                fail(
                    "CALENDAR_MUTATION_PRESENTATION_PROVENANCE_INVALID",
                    "accepted mutation-result presentation lacks canonical event or sink evidence",
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
            digest = request_digest(provenance)
            replay = load_operation_receipt(
                conn,
                scope=_EVENT_PROVENANCE_SCOPE,
                operation_id=event_id,
                expected_request_digest=digest,
            )
            if replay:
                return
            save_operation_receipt(
                conn,
                scope=_EVENT_PROVENANCE_SCOPE,
                operation_id=event_id,
                req_digest=digest,
                result_kind="PersonalCalendarMutationPresentedEventProvenance",
                result_ref=event_id,
                result_json=provenance,
                committed_at=self.clock.now(),
            )

    def _require_first_party_route(
        self,
        conn,
        *,
        relationship: dict[str, Any],
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
            or surface["companion_person_id"] != relationship["companion_person_id"]
            or channel["companion_person_id"] != relationship["companion_person_id"]
        ):
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ROUTE_INVALID",
                "first-party surface/channel route does not belong to the CompanionPerson",
            )

    @staticmethod
    def _latest_attempt(conn, companion_output_id: UUID):
        return conn.execute(
            select(schema.personal_calendar_mutation_presentation_attempt)
            .where(
                schema.personal_calendar_mutation_presentation_attempt.c.companion_output_id
                == companion_output_id
            )
            .order_by(
                schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_generation.desc()
            )
            .limit(1)
        ).mappings().one_or_none()

    @staticmethod
    def _attempt(conn, attempt_id: UUID):
        row = conn.execute(
            select(schema.personal_calendar_mutation_presentation_attempt).where(
                schema.personal_calendar_mutation_presentation_attempt.c.presentation_attempt_id
                == attempt_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "CALENDAR_MUTATION_PRESENTATION_ATTEMPT_NOT_FOUND",
                "mutation-result presentation attempt does not exist",
            )
        return row

    @staticmethod
    def _cas_revision_head(
        conn,
        *,
        table,
        key_column,
        key_value: UUID,
        expected_revision: int,
        conflict_code: str,
    ) -> None:
        changed = conn.execute(
            update(table)
            .where(key_column == key_value, table.c.current_revision == expected_revision)
            .values(current_revision=expected_revision)
        )
        if changed.rowcount != 1:
            fail(
                conflict_code,
                "mutation-result presentation authority changed concurrently",
            )


__all__ = ["PersonalCalendarMutationPresentationServices"]
