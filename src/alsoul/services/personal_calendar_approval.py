from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    CalendarApprovalPresentationAdapter,
)
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_action import (
    CALENDAR_CREATE_ACTION_SCHEMA_VERSION,
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
)
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    CALENDAR_CREATE_APPROVAL_CEREMONY,
    CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION,
    CALENDAR_CREATE_APPROVAL_TEXT,
    PersonalCalendarCreateApprovalPresentationResult,
    PersonalCalendarCreateApprovalResult,
    PersonalCalendarCreateApprovalStateResult,
    PresentPersonalCalendarCreateApprovalCommand,
    RevokePersonalCalendarCreateApprovalCommand,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar_action_v2 import PersonalCalendarActionServices
from alsoul.storage import schema

_PRESENT_SCOPE = "PresentPersonalCalendarCreateApproval"
_ADMIT_SCOPE = "AdmitPersonalCalendarCreateApproval"
_REVOKE_SCOPE = "RevokePersonalCalendarCreateApproval"


class PersonalCalendarApprovalServices(PersonalCalendarActionServices):
    """F5.B faithful consent-presentation and exact Action Approval boundary."""

    def __init__(self, engine, *, time_resolver, approval_adapter=None, clock=None, ids=None):
        super().__init__(engine, time_resolver=time_resolver, clock=clock, ids=ids)
        self.approval_adapter = approval_adapter

    def present_create_approval(
        self, command: PresentPersonalCalendarCreateApprovalCommand
    ) -> PersonalCalendarCreateApprovalPresentationResult:
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PRESENT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._presentation_result_from_json(replay)
            existing = conn.execute(
                select(schema.personal_calendar_create_approval_presentation).where(
                    schema.personal_calendar_create_approval_presentation.c.action_id
                    == command.action_id
                )
            ).mappings().one_or_none()
        if existing is not None:
            return self._bind_existing_presentation_operation(
                command=command, req=req, presentation=dict(existing)
            )

        adapter = self._require_approval_adapter()
        with self.engine.connect() as conn:
            action, source_event, relationship, resource = self._load_action_lineage(
                conn, command.action_id
            )
            self._require_current_action_authority(
                conn,
                action=action,
                relationship=relationship,
                resource=resource,
            )
            consent = self._consent_payload(action=action, resource=resource)
            surface_binding_id = source_event["surface_binding_id"]
            channel_binding_id = source_event["channel_binding_id"]
            if surface_binding_id is None or channel_binding_id is None:
                fail(
                    "CALENDAR_CREATE_APPROVAL_ROUTE_MISSING",
                    "calendar-create Action lacks a trusted first-party presentation route",
                )

        sink_binding_ref = adapter.sink_binding_ref.strip()
        contract_version = adapter.presentation_contract_version.strip()
        presentation_key = self._presentation_key(
            action_id=command.action_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
        )
        consent_text = self._render_consent(consent)
        consent_digest = sha256_text(canonical_json(consent))
        try:
            acceptance = adapter.present_calendar_create_approval(
                presentation_key=presentation_key,
                action_id=command.action_id,
                surface_binding_id=surface_binding_id,
                channel_binding_id=channel_binding_id,
                consent_text=consent_text,
                consent_payload_digest=consent_digest,
            )
        except (AdapterOutcomeUnknown, AdapterRejected) as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_OUTCOME_UNKNOWN",
                "approval consent presentation did not establish trustworthy acceptance",
            ) from exc
        except Exception as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_OUTCOME_UNKNOWN",
                "approval consent presentation outcome is unknown",
            ) from exc

        if (
            adapter.sink_binding_ref.strip() != sink_binding_ref
            or adapter.presentation_contract_version.strip() != contract_version
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_ADAPTER_CHANGED",
                "approval presentation adapter identity changed during dispatch",
            )
        if (
            acceptance.presentation_key != presentation_key
            or acceptance.consent_payload_digest != consent_digest
            or not isinstance(acceptance.receipt_ref, str)
            or not acceptance.receipt_ref.strip()
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_INVALID",
                "approval sink acceptance does not bind the exact consent payload",
            )

        presentation_id = self.ids.new()
        now = self.clock.now()
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_PRESENT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._presentation_result_from_json(replay)
                existing = conn.execute(
                    select(schema.personal_calendar_create_approval_presentation).where(
                        schema.personal_calendar_create_approval_presentation.c.action_id
                        == command.action_id
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    return self._bind_existing_presentation_operation_in_connection(
                        conn,
                        command=command,
                        req=req,
                        presentation=dict(existing),
                    )

                current_action, current_source, current_relationship, current_resource = (
                    self._load_action_lineage(conn, command.action_id)
                )
                self._require_current_action_authority(
                    conn,
                    action=current_action,
                    relationship=current_relationship,
                    resource=current_resource,
                )
                if (
                    current_action["action_digest"] != action["action_digest"]
                    or current_source["surface_binding_id"] != surface_binding_id
                    or current_source["channel_binding_id"] != channel_binding_id
                    or self._consent_payload(
                        action=current_action, resource=current_resource
                    )
                    != consent
                ):
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PRESENTATION_STALE",
                        "Action semantics or trusted presentation route changed before consent acceptance was committed",
                    )
                timeline = conn.execute(
                    select(schema.relationship_timeline_head).where(
                        schema.relationship_timeline_head.c.relationship_id
                        == current_action["relationship_id"]
                    )
                ).mappings().one_or_none()
                if timeline is None:
                    fail(
                        "CALENDAR_CREATE_APPROVAL_TIMELINE_MISSING",
                        "calendar-create approval presentation lacks canonical Timeline state",
                    )
                frontier = int(timeline["last_timeline_seq"])
                conn.execute(
                    insert(schema.personal_calendar_create_approval_presentation).values(
                        approval_presentation_id=presentation_id,
                        action_id=command.action_id,
                        action_digest=current_action["action_digest"],
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                        personal_resource_binding_id=current_action[
                            "personal_resource_binding_id"
                        ],
                        target_calendar_display_identity=consent[
                            "target_calendar_display_identity"
                        ],
                        summary=current_action["summary"],
                        start_text=current_action["start_text"],
                        end_text=current_action["end_text"],
                        normalized_start_at=current_action["normalized_start_at"],
                        normalized_end_at=current_action["normalized_end_at"],
                        consent_rendering_version=(
                            CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION
                        ),
                        consent_payload_digest=consent_digest,
                        presented_to_counterpart_id=current_action["counterpart_id"],
                        surface_binding_id=surface_binding_id,
                        channel_binding_id=channel_binding_id,
                        presentation_timeline_frontier=frontier,
                        presentation_key=presentation_key,
                        sink_binding_ref=sink_binding_ref,
                        presentation_contract_version=contract_version,
                        presentation_acceptance_ref=acceptance.receipt_ref.strip(),
                        presented_at=now,
                    )
                )
                result_json = self._presentation_result_json(
                    presentation_id=presentation_id,
                    action=current_action,
                    consent_digest=consent_digest,
                    presentation_key=presentation_key,
                    acceptance_ref=acceptance.receipt_ref.strip(),
                    presented_at=now,
                )
                save_operation_receipt(
                    conn,
                    scope=_PRESENT_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateApprovalPresentation",
                    result_ref=presentation_id,
                    result_json=result_json,
                    committed_at=now,
                )
                return self._presentation_result_from_json(result_json)
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_CONFLICT",
                "calendar-create Action already has a competing consent presentation",
            ) from exc

    def admit_create_approval(
        self, command: AdmitPersonalCalendarCreateApprovalCommand
    ) -> PersonalCalendarCreateApprovalResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_ADMIT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._approval_result_from_json(replay)
                presentation = conn.execute(
                    select(schema.personal_calendar_create_approval_presentation).where(
                        schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                        == command.approval_presentation_id
                    )
                ).mappings().one_or_none()
                if presentation is None:
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PRESENTATION_NOT_FOUND",
                        "trusted approval presentation does not exist",
                    )
                action, _, relationship, resource = self._load_action_lineage(
                    conn, presentation["action_id"]
                )
                self._require_presentation_equivalence(
                    action=action, resource=resource, presentation=presentation
                )
                authority = self._require_current_action_authority(
                    conn,
                    action=action,
                    relationship=relationship,
                    resource=resource,
                )
                source = conn.execute(
                    select(schema.interaction_event).where(
                        schema.interaction_event.c.event_id
                        == command.source_interaction_event_id
                    )
                ).mappings().one_or_none()
                if (
                    source is None
                    or source["event_kind"] != "COUNTERPART_INPUT"
                    or source["actor_kind"] != "COUNTERPART"
                    or source["actor_ref"] != action["counterpart_id"]
                    or source["relationship_id"] != action["relationship_id"]
                    or source["surface_binding_id"] != presentation["surface_binding_id"]
                    or source["channel_binding_id"] != presentation["channel_binding_id"]
                    or source["content_text"] != CALENDAR_CREATE_APPROVAL_TEXT
                ):
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID",
                        "Approval must come from the authorized counterpart on the same trusted route",
                    )
                source_seq = int(source["timeline_seq"])
                if (
                    source_seq <= int(presentation["presentation_timeline_frontier"])
                    or _aware_utc(source["recorded_at"])
                    < _aware_utc(presentation["presented_at"])
                ):
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID",
                        "Approval input must occur after the accepted faithful consent presentation",
                    )
                timeline = conn.execute(
                    select(schema.relationship_timeline_head).where(
                        schema.relationship_timeline_head.c.relationship_id
                        == action["relationship_id"]
                    )
                ).mappings().one_or_none()
                if timeline is None or int(timeline["last_timeline_seq"]) != source_seq:
                    fail(
                        "CALENDAR_CREATE_APPROVAL_SOURCE_NOT_CURRENT",
                        "Approval input must be the current counterpart Timeline event",
                    )

                existing = conn.execute(
                    select(schema.personal_calendar_create_approval).where(
                        schema.personal_calendar_create_approval.c.action_id
                        == action["action_id"]
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    if (
                        existing["approval_presentation_id"]
                        == command.approval_presentation_id
                        and existing["source_interaction_event_id"]
                        == command.source_interaction_event_id
                    ):
                        result_json = {
                            "approval_id": str(existing["approval_id"]),
                            "action_id": str(existing["action_id"]),
                            "approval_presentation_id": str(
                                existing["approval_presentation_id"]
                            ),
                            "revision": 1,
                        }
                        save_operation_receipt(
                            conn,
                            scope=_ADMIT_SCOPE,
                            operation_id=command.operation_id,
                            req_digest=req,
                            result_kind="PersonalCalendarCreateApproval",
                            result_ref=existing["approval_id"],
                            result_json=result_json,
                            committed_at=self.clock.now(),
                        )
                        return self._approval_result_from_json(result_json)
                    fail(
                        "CALENDAR_CREATE_APPROVAL_ALREADY_EXISTS",
                        "calendar-create Action already has an Approval",
                    )

                self._cas_head_same(
                    conn,
                    table=schema.personal_world_relationship_head,
                    key_name="relationship_id",
                    key_value=action["relationship_id"],
                    expected_revision=authority["relationship_revision"],
                    conflict_code="CALENDAR_CREATE_APPROVAL_RELATIONSHIP_CHANGED",
                )
                self._cas_head_same(
                    conn,
                    table=schema.personal_resource_binding_head,
                    key_name="personal_resource_binding_id",
                    key_value=action["personal_resource_binding_id"],
                    expected_revision=authority["resource_revision"],
                    conflict_code="CALENDAR_CREATE_APPROVAL_RESOURCE_CHANGED",
                )
                self._cas_head_same(
                    conn,
                    table=schema.personal_calendar_create_policy_head,
                    key_name="relationship_id",
                    key_value=action["relationship_id"],
                    expected_revision=authority["policy_revision"],
                    conflict_code="CALENDAR_CREATE_APPROVAL_POLICY_CHANGED",
                )
                self._cas_head_same(
                    conn,
                    table=schema.personal_calendar_write_permission_head,
                    key_name="permission_id",
                    key_value=action["write_permission_id"],
                    expected_revision=authority["permission_revision"],
                    conflict_code="CALENDAR_CREATE_APPROVAL_PERMISSION_CHANGED",
                )
                changed = conn.execute(
                    update(schema.relationship_timeline_head)
                    .where(
                        schema.relationship_timeline_head.c.relationship_id
                        == action["relationship_id"],
                        schema.relationship_timeline_head.c.last_timeline_seq
                        == source_seq,
                    )
                    .values(last_timeline_seq=source_seq)
                )
                if changed.rowcount != 1:
                    fail(
                        "CALENDAR_CREATE_APPROVAL_SOURCE_NOT_CURRENT",
                        "Approval source stopped being current during admission",
                    )

                approval_id = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_calendar_create_approval).values(
                        approval_id=approval_id,
                        action_id=action["action_id"],
                        approval_presentation_id=command.approval_presentation_id,
                        action_digest=action["action_digest"],
                        consent_payload_digest=presentation["consent_payload_digest"],
                        authorized_approver_ref=action["counterpart_id"],
                        source_interaction_event_id=command.source_interaction_event_id,
                        relationship_id=action["relationship_id"],
                        personal_resource_binding_id=action[
                            "personal_resource_binding_id"
                        ],
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                        approval_ceremony_source=CALENDAR_CREATE_APPROVAL_CEREMONY,
                        approval_policy_revision=authority["policy_revision"],
                        approval_policy_version=authority["policy"]["ai_policy_version"],
                        relationship_authority_revision=authority[
                            "relationship_revision"
                        ],
                        resource_binding_state_revision=authority[
                            "resource_revision"
                        ],
                        write_permission_id=action["write_permission_id"],
                        write_permission_state_revision=authority[
                            "permission_revision"
                        ],
                        granted_at=now,
                        expires_at=None,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_create_approval_state).values(
                        approval_id=approval_id,
                        revision=1,
                        parent_revision=None,
                        status="ACTIVE",
                        committed_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_create_approval_head).values(
                        approval_id=approval_id,
                        current_revision=1,
                    )
                )
                result_json = {
                    "approval_id": str(approval_id),
                    "action_id": str(action["action_id"]),
                    "approval_presentation_id": str(command.approval_presentation_id),
                    "revision": 1,
                }
                save_operation_receipt(
                    conn,
                    scope=_ADMIT_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateApproval",
                    result_ref=approval_id,
                    result_json=result_json,
                    committed_at=now,
                )
                return self._approval_result_from_json(result_json)
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_CONFLICT",
                "calendar-create Approval admission conflicted with durable state",
            ) from exc

    def revoke_create_approval(
        self, command: RevokePersonalCalendarCreateApprovalCommand
    ) -> PersonalCalendarCreateApprovalStateResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_REVOKE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return PersonalCalendarCreateApprovalStateResult(
                        approval_id=command.approval_id,
                        revision=int(replay["revision"]),
                    )
                approval = conn.execute(
                    select(schema.personal_calendar_create_approval).where(
                        schema.personal_calendar_create_approval.c.approval_id
                        == command.approval_id
                    )
                ).mappings().one_or_none()
                if approval is None:
                    fail(
                        "CALENDAR_CREATE_APPROVAL_NOT_FOUND",
                        "calendar-create Approval does not exist",
                    )
                state, revision = self._current_approval(conn, command.approval_id)
                if state["status"] == "REVOKED":
                    new_revision = revision
                else:
                    new_revision = revision + 1
                    now = self.clock.now()
                    conn.execute(
                        insert(schema.personal_calendar_create_approval_state).values(
                            approval_id=command.approval_id,
                            revision=new_revision,
                            parent_revision=revision,
                            status="REVOKED",
                            committed_at=now,
                        )
                    )
                    self._advance_head(
                        conn,
                        head_table=schema.personal_calendar_create_approval_head,
                        key_name="approval_id",
                        key_value=command.approval_id,
                        expected_revision=revision,
                        new_revision=new_revision,
                        conflict_code="CALENDAR_CREATE_APPROVAL_STATE_CONFLICT",
                    )
                now = self.clock.now()
                save_operation_receipt(
                    conn,
                    scope=_REVOKE_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateApprovalState",
                    result_ref=command.approval_id,
                    result_json={"revision": new_revision},
                    committed_at=now,
                )
                return PersonalCalendarCreateApprovalStateResult(
                    approval_id=command.approval_id,
                    revision=new_revision,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_STATE_CONFLICT",
                "calendar-create Approval state advanced concurrently",
            ) from exc

    def _bind_existing_presentation_operation(self, *, command, req, presentation):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PRESENT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._presentation_result_from_json(replay)
            current = conn.execute(
                select(schema.personal_calendar_create_approval_presentation).where(
                    schema.personal_calendar_create_approval_presentation.c.action_id
                    == command.action_id
                )
            ).mappings().one_or_none()
            if current is None:
                fail(
                    "CALENDAR_CREATE_APPROVAL_PRESENTATION_NOT_FOUND",
                    "approval presentation disappeared during deterministic replay",
                )
            return self._bind_existing_presentation_operation_in_connection(
                conn, command=command, req=req, presentation=dict(current)
            )

    def _bind_existing_presentation_operation_in_connection(
        self, conn, *, command, req, presentation
    ):
        result_json = self._presentation_result_json_from_row(presentation)
        save_operation_receipt(
            conn,
            scope=_PRESENT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="PersonalCalendarCreateApprovalPresentation",
            result_ref=presentation["approval_presentation_id"],
            result_json=result_json,
            committed_at=self.clock.now(),
        )
        return self._presentation_result_from_json(result_json)

    def _require_approval_adapter(self) -> CalendarApprovalPresentationAdapter:
        adapter = self.approval_adapter
        if adapter is None or not isinstance(adapter, CalendarApprovalPresentationAdapter):
            fail(
                "CALENDAR_CREATE_APPROVAL_ADAPTER_INELIGIBLE",
                "trusted calendar-create approval presentation adapter is required",
            )
        sink_ref = getattr(adapter, "sink_binding_ref", None)
        contract = getattr(adapter, "presentation_contract_version", None)
        if (
            not isinstance(sink_ref, str)
            or not sink_ref.strip()
            or len(sink_ref) > 128
            or not isinstance(contract, str)
            or not contract.strip()
            or len(contract) > 128
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_ADAPTER_INELIGIBLE",
                "approval presentation adapter must expose stable bounded identity and contract version",
            )
        return adapter

    def _load_action_lineage(self, conn, action_id: UUID):
        action = conn.execute(
            select(schema.personal_calendar_create_action).where(
                schema.personal_calendar_create_action.c.action_id == action_id
            )
        ).mappings().one_or_none()
        if action is None:
            fail("CALENDAR_CREATE_ACTION_NOT_FOUND", "calendar-create Action does not exist")
        source = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == action["source_interaction_event_id"]
            )
        ).mappings().one()
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == action["relationship_id"]
            )
        ).mappings().one()
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == action["personal_resource_binding_id"]
            )
        ).mappings().one()
        if (
            source["relationship_id"] != action["relationship_id"]
            or source["actor_kind"] != "COUNTERPART"
            or source["actor_ref"] != action["counterpart_id"]
            or relationship["counterpart_id"] != action["counterpart_id"]
            or resource["relationship_id"] != action["relationship_id"]
            or resource["counterpart_id"] != action["counterpart_id"]
        ):
            fail(
                "CALENDAR_CREATE_ACTION_PROVENANCE_INVALID",
                "calendar-create Action lineage is inconsistent",
            )
        if self._action_digest(action) != action["action_digest"]:
            fail(
                "CALENDAR_CREATE_ACTION_DIGEST_INVALID",
                "calendar-create Action digest does not match immutable semantics",
            )
        return dict(action), dict(source), dict(relationship), dict(resource)

    def _require_current_action_authority(self, conn, *, action, relationship, resource):
        relationship_state, relationship_revision = self._current_relationship_authority(
            conn, action["relationship_id"]
        )
        if relationship_state["status"] != "ACTIVE":
            fail("RELATIONSHIP_NOT_ACTIVE", "calendar-create relationship authority is not active")
        current_resource, resource_state, resource_revision = self._current_resource(
            conn, action["personal_resource_binding_id"]
        )
        active = self._active_calendar_bindings(conn, action["relationship_id"])
        if (
            resource_state["status"] != "ACTIVE"
            or current_resource["relationship_id"] != action["relationship_id"]
            or current_resource["counterpart_id"] != action["counterpart_id"]
            or len(active) != 1
            or active[0]["personal_resource_binding_id"]
            != action["personal_resource_binding_id"]
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_RESOURCE_NOT_CURRENT",
                "calendar-create Approval target is not the unique active calendar",
            )
        policy, policy_revision = self._current_create_policy(conn, action["relationship_id"])
        if (
            policy["status"] != "ALLOW"
            or policy["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
            or policy["capability_effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
            or policy["capability_contract_version"] != action["capability_contract_version"]
            or str(action["personal_resource_binding_id"])
            not in policy["allowed_resource_binding_ids_json"]
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_POLICY_DENIED",
                "current calendar-create policy does not permit Approval",
            )
        grant = conn.execute(
            select(schema.personal_calendar_write_permission_grant).where(
                schema.personal_calendar_write_permission_grant.c.permission_id
                == action["write_permission_id"]
            )
        ).mappings().one_or_none()
        if grant is None:
            fail(
                "CALENDAR_CREATE_APPROVAL_PERMISSION_DENIED",
                "calendar-create Action write Permission no longer exists",
            )
        permission_state, permission_revision = self._current_write_permission(
            conn, action["write_permission_id"]
        )
        now = _aware_utc(self.clock.now())
        if (
            permission_state["status"] != "ACTIVE"
            or grant["holder_companion_person_id"] != relationship["companion_person_id"]
            or grant["counterpart_id"] != action["counterpart_id"]
            or grant["relationship_id"] != action["relationship_id"]
            or grant["personal_resource_binding_id"] != action["personal_resource_binding_id"]
            or grant["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
            or grant["capability_contract_version"] != action["capability_contract_version"]
            or grant["operation_class"] != CALENDAR_CREATE_EFFECT_CLASS
            or grant["grantor_ref"] != action["counterpart_id"]
            or grant["grant_policy_version"] != policy["permission_grant_policy_version"]
            or (
                grant["expires_at"] is not None
                and _aware_utc(grant["expires_at"]) <= now
            )
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_PERMISSION_DENIED",
                "current write Permission does not authorize the exact Action",
            )
        return {
            "relationship_revision": relationship_revision,
            "resource_revision": resource_revision,
            "policy_revision": policy_revision,
            "permission_revision": permission_revision,
            "policy": dict(policy),
        }

    def _require_presentation_equivalence(self, *, action, resource, presentation) -> None:
        consent = self._consent_payload(action=action, resource=resource)
        expected_digest = sha256_text(canonical_json(consent))
        if (
            presentation["action_id"] != action["action_id"]
            or presentation["action_digest"] != action["action_digest"]
            or presentation["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
            or presentation["effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
            or presentation["personal_resource_binding_id"] != action["personal_resource_binding_id"]
            or presentation["target_calendar_display_identity"]
            != consent["target_calendar_display_identity"]
            or presentation["summary"] != action["summary"]
            or presentation["start_text"] != action["start_text"]
            or presentation["end_text"] != action["end_text"]
            or _aware_utc(presentation["normalized_start_at"])
            != _aware_utc(action["normalized_start_at"])
            or _aware_utc(presentation["normalized_end_at"])
            != _aware_utc(action["normalized_end_at"])
            or presentation["consent_rendering_version"]
            != CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION
            or presentation["consent_payload_digest"] != expected_digest
            or not presentation["presentation_acceptance_ref"]
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_SEMANTIC_MISMATCH",
                "presented consent does not mechanically equal the immutable Action",
            )

    def _consent_payload(self, *, action, resource) -> dict[str, Any]:
        return {
            "consent_rendering_version": CALENDAR_CREATE_APPROVAL_CONSENT_RENDERING_VERSION,
            "action_id": str(action["action_id"]),
            "action_digest": action["action_digest"],
            "capability_semantic_operation": CALENDAR_EVENT_CREATE,
            "effect_class": CALENDAR_CREATE_EFFECT_CLASS,
            "personal_resource_binding_id": str(action["personal_resource_binding_id"]),
            "target_calendar_display_identity": self._display_identity(resource),
            "summary": action["summary"],
            "start_text": action["start_text"],
            "end_text": action["end_text"],
            "normalized_start_at": _aware_utc(action["normalized_start_at"]).isoformat(),
            "normalized_end_at": _aware_utc(action["normalized_end_at"]).isoformat(),
        }

    @staticmethod
    def _render_consent(consent: dict[str, Any]) -> str:
        return (
            "Approve this calendar mutation?\n"
            f"Calendar: {consent['target_calendar_display_identity']}\n"
            f"Title: {consent['summary']}\n"
            f"Start: {consent['start_text']} ({consent['normalized_start_at']})\n"
            f"End: {consent['end_text']} ({consent['normalized_end_at']})\n"
            f"Capability: {consent['capability_semantic_operation']}\n"
            f"Effect: {consent['effect_class']}"
        )

    @staticmethod
    def _display_identity(resource) -> str:
        system_ref = str(resource["external_system_ref"]).strip()
        resource_ref = str(resource["external_resource_ref"]).strip()
        if not system_ref or not resource_ref:
            fail(
                "CALENDAR_CREATE_APPROVAL_DISPLAY_IDENTITY_INVALID",
                "calendar target lacks trusted display identity",
            )
        return f"{system_ref}:{resource_ref}"

    @staticmethod
    def _presentation_key(*, action_id: UUID, surface_binding_id: UUID, channel_binding_id: UUID) -> str:
        digest = sha256_text(
            canonical_json(
                {
                    "action_id": action_id,
                    "surface_binding_id": surface_binding_id,
                    "channel_binding_id": channel_binding_id,
                    "purpose": "calendar.event.create.approval",
                }
            )
        )
        return f"calendar-create-approval:{digest}"

    @staticmethod
    def _action_digest(action) -> str:
        return sha256_text(
            canonical_json(
                {
                    "action_schema_version": CALENDAR_CREATE_ACTION_SCHEMA_VERSION,
                    "relationship_id": str(action["relationship_id"]),
                    "personal_resource_binding_id": str(action["personal_resource_binding_id"]),
                    "source_interaction_event_id": str(action["source_interaction_event_id"]),
                    "summary": action["summary"],
                    "start_text": action["start_text"],
                    "end_text": action["end_text"],
                    "normalized_start_at": _aware_utc(action["normalized_start_at"]).isoformat(),
                    "normalized_end_at": _aware_utc(action["normalized_end_at"]).isoformat(),
                    "capability_semantic_operation": CALENDAR_EVENT_CREATE,
                    "capability_contract_version": action["capability_contract_version"],
                }
            )
        )

    def _current_approval(self, conn, approval_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_create_approval_head).where(
                schema.personal_calendar_create_approval_head.c.approval_id == approval_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "CALENDAR_CREATE_APPROVAL_STATE_MISSING",
                "calendar-create Approval state is missing",
            )
        revision = int(head["current_revision"])
        state = conn.execute(
            select(schema.personal_calendar_create_approval_state).where(
                schema.personal_calendar_create_approval_state.c.approval_id == approval_id,
                schema.personal_calendar_create_approval_state.c.revision == revision,
            )
        ).mappings().one_or_none()
        if state is None:
            fail(
                "CALENDAR_CREATE_APPROVAL_STATE_MISSING",
                "calendar-create Approval revision is missing",
            )
        return dict(state), revision

    @staticmethod
    def _presentation_result_json(
        *, presentation_id, action, consent_digest, presentation_key, acceptance_ref, presented_at
    ):
        return {
            "approval_presentation_id": str(presentation_id),
            "action_id": str(action["action_id"]),
            "action_digest": action["action_digest"],
            "consent_payload_digest": consent_digest,
            "presentation_key": presentation_key,
            "acceptance_ref": acceptance_ref,
            "presented_at": presented_at.isoformat(),
        }

    @staticmethod
    def _presentation_result_json_from_row(row):
        return {
            "approval_presentation_id": str(row["approval_presentation_id"]),
            "action_id": str(row["action_id"]),
            "action_digest": row["action_digest"],
            "consent_payload_digest": row["consent_payload_digest"],
            "presentation_key": row["presentation_key"],
            "acceptance_ref": row["presentation_acceptance_ref"],
            "presented_at": row["presented_at"].isoformat(),
        }

    @staticmethod
    def _presentation_result_from_json(payload: dict[str, Any]):
        return PersonalCalendarCreateApprovalPresentationResult(
            approval_presentation_id=UUID(payload["approval_presentation_id"]),
            action_id=UUID(payload["action_id"]),
            action_digest=payload["action_digest"],
            consent_payload_digest=payload["consent_payload_digest"],
            presentation_key=payload["presentation_key"],
            acceptance_ref=payload["acceptance_ref"],
            presented_at=datetime.fromisoformat(payload["presented_at"]),
        )

    @staticmethod
    def _approval_result_from_json(payload: dict[str, Any]):
        return PersonalCalendarCreateApprovalResult(
            approval_id=UUID(payload["approval_id"]),
            action_id=UUID(payload["action_id"]),
            approval_presentation_id=UUID(payload["approval_presentation_id"]),
            revision=int(payload["revision"]),
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["PersonalCalendarApprovalServices"]
