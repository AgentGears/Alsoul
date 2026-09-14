from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_action import (
    CALENDAR_CREATE_ACTION_SCHEMA_VERSION,
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
    CalendarCreatePermissionStateResult,
    CalendarCreatePolicyResult,
    GrantCalendarCreatePermissionCommand,
    GrantCalendarCreatePermissionResult,
    PersonalCalendarCreateActionResult,
    PreparePersonalCalendarCreateActionCommand,
    SetCalendarCreatePermissionStatusCommand,
    SetCalendarCreatePolicyCommand,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar import PersonalCalendarReadServices
from alsoul.storage import schema


CALENDAR_CREATE_PERMISSION_GRANT_TEXT = (
    "Allow my companion to add events to my calendar."
)
_CALENDAR_CREATE_PERMISSION_GRANT_CONTRACT = "CALENDAR_CREATE_PERMISSION_GRANT_V1"
_CREATE_POLICY_SCOPE = "SetCalendarCreatePolicy"
_GRANT_PERMISSION_SCOPE = "GrantCalendarCreatePermission"
_GRANT_SOURCE_CONSUMPTION_SCOPE = "ConsumeCalendarCreatePermissionGrantEvent"
_SET_PERMISSION_STATUS_SCOPE = "SetCalendarCreatePermissionStatus"
_PREPARE_ACTION_SCOPE = "PreparePersonalCalendarCreateAction"
_RESOURCE_REGISTRATION_SCOPE = "RegisterPersonalCalendarResource"

_CREATE_REQUEST = re.compile(
    r"^Add '(?P<summary>[^'\r\n]+)' to my calendar from "
    r"(?P<start>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})) to "
    r"(?P<end>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))\.$"
)


class PersonalCalendarActionServices(PersonalCalendarReadServices):
    """F5.B immutable calendar-create Action and write-authority boundary."""

    def set_create_policy(
        self, command: SetCalendarCreatePolicyCommand
    ) -> CalendarCreatePolicyResult:
        req = request_digest(asdict(command))
        required = (
            command.capability_contract_version,
            command.ai_policy_version,
            command.resource_scope_version,
            command.required_provider_scope,
            command.permission_grant_policy_version,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            fail(
                "CALENDAR_CREATE_POLICY_INVALID",
                "calendar-create policy versions and provider scope must be explicit",
            )
        if command.status not in {"ALLOW", "DENY"}:
            fail(
                "CALENDAR_CREATE_POLICY_INVALID",
                "calendar-create policy status is invalid",
            )
        if len(set(command.allowed_resource_binding_ids)) != len(
            command.allowed_resource_binding_ids
        ):
            fail(
                "CALENDAR_CREATE_POLICY_INVALID",
                "calendar-create resource scope must not contain duplicates",
            )
        if command.status == "ALLOW" and not command.allowed_resource_binding_ids:
            fail(
                "CALENDAR_CREATE_POLICY_INVALID",
                "an ALLOW calendar-create policy requires explicit resource scope",
            )

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_CREATE_POLICY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreatePolicyResult(
                    command.relationship_id, int(replay["revision"])
                )

            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            for resource_id in command.allowed_resource_binding_ids:
                resource = conn.execute(
                    select(schema.personal_resource_binding).where(
                        schema.personal_resource_binding.c.personal_resource_binding_id
                        == resource_id
                    )
                ).mappings().one_or_none()
                if (
                    resource is None
                    or resource["relationship_id"] != command.relationship_id
                    or resource["counterpart_id"] != command.counterpart_id
                    or resource["resource_kind"] != "CALENDAR"
                ):
                    fail(
                        "CALENDAR_CREATE_POLICY_RESOURCE_MISMATCH",
                        "calendar-create policy references a resource outside the trusted relationship",
                    )

            head = conn.execute(
                select(schema.personal_calendar_create_policy_head).where(
                    schema.personal_calendar_create_policy_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            parent = int(head["current_revision"]) if head is not None else None
            revision = 1 if parent is None else parent + 1
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_create_policy_revision).values(
                    relationship_id=command.relationship_id,
                    revision=revision,
                    parent_revision=parent,
                    capability_semantic_operation=CALENDAR_EVENT_CREATE,
                    capability_contract_version=command.capability_contract_version.strip(),
                    capability_effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                    ai_policy_version=command.ai_policy_version.strip(),
                    resource_scope_version=command.resource_scope_version.strip(),
                    required_provider_scope=command.required_provider_scope.strip(),
                    permission_grant_policy_version=(
                        command.permission_grant_policy_version.strip()
                    ),
                    allowed_resource_binding_ids_json=[
                        str(value) for value in command.allowed_resource_binding_ids
                    ],
                    status=command.status,
                    committed_at=now,
                )
            )
            if parent is None:
                try:
                    conn.execute(
                        insert(schema.personal_calendar_create_policy_head).values(
                            relationship_id=command.relationship_id,
                            current_revision=revision,
                        )
                    )
                except IntegrityError:
                    fail(
                        "CALENDAR_CREATE_POLICY_CONFLICT",
                        "calendar-create policy head was created concurrently",
                    )
            else:
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_policy_head,
                    key_name="relationship_id",
                    key_value=command.relationship_id,
                    expected_revision=parent,
                    new_revision=revision,
                    conflict_code="CALENDAR_CREATE_POLICY_CONFLICT",
                )
            save_operation_receipt(
                conn,
                scope=_CREATE_POLICY_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarCreatePolicy",
                result_ref=command.relationship_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return CalendarCreatePolicyResult(command.relationship_id, revision)

    def grant_create_permission(
        self, command: GrantCalendarCreatePermissionCommand
    ) -> GrantCalendarCreatePermissionResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_GRANT_PERMISSION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return GrantCalendarCreatePermissionResult(UUID(replay["permission_id"]))

            relationship = self._require_relationship(
                conn,
                companion_person_id=command.holder_companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            if (
                not command.capability_contract_version.strip()
                or not command.grant_policy_version.strip()
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "calendar-create capability and grant policy versions must be explicit",
                )

            grant_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            if (
                grant_event is None
                or grant_event["event_kind"] != "COUNTERPART_INPUT"
                or grant_event["actor_kind"] != "COUNTERPART"
                or grant_event["relationship_id"] != command.relationship_id
                or grant_event["actor_ref"] != command.counterpart_id
                or grant_event["surface_binding_id"] is None
                or grant_event["channel_binding_id"] is None
                or grant_event["content_text"]
                != CALENDAR_CREATE_PERMISSION_GRANT_TEXT
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "calendar-create Permission lacks exact trusted counterpart grant evidence",
                )

            relationship_state, relationship_revision = (
                self._current_relationship_authority(conn, command.relationship_id)
            )
            if relationship_state["status"] != "ACTIVE":
                fail(
                    "RELATIONSHIP_NOT_ACTIVE",
                    "personal-world relationship authority is not active",
                )

            binding, binding_state, resource_revision = self._current_resource(
                conn, command.personal_resource_binding_id
            )
            active = self._active_calendar_bindings(conn, command.relationship_id)
            if (
                binding["relationship_id"] != command.relationship_id
                or binding["counterpart_id"] != command.counterpart_id
                or binding_state["status"] != "ACTIVE"
                or len(active) != 1
                or active[0]["personal_resource_binding_id"]
                != command.personal_resource_binding_id
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_RESOURCE_MISMATCH",
                    "calendar-create Permission target is not the unique active calendar",
                )

            policy, policy_revision = self._current_create_policy(
                conn, command.relationship_id
            )
            if (
                policy["status"] != "ALLOW"
                or policy["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
                or policy["capability_effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
                or policy["capability_contract_version"]
                != command.capability_contract_version
                or policy["permission_grant_policy_version"]
                != command.grant_policy_version
                or str(command.personal_resource_binding_id)
                not in policy["allowed_resource_binding_ids_json"]
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_POLICY_DENIED",
                    "current calendar-create policy does not authorize this grant lineage",
                )

            registration_receipt = conn.execute(
                select(schema.operation_receipt).where(
                    schema.operation_receipt.c.operation_scope
                    == _RESOURCE_REGISTRATION_SCOPE,
                    schema.operation_receipt.c.result_ref
                    == command.personal_resource_binding_id,
                )
            ).mappings().one_or_none()
            if registration_receipt is None:
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "calendar-create Permission requires trusted resource activation provenance",
                )
            registration_result = registration_receipt["result_json"]
            if (
                not isinstance(registration_result, dict)
                or "activation_timeline_frontier" not in registration_result
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "calendar resource activation lacks a canonical Timeline frontier",
                )
            activation_frontier = int(
                registration_result["activation_timeline_frontier"]
            )
            if int(grant_event["timeline_seq"]) <= activation_frontier:
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_INVALID",
                    "calendar-create grant evidence must follow resource activation",
                )

            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            grant_seq = int(grant_event["timeline_seq"])
            if timeline is None or int(timeline["last_timeline_seq"]) != grant_seq:
                fail(
                    "CALENDAR_CREATE_PERMISSION_GRANT_NOT_CURRENT",
                    "calendar-create grant must be the current counterpart Timeline event",
                )

            consumed = conn.execute(
                select(schema.operation_receipt).where(
                    schema.operation_receipt.c.operation_scope
                    == _GRANT_SOURCE_CONSUMPTION_SCOPE,
                    schema.operation_receipt.c.operation_id
                    == command.source_interaction_event_id,
                )
            ).mappings().one_or_none()
            if consumed is not None:
                fail(
                    "CALENDAR_CREATE_PERMISSION_PROVENANCE_REUSED",
                    "one counterpart grant event cannot mint another write Permission",
                )
            if self._active_write_permissions(
                conn,
                relationship_id=command.relationship_id,
                resource_id=command.personal_resource_binding_id,
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_ALREADY_ACTIVE",
                    "an active calendar-create Permission already exists for this resource",
                )

            self._cas_head_same(
                conn,
                table=schema.personal_world_relationship_head,
                key_name="relationship_id",
                key_value=command.relationship_id,
                expected_revision=relationship_revision,
                conflict_code="CALENDAR_CREATE_RELATIONSHIP_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_resource_binding_head,
                key_name="personal_resource_binding_id",
                key_value=command.personal_resource_binding_id,
                expected_revision=resource_revision,
                conflict_code="CALENDAR_CREATE_RESOURCE_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_calendar_create_policy_head,
                key_name="relationship_id",
                key_value=command.relationship_id,
                expected_revision=policy_revision,
                conflict_code="CALENDAR_CREATE_POLICY_CHANGED",
            )
            changed = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id,
                    schema.relationship_timeline_head.c.last_timeline_seq == grant_seq,
                )
                .values(last_timeline_seq=grant_seq)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_CREATE_PERMISSION_GRANT_NOT_CURRENT",
                    "calendar-create grant stopped being current during admission",
                )

            permission_id = self.ids.new()
            now = self.clock.now()
            source_ref = str(command.source_interaction_event_id)
            consumption_digest = request_digest(
                {
                    "source_interaction_event_id": command.source_interaction_event_id,
                    "relationship_id": command.relationship_id,
                    "personal_resource_binding_id": command.personal_resource_binding_id,
                    "capability_semantic_operation": CALENDAR_EVENT_CREATE,
                    "capability_contract_version": command.capability_contract_version,
                    "grant_policy_version": command.grant_policy_version,
                }
            )
            try:
                save_operation_receipt(
                    conn,
                    scope=_GRANT_SOURCE_CONSUMPTION_SCOPE,
                    operation_id=command.source_interaction_event_id,
                    req_digest=consumption_digest,
                    result_kind="ConsumedCalendarCreatePermissionGrantEvent",
                    result_ref=permission_id,
                    result_json={
                        "source_interaction_event_id": source_ref,
                        "permission_id": str(permission_id),
                    },
                    committed_at=now,
                )
                conn.execute(
                    insert(schema.personal_calendar_write_permission_grant).values(
                        permission_id=permission_id,
                        holder_companion_person_id=(
                            command.holder_companion_person_id
                        ),
                        counterpart_id=command.counterpart_id,
                        relationship_id=command.relationship_id,
                        personal_resource_binding_id=(
                            command.personal_resource_binding_id
                        ),
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        capability_contract_version=(
                            command.capability_contract_version
                        ),
                        operation_class=CALENDAR_CREATE_EFFECT_CLASS,
                        grantor_ref=relationship["counterpart_id"],
                        grant_source="FIRST_PARTY_COUNTERPART",
                        grant_policy_version=command.grant_policy_version,
                        constraints_json={
                            "resource_kind": "CALENDAR",
                            "grant_contract_version": (
                                _CALENDAR_CREATE_PERMISSION_GRANT_CONTRACT
                            ),
                            "grant_source_event_id": source_ref,
                            "resource_activation_timeline_frontier": (
                                activation_frontier
                            ),
                        },
                        granted_at=now,
                        expires_at=None,
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
            except IntegrityError:
                fail(
                    "CALENDAR_CREATE_PERMISSION_CONFLICT",
                    "calendar-create Permission admission conflicted with durable state",
                )
            save_operation_receipt(
                conn,
                scope=_GRANT_PERMISSION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarWritePermission",
                result_ref=permission_id,
                result_json={"permission_id": str(permission_id)},
                committed_at=now,
            )
            return GrantCalendarCreatePermissionResult(permission_id)

    def set_create_permission_status(
        self, command: SetCalendarCreatePermissionStatusCommand
    ) -> CalendarCreatePermissionStateResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_SET_PERMISSION_STATUS_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreatePermissionStateResult(
                    command.permission_id, int(replay["revision"])
                )
            grant = conn.execute(
                select(schema.personal_calendar_write_permission_grant).where(
                    schema.personal_calendar_write_permission_grant.c.permission_id
                    == command.permission_id
                )
            ).mappings().one_or_none()
            if grant is None:
                fail(
                    "CALENDAR_CREATE_PERMISSION_NOT_FOUND",
                    "calendar-create Permission does not exist",
                )
            state, revision = self._current_write_permission(
                conn, command.permission_id
            )
            if state["status"] == "REVOKED":
                new_revision = revision
            else:
                new_revision = revision + 1
                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_calendar_write_permission_state).values(
                        permission_id=command.permission_id,
                        revision=new_revision,
                        parent_revision=revision,
                        status="REVOKED",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_write_permission_head,
                    key_name="permission_id",
                    key_value=command.permission_id,
                    expected_revision=revision,
                    new_revision=new_revision,
                    conflict_code="CALENDAR_CREATE_PERMISSION_STATE_CONFLICT",
                )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=_SET_PERMISSION_STATUS_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarWritePermissionState",
                result_ref=command.permission_id,
                result_json={"revision": new_revision},
                committed_at=now,
            )
            return CalendarCreatePermissionStateResult(
                command.permission_id, new_revision
            )

    def prepare_create_action(
        self, command: PreparePersonalCalendarCreateActionCommand
    ) -> PersonalCalendarCreateActionResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PREPARE_ACTION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._action_result_from_json(replay)

            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            source = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            if (
                relationship is None
                or source is None
                or source["relationship_id"] != command.relationship_id
                or source["event_kind"] != "COUNTERPART_INPUT"
                or source["actor_kind"] != "COUNTERPART"
                or source["actor_ref"] != relationship["counterpart_id"]
                or source["surface_binding_id"] is None
                or source["channel_binding_id"] is None
            ):
                fail(
                    "CALENDAR_CREATE_SOURCE_INVALID",
                    "calendar-create Action must originate from matching counterpart input",
                )
            summary, start_text, end_text, normalized_start, normalized_end = (
                parse_personal_calendar_create_request(source["content_text"])
            )

            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            source_seq = int(source["timeline_seq"])
            if timeline is None or int(timeline["last_timeline_seq"]) != source_seq:
                fail(
                    "CALENDAR_CREATE_SOURCE_NOT_CURRENT",
                    "calendar-create Action must bind the current Timeline request",
                )

            relationship_state, relationship_revision = (
                self._current_relationship_authority(conn, command.relationship_id)
            )
            if relationship_state["status"] != "ACTIVE":
                fail(
                    "RELATIONSHIP_NOT_ACTIVE",
                    "calendar-create relationship authority is not active",
                )
            binding, binding_state, resource_revision = self._current_resource(
                conn, command.personal_resource_binding_id
            )
            active = self._active_calendar_bindings(conn, command.relationship_id)
            if (
                binding_state["status"] != "ACTIVE"
                or binding["relationship_id"] != command.relationship_id
                or binding["counterpart_id"] != relationship["counterpart_id"]
                or len(active) != 1
                or active[0]["personal_resource_binding_id"]
                != command.personal_resource_binding_id
            ):
                fail(
                    "CALENDAR_CREATE_RESOURCE_NOT_CURRENT",
                    "calendar-create target is not the unique active calendar",
                )

            policy, policy_revision = self._current_create_policy(
                conn, command.relationship_id
            )
            if (
                policy["status"] != "ALLOW"
                or policy["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
                or policy["capability_effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
                or policy["capability_contract_version"]
                != command.capability_contract_version
                or str(command.personal_resource_binding_id)
                not in policy["allowed_resource_binding_ids_json"]
            ):
                fail(
                    "CALENDAR_CREATE_POLICY_DENIED",
                    "current calendar-create policy denies Action preparation",
                )

            grant = conn.execute(
                select(schema.personal_calendar_write_permission_grant).where(
                    schema.personal_calendar_write_permission_grant.c.permission_id
                    == command.permission_id
                )
            ).mappings().one_or_none()
            if grant is None:
                fail(
                    "CALENDAR_CREATE_PERMISSION_MISSING",
                    "calendar-create Action requires current write Permission",
                )
            permission_state, permission_revision = self._current_write_permission(
                conn, command.permission_id
            )
            now_utc = _aware_utc(self.clock.now())
            if (
                permission_state["status"] != "ACTIVE"
                or grant["holder_companion_person_id"]
                != relationship["companion_person_id"]
                or grant["counterpart_id"] != relationship["counterpart_id"]
                or grant["relationship_id"] != command.relationship_id
                or grant["personal_resource_binding_id"]
                != command.personal_resource_binding_id
                or grant["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
                or grant["capability_contract_version"]
                != command.capability_contract_version
                or grant["operation_class"] != CALENDAR_CREATE_EFFECT_CLASS
                or grant["grantor_ref"] != relationship["counterpart_id"]
                or grant["grant_source"] != "FIRST_PARTY_COUNTERPART"
                or grant["grant_policy_version"]
                != policy["permission_grant_policy_version"]
                or (
                    grant["expires_at"] is not None
                    and _aware_utc(grant["expires_at"]) <= now_utc
                )
            ):
                fail(
                    "CALENDAR_CREATE_PERMISSION_DENIED",
                    "calendar-create write Permission is revoked, expired, or mismatched",
                )

            self._cas_head_same(
                conn,
                table=schema.personal_world_relationship_head,
                key_name="relationship_id",
                key_value=command.relationship_id,
                expected_revision=relationship_revision,
                conflict_code="CALENDAR_CREATE_RELATIONSHIP_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_resource_binding_head,
                key_name="personal_resource_binding_id",
                key_value=command.personal_resource_binding_id,
                expected_revision=resource_revision,
                conflict_code="CALENDAR_CREATE_RESOURCE_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_calendar_create_policy_head,
                key_name="relationship_id",
                key_value=command.relationship_id,
                expected_revision=policy_revision,
                conflict_code="CALENDAR_CREATE_POLICY_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_calendar_write_permission_head,
                key_name="permission_id",
                key_value=command.permission_id,
                expected_revision=permission_revision,
                conflict_code="CALENDAR_CREATE_PERMISSION_CHANGED",
            )
            changed = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id,
                    schema.relationship_timeline_head.c.last_timeline_seq == source_seq,
                )
                .values(last_timeline_seq=source_seq)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_CREATE_SOURCE_NOT_CURRENT",
                    "calendar-create source stopped being current during admission",
                )

            action_id = self.ids.new()
            digest_payload = {
                "action_schema_version": CALENDAR_CREATE_ACTION_SCHEMA_VERSION,
                "relationship_id": str(command.relationship_id),
                "personal_resource_binding_id": str(
                    command.personal_resource_binding_id
                ),
                "source_interaction_event_id": str(
                    command.source_interaction_event_id
                ),
                "summary": summary,
                "start_text": start_text,
                "end_text": end_text,
                "normalized_start_at": normalized_start.isoformat(),
                "normalized_end_at": normalized_end.isoformat(),
                "capability_semantic_operation": CALENDAR_EVENT_CREATE,
                "capability_contract_version": command.capability_contract_version,
            }
            action_digest = sha256_text(canonical_json(digest_payload))
            now = self.clock.now()
            try:
                conn.execute(
                    insert(schema.personal_calendar_create_action).values(
                        action_id=action_id,
                        relationship_id=command.relationship_id,
                        counterpart_id=relationship["counterpart_id"],
                        personal_resource_binding_id=(
                            command.personal_resource_binding_id
                        ),
                        source_interaction_event_id=(
                            command.source_interaction_event_id
                        ),
                        summary=summary,
                        start_text=start_text,
                        end_text=end_text,
                        normalized_start_at=normalized_start,
                        normalized_end_at=normalized_end,
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        capability_contract_version=(
                            command.capability_contract_version
                        ),
                        action_schema_version=CALENDAR_CREATE_ACTION_SCHEMA_VERSION,
                        action_digest=action_digest,
                        source_timeline_frontier=source_seq,
                        relationship_authority_revision=relationship_revision,
                        resource_binding_state_revision=resource_revision,
                        write_policy_revision=policy_revision,
                        write_permission_id=command.permission_id,
                        write_permission_state_revision=permission_revision,
                        prepared_at=now,
                    )
                )
            except IntegrityError:
                fail(
                    "CALENDAR_CREATE_ACTION_CONFLICT",
                    "calendar-create source already produced an immutable Action",
                )
            result_json = {
                "action_id": str(action_id),
                "personal_resource_binding_id": str(
                    command.personal_resource_binding_id
                ),
                "summary": summary,
                "start_text": start_text,
                "end_text": end_text,
                "normalized_start_at": normalized_start.isoformat(),
                "normalized_end_at": normalized_end.isoformat(),
                "action_digest": action_digest,
            }
            save_operation_receipt(
                conn,
                scope=_PREPARE_ACTION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarCreateAction",
                result_ref=action_id,
                result_json=result_json,
                committed_at=now,
            )
            return self._action_result_from_json(result_json)

    def _current_create_policy(self, conn, relationship_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_create_policy_head).where(
                schema.personal_calendar_create_policy_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "CALENDAR_CREATE_POLICY_MISSING",
                "current calendar-create policy is missing",
            )
        revision = int(head["current_revision"])
        policy = conn.execute(
            select(schema.personal_calendar_create_policy_revision).where(
                schema.personal_calendar_create_policy_revision.c.relationship_id
                == relationship_id,
                schema.personal_calendar_create_policy_revision.c.revision == revision,
            )
        ).mappings().one_or_none()
        if policy is None:
            fail(
                "CALENDAR_CREATE_POLICY_MISSING",
                "current calendar-create policy revision is missing",
            )
        return dict(policy), revision

    def _current_write_permission(self, conn, permission_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_write_permission_head).where(
                schema.personal_calendar_write_permission_head.c.permission_id
                == permission_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "CALENDAR_CREATE_PERMISSION_STATE_MISSING",
                "calendar-create Permission state is missing",
            )
        revision = int(head["current_revision"])
        state = conn.execute(
            select(schema.personal_calendar_write_permission_state).where(
                schema.personal_calendar_write_permission_state.c.permission_id
                == permission_id,
                schema.personal_calendar_write_permission_state.c.revision == revision,
            )
        ).mappings().one_or_none()
        if state is None:
            fail(
                "CALENDAR_CREATE_PERMISSION_STATE_MISSING",
                "calendar-create Permission revision is missing",
            )
        return dict(state), revision

    def _active_write_permissions(
        self, conn, *, relationship_id: UUID, resource_id: UUID
    ):
        grants = conn.execute(
            select(schema.personal_calendar_write_permission_grant).where(
                schema.personal_calendar_write_permission_grant.c.relationship_id
                == relationship_id,
                schema.personal_calendar_write_permission_grant.c.personal_resource_binding_id
                == resource_id,
                schema.personal_calendar_write_permission_grant.c.capability_semantic_operation
                == CALENDAR_EVENT_CREATE,
            )
        ).mappings().all()
        active = []
        for grant in grants:
            state, _ = self._current_write_permission(conn, grant["permission_id"])
            if state["status"] == "ACTIVE":
                active.append(dict(grant))
        return active

    @staticmethod
    def _cas_head_same(
        conn,
        *,
        table,
        key_name: str,
        key_value: UUID,
        expected_revision: int,
        conflict_code: str,
    ) -> None:
        changed = conn.execute(
            update(table)
            .where(
                getattr(table.c, key_name) == key_value,
                table.c.current_revision == expected_revision,
            )
            .values(current_revision=expected_revision)
        )
        if changed.rowcount != 1:
            fail(conflict_code, "calendar-create authority changed concurrently")

    @staticmethod
    def _action_result_from_json(payload: dict[str, Any]):
        return PersonalCalendarCreateActionResult(
            action_id=UUID(payload["action_id"]),
            personal_resource_binding_id=UUID(
                payload["personal_resource_binding_id"]
            ),
            summary=payload["summary"],
            start_text=payload["start_text"],
            end_text=payload["end_text"],
            normalized_start_at=datetime.fromisoformat(
                payload["normalized_start_at"]
            ),
            normalized_end_at=datetime.fromisoformat(payload["normalized_end_at"]),
            action_digest=payload["action_digest"],
        )


def parse_personal_calendar_create_request(
    text: str,
) -> tuple[str, str, str, datetime, datetime]:
    match = _CREATE_REQUEST.fullmatch(text)
    if match is None:
        fail(
            "PERSONAL_CALENDAR_CREATE_REQUEST_UNSUPPORTED",
            "request is outside the first F5.B explicit-offset calendar-create grammar",
        )
    summary = match.group("summary")
    if len(summary) > 256 or not summary.strip():
        fail(
            "PERSONAL_CALENDAR_CREATE_SUMMARY_INVALID",
            "calendar-create summary must be non-empty and at most 256 characters",
        )
    start_text = match.group("start")
    end_text = match.group("end")
    try:
        start = _parse_offset_timestamp(start_text)
        end = _parse_offset_timestamp(end_text)
    except ValueError:
        fail(
            "PERSONAL_CALENDAR_CREATE_TIME_INVALID",
            "calendar-create timestamps must be valid offset-aware ISO timestamps",
        )
    if end <= start:
        fail(
            "PERSONAL_CALENDAR_CREATE_INTERVAL_INVALID",
            "calendar-create end instant must be after start instant",
        )
    return summary, start_text, end_text, start, end


def _parse_offset_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("offset required")
    return parsed.astimezone(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "CALENDAR_CREATE_PERMISSION_GRANT_TEXT",
    "PersonalCalendarActionServices",
    "parse_personal_calendar_create_request",
]
