from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_CONSENT_RENDERING_VERSION,
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
    CalendarCreateApprovalPresentationAcceptance,
    CalendarCreateApprovalPresentationResult,
    CalendarCreateApprovalPresenter,
    PresentCalendarCreateApprovalCommand,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar_mutation_action import _aware_compare
from alsoul.services.personal_calendar_mutation_policy import PersonalCalendarMutationPolicyServices
from alsoul.storage import schema

_APPROVAL_PRESENTATION_SCOPE = "PresentCalendarCreateApproval"
_APPROVAL_PRESENTATION_CONTRACT_VERSION = "CALENDAR_CREATE_APPROVAL_PRESENTATION_V1"


class PersonalCalendarMutationPresentationServices(PersonalCalendarMutationPolicyServices):
    def __init__(
        self,
        *args,
        approval_presenter: CalendarCreateApprovalPresenter | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.approval_presenter = approval_presenter

    def present_action_for_approval(
        self, command: PresentCalendarCreateApprovalCommand
    ) -> CalendarCreateApprovalPresentationResult:
        if self.approval_presenter is None:
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTER_UNAVAILABLE",
                "trusted first-party approval presenter is required",
            )
        if (
            getattr(self.approval_presenter, "presentation_contract_version", None)
            != _APPROVAL_PRESENTATION_CONTRACT_VERSION
            or not isinstance(
                getattr(self.approval_presenter, "presenter_binding_ref", None), str
            )
            or not self.approval_presenter.presenter_binding_ref.strip()
            or not callable(getattr(self.approval_presenter, "present_approval", None))
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTER_INELIGIBLE",
                "approval presenter lacks the trusted first-party contract",
            )
        if command.consent_rendering_version != CALENDAR_CREATE_CONSENT_RENDERING_VERSION:
            fail(
                "CALENDAR_CREATE_CONSENT_RENDERING_INVALID",
                "approval presentation rendering contract is unsupported",
            )
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_APPROVAL_PRESENTATION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateApprovalPresentationResult(
                    approval_presentation_id=UUID(replay["approval_presentation_id"]),
                    action_id=UUID(replay["action_id"]),
                    consent_payload_digest=replay["consent_payload_digest"],
                    presentation_acceptance_ref=replay["presentation_acceptance_ref"],
                )
            context = self._approval_presentation_context(conn, command)
        presentation_id = self.ids.new()
        payload = self._consent_payload(
            context["action"],
            context["resource"],
            command.consent_rendering_version,
        )
        payload_text = canonical_json(payload)
        payload_digest = sha256_text(payload_text)
        try:
            acceptance = self.approval_presenter.present_approval(
                approval_presentation_id=presentation_id,
                surface_binding_id=command.surface_binding_id,
                channel_binding_id=command.channel_binding_id,
                consent_payload_text=payload_text,
                consent_payload_digest=payload_digest,
            )
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_UNCONFIRMED",
                "approval presentation acceptance was not established",
            ) from exc
        if not isinstance(acceptance, CalendarCreateApprovalPresentationAcceptance):
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_UNCONFIRMED",
                "approval presenter returned an untrusted acceptance result",
            )
        acceptance_ref = acceptance.presentation_acceptance_ref.strip()
        if not acceptance_ref or len(acceptance_ref) > 128:
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_UNCONFIRMED",
                "approval presentation acceptance reference is invalid",
            )

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_APPROVAL_PRESENTATION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateApprovalPresentationResult(
                    approval_presentation_id=UUID(replay["approval_presentation_id"]),
                    action_id=UUID(replay["action_id"]),
                    consent_payload_digest=replay["consent_payload_digest"],
                    presentation_acceptance_ref=replay["presentation_acceptance_ref"],
                )
            current = self._approval_presentation_context(conn, command)
            if current["timeline_frontier"] != context["timeline_frontier"]:
                fail(
                    "CALENDAR_CREATE_APPROVAL_PRESENTATION_STALE",
                    "relationship Timeline changed while approval consent was being presented",
                )
            if current["action"]["action_digest"] != context["action"]["action_digest"]:
                fail(
                    "CALENDAR_CREATE_ACTION_CHANGED",
                    "immutable calendar Action changed unexpectedly",
                )
            now = self.clock.now()
            action = current["action"]
            resource = current["resource"]
            conn.execute(
                insert(schema.personal_calendar_approval_presentation).values(
                    approval_presentation_id=presentation_id,
                    action_id=action["action_id"],
                    action_digest=action["action_digest"],
                    capability_semantic_operation=CALENDAR_EVENT_CREATE,
                    effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                    personal_resource_binding_id=action[
                        "personal_resource_binding_id"
                    ],
                    target_calendar_display_identity=self._target_display_identity(
                        resource
                    ),
                    title=action["title"],
                    start_timestamp_text=action["start_timestamp_text"],
                    end_timestamp_text=action["end_timestamp_text"],
                    normalized_start_at=action["normalized_start_at"],
                    normalized_end_at=action["normalized_end_at"],
                    consent_rendering_version=command.consent_rendering_version,
                    consent_payload_digest=payload_digest,
                    presented_to_counterpart_id=action["counterpart_id"],
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                    source_timeline_frontier=current["timeline_frontier"],
                    presented_at=now,
                    presentation_acceptance_ref=acceptance_ref,
                )
            )
            save_operation_receipt(
                conn,
                scope=_APPROVAL_PRESENTATION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarApprovalPresentation",
                result_ref=presentation_id,
                result_json={
                    "approval_presentation_id": str(presentation_id),
                    "action_id": str(action["action_id"]),
                    "consent_payload_digest": payload_digest,
                    "presentation_acceptance_ref": acceptance_ref,
                },
                committed_at=now,
            )
        return CalendarCreateApprovalPresentationResult(
            presentation_id,
            command.action_id,
            payload_digest,
            acceptance_ref,
        )

    def _approval_presentation_context(self, conn, command):
        action = self._action(conn, command.action_id)
        source = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == action["source_interaction_event_id"]
            )
        ).mappings().one()
        timeline = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id
                == action["relationship_id"]
            )
        ).mappings().one_or_none()
        if timeline is None or int(timeline["last_timeline_seq"]) != int(
            source["timeline_seq"]
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_STALE",
                "approval consent may be presented only while the Action request is current",
            )
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == action["relationship_id"]
            )
        ).mappings().one()
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
                "CALENDAR_CREATE_APPROVAL_PRESENTATION_INELIGIBLE",
                "Action relationship/resource is no longer current",
            )
        if (
            source["surface_binding_id"] != command.surface_binding_id
            or source["channel_binding_id"] != command.channel_binding_id
        ):
            fail(
                "CALENDAR_CREATE_APPROVAL_ROUTE_MISMATCH",
                "approval consent must use the originating trusted first-party route",
            )
        self._require_presence(
            conn,
            relationship["companion_person_id"],
            command.surface_binding_id,
            command.channel_binding_id,
        )
        return {
            "action": action,
            "resource": resource,
            "timeline_frontier": int(timeline["last_timeline_seq"]),
        }

    def _consent_payload(self, action, resource, rendering_version: str) -> dict[str, Any]:
        return {
            "consent_rendering_version": rendering_version,
            "action_id": str(action["action_id"]),
            "action_digest": action["action_digest"],
            "capability": CALENDAR_EVENT_CREATE,
            "effect_class": CALENDAR_CREATE_EFFECT_CLASS,
            "target_calendar": self._target_display_identity(resource),
            "title": action["title"],
            "start_timestamp": action["start_timestamp_text"],
            "end_timestamp": action["end_timestamp_text"],
            "normalized_start_at": _aware_compare(action["normalized_start_at"]).isoformat(),
            "normalized_end_at": _aware_compare(action["normalized_end_at"]).isoformat(),
        }

    def _target_display_identity(self, resource) -> str:
        return f"{resource['external_system_ref']}:{resource['external_resource_ref']}"

    def _action(self, conn, action_id: UUID):
        row = conn.execute(
            select(schema.personal_calendar_action).where(
                schema.personal_calendar_action.c.action_id == action_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail("CALENDAR_CREATE_ACTION_NOT_FOUND", "calendar-create Action does not exist")
        return row

    def _require_presence(
        self,
        conn,
        companion_person_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
    ) -> None:
        surface = conn.execute(
            select(schema.surface_binding).where(
                schema.surface_binding.c.surface_binding_id == surface_binding_id,
                schema.surface_binding.c.companion_person_id == companion_person_id,
            )
        ).mappings().one_or_none()
        channel = conn.execute(
            select(schema.channel_binding).where(
                schema.channel_binding.c.channel_binding_id == channel_binding_id,
                schema.channel_binding.c.companion_person_id == companion_person_id,
            )
        ).mappings().one_or_none()
        if surface is None or channel is None:
            fail(
                "CALENDAR_CREATE_APPROVAL_ROUTE_MISMATCH",
                "approval route is not bound to the Action companion",
            )


__all__ = ["PersonalCalendarMutationPresentationServices"]
