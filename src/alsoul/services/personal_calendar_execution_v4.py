from __future__ import annotations

from alsoul.services.personal_calendar_execution_v3 import (
    PersonalCalendarExecutionServices as PersonalCalendarExecutionServicesV3,
)
from alsoul.storage import schema


class PersonalCalendarExecutionServices(PersonalCalendarExecutionServicesV3):
    """Current execution boundary with atomic fresh-authority admission.

    The retry transition must not merely observe current mutation authority; the same
    transaction that creates the next attempt must linearize against every mutable
    authority head. The inherited dispatch-fence path repeats these harmless same-head
    CAS writes before pinning its fence, while ordinary preparation also becomes
    race-safe under the same stronger invariant.
    """

    def _require_execution_authority(
        self,
        conn,
        *,
        action,
        relationship,
        resource,
        approval_id,
        credential_binding_id,
        require_binding,
    ):
        authority = super()._require_execution_authority(
            conn,
            action=action,
            relationship=relationship,
            resource=resource,
            approval_id=approval_id,
            credential_binding_id=credential_binding_id,
            require_binding=require_binding,
        )
        self._cas_head_same(
            conn,
            table=schema.personal_world_relationship_head,
            key_name="relationship_id",
            key_value=action["relationship_id"],
            expected_revision=authority["relationship_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_RELATIONSHIP_CHANGED",
        )
        self._cas_head_same(
            conn,
            table=schema.personal_resource_binding_head,
            key_name="personal_resource_binding_id",
            key_value=action["personal_resource_binding_id"],
            expected_revision=authority["resource_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_RESOURCE_CHANGED",
        )
        self._cas_head_same(
            conn,
            table=schema.personal_calendar_create_policy_head,
            key_name="relationship_id",
            key_value=action["relationship_id"],
            expected_revision=authority["policy_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_POLICY_CHANGED",
        )
        self._cas_head_same(
            conn,
            table=schema.personal_calendar_write_permission_head,
            key_name="permission_id",
            key_value=action["write_permission_id"],
            expected_revision=authority["permission_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_PERMISSION_CHANGED",
        )
        self._cas_head_same(
            conn,
            table=schema.personal_calendar_create_approval_head,
            key_name="approval_id",
            key_value=approval_id,
            expected_revision=authority["approval_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_APPROVAL_CHANGED",
        )
        self._cas_head_same(
            conn,
            table=schema.credential_binding_head,
            key_name="credential_binding_id",
            key_value=credential_binding_id,
            expected_revision=authority["credential_revision"],
            conflict_code="CALENDAR_CREATE_EXECUTION_CREDENTIAL_CHANGED",
        )
        return authority


__all__ = ["PersonalCalendarExecutionServices"]
