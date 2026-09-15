from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_action import (
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
)
from alsoul.domain.personal_calendar_execution import (
    AbandonPersonalCalendarCreateExecutionAttemptCommand,
    CALENDAR_CREATE_ACTION_CONSTRAINT_VERSION,
    CALENDAR_CREATE_APPROVER_ELIGIBILITY_VERSION,
    CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION,
    CalendarCreateExecutionBinding,
    FencePersonalCalendarCreateExecutionAttemptCommand,
    PersonalCalendarCreateExecutionAttemptResult,
    PersonalCalendarCreateExecutionFenceResult,
    PreparePersonalCalendarCreateExecutionAttemptCommand,
    RecoverPersonalCalendarCreateFencedAttemptCommand,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar_approval_v2 import PersonalCalendarApprovalServices
from alsoul.storage import schema


_PREPARE_SCOPE = "PreparePersonalCalendarCreateExecutionAttempt"
_FENCE_SCOPE = "FencePersonalCalendarCreateExecutionAttempt"
_ABANDON_SCOPE = "AbandonPersonalCalendarCreateExecutionAttempt"
_RECOVER_SCOPE = "RecoverPersonalCalendarCreateFencedAttempt"


class PersonalCalendarExecutionServices(PersonalCalendarApprovalServices):
    """F5.B per-Action execution serialization and durable dispatch-fence boundary.

    This increment deliberately stops before provider mutation transport. A
    ``DISPATCH_FENCED`` result records the exact authority and execution semantics
    that a later transport boundary must consume; it is not evidence that a provider
    request was sent or that any external effect occurred.
    """

    def __init__(
        self,
        engine,
        *,
        time_resolver,
        execution_binding: CalendarCreateExecutionBinding | None = None,
        approval_adapter=None,
        clock=None,
        ids=None,
    ) -> None:
        super().__init__(
            engine,
            time_resolver=time_resolver,
            approval_adapter=approval_adapter,
            clock=clock,
            ids=ids,
        )
        self.execution_binding = execution_binding

    def prepare_execution_attempt(
        self, command: PreparePersonalCalendarCreateExecutionAttemptCommand
    ) -> PersonalCalendarCreateExecutionAttemptResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_PREPARE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._attempt_result_from_json(replay)

                action, _, relationship, resource = self._load_action_lineage(
                    conn, command.action_id
                )
                authority = self._require_execution_authority(
                    conn,
                    action=action,
                    relationship=relationship,
                    resource=resource,
                    approval_id=command.approval_id,
                    credential_binding_id=command.credential_binding_id,
                    require_binding=True,
                )
                del authority

                head, guard = self._current_guard(conn, command.action_id)
                if head is not None and guard["status"] != "AVAILABLE":
                    fail(
                        "CALENDAR_CREATE_ACTION_DISPATCH_LOCKED",
                        "calendar-create Action already has a dispatch-eligible or unresolved execution attempt",
                    )

                max_generation = conn.execute(
                    select(
                        func.max(
                            schema.personal_calendar_create_execution_attempt.c.attempt_generation
                        )
                    ).where(
                        schema.personal_calendar_create_execution_attempt.c.action_id
                        == command.action_id
                    )
                ).scalar_one()
                generation = 1 if max_generation is None else int(max_generation) + 1
                execution_attempt_id = self.ids.new()
                correlation_key = self._action_correlation_key(command.action_id)
                now = self.clock.now()

                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt).values(
                        execution_attempt_id=execution_attempt_id,
                        action_id=command.action_id,
                        attempt_generation=generation,
                        approval_id=command.approval_id,
                        credential_binding_id=command.credential_binding_id,
                        correlation_key=correlation_key,
                        correlation_contract_version=(
                            CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION
                        ),
                        prepared_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt_state).values(
                        execution_attempt_id=execution_attempt_id,
                        revision=1,
                        parent_revision=None,
                        status="PREPARED",
                        committed_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt_head).values(
                        execution_attempt_id=execution_attempt_id,
                        current_revision=1,
                    )
                )

                if head is None:
                    guard_revision = 1
                    conn.execute(
                        insert(schema.personal_calendar_create_action_dispatch_state).values(
                            action_id=command.action_id,
                            revision=guard_revision,
                            parent_revision=None,
                            execution_attempt_id=execution_attempt_id,
                            status="PREPARED",
                            committed_at=now,
                        )
                    )
                    conn.execute(
                        insert(schema.personal_calendar_create_action_dispatch_head).values(
                            action_id=command.action_id,
                            current_revision=guard_revision,
                        )
                    )
                else:
                    parent = int(head["current_revision"])
                    guard_revision = parent + 1
                    conn.execute(
                        insert(schema.personal_calendar_create_action_dispatch_state).values(
                            action_id=command.action_id,
                            revision=guard_revision,
                            parent_revision=parent,
                            execution_attempt_id=execution_attempt_id,
                            status="PREPARED",
                            committed_at=now,
                        )
                    )
                    self._advance_head(
                        conn,
                        head_table=schema.personal_calendar_create_action_dispatch_head,
                        key_name="action_id",
                        key_value=command.action_id,
                        expected_revision=parent,
                        new_revision=guard_revision,
                        conflict_code="CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
                    )

                result_json = {
                    "execution_attempt_id": str(execution_attempt_id),
                    "action_id": str(command.action_id),
                    "attempt_generation": generation,
                    "correlation_key": correlation_key,
                    "status": "PREPARED",
                    "guard_revision": guard_revision,
                }
                save_operation_receipt(
                    conn,
                    scope=_PREPARE_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateExecutionAttempt",
                    result_ref=execution_attempt_id,
                    result_json=result_json,
                    committed_at=now,
                )
                return self._attempt_result_from_json(result_json)
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
                "calendar-create Action dispatch eligibility was claimed concurrently",
            ) from exc

    def fence_execution_attempt(
        self, command: FencePersonalCalendarCreateExecutionAttemptCommand
    ) -> PersonalCalendarCreateExecutionFenceResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_FENCE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._fence_result_from_json(replay)

                attempt = self._load_attempt(conn, command.execution_attempt_id)
                attempt_state, attempt_revision = self._current_attempt_state(
                    conn, command.execution_attempt_id
                )
                if attempt_state["status"] != "PREPARED":
                    fail(
                        "CALENDAR_CREATE_EXECUTION_ATTEMPT_NOT_PREPARED",
                        "only the current PREPARED execution attempt may be dispatch-fenced",
                    )
                head, guard = self._current_guard(conn, attempt["action_id"])
                if (
                    head is None
                    or guard["status"] != "PREPARED"
                    or guard["execution_attempt_id"] != command.execution_attempt_id
                ):
                    fail(
                        "CALENDAR_CREATE_ACTION_DISPATCH_NOT_OWNED",
                        "execution attempt does not own the current per-Action dispatch guard",
                    )

                action, _, relationship, resource = self._load_action_lineage(
                    conn, attempt["action_id"]
                )
                authority = self._require_execution_authority(
                    conn,
                    action=action,
                    relationship=relationship,
                    resource=resource,
                    approval_id=attempt["approval_id"],
                    credential_binding_id=attempt["credential_binding_id"],
                    require_binding=True,
                )
                binding = authority["execution_binding"]

                if attempt["correlation_key"] != self._action_correlation_key(
                    action["action_id"]
                ):
                    fail(
                        "CALENDAR_CREATE_EXECUTION_CORRELATION_INVALID",
                        "execution attempt correlation is not the host-derived key for the immutable Action",
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
                    key_value=attempt["approval_id"],
                    expected_revision=authority["approval_revision"],
                    conflict_code="CALENDAR_CREATE_EXECUTION_APPROVAL_CHANGED",
                )
                self._cas_head_same(
                    conn,
                    table=schema.credential_binding_head,
                    key_name="credential_binding_id",
                    key_value=attempt["credential_binding_id"],
                    expected_revision=authority["credential_revision"],
                    conflict_code="CALENDAR_CREATE_EXECUTION_CREDENTIAL_CHANGED",
                )

                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_calendar_create_execution_fence).values(
                        execution_attempt_id=command.execution_attempt_id,
                        action_id=action["action_id"],
                        attempt_generation=attempt["attempt_generation"],
                        correlation_key=attempt["correlation_key"],
                        relationship_id=action["relationship_id"],
                        relationship_authority_revision=authority[
                            "relationship_revision"
                        ],
                        personal_resource_binding_id=action[
                            "personal_resource_binding_id"
                        ],
                        resource_binding_state_revision=authority["resource_revision"],
                        write_policy_revision=authority["policy_revision"],
                        write_permission_id=action["write_permission_id"],
                        write_permission_state_revision=authority["permission_revision"],
                        approval_id=attempt["approval_id"],
                        approval_state_revision=authority["approval_revision"],
                        approval_presentation_id=authority["approval"][
                            "approval_presentation_id"
                        ],
                        consent_payload_digest=authority["approval"][
                            "consent_payload_digest"
                        ],
                        authorized_approver_ref=authority["approval"][
                            "authorized_approver_ref"
                        ],
                        approver_eligibility_version=(
                            CALENDAR_CREATE_APPROVER_ELIGIBILITY_VERSION
                        ),
                        credential_binding_id=attempt["credential_binding_id"],
                        credential_binding_state_revision=authority[
                            "credential_revision"
                        ],
                        provider_scope_snapshot_json=authority["provider_scopes"],
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        capability_contract_version=action[
                            "capability_contract_version"
                        ],
                        ai_policy_version=authority["policy"]["ai_policy_version"],
                        resource_scope_version=authority["policy"][
                            "resource_scope_version"
                        ],
                        action_constraint_version=CALENDAR_CREATE_ACTION_CONSTRAINT_VERSION,
                        adapter_binding_ref=binding.adapter_binding_ref,
                        adapter_contract_version=binding.adapter_contract_version,
                        executor_contract_version=binding.executor_contract_version,
                        correlation_contract_version=binding.correlation_contract_version,
                        negative_confirmation_contract_version=(
                            binding.negative_confirmation_contract_version
                        ),
                        authority_evaluated_at=now,
                        dispatch_fenced_at=now,
                    )
                )

                new_attempt_revision = attempt_revision + 1
                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt_state).values(
                        execution_attempt_id=command.execution_attempt_id,
                        revision=new_attempt_revision,
                        parent_revision=attempt_revision,
                        status="DISPATCH_FENCED",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_execution_attempt_head,
                    key_name="execution_attempt_id",
                    key_value=command.execution_attempt_id,
                    expected_revision=attempt_revision,
                    new_revision=new_attempt_revision,
                    conflict_code="CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_CONFLICT",
                )

                guard_parent = int(head["current_revision"])
                guard_revision = guard_parent + 1
                conn.execute(
                    insert(schema.personal_calendar_create_action_dispatch_state).values(
                        action_id=action["action_id"],
                        revision=guard_revision,
                        parent_revision=guard_parent,
                        execution_attempt_id=command.execution_attempt_id,
                        status="DISPATCH_FENCED",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_action_dispatch_head,
                    key_name="action_id",
                    key_value=action["action_id"],
                    expected_revision=guard_parent,
                    new_revision=guard_revision,
                    conflict_code="CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
                )

                result_json = self._fence_result_json(
                    attempt=attempt,
                    fence={
                        "adapter_binding_ref": binding.adapter_binding_ref,
                        "adapter_contract_version": binding.adapter_contract_version,
                        "executor_contract_version": binding.executor_contract_version,
                        "correlation_contract_version": binding.correlation_contract_version,
                        "negative_confirmation_contract_version": (
                            binding.negative_confirmation_contract_version
                        ),
                        "dispatch_fenced_at": now,
                    },
                    status="DISPATCH_FENCED",
                    guard_revision=guard_revision,
                )
                save_operation_receipt(
                    conn,
                    scope=_FENCE_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateExecutionFence",
                    result_ref=command.execution_attempt_id,
                    result_json=result_json,
                    committed_at=now,
                )
                return self._fence_result_from_json(result_json)
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_EXECUTION_FENCE_CONFLICT",
                "calendar-create execution fence conflicted with current durable state",
            ) from exc

    def abandon_prepared_attempt(
        self, command: AbandonPersonalCalendarCreateExecutionAttemptCommand
    ) -> PersonalCalendarCreateExecutionAttemptResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ABANDON_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._attempt_result_from_json(replay)

            attempt = self._load_attempt(conn, command.execution_attempt_id)
            state, attempt_revision = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            if state["status"] != "PREPARED":
                fail(
                    "CALENDAR_CREATE_EXECUTION_ATTEMPT_NOT_ABANDONABLE",
                    "only a PREPARED attempt with no dispatch fence may be abandoned",
                )
            fence = conn.execute(
                select(schema.personal_calendar_create_execution_fence).where(
                    schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).first()
            if fence is not None:
                fail(
                    "CALENDAR_CREATE_EXECUTION_ATTEMPT_NOT_ABANDONABLE",
                    "a dispatch-fenced attempt cannot be released as known-no-transport",
                )
            head, guard = self._current_guard(conn, attempt["action_id"])
            if (
                head is None
                or guard["status"] != "PREPARED"
                or guard["execution_attempt_id"] != command.execution_attempt_id
            ):
                fail(
                    "CALENDAR_CREATE_ACTION_DISPATCH_NOT_OWNED",
                    "prepared attempt no longer owns the Action dispatch guard",
                )

            now = self.clock.now()
            new_attempt_revision = attempt_revision + 1
            conn.execute(
                insert(schema.personal_calendar_create_execution_attempt_state).values(
                    execution_attempt_id=command.execution_attempt_id,
                    revision=new_attempt_revision,
                    parent_revision=attempt_revision,
                    status="ABANDONED",
                    committed_at=now,
                )
            )
            self._advance_head(
                conn,
                head_table=schema.personal_calendar_create_execution_attempt_head,
                key_name="execution_attempt_id",
                key_value=command.execution_attempt_id,
                expected_revision=attempt_revision,
                new_revision=new_attempt_revision,
                conflict_code="CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_CONFLICT",
            )
            guard_parent = int(head["current_revision"])
            guard_revision = guard_parent + 1
            conn.execute(
                insert(schema.personal_calendar_create_action_dispatch_state).values(
                    action_id=attempt["action_id"],
                    revision=guard_revision,
                    parent_revision=guard_parent,
                    execution_attempt_id=None,
                    status="AVAILABLE",
                    committed_at=now,
                )
            )
            self._advance_head(
                conn,
                head_table=schema.personal_calendar_create_action_dispatch_head,
                key_name="action_id",
                key_value=attempt["action_id"],
                expected_revision=guard_parent,
                new_revision=guard_revision,
                conflict_code="CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
            )
            result_json = {
                "execution_attempt_id": str(command.execution_attempt_id),
                "action_id": str(attempt["action_id"]),
                "attempt_generation": int(attempt["attempt_generation"]),
                "correlation_key": attempt["correlation_key"],
                "status": "ABANDONED",
                "guard_revision": guard_revision,
            }
            save_operation_receipt(
                conn,
                scope=_ABANDON_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarCreateExecutionAttempt",
                result_ref=command.execution_attempt_id,
                result_json=result_json,
                committed_at=now,
            )
            return self._attempt_result_from_json(result_json)

    def recover_fenced_attempt(
        self, command: RecoverPersonalCalendarCreateFencedAttemptCommand
    ) -> PersonalCalendarCreateExecutionFenceResult:
        """Conservatively turn a surviving dispatch fence into UNKNOWN_EFFECT.

        Recovery consumes only durable Alsoul state. It deliberately does not consult
        current Permission, Approval, credentials, or a replacement execution binding:
        those cannot erase or reinterpret the fact that the old fenced attempt may have
        crossed the external mutation boundary.
        """

        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECOVER_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._fence_result_from_json(replay)

            attempt = self._load_attempt(conn, command.execution_attempt_id)
            fence = conn.execute(
                select(schema.personal_calendar_create_execution_fence).where(
                    schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if fence is None:
                fail(
                    "CALENDAR_CREATE_EXECUTION_FENCE_MISSING",
                    "only an attempt with a durable dispatch fence can recover as UNKNOWN_EFFECT",
                )
            state, attempt_revision = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            head, guard = self._current_guard(conn, attempt["action_id"])
            if (
                head is None
                or guard["execution_attempt_id"] != command.execution_attempt_id
                or guard["status"] not in {"DISPATCH_FENCED", "UNKNOWN_EFFECT"}
            ):
                fail(
                    "CALENDAR_CREATE_ACTION_DISPATCH_NOT_OWNED",
                    "fenced attempt no longer owns the unresolved Action dispatch guard",
                )

            now = self.clock.now()
            if state["status"] == "DISPATCH_FENCED":
                new_attempt_revision = attempt_revision + 1
                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt_state).values(
                        execution_attempt_id=command.execution_attempt_id,
                        revision=new_attempt_revision,
                        parent_revision=attempt_revision,
                        status="UNKNOWN_EFFECT",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_execution_attempt_head,
                    key_name="execution_attempt_id",
                    key_value=command.execution_attempt_id,
                    expected_revision=attempt_revision,
                    new_revision=new_attempt_revision,
                    conflict_code="CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_CONFLICT",
                )
                guard_parent = int(head["current_revision"])
                guard_revision = guard_parent + 1
                conn.execute(
                    insert(schema.personal_calendar_create_action_dispatch_state).values(
                        action_id=attempt["action_id"],
                        revision=guard_revision,
                        parent_revision=guard_parent,
                        execution_attempt_id=command.execution_attempt_id,
                        status="UNKNOWN_EFFECT",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_action_dispatch_head,
                    key_name="action_id",
                    key_value=attempt["action_id"],
                    expected_revision=guard_parent,
                    new_revision=guard_revision,
                    conflict_code="CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
                )
            elif state["status"] == "UNKNOWN_EFFECT":
                guard_revision = int(head["current_revision"])
            else:
                fail(
                    "CALENDAR_CREATE_EXECUTION_RECOVERY_INVALID",
                    "execution attempt is not in a recoverable fenced state",
                )

            result_json = self._fence_result_json(
                attempt=attempt,
                fence=fence,
                status="UNKNOWN_EFFECT",
                guard_revision=guard_revision,
            )
            save_operation_receipt(
                conn,
                scope=_RECOVER_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarCreateExecutionFence",
                result_ref=command.execution_attempt_id,
                result_json=result_json,
                committed_at=now,
            )
            return self._fence_result_from_json(result_json)

    def _require_execution_authority(
        self,
        conn,
        *,
        action,
        relationship,
        resource,
        approval_id: UUID,
        credential_binding_id: UUID,
        require_binding: bool,
    ) -> dict[str, Any]:
        authority = self._require_current_action_authority(
            conn,
            action=action,
            relationship=relationship,
            resource=resource,
        )
        approval = conn.execute(
            select(schema.personal_calendar_create_approval).where(
                schema.personal_calendar_create_approval.c.approval_id == approval_id
            )
        ).mappings().one_or_none()
        if approval is None or approval["action_id"] != action["action_id"]:
            fail(
                "CALENDAR_CREATE_EXECUTION_APPROVAL_INVALID",
                "execution requires the current Approval for the exact immutable Action",
            )
        approval_state, approval_revision = self._current_approval(conn, approval_id)
        now = _aware_utc(self.clock.now())
        if (
            approval_state["status"] != "ACTIVE"
            or approval["action_digest"] != action["action_digest"]
            or approval["relationship_id"] != action["relationship_id"]
            or approval["personal_resource_binding_id"]
            != action["personal_resource_binding_id"]
            or approval["write_permission_id"] != action["write_permission_id"]
            or approval["authorized_approver_ref"] != action["counterpart_id"]
            or approval["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
            or approval["effect_class"] != CALENDAR_CREATE_EFFECT_CLASS
            or (
                approval["expires_at"] is not None
                and _aware_utc(approval["expires_at"]) <= now
            )
        ):
            fail(
                "CALENDAR_CREATE_EXECUTION_APPROVAL_INVALID",
                "current Approval does not authorize the exact calendar-create Action",
            )
        presentation = conn.execute(
            select(schema.personal_calendar_create_approval_presentation).where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == approval["approval_presentation_id"]
            )
        ).mappings().one_or_none()
        if presentation is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_APPROVAL_INVALID",
                "Approval presentation provenance is missing",
            )
        self._require_presentation_equivalence(
            action=action,
            resource=resource,
            presentation=presentation,
        )

        credential = conn.execute(
            select(schema.credential_binding).where(
                schema.credential_binding.c.credential_binding_id
                == credential_binding_id
            )
        ).mappings().one_or_none()
        if credential is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_CREDENTIAL_INVALID",
                "selected credential binding does not exist",
            )
        credential_head = conn.execute(
            select(schema.credential_binding_head).where(
                schema.credential_binding_head.c.credential_binding_id
                == credential_binding_id
            )
        ).mappings().one_or_none()
        if credential_head is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_CREDENTIAL_INVALID",
                "selected credential binding lacks current state",
            )
        credential_revision = int(credential_head["current_revision"])
        credential_state = conn.execute(
            select(schema.credential_binding_state).where(
                schema.credential_binding_state.c.credential_binding_id
                == credential_binding_id,
                schema.credential_binding_state.c.revision == credential_revision,
            )
        ).mappings().one_or_none()
        provider_scopes = (
            list(credential_state["provider_scopes_json"])
            if credential_state is not None
            and isinstance(credential_state["provider_scopes_json"], list)
            else []
        )
        required_scope = authority["policy"]["required_provider_scope"]
        if (
            credential_state is None
            or credential_state["status"] != "ACTIVE"
            or credential["external_system_ref"] != resource["external_system_ref"]
            or required_scope not in provider_scopes
            or any(not isinstance(scope, str) or not scope.strip() for scope in provider_scopes)
        ):
            fail(
                "CALENDAR_CREATE_EXECUTION_CREDENTIAL_INVALID",
                "current credential binding cannot execute the selected Action under required provider scope",
            )

        if (
            not action["summary"]
            or _aware_utc(action["normalized_end_at"])
            <= _aware_utc(action["normalized_start_at"])
        ):
            fail(
                "CALENDAR_CREATE_EXECUTION_ACTION_CONSTRAINT_DENIED",
                "immutable Action violates current first-slice execution constraints",
            )

        binding = self._require_execution_binding(action=action, resource=resource)
        if not require_binding:
            binding = None
        return {
            **authority,
            "approval": dict(approval),
            "approval_revision": approval_revision,
            "credential_revision": credential_revision,
            "provider_scopes": sorted(set(provider_scopes)),
            "execution_binding": binding,
        }

    def _require_execution_binding(self, *, action, resource) -> CalendarCreateExecutionBinding:
        binding = self.execution_binding
        if binding is None or not isinstance(binding, CalendarCreateExecutionBinding):
            fail(
                "CALENDAR_CREATE_EXECUTION_BINDING_MISSING",
                "calendar-create dispatch fencing requires an explicit trusted execution binding",
            )
        values = (
            binding.adapter_binding_ref,
            binding.adapter_contract_version,
            binding.executor_contract_version,
            binding.correlation_contract_version,
            binding.negative_confirmation_contract_version,
            binding.capability_contract_version,
            binding.external_system_ref,
        )
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > 128
            for value in values
        ):
            fail(
                "CALENDAR_CREATE_EXECUTION_BINDING_INVALID",
                "execution binding identities and contract versions must be explicit bounded strings",
            )
        if (
            binding.capability_contract_version != action["capability_contract_version"]
            or binding.external_system_ref != resource["external_system_ref"]
            or binding.correlation_contract_version
            != CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION
            or binding.negative_confirmation_contract_version
            != CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION
        ):
            fail(
                "CALENDAR_CREATE_EXECUTION_BINDING_INVALID",
                "execution binding does not match the exact Action capability, resource, and supported correlation semantics",
            )
        return binding

    def _current_guard(self, conn, action_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_head).where(
                schema.personal_calendar_create_action_dispatch_head.c.action_id
                == action_id
            )
        ).mappings().one_or_none()
        if head is None:
            return None, None
        revision = int(head["current_revision"])
        state = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_state).where(
                schema.personal_calendar_create_action_dispatch_state.c.action_id
                == action_id,
                schema.personal_calendar_create_action_dispatch_state.c.revision
                == revision,
            )
        ).mappings().one_or_none()
        if state is None:
            fail(
                "CALENDAR_CREATE_ACTION_DISPATCH_STATE_MISSING",
                "calendar-create Action dispatch head does not resolve to durable state",
            )
        return dict(head), dict(state)

    def _load_attempt(self, conn, execution_attempt_id: UUID) -> dict[str, Any]:
        row = conn.execute(
            select(schema.personal_calendar_create_execution_attempt).where(
                schema.personal_calendar_create_execution_attempt.c.execution_attempt_id
                == execution_attempt_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_ATTEMPT_NOT_FOUND",
                "calendar-create execution attempt does not exist",
            )
        return dict(row)

    def _current_attempt_state(self, conn, execution_attempt_id: UUID):
        head = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_head).where(
                schema.personal_calendar_create_execution_attempt_head.c.execution_attempt_id
                == execution_attempt_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_MISSING",
                "calendar-create execution attempt lacks current state",
            )
        revision = int(head["current_revision"])
        state = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_state).where(
                schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id
                == execution_attempt_id,
                schema.personal_calendar_create_execution_attempt_state.c.revision
                == revision,
            )
        ).mappings().one_or_none()
        if state is None:
            fail(
                "CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_MISSING",
                "calendar-create execution attempt state is missing",
            )
        return dict(state), revision

    @staticmethod
    def _action_correlation_key(action_id: UUID) -> str:
        digest = sha256_text(
            canonical_json(
                {
                    "action_id": str(action_id),
                    "purpose": "calendar.event.create.external-correlation",
                    "contract_version": CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
                }
            )
        )
        return f"calendar-create:{digest}"

    @staticmethod
    def _attempt_result_from_json(payload: dict[str, Any]):
        return PersonalCalendarCreateExecutionAttemptResult(
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            attempt_generation=int(payload["attempt_generation"]),
            correlation_key=payload["correlation_key"],
            status=payload["status"],
            guard_revision=int(payload["guard_revision"]),
        )

    @staticmethod
    def _fence_result_json(*, attempt, fence, status: str, guard_revision: int):
        fenced_at = fence["dispatch_fenced_at"]
        if isinstance(fenced_at, datetime):
            fenced_at = _aware_utc(fenced_at).isoformat()
        return {
            "execution_attempt_id": str(attempt["execution_attempt_id"]),
            "action_id": str(attempt["action_id"]),
            "attempt_generation": int(attempt["attempt_generation"]),
            "correlation_key": attempt["correlation_key"],
            "status": status,
            "guard_revision": guard_revision,
            "adapter_binding_ref": fence["adapter_binding_ref"],
            "adapter_contract_version": fence["adapter_contract_version"],
            "executor_contract_version": fence["executor_contract_version"],
            "correlation_contract_version": fence["correlation_contract_version"],
            "negative_confirmation_contract_version": fence[
                "negative_confirmation_contract_version"
            ],
            "dispatch_fenced_at": fenced_at,
        }

    @staticmethod
    def _fence_result_from_json(payload: dict[str, Any]):
        return PersonalCalendarCreateExecutionFenceResult(
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            attempt_generation=int(payload["attempt_generation"]),
            correlation_key=payload["correlation_key"],
            status=payload["status"],
            guard_revision=int(payload["guard_revision"]),
            adapter_binding_ref=payload["adapter_binding_ref"],
            adapter_contract_version=payload["adapter_contract_version"],
            executor_contract_version=payload["executor_contract_version"],
            correlation_contract_version=payload["correlation_contract_version"],
            negative_confirmation_contract_version=payload[
                "negative_confirmation_contract_version"
            ],
            dispatch_fenced_at=datetime.fromisoformat(payload["dispatch_fenced_at"]),
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["PersonalCalendarExecutionServices"]
