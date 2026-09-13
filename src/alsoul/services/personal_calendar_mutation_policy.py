from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
    CalendarCreateWritePolicyResult,
    SetCalendarCreatePolicyCommand,
)
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.personal_calendar_mutation_permission import PersonalCalendarMutationPermissionServices
from alsoul.storage import schema

_WRITE_POLICY_SCOPE = "SetPersonalCalendarWritePolicy"


class PersonalCalendarMutationPolicyServices(PersonalCalendarMutationPermissionServices):
    def set_write_policy(
        self, command: SetCalendarCreatePolicyCommand
    ) -> CalendarCreateWritePolicyResult:
        req = request_digest(asdict(command))
        if command.status not in {"ALLOW", "DENY"}:
            fail("CALENDAR_CREATE_POLICY_INVALID", "write policy status is invalid")
        values = (
            command.capability_contract_version,
            command.ai_policy_version,
            command.resource_scope_version,
            command.required_provider_scope,
            command.permission_grant_policy_version,
            command.approval_policy_version,
        )
        if not all(value.strip() for value in values):
            fail(
                "CALENDAR_CREATE_POLICY_INVALID",
                "calendar-create policy versions/scopes must be explicit",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_WRITE_POLICY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateWritePolicyResult(
                    command.relationship_id, int(replay["revision"])
                )
            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            relationship_state, _ = self._current_relationship_authority(
                conn, command.relationship_id
            )
            if relationship_state["status"] != "ACTIVE" and command.status == "ALLOW":
                fail("RELATIONSHIP_NOT_ACTIVE", "cannot allow writes on an ended relationship")
            allowed: list[str] = []
            for resource_id in command.allowed_resource_binding_ids:
                resource, _, _ = self._current_resource(conn, resource_id)
                if (
                    resource["relationship_id"] != command.relationship_id
                    or resource["counterpart_id"] != command.counterpart_id
                ):
                    fail(
                        "RESOURCE_SCOPE_MISMATCH",
                        "write policy references a calendar outside this relationship",
                    )
                allowed.append(str(resource_id))
            allowed = sorted(set(allowed))
            if command.status == "ALLOW" and not allowed:
                fail("RESOURCE_SCOPE_EMPTY", "allowing calendar create requires a bounded resource scope")
            head = conn.execute(
                select(schema.personal_calendar_write_policy_head).where(
                    schema.personal_calendar_write_policy_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            parent = int(head["current_revision"]) if head is not None else None
            revision = 1 if parent is None else parent + 1
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_write_policy_revision).values(
                    relationship_id=command.relationship_id,
                    revision=revision,
                    parent_revision=parent,
                    capability_semantic_operation=CALENDAR_EVENT_CREATE,
                    capability_contract_version=command.capability_contract_version,
                    capability_effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                    ai_policy_version=command.ai_policy_version,
                    resource_scope_version=command.resource_scope_version,
                    required_provider_scope=command.required_provider_scope,
                    permission_grant_policy_version=command.permission_grant_policy_version,
                    approval_policy_version=command.approval_policy_version,
                    allowed_resource_binding_ids_json=allowed,
                    status=command.status,
                    committed_at=now,
                )
            )
            if parent is None:
                try:
                    conn.execute(
                        insert(schema.personal_calendar_write_policy_head).values(
                            relationship_id=command.relationship_id,
                            current_revision=revision,
                        )
                    )
                except Exception as exc:
                    fail(
                        "CALENDAR_CREATE_POLICY_CONFLICT",
                        f"write policy head was created concurrently: {type(exc).__name__}",
                    )
            else:
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_write_policy_head,
                    key_name="relationship_id",
                    key_value=command.relationship_id,
                    expected_revision=parent,
                    new_revision=revision,
                    conflict_code="CALENDAR_CREATE_POLICY_CONFLICT",
                )
            save_operation_receipt(
                conn,
                scope=_WRITE_POLICY_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarWritePolicy",
                result_ref=command.relationship_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return CalendarCreateWritePolicyResult(command.relationship_id, revision)

    def _current_write_policy(self, conn, relationship_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_write_policy_head).where(
                schema.personal_calendar_write_policy_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail("CALENDAR_CREATE_POLICY_MISSING", "calendar-create policy is not configured")
        revision = int(head["current_revision"])
        row = conn.execute(
            select(schema.personal_calendar_write_policy_revision).where(
                schema.personal_calendar_write_policy_revision.c.relationship_id
                == relationship_id,
                schema.personal_calendar_write_policy_revision.c.revision == revision,
            )
        ).mappings().one()
        return row, revision


__all__ = ["PersonalCalendarMutationPolicyServices"]
