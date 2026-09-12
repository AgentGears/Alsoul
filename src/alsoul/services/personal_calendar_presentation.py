from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.commands import PresentCompanionOutputCommand
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ
from alsoul.domain.personal_calendar_presentation import (
    PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION,
    PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION,
    PersonalCalendarDisclosurePolicyResult,
    PersonalCalendarPresentationAdapter,
    PersonalCalendarPresentationDispatchResult,
    PersonalCalendarPresentationResult,
    PersonalCalendarPresentationStatusResult,
    PresentPersonalCalendarOutputCommand,
    RecoverPersonalCalendarPresentationCommand,
    SetPersonalCalendarDisclosurePolicyCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.foundation_v4 import FoundationServices as FoundationServicesV4
from alsoul.services.runtime_identity import presentation_idempotency_key
from alsoul.storage import schema

_DISCLOSURE_POLICY_SCOPE = "SetPersonalCalendarDisclosurePolicy"
_PRESENT_SCOPE = "PresentPersonalCalendarOutput"
_PRESENTATION_NAMESPACE = UUID("64a10cd9-7636-4dcb-9c70-5c9e9bd1ea9c")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        fail("CALENDAR_PRESENTATION_TIME_INVALID", "presentation time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_text(value: Any, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(code, message)
    return value.strip()


class PersonalCalendarPresentationServices:
    """Current-authority first presentation and content-free reconciliation for F5.A."""

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

    def set_disclosure_policy(
        self, command: SetPersonalCalendarDisclosurePolicyCommand
    ) -> PersonalCalendarDisclosurePolicyResult:
        req = request_digest(asdict(command))
        _required_text(
            command.policy_version,
            "CALENDAR_DISCLOSURE_POLICY_INVALID",
            "disclosure policy version must be explicit",
        )
        if command.status not in {"ALLOW", "DENY"}:
            fail("CALENDAR_DISCLOSURE_POLICY_INVALID", "disclosure policy status is invalid")
        if command.presentation_contract_version != PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION:
            fail("CALENDAR_DISCLOSURE_POLICY_INVALID", "presentation contract version is unsupported")
        if command.status_contract_version != PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION:
            fail("CALENDAR_DISCLOSURE_POLICY_INVALID", "presentation status contract version is unsupported")

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISCLOSURE_POLICY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarDisclosurePolicyResult(
                    command.relationship_id, int(replay["revision"])
                )
            relationship = self._relationship(conn, command.relationship_id)
            self._require_first_party_route(
                conn,
                relationship=relationship,
                surface_binding_id=command.surface_binding_id,
                channel_binding_id=command.channel_binding_id,
            )
            head = conn.execute(
                select(schema.personal_calendar_disclosure_policy_head).where(
                    schema.personal_calendar_disclosure_policy_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            parent = int(head["current_revision"]) if head is not None else None
            revision = 1 if parent is None else parent + 1
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_disclosure_policy_revision).values(
                    relationship_id=command.relationship_id,
                    revision=revision,
                    parent_revision=parent,
                    policy_version=command.policy_version,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                    presentation_contract_version=command.presentation_contract_version,
                    status_contract_version=command.status_contract_version,
                    status=command.status,
                    committed_at=now,
                )
            )
            if parent is None:
                try:
                    conn.execute(
                        insert(schema.personal_calendar_disclosure_policy_head).values(
                            relationship_id=command.relationship_id,
                            current_revision=revision,
                        )
                    )
                except IntegrityError:
                    fail(
                        "CALENDAR_DISCLOSURE_POLICY_CONFLICT",
                        "disclosure policy head was created concurrently",
                    )
            else:
                self._cas_revision_head(
                    conn,
                    table=schema.personal_calendar_disclosure_policy_head,
                    key_column=schema.personal_calendar_disclosure_policy_head.c.relationship_id,
                    key_value=command.relationship_id,
                    expected_revision=parent,
                    conflict_code="CALENDAR_DISCLOSURE_POLICY_CONFLICT",
                    new_revision=revision,
                )
            save_operation_receipt(
                conn,
                scope=_DISCLOSURE_POLICY_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarDisclosurePolicy",
                result_ref=command.relationship_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return PersonalCalendarDisclosurePolicyResult(command.relationship_id, revision)

    def present_output(
        self, command: PresentPersonalCalendarOutputCommand
    ) -> PersonalCalendarPresentationResult:
        self._require_adapter()
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PRESENT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._result_for_attempt(UUID(replay["presentation_attempt_id"]))
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is not None:
            if latest["sink_acceptance_state"] == "ACCEPTED":
                return self._result_for_attempt(latest["presentation_attempt_id"], commit_accepted=True)
            if latest["sink_acceptance_state"] == "UNKNOWN":
                fail(
                    "CALENDAR_PRESENTATION_RECONCILIATION_REQUIRED",
                    "uncertain personal presentation must be reconciled content-free before another payload send",
                )

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

            lineage = self._load_output_lineage(conn, command.companion_output_id)
            if (
                command.surface_binding_id != lineage["source_event"]["surface_binding_id"]
                or command.channel_binding_id != lineage["source_event"]["channel_binding_id"]
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
                },
                committed_at=now,
            )

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
            lineage = self._load_output_lineage(conn, command.companion_output_id)
            latest = self._latest_attempt(conn, command.companion_output_id)
        if latest is None:
            fail(
                "CALENDAR_PRESENTATION_ATTEMPT_NOT_FOUND",
                "no personal presentation attempt exists to reconcile",
            )
        if (
            latest["surface_binding_id"] != command.surface_binding_id
            or latest["channel_binding_id"] != command.channel_binding_id
            or lineage["source_event"]["surface_binding_id"] != command.surface_binding_id
            or lineage["source_event"]["channel_binding_id"] != command.channel_binding_id
        ):
            fail(
                "CALENDAR_PRESENTATION_ROUTE_MISMATCH",
                "presentation recovery route does not match the fenced attempt",
            )
        if latest["sink_acceptance_state"] == "ACCEPTED":
            return self._result_for_attempt(latest["presentation_attempt_id"], commit_accepted=True)
        if latest["sink_acceptance_state"] == "NOT_ACCEPTED":
            return self._result_for_attempt(latest["presentation_attempt_id"])

        try:
            status = self.adapter.lookup_personal_status(
                presentation_key=latest["presentation_key"],
                presentation_attempt_generation=int(latest["presentation_attempt_generation"]),
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

        self._validate_status_identity(status, attempt_id=latest["presentation_attempt_id"])
        if status.state == "UNKNOWN":
            return self._result_for_attempt(latest["presentation_attempt_id"])
        self._settle_attempt(latest["presentation_attempt_id"], status)
        return self._result_for_attempt(
            latest["presentation_attempt_id"], commit_accepted=True
        )

    def _require_adapter(self) -> None:
        if self.adapter is None:
            fail("CALENDAR_PRESENTATION_ADAPTER_UNAVAILABLE", "qualified presentation adapter is required")
        if (
            self.adapter.presentation_contract_version
            != PERSONAL_CALENDAR_PRESENTATION_CONTRACT_VERSION
            or self.adapter.status_contract_version
            != PERSONAL_CALENDAR_PRESENTATION_STATUS_CONTRACT_VERSION
            or not callable(getattr(self.adapter, "present_personal", None))
            or not callable(getattr(self.adapter, "lookup_personal_status", None))
        ):
            fail(
                "CALENDAR_PRESENTATION_ADAPTER_INELIGIBLE",
                "presentation sink lacks the trusted payload/status-generation contract",
            )

    def _record_presentation_freshness(self, conn, *, decision_id: UUID, lineage: dict[str, Any]) -> dict[str, Any]:
        relationship_id = lineage["relationship"]["relationship_id"]
        head = conn.execute(
            select(schema.personal_calendar_freshness_policy_head).where(
                schema.personal_calendar_freshness_policy_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail("CALENDAR_FRESHNESS_POLICY_MISSING", "current calendar freshness policy is missing")
        revision = int(head["current_revision"])
        policy = conn.execute(
            select(schema.personal_calendar_freshness_policy_revision).where(
                schema.personal_calendar_freshness_policy_revision.c.relationship_id == relationship_id,
                schema.personal_calendar_freshness_policy_revision.c.revision == revision,
            )
        ).mappings().one_or_none()
        if policy is None or policy["status"] != "ALLOW":
            fail("CALENDAR_FRESHNESS_POLICY_DENIED", "current calendar freshness policy denies presentation")
        evaluated_at = _aware_utc(self.clock.now())
        anchor = _aware_utc(lineage["personal_result"]["freshness_anchor_at"])
        elapsed = evaluated_at - anchor
        if elapsed < timedelta(0):
            fail("CALENDAR_FRESHNESS_CLOCK_INVALID", "freshness anchor lies after the evaluation clock")
        maximum = timedelta(seconds=int(policy["max_age_seconds"]))
        if elapsed > maximum:
            fail("CALENDAR_RESULT_STALE", "personal calendar output is stale before first presentation")
        age_us = int(elapsed.total_seconds() * 1_000_000)
        max_us = int(maximum.total_seconds() * 1_000_000)
        conn.execute(
            insert(schema.personal_calendar_presentation_freshness_decision).values(
                freshness_decision_id=decision_id,
                relationship_id=relationship_id,
                world_result_id=lineage["personal_result"]["world_result_id"],
                policy_revision=revision,
                policy_version=policy["policy_version"],
                freshness_anchor_at=anchor,
                evaluated_at=evaluated_at,
                max_age_microseconds=max_us,
                age_microseconds=age_us,
            )
        )
        self._cas_revision_head(
            conn,
            table=schema.personal_calendar_freshness_policy_head,
            key_column=schema.personal_calendar_freshness_policy_head.c.relationship_id,
            key_value=relationship_id,
            expected_revision=revision,
            conflict_code="CALENDAR_FRESHNESS_POLICY_CHANGED",
        )
        return {"freshness_decision_id": decision_id, "policy_revision": revision}

    def _evaluate_disclosure_authority(
        self,
        conn,
        *,
        lineage: dict[str, Any],
        permission_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> dict[str, int]:
        relationship = lineage["relationship"]
        relationship_id = relationship["relationship_id"]
        source = lineage["source_event"]
        timeline = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if timeline is None or int(timeline["last_timeline_seq"]) != int(source["timeline_seq"]):
            fail(
                "CALENDAR_PRESENTATION_INTERACTION_NOT_CURRENT",
                "first presentation requires the originating interaction at the Timeline frontier",
            )
        relationship_head = conn.execute(
            select(schema.personal_world_relationship_head).where(
                schema.personal_world_relationship_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if relationship_head is None:
            fail("CALENDAR_DISCLOSURE_DENIED", "personal-world relationship authority is missing")
        relationship_revision = int(relationship_head["current_revision"])
        relationship_state = conn.execute(
            select(schema.personal_world_relationship_state).where(
                schema.personal_world_relationship_state.c.relationship_id == relationship_id,
                schema.personal_world_relationship_state.c.revision == relationship_revision,
            )
        ).mappings().one_or_none()
        if relationship_state is None or relationship_state["status"] != "ACTIVE":
            fail("CALENDAR_DISCLOSURE_DENIED", "personal-world relationship is not active")

        resource_id = lineage["resource"]["personal_resource_binding_id"]
        resource_head = conn.execute(
            select(schema.personal_resource_binding_head).where(
                schema.personal_resource_binding_head.c.personal_resource_binding_id == resource_id
            )
        ).mappings().one_or_none()
        if resource_head is None:
            fail("CALENDAR_DISCLOSURE_DENIED", "calendar resource state is missing")
        resource_revision = int(resource_head["current_revision"])
        resource_state = conn.execute(
            select(schema.personal_resource_binding_state).where(
                schema.personal_resource_binding_state.c.personal_resource_binding_id == resource_id,
                schema.personal_resource_binding_state.c.revision == resource_revision,
            )
        ).mappings().one_or_none()
        if resource_state is None or resource_state["status"] != "ACTIVE":
            fail("CALENDAR_DISCLOSURE_DENIED", "calendar resource is no longer active")

        grant = conn.execute(
            select(schema.permission_grant).where(schema.permission_grant.c.permission_id == permission_id)
        ).mappings().one_or_none()
        permission_head = conn.execute(
            select(schema.permission_head).where(schema.permission_head.c.permission_id == permission_id)
        ).mappings().one_or_none()
        if grant is None or permission_head is None:
            fail("CALENDAR_DISCLOSURE_DENIED", "calendar read Permission is missing")
        permission_revision = int(permission_head["current_revision"])
        permission_state = conn.execute(
            select(schema.permission_state).where(
                schema.permission_state.c.permission_id == permission_id,
                schema.permission_state.c.revision == permission_revision,
            )
        ).mappings().one_or_none()
        now = _aware_utc(self.clock.now())
        if (
            permission_state is None
            or permission_state["status"] != "ACTIVE"
            or grant["holder_companion_person_id"] != relationship["companion_person_id"]
            or grant["counterpart_id"] != relationship["counterpart_id"]
            or grant["relationship_id"] != relationship_id
            or grant["personal_resource_binding_id"] != resource_id
            or grant["capability_semantic_operation"] != CALENDAR_EVENTS_READ
            or grant["operation_class"] != "READ"
            or grant["grantor_ref"] != relationship["counterpart_id"]
            or grant["grant_source"] != "FIRST_PARTY_COUNTERPART"
            or (grant["expires_at"] is not None and _aware_utc(grant["expires_at"]) <= now)
        ):
            fail("CALENDAR_DISCLOSURE_DENIED", "calendar Permission is revoked, expired, or mismatched")

        read_head = conn.execute(
            select(schema.personal_calendar_read_policy_head).where(
                schema.personal_calendar_read_policy_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if read_head is None:
            fail("CALENDAR_DISCLOSURE_DENIED", "calendar read policy is missing")
        read_revision = int(read_head["current_revision"])
        read_policy = conn.execute(
            select(schema.personal_calendar_read_policy_revision).where(
                schema.personal_calendar_read_policy_revision.c.relationship_id == relationship_id,
                schema.personal_calendar_read_policy_revision.c.revision == read_revision,
            )
        ).mappings().one_or_none()
        if (
            read_policy is None
            or read_policy["status"] != "ALLOW"
            or read_policy["capability_semantic_operation"] != CALENDAR_EVENTS_READ
            or read_policy["capability_effect_class"] != "READ_ONLY"
            or read_policy["capability_contract_version"] != grant["capability_contract_version"]
            or read_policy["permission_grant_policy_version"] != grant["grant_policy_version"]
            or str(resource_id) not in read_policy["allowed_resource_binding_ids_json"]
        ):
            fail("CALENDAR_DISCLOSURE_DENIED", "current calendar policy denies disclosure lineage")

        disclosure_head = conn.execute(
            select(schema.personal_calendar_disclosure_policy_head).where(
                schema.personal_calendar_disclosure_policy_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if disclosure_head is None:
            fail("CALENDAR_DISCLOSURE_POLICY_MISSING", "current personal-data disclosure policy is missing")
        disclosure_revision = int(disclosure_head["current_revision"])
        disclosure = conn.execute(
            select(schema.personal_calendar_disclosure_policy_revision).where(
                schema.personal_calendar_disclosure_policy_revision.c.relationship_id == relationship_id,
                schema.personal_calendar_disclosure_policy_revision.c.revision == disclosure_revision,
            )
        ).mappings().one_or_none()
        if (
            disclosure is None
            or disclosure["status"] != "ALLOW"
            or disclosure["surface_binding_id"] != surface_binding_id
            or disclosure["channel_binding_id"] != channel_binding_id
            or disclosure["presentation_contract_version"] != self.adapter.presentation_contract_version
            or disclosure["status_contract_version"] != self.adapter.status_contract_version
        ):
            fail("CALENDAR_DISCLOSURE_DENIED", "current disclosure policy denies this first-party route")
        self._require_first_party_route(
            conn,
            relationship=relationship,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        return {
            "relationship_revision": relationship_revision,
            "resource_revision": resource_revision,
            "permission_revision": permission_revision,
            "read_policy_revision": read_revision,
            "disclosure_policy_revision": disclosure_revision,
        }

    def _linearize_disclosure(self, conn, *, lineage: dict[str, Any], permission_id: UUID, authority: dict[str, int]) -> None:
        relationship_id = lineage["relationship"]["relationship_id"]
        resource_id = lineage["resource"]["personal_resource_binding_id"]
        self._cas_revision_head(conn, table=schema.personal_world_relationship_head, key_column=schema.personal_world_relationship_head.c.relationship_id, key_value=relationship_id, expected_revision=authority["relationship_revision"], conflict_code="CALENDAR_DISCLOSURE_RELATIONSHIP_CHANGED")
        self._cas_revision_head(conn, table=schema.personal_resource_binding_head, key_column=schema.personal_resource_binding_head.c.personal_resource_binding_id, key_value=resource_id, expected_revision=authority["resource_revision"], conflict_code="CALENDAR_DISCLOSURE_RESOURCE_CHANGED")
        self._cas_revision_head(conn, table=schema.permission_head, key_column=schema.permission_head.c.permission_id, key_value=permission_id, expected_revision=authority["permission_revision"], conflict_code="CALENDAR_DISCLOSURE_PERMISSION_CHANGED")
        self._cas_revision_head(conn, table=schema.personal_calendar_read_policy_head, key_column=schema.personal_calendar_read_policy_head.c.relationship_id, key_value=relationship_id, expected_revision=authority["read_policy_revision"], conflict_code="CALENDAR_DISCLOSURE_READ_POLICY_CHANGED")
        self._cas_revision_head(conn, table=schema.personal_calendar_disclosure_policy_head, key_column=schema.personal_calendar_disclosure_policy_head.c.relationship_id, key_value=relationship_id, expected_revision=authority["disclosure_policy_revision"], conflict_code="CALENDAR_DISCLOSURE_POLICY_CHANGED")
        changed = conn.execute(
            update(schema.relationship_timeline_head)
            .where(
                schema.relationship_timeline_head.c.relationship_id == relationship_id,
                schema.relationship_timeline_head.c.last_timeline_seq == int(lineage["source_event"]["timeline_seq"]),
            )
            .values(last_timeline_seq=int(lineage["source_event"]["timeline_seq"]))
        )
        if changed.rowcount != 1:
            fail("CALENDAR_PRESENTATION_INTERACTION_CHANGED", "Timeline changed before presentation dispatch could linearize")

    def _load_output_lineage(self, conn, companion_output_id: UUID) -> dict[str, Any]:
        specialized = conn.execute(
            select(schema.personal_calendar_companion_output).where(
                schema.personal_calendar_companion_output.c.companion_output_id == companion_output_id
            )
        ).mappings().one_or_none()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id == companion_output_id
            )
        ).mappings().one_or_none()
        if specialized is None or output is None:
            fail("CALENDAR_COMPANION_OUTPUT_NOT_FOUND", "personal calendar CompanionOutput does not exist")
        projection = conn.execute(
            select(schema.personal_calendar_context_projection).where(
                schema.personal_calendar_context_projection.c.projection_id == specialized["projection_id"]
            )
        ).mappings().one_or_none()
        base_projection = conn.execute(
            select(schema.context_projection).where(
                schema.context_projection.c.projection_id == specialized["projection_id"]
            )
        ).mappings().one_or_none()
        personal_result = conn.execute(
            select(schema.personal_calendar_world_result).where(
                schema.personal_calendar_world_result.c.world_result_id == specialized["world_result_id"]
            )
        ).mappings().one_or_none()
        target = conn.execute(
            select(schema.output_target).where(
                schema.output_target.c.output_target_id == output["output_target_id"]
            )
        ).mappings().one_or_none()
        if projection is None or base_projection is None or personal_result is None or target is None:
            fail("CALENDAR_PRESENTATION_LINEAGE_INVALID", "calendar presentation lineage is incomplete")
        source = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == projection["source_interaction_event_id"]
            )
        ).mappings().one_or_none()
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id == projection["personal_resource_binding_id"]
            )
        ).mappings().one_or_none()
        relationship = self._relationship(conn, base_projection["relationship_id"])
        if source is None or resource is None:
            fail("CALENDAR_PRESENTATION_LINEAGE_INVALID", "calendar source interaction or resource is missing")
        if (
            output["source_generated_output_id"] != specialized["generated_output_id"]
            or output["origin_kind"] != "PERSONAL_CALENDAR_SCHEDULE"
            or output["origin_ref"] != specialized["world_result_id"]
            or output["content_digest"] != specialized["deterministic_render_digest"]
            or sha256_text(output["content_text"]) != output["content_digest"]
            or specialized["world_result_id"] != projection["world_result_id"]
            or personal_result["personal_resource_binding_id"] != projection["personal_resource_binding_id"]
            or personal_result["source_interaction_event_id"] != source["event_id"]
            or base_projection["current_input_event_id"] != source["event_id"]
            or base_projection["relationship_id"] != resource["relationship_id"]
            or output["relationship_id"] != resource["relationship_id"]
            or output["companion_person_id"] != relationship["companion_person_id"]
            or target["relationship_id"] != resource["relationship_id"]
            or target["target_kind"] != "INTERACTION_EVENT"
            or target["target_ref"] != source["event_id"]
            or target["purpose"] != "RESPOND_TO_INTERACTION"
            or source["event_kind"] != "COUNTERPART_INPUT"
            or source["actor_kind"] != "COUNTERPART"
            or source["actor_ref"] != relationship["counterpart_id"]
            or source["relationship_id"] != relationship["relationship_id"]
            or resource["counterpart_id"] != relationship["counterpart_id"]
        ):
            fail("CALENDAR_PRESENTATION_LINEAGE_INVALID", "calendar presentation lineage is inconsistent")
        return {
            "specialized": dict(specialized),
            "output": dict(output),
            "projection": dict(projection),
            "base_projection": dict(base_projection),
            "personal_result": dict(personal_result),
            "target": dict(target),
            "source_event": dict(source),
            "resource": dict(resource),
            "relationship": relationship,
        }

    def _settle_attempt(self, attempt_id: UUID, status: PersonalCalendarPresentationDispatchResult | PersonalCalendarPresentationStatusResult) -> None:
        with self.engine.begin() as conn:
            attempt = self._attempt(conn, attempt_id)
            if attempt["sink_acceptance_state"] != "UNKNOWN":
                if attempt["sink_acceptance_state"] == status.state:
                    return
                fail("CALENDAR_PRESENTATION_SETTLEMENT_CONFLICT", "presentation attempt already has a different terminal state")
            if status.state == "ACCEPTED":
                receipt_ref = _required_text(status.receipt_ref, "CALENDAR_PRESENTATION_ACCEPTANCE_INVALID", "accepted presentation requires a sink receipt")
                accepted_at = status.accepted_at
                proof_kind = None
                settled_ref = None
                proved_at = None
            elif status.state == "NOT_ACCEPTED":
                receipt_ref = None
                proof_kind = _required_text(status.terminal_proof_kind, "CALENDAR_PRESENTATION_TERMINALITY_INVALID", "NOT_ACCEPTED requires terminal proof kind")
                settled_ref = _required_text(status.settled_through_ref, "CALENDAR_PRESENTATION_TERMINALITY_INVALID", "NOT_ACCEPTED requires settled-through evidence")
                accepted_at = None
                proved_at = status.proved_at or self.clock.now()
            else:
                fail("CALENDAR_PRESENTATION_STATUS_INVALID", "only terminal presentation status can settle an attempt")
            observed_at = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_presentation_status_evidence).values(
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
                update(schema.personal_calendar_presentation_attempt)
                .where(
                    schema.personal_calendar_presentation_attempt.c.presentation_attempt_id == attempt_id,
                    schema.personal_calendar_presentation_attempt.c.sink_acceptance_state == "UNKNOWN",
                )
                .values(sink_acceptance_state=status.state, settled_at=observed_at)
            )
            if changed.rowcount != 1:
                fail("CALENDAR_PRESENTATION_SETTLEMENT_CONFLICT", "presentation attempt settled concurrently")

    def _validate_status_identity(self, status: PersonalCalendarPresentationDispatchResult | PersonalCalendarPresentationStatusResult, *, attempt_id: UUID) -> None:
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
        if (
            status.presentation_key != attempt["presentation_key"]
            or status.presentation_attempt_generation != int(attempt["presentation_attempt_generation"])
            or status.presentation_transport_fence_scope_id != attempt["presentation_transport_fence_scope_id"]
            or status.status_contract_version != attempt["status_contract_version"]
            or status.state not in {"UNKNOWN", "ACCEPTED", "NOT_ACCEPTED"}
        ):
            fail("CALENDAR_PRESENTATION_STATUS_INVALID", "sink status does not bind the exact presentation generation/fence")

    def _result_for_attempt(self, attempt_id: UUID, *, commit_accepted: bool = False) -> PersonalCalendarPresentationResult:
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
                schema.interaction_event.c.companion_output_id == attempt["companion_output_id"]
            )
        ).scalar_one_or_none()
        return PersonalCalendarPresentationResult(
            companion_output_id=attempt["companion_output_id"],
            presentation_attempt_id=attempt["presentation_attempt_id"],
            presentation_attempt_generation=int(attempt["presentation_attempt_generation"]),
            presentation_key=attempt["presentation_key"],
            state=attempt["sink_acceptance_state"],
            interaction_event_id=event_id,
        )

    def _commit_accepted_presentation(self, attempt_id: UUID) -> None:
        with self.engine.connect() as conn:
            attempt = self._attempt(conn, attempt_id)
            if attempt["sink_acceptance_state"] != "ACCEPTED":
                fail("CALENDAR_PRESENTATION_NOT_ACCEPTED", "cannot commit Timeline presentation without acceptance evidence")
            evidence = conn.execute(
                select(schema.personal_calendar_presentation_status_evidence).where(
                    schema.personal_calendar_presentation_status_evidence.c.presentation_attempt_id == attempt_id,
                    schema.personal_calendar_presentation_status_evidence.c.state == "ACCEPTED",
                )
            ).mappings().one_or_none()
            if evidence is None:
                fail("CALENDAR_PRESENTATION_ACCEPTANCE_INVALID", "accepted attempt lacks durable sink evidence")
            presented_at = evidence["accepted_at"] or evidence["observed_at"]
        operation_id = uuid5(
            _PRESENTATION_NAMESPACE,
            f"{attempt['companion_output_id']}:personal-calendar-presentation-commit-v1",
        )
        FoundationServicesV4(self.engine, clock=self.clock, ids=self.ids).present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=operation_id,
                companion_output_id=attempt["companion_output_id"],
                surface_binding_id=attempt["surface_binding_id"],
                channel_binding_id=attempt["channel_binding_id"],
                presented_at=presented_at,
            )
        )

    def _relationship(self, conn, relationship_id: UUID) -> dict[str, Any]:
        row = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail("RELATIONSHIP_NOT_FOUND", "relationship does not exist")
        return dict(row)

    def _require_first_party_route(self, conn, *, relationship: dict[str, Any], surface_binding_id: UUID, channel_binding_id: UUID) -> None:
        surface = conn.execute(
            select(schema.surface_binding).where(schema.surface_binding.c.surface_binding_id == surface_binding_id)
        ).mappings().one_or_none()
        channel = conn.execute(
            select(schema.channel_binding).where(schema.channel_binding.c.channel_binding_id == channel_binding_id)
        ).mappings().one_or_none()
        if (
            surface is None
            or channel is None
            or surface["companion_person_id"] != relationship["companion_person_id"]
            or channel["companion_person_id"] != relationship["companion_person_id"]
        ):
            fail("CALENDAR_PRESENTATION_ROUTE_INVALID", "first-party surface/channel route does not belong to the CompanionPerson")

    @staticmethod
    def _latest_attempt(conn, companion_output_id: UUID):
        return conn.execute(
            select(schema.personal_calendar_presentation_attempt)
            .where(schema.personal_calendar_presentation_attempt.c.companion_output_id == companion_output_id)
            .order_by(schema.personal_calendar_presentation_attempt.c.presentation_attempt_generation.desc())
            .limit(1)
        ).mappings().one_or_none()

    @staticmethod
    def _attempt(conn, attempt_id: UUID):
        row = conn.execute(
            select(schema.personal_calendar_presentation_attempt).where(
                schema.personal_calendar_presentation_attempt.c.presentation_attempt_id == attempt_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail("CALENDAR_PRESENTATION_ATTEMPT_NOT_FOUND", "presentation attempt does not exist")
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
        new_revision: int | None = None,
    ) -> None:
        target_revision = expected_revision if new_revision is None else new_revision
        changed = conn.execute(
            update(table)
            .where(key_column == key_value, table.c.current_revision == expected_revision)
            .values(current_revision=target_revision)
        )
        if changed.rowcount != 1:
            fail(conflict_code, "presentation authority changed concurrently")


__all__ = ["PersonalCalendarPresentationServices"]
