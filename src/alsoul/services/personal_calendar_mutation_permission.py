from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT,
    CALENDAR_EVENT_CREATE,
    CalendarCreateAuthorityStateResult,
    CalendarCreateWritePermissionResult,
    GrantCalendarCreatePermissionCommand,
    RevokeCalendarCreatePermissionCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.personal_calendar_mutation_action import (
    PersonalCalendarMutationActionServices,
    _aware_compare,
)
from alsoul.storage import schema

_WRITE_PERMISSION_SCOPE = "GrantCalendarCreatePermission"
_REVOKE_PERMISSION_SCOPE = "RevokeCalendarCreatePermission"


class PersonalCalendarMutationPermissionServices(PersonalCalendarMutationActionServices):
    def grant_write_permission(
        self, command: GrantCalendarCreatePermissionCommand
    ) -> CalendarCreateWritePermissionResult:
        req = request_digest(asdict(command))
        if not command.capability_contract_version.strip() or not command.grant_policy_version.strip():
            fail(
                "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                "write Permission requires explicit capability and grant policy versions",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_WRITE_PERMISSION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateWritePermissionResult(UUID(replay["permission_id"]))
            source = self._counterpart_event(
                conn,
                command.source_interaction_event_id,
                required_text=CALENDAR_CREATE_WRITE_PERMISSION_GRANT_TEXT,
                require_frontier=True,
            )
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == source["relationship_id"]
                )
            ).mappings().one()
            relationship_state, _ = self._current_relationship_authority(
                conn, source["relationship_id"]
            )
            if relationship_state["status"] != "ACTIVE":
                fail("RELATIONSHIP_NOT_ACTIVE", "write Permission relationship is not active")
            active = self._active_calendar_bindings(conn, source["relationship_id"])
            if len(active) != 1:
                fail(
                    "PERMISSION_RESOURCE_MISMATCH",
                    "write Permission requires the unique active calendar resource",
                )
            resource = active[0]
            registration = conn.execute(
                select(schema.operation_receipt).where(
                    schema.operation_receipt.c.operation_scope
                    == "RegisterPersonalCalendarResource",
                    schema.operation_receipt.c.result_ref
                    == resource["personal_resource_binding_id"],
                )
            ).mappings().one_or_none()
            if registration is None or not isinstance(registration["result_json"], dict):
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "write Permission requires trusted calendar activation provenance",
                )
            activation_frontier = registration["result_json"].get(
                "activation_timeline_frontier"
            )
            if activation_frontier is None or int(source["timeline_seq"]) <= int(
                activation_frontier
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "write Permission grant must follow selected-resource activation",
                )
            if conn.execute(
                select(schema.personal_calendar_write_permission_grant.c.permission_id).where(
                    schema.personal_calendar_write_permission_grant.c.source_interaction_event_id
                    == command.source_interaction_event_id
                )
            ).scalar_one_or_none() is not None:
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_REUSED",
                    "one counterpart grant event cannot mint multiple write Permissions",
                )
            now = self.clock.now()
            if command.expires_at is not None and _aware_compare(command.expires_at) <= _aware_compare(now):
                fail(
                    "CALENDAR_CREATE_PERMISSION_EXPIRY_INVALID",
                    "write Permission expiry must be in the future",
                )
            permission_id = self.ids.new()
            conn.execute(
                insert(schema.personal_calendar_write_permission_grant).values(
                    permission_id=permission_id,
                    holder_companion_person_id=relationship["companion_person_id"],
                    counterpart_id=relationship["counterpart_id"],
                    relationship_id=source["relationship_id"],
                    personal_resource_binding_id=resource[
                        "personal_resource_binding_id"
                    ],
                    capability_semantic_operation=CALENDAR_EVENT_CREATE,
                    capability_contract_version=command.capability_contract_version,
                    operation_class="WRITE",
                    grantor_ref=relationship["counterpart_id"],
                    grant_source="FIRST_PARTY_COUNTERPART",
                    grant_policy_version=command.grant_policy_version,
                    constraints_json={"resource_kind": "CALENDAR"},
                    source_interaction_event_id=command.source_interaction_event_id,
                    granted_at=now,
                    expires_at=command.expires_at,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_write_permission_state).values(
                    permission_id=permission_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_write_permission_head).values(
                    permission_id=permission_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=_WRITE_PERMISSION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarWritePermission",
                result_ref=permission_id,
                result_json={"permission_id": str(permission_id)},
                committed_at=now,
            )
            return CalendarCreateWritePermissionResult(permission_id)

    def revoke_write_permission(
        self, command: RevokeCalendarCreatePermissionCommand
    ) -> CalendarCreateAuthorityStateResult:
        return self._revoke_state(
            operation_id=command.operation_id,
            entity_id=command.permission_id,
            scope=_REVOKE_PERMISSION_SCOPE,
            entity_table=schema.personal_calendar_write_permission_grant,
            entity_key="permission_id",
            state_table=schema.personal_calendar_write_permission_state,
            head_table=schema.personal_calendar_write_permission_head,
            result_kind="PersonalCalendarWritePermissionState",
        )

    def _revoke_state(
        self,
        *,
        operation_id: UUID,
        entity_id: UUID,
        scope: str,
        entity_table,
        entity_key: str,
        state_table,
        head_table,
        result_kind: str,
    ) -> CalendarCreateAuthorityStateResult:
        req = request_digest({"entity_id": entity_id})
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateAuthorityStateResult(
                    entity_id, int(replay["revision"])
                )
            key_column = getattr(entity_table.c, entity_key)
            if conn.execute(
                select(key_column).where(key_column == entity_id)
            ).scalar_one_or_none() is None:
                fail("CALENDAR_CREATE_AUTHORITY_NOT_FOUND", "authority entity does not exist")
            head = conn.execute(
                select(head_table).where(getattr(head_table.c, entity_key) == entity_id)
            ).mappings().one()
            parent = int(head["current_revision"])
            current = conn.execute(
                select(state_table).where(
                    getattr(state_table.c, entity_key) == entity_id,
                    state_table.c.revision == parent,
                )
            ).mappings().one()
            if current["status"] == "REVOKED":
                revision = parent
            else:
                revision = parent + 1
                now = self.clock.now()
                conn.execute(
                    insert(state_table).values(
                        **{
                            entity_key: entity_id,
                            "revision": revision,
                            "parent_revision": parent,
                            "status": "REVOKED",
                            "committed_at": now,
                        }
                    )
                )
                self._advance_head(
                    conn,
                    head_table=head_table,
                    key_name=entity_key,
                    key_value=entity_id,
                    expected_revision=parent,
                    new_revision=revision,
                    conflict_code="CALENDAR_CREATE_AUTHORITY_STATE_CONFLICT",
                )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=operation_id,
                req_digest=req,
                result_kind=result_kind,
                result_ref=entity_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return CalendarCreateAuthorityStateResult(entity_id, revision)


__all__ = ["PersonalCalendarMutationPermissionServices"]
