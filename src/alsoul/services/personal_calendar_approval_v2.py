from __future__ import annotations

from datetime import datetime, timezone

from alsoul.domain.errors import fail
from alsoul.services.personal_calendar_approval import (
    PersonalCalendarApprovalServices as PersonalCalendarApprovalServicesV1,
)


class PersonalCalendarApprovalServices(PersonalCalendarApprovalServicesV1):
    """Current F5.B Approval boundary with stricter durable-provenance validation."""

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
