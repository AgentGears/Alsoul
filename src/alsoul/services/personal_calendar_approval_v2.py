from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_action import (
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
)
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    CALENDAR_CREATE_APPROVAL_CEREMONY,
    PersonalCalendarCreateApprovalResult,
    calendar_create_approval_challenge,
)
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.personal_calendar_approval import (
    PersonalCalendarApprovalServices as PersonalCalendarApprovalServicesV1,
)
from alsoul.storage import schema

_ADMIT_SCOPE = "AdmitPersonalCalendarCreateApproval"


class PersonalCalendarApprovalServices(PersonalCalendarApprovalServicesV1):
    """Current F5.B Approval boundary with exact presentation-bound consent replies."""

    def _consent_payload(self, *, action, resource):
        consent = super()._consent_payload(action=action, resource=resource)
        summary = consent["summary"]
        if (
            not isinstance(summary, str)
            or not summary
            or _contains_control_character(summary)
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_SUMMARY_UNSAFE",
                "calendar event summary must be non-empty and free of control characters for faithful consent presentation",
            )
        consent["approval_challenge"] = calendar_create_approval_challenge(
            action["action_digest"]
        )
        return consent

    @staticmethod
    def _render_consent(consent):
        return (
            "Approve this calendar mutation?\n"
            f"Calendar: {consent['target_calendar_display_identity']}\n"
            f"Title: {consent['summary']}\n"
            f"Start: {consent['start_text']} ({consent['normalized_start_at']})\n"
            f"End: {consent['end_text']} ({consent['normalized_end_at']})\n"
            f"Capability: {consent['capability_semantic_operation']}\n"
            f"Effect: {consent['effect_class']}\n"
            f"Reply exactly: {consent['approval_challenge']}"
        )

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

                action, action_source, relationship, resource = self._load_action_lineage(
                    conn, presentation["action_id"]
                )
                if (
                    presentation["surface_binding_id"]
                    != action_source["surface_binding_id"]
                    or presentation["channel_binding_id"]
                    != action_source["channel_binding_id"]
                ):
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID",
                        "approval presentation route does not match the immutable Action source route",
                    )
                self._require_presentation_equivalence(
                    action=action,
                    resource=resource,
                    presentation=presentation,
                )
                authority = self._require_current_action_authority(
                    conn,
                    action=action,
                    relationship=relationship,
                    resource=resource,
                )
                expected_challenge = calendar_create_approval_challenge(
                    action["action_digest"]
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
                    or source["content_text"] != expected_challenge
                ):
                    fail(
                        "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID",
                        "Approval must be the exact Action-bound reply from the authorized counterpart on the same trusted route",
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
                return PersonalCalendarCreateApprovalResult(
                    approval_id=approval_id,
                    action_id=action["action_id"],
                    approval_presentation_id=command.approval_presentation_id,
                    revision=1,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_CONFLICT",
                "calendar-create Approval admission conflicted with durable state",
            ) from exc

    def _require_presentation_equivalence(self, *, action, resource, presentation) -> None:
        super()._require_presentation_equivalence(
            action=action,
            resource=resource,
            presentation=presentation,
        )
        sink_binding_ref = presentation["sink_binding_ref"]
        presentation_contract_version = presentation["presentation_contract_version"]
        if (
            presentation["presented_to_counterpart_id"] != action["counterpart_id"]
            or not isinstance(sink_binding_ref, str)
            or not sink_binding_ref.strip()
            or len(sink_binding_ref) > 128
            or not isinstance(presentation_contract_version, str)
            or not presentation_contract_version.strip()
            or len(presentation_contract_version) > 128
            or presentation["presentation_key"]
            != self._presentation_key(
                action_id=action["action_id"],
                surface_binding_id=presentation["surface_binding_id"],
                channel_binding_id=presentation["channel_binding_id"],
            )
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_PROVENANCE_INVALID",
                "approval presentation provenance does not bind the exact Action, counterpart, route, and sink contract",
            )

    @staticmethod
    def _display_identity(resource) -> str:
        system_ref = str(resource["external_system_ref"]).strip()
        resource_ref = str(resource["external_resource_ref"]).strip()
        if (
            not system_ref
            or not resource_ref
            or _contains_control_character(system_ref)
            or _contains_control_character(resource_ref)
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_DISPLAY_IDENTITY_INVALID",
                "calendar target display identity must be non-empty and free of control characters",
            )
        return f"{system_ref}:{resource_ref}"

    @staticmethod
    def _presentation_result_json_from_row(row):
        presented_at = _aware_utc(row["presented_at"])
        return {
            "approval_presentation_id": str(row["approval_presentation_id"]),
            "action_id": str(row["action_id"]),
            "action_digest": row["action_digest"],
            "consent_payload_digest": row["consent_payload_digest"],
            "presentation_key": row["presentation_key"],
            "acceptance_ref": row["presentation_acceptance_ref"],
            "presented_at": presented_at.isoformat(),
        }


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["PersonalCalendarApprovalServices"]
