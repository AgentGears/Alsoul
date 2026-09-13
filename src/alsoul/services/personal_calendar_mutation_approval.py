from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import insert, select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_APPROVAL_TEXT,
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
    CalendarCreateApprovalResult,
    CalendarCreateAuthorityStateResult,
    GrantCalendarCreateApprovalCommand,
    RevokeCalendarCreateApprovalCommand,
)
from alsoul.services.common import canonical_json, load_operation_receipt, request_digest, save_operation_receipt, sha256_text
from alsoul.services.personal_calendar_mutation_action import _aware_compare
from alsoul.services.personal_calendar_mutation_presentation import PersonalCalendarMutationPresentationServices
from alsoul.storage import schema

_APPROVAL_SCOPE = "GrantCalendarCreateApproval"
_REVOKE_APPROVAL_SCOPE = "RevokeCalendarCreateApproval"


class PersonalCalendarMutationAuthorityServices(PersonalCalendarMutationPresentationServices):
    def grant_approval(
        self, command: GrantCalendarCreateApprovalCommand
    ) -> CalendarCreateApprovalResult:
        req = request_digest(asdict(command))
        if not command.approval_policy_version.strip():
            fail(
                "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID",
                "approval policy version must be explicit",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_APPROVAL_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateApprovalResult(
                    UUID(replay["approval_id"]), UUID(replay["action_id"])
                )
            action = self._action(conn, command.action_id)
            presentation = conn.execute(
                select(schema.personal_calendar_approval_presentation).where(
                    schema.personal_calendar_approval_presentation.c.approval_presentation_id
                    == command.approval_presentation_id
                )
            ).mappings().one_or_none()
            if presentation is None:
                fail(
                    "CALENDAR_CREATE_APPROVAL_PRESENTATION_MISSING",
                    "approval requires trusted presentation provenance",
                )
            self._validate_presentation_equivalence(conn, action, presentation)
            source = self._counterpart_event(
                conn,
                command.source_interaction_event_id,
                required_text=CALENDAR_CREATE_APPROVAL_TEXT,
                require_frontier=True,
            )
            if (
                source["relationship_id"] != action["relationship_id"]
                or source["actor_ref"] != action["counterpart_id"]
                or source["surface_binding_id"] != presentation["surface_binding_id"]
                or source["channel_binding_id"] != presentation["channel_binding_id"]
                or int(source["timeline_seq"])
                != int(presentation["source_timeline_frontier"]) + 1
                or _aware_compare(source["recorded_at"])
                < _aware_compare(presentation["presented_at"])
            ):
                fail(
                    "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID",
                    "approval input does not bind the exact trusted consent presentation",
                )
            relationship_state, _ = self._current_relationship_authority(
                conn, action["relationship_id"]
            )
            resource, resource_state, _ = self._current_resource(
                conn, action["personal_resource_binding_id"]
            )
            if (
                relationship_state["status"] != "ACTIVE"
                or resource_state["status"] != "ACTIVE"
                or resource["relationship_id"] != action["relationship_id"]
                or resource["counterpart_id"] != action["counterpart_id"]
            ):
                fail(
                    "CALENDAR_CREATE_APPROVER_NOT_CURRENT",
                    "approval cannot be admitted for an inactive relationship/resource",
                )
            policy, policy_revision = self._current_write_policy(
                conn, action["relationship_id"]
            )
            if (
                policy["status"] != "ALLOW"
                or policy["approval_policy_version"]
                != command.approval_policy_version
                or policy["capability_contract_version"]
                != action["capability_contract_version"]
                or str(action["personal_resource_binding_id"])
                not in {
                    str(value)
                    for value in policy["allowed_resource_binding_ids_json"]
                }
            ):
                fail(
                    "CALENDAR_CREATE_APPROVAL_POLICY_MISMATCH",
                    "approval is not recognized by the current calendar-create policy",
                )
            if conn.execute(
                select(schema.personal_calendar_approval.c.approval_id).where(
                    schema.personal_calendar_approval.c.source_interaction_event_id
                    == command.source_interaction_event_id
                )
            ).scalar_one_or_none() is not None:
                fail(
                    "CALENDAR_CREATE_APPROVAL_PROVENANCE_REUSED",
                    "one counterpart approval event cannot mint multiple Approvals",
                )
            now = self.clock.now()
            if command.expires_at is not None and _aware_compare(command.expires_at) <= _aware_compare(now):
                fail(
                    "CALENDAR_CREATE_APPROVAL_EXPIRY_INVALID",
                    "Approval expiry must be in the future",
                )
            approval_id = self.ids.new()
            conn.execute(
                insert(schema.personal_calendar_approval).values(
                    approval_id=approval_id,
                    action_id=action["action_id"],
                    action_digest=action["action_digest"],
                    approval_presentation_id=presentation[
                        "approval_presentation_id"
                    ],
                    consent_payload_digest=presentation[
                        "consent_payload_digest"
                    ],
                    approver_ref=action["counterpart_id"],
                    grant_source="FIRST_PARTY_COUNTERPART",
                    approval_policy_version=command.approval_policy_version,
                    write_policy_revision=policy_revision,
                    relationship_id=action["relationship_id"],
                    personal_resource_binding_id=action[
                        "personal_resource_binding_id"
                    ],
                    source_interaction_event_id=command.source_interaction_event_id,
                    granted_at=now,
                    expires_at=command.expires_at,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_approval_state).values(
                    approval_id=approval_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_approval_head).values(
                    approval_id=approval_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=_APPROVAL_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarApproval",
                result_ref=approval_id,
                result_json={
                    "approval_id": str(approval_id),
                    "action_id": str(action["action_id"]),
                },
                committed_at=now,
            )
            return CalendarCreateApprovalResult(approval_id, action["action_id"])

    def revoke_approval(
        self, command: RevokeCalendarCreateApprovalCommand
    ) -> CalendarCreateAuthorityStateResult:
        return self._revoke_state(
            operation_id=command.operation_id,
            entity_id=command.approval_id,
            scope=_REVOKE_APPROVAL_SCOPE,
            entity_table=schema.personal_calendar_approval,
            entity_key="approval_id",
            state_table=schema.personal_calendar_approval_state,
            head_table=schema.personal_calendar_approval_head,
            result_kind="PersonalCalendarApprovalState",
        )

    def _validate_presentation_equivalence(self, conn, action, presentation) -> None:
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == action["personal_resource_binding_id"]
            )
        ).mappings().one()
        expected_payload = self._consent_payload(
            action,
            resource,
            presentation["consent_rendering_version"],
        )
        expected_digest = sha256_text(canonical_json(expected_payload))
        if (
            presentation["action_id"] != action["action_id"]
            or presentation["action_digest"] != action["action_digest"]
            or presentation["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
            or presentation["effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
            or presentation["personal_resource_binding_id"]
            != action["personal_resource_binding_id"]
            or presentation["target_calendar_display_identity"]
            != self._target_display_identity(resource)
            or presentation["title"] != action["title"]
            or presentation["start_timestamp_text"] != action["start_timestamp_text"]
            or presentation["end_timestamp_text"] != action["end_timestamp_text"]
            or _aware_compare(presentation["normalized_start_at"])
            != _aware_compare(action["normalized_start_at"])
            or _aware_compare(presentation["normalized_end_at"])
            != _aware_compare(action["normalized_end_at"])
            or presentation["consent_payload_digest"] != expected_digest
            or presentation["presented_to_counterpart_id"]
            != action["counterpart_id"]
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_SEMANTICS_MISMATCH",
                "trusted consent presentation does not mechanically equal the immutable Action",
            )


from uuid import UUID

__all__ = ["PersonalCalendarMutationAuthorityServices"]
