from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_execution import (
    CALENDAR_CREATE_CORRELATION_CONTRACT_VERSION,
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION,
    CalendarCreateExecutionBinding,
)
from alsoul.domain.personal_calendar_no_effect import (
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION,
    CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION,
    CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION,
    CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND,
    CALENDAR_CREATE_RETRY_CONTRACT_VERSION,
    PersonalCalendarCreateRetryAttemptResult,
    PreparePersonalCalendarCreateRetryAttemptCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_execution_v2 import (
    PersonalCalendarExecutionServices as PersonalCalendarExecutionServicesV2,
    _is_transient_lock_collision,
)
from alsoul.storage import schema


_RETRY_SCOPE = "PreparePersonalCalendarCreateRetryAttempt"
_RETRY_CONFLICT_CODE = "CALENDAR_CREATE_RETRY_CLAIM_CONFLICT"


def require_current_calendar_create_execution_binding(service, *, action, resource):
    """Validate one trusted execution binding for a fresh fence or retry.

    The original first increment admitted only the explicit UNSUPPORTED negative
    contract. F5.B now also recognizes one exact terminal-negative contract version;
    no arbitrary version string becomes trusted merely by being configured.
    """

    binding = service.execution_binding
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
        not in {
            CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_VERSION,
            CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION,
        }
    ):
        fail(
            "CALENDAR_CREATE_EXECUTION_BINDING_INVALID",
            "execution binding does not match the exact Action capability, resource, correlation, and trusted negative-confirmation semantics",
        )
    return binding


class PersonalCalendarExecutionServices(PersonalCalendarExecutionServicesV2):
    """Current execution boundary with terminal no-effect retry consumption."""

    def _require_execution_binding(self, *, action, resource):
        return require_current_calendar_create_execution_binding(
            self, action=action, resource=resource
        )

    def prepare_retry_attempt(
        self, command: PreparePersonalCalendarCreateRetryAttemptCommand
    ) -> PersonalCalendarCreateRetryAttemptResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RETRY_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._retry_result_from_json(replay)

                prior = self._load_attempt(conn, command.prior_execution_attempt_id)
                locked = conn.execute(
                    update(schema.personal_calendar_create_execution_attempt)
                    .where(
                        schema.personal_calendar_create_execution_attempt.c.execution_attempt_id
                        == command.prior_execution_attempt_id
                    )
                    .values(
                        correlation_key=(
                            schema.personal_calendar_create_execution_attempt.c.correlation_key
                        )
                    )
                )
                if locked.rowcount != 1:
                    fail(
                        "CALENDAR_CREATE_RETRY_PRIOR_ATTEMPT_NOT_FOUND",
                        "retry requires the exact prior terminal no-effect execution attempt",
                    )

                prior_state, _ = self._current_attempt_state(
                    conn, command.prior_execution_attempt_id
                )
                guard_head, guard = self._current_guard(conn, prior["action_id"])
                if (
                    guard_head is None
                    or prior_state["status"] != "CONFIRMED_NO_EFFECT"
                    or guard["status"] != "CONFIRMED_NO_EFFECT"
                    or guard["execution_attempt_id"]
                    != command.prior_execution_attempt_id
                ):
                    fail(
                        "CALENDAR_CREATE_RETRY_NOT_ELIGIBLE",
                        "retry requires the exact CONFIRMED_NO_EFFECT attempt to own the Action guard",
                    )

                no_effect = conn.execute(
                    select(schema.personal_calendar_create_no_effect).where(
                        schema.personal_calendar_create_no_effect.c.execution_attempt_id
                        == command.prior_execution_attempt_id
                    )
                ).mappings().one_or_none()
                if (
                    no_effect is None
                    or no_effect["action_id"] != prior["action_id"]
                    or no_effect["status"] != "CONFIRMED_NO_EFFECT"
                    or no_effect["no_effect_schema_version"]
                    != CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION
                ):
                    fail(
                        "CALENDAR_CREATE_RETRY_NO_EFFECT_PROOF_MISSING",
                        "retry requires the exact durable confirmed no-effect lineage",
                    )
                support = conn.execute(
                    select(schema.personal_calendar_create_no_effect_support).where(
                        schema.personal_calendar_create_no_effect_support.c.no_effect_id
                        == no_effect["no_effect_id"]
                    )
                ).mappings().one_or_none()
                evidence = None
                if support is not None:
                    evidence = conn.execute(
                        select(schema.personal_calendar_create_no_effect_evidence).where(
                            schema.personal_calendar_create_no_effect_evidence.c.no_effect_evidence_id
                            == support["no_effect_evidence_id"]
                        )
                    ).mappings().one_or_none()
                if (
                    support is None
                    or support["support_kind"]
                    != CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND
                    or evidence is None
                    or evidence["execution_attempt_id"]
                    != command.prior_execution_attempt_id
                    or evidence["action_id"] != prior["action_id"]
                    or evidence["correlation_key"] != prior["correlation_key"]
                    or evidence["operation_status"] != "TERMINAL_NOT_APPLIED"
                    or evidence["terminality_scope"] != "EXACT_EXECUTION_ATTEMPT"
                    or not evidence["intended_effect_absent"]
                    or not evidence["terminal_non_application"]
                    or evidence["negative_confirmation_contract_version"]
                    != CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
                    or evidence["evidence_schema_version"]
                    != CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION
                ):
                    fail(
                        "CALENDAR_CREATE_RETRY_NO_EFFECT_PROOF_INVALID",
                        "retry requires durable terminal non-application proof for the exact prior attempt",
                    )

                consumed = conn.execute(
                    select(schema.personal_calendar_create_retry_claim).where(
                        schema.personal_calendar_create_retry_claim.c.prior_execution_attempt_id
                        == command.prior_execution_attempt_id
                    )
                ).mappings().one_or_none()
                if consumed is not None:
                    fail(
                        "CALENDAR_CREATE_RETRY_ALREADY_CONSUMED",
                        "confirmed no-effect retry authority has already been consumed",
                    )

                action, _, relationship, resource = self._load_action_lineage(
                    conn, prior["action_id"]
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
                binding = authority["execution_binding"]
                if (
                    binding.negative_confirmation_contract_version
                    != CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
                ):
                    fail(
                        "CALENDAR_CREATE_RETRY_NEGATIVE_CONTRACT_REQUIRED",
                        "retry requires the trusted terminal negative-confirmation contract for the new attempt",
                    )

                maximum_generation = conn.execute(
                    select(
                        func.max(
                            schema.personal_calendar_create_execution_attempt.c.attempt_generation
                        )
                    ).where(
                        schema.personal_calendar_create_execution_attempt.c.action_id
                        == prior["action_id"]
                    )
                ).scalar_one()
                generation = int(maximum_generation or 0) + 1
                execution_attempt_id = self.ids.new()
                correlation_key = self._action_correlation_key(prior["action_id"])
                if correlation_key != prior["correlation_key"]:
                    fail(
                        "CALENDAR_CREATE_RETRY_CORRELATION_INVALID",
                        "retry must preserve the trusted Action-specific external correlation identity",
                    )
                now = self.clock.now()

                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt).values(
                        execution_attempt_id=execution_attempt_id,
                        action_id=prior["action_id"],
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
                conn.execute(
                    insert(schema.personal_calendar_create_retry_claim).values(
                        new_execution_attempt_id=execution_attempt_id,
                        prior_execution_attempt_id=command.prior_execution_attempt_id,
                        action_id=prior["action_id"],
                        no_effect_id=no_effect["no_effect_id"],
                        no_effect_evidence_id=evidence["no_effect_evidence_id"],
                        retry_contract_version=CALENDAR_CREATE_RETRY_CONTRACT_VERSION,
                        claimed_at=now,
                    )
                )

                guard_parent = int(guard_head["current_revision"])
                guard_revision = guard_parent + 1
                conn.execute(
                    insert(schema.personal_calendar_create_action_dispatch_state).values(
                        action_id=prior["action_id"],
                        revision=guard_revision,
                        parent_revision=guard_parent,
                        execution_attempt_id=execution_attempt_id,
                        status="PREPARED",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_action_dispatch_head,
                    key_name="action_id",
                    key_value=prior["action_id"],
                    expected_revision=guard_parent,
                    new_revision=guard_revision,
                    conflict_code=_RETRY_CONFLICT_CODE,
                )

                result = PersonalCalendarCreateRetryAttemptResult(
                    execution_attempt_id=execution_attempt_id,
                    prior_execution_attempt_id=command.prior_execution_attempt_id,
                    action_id=prior["action_id"],
                    no_effect_id=no_effect["no_effect_id"],
                    attempt_generation=generation,
                    correlation_key=correlation_key,
                    status="PREPARED",
                    guard_revision=guard_revision,
                )
                save_operation_receipt(
                    conn,
                    scope=_RETRY_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarCreateRetryAttempt",
                    result_ref=execution_attempt_id,
                    result_json={
                        "execution_attempt_id": str(result.execution_attempt_id),
                        "prior_execution_attempt_id": str(
                            result.prior_execution_attempt_id
                        ),
                        "action_id": str(result.action_id),
                        "no_effect_id": str(result.no_effect_id),
                        "attempt_generation": result.attempt_generation,
                        "correlation_key": result.correlation_key,
                        "status": result.status,
                        "guard_revision": result.guard_revision,
                        "retry_contract_version": result.retry_contract_version,
                    },
                    committed_at=now,
                )
                return result
        except IntegrityError as exc:
            raise DomainError(
                _RETRY_CONFLICT_CODE,
                "calendar-create retry authority was consumed concurrently",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                _RETRY_CONFLICT_CODE,
                "calendar-create retry transition conflicted with concurrent durable state",
            ) from exc

    @staticmethod
    def _retry_result_from_json(payload):
        return PersonalCalendarCreateRetryAttemptResult(
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            prior_execution_attempt_id=UUID(payload["prior_execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            no_effect_id=UUID(payload["no_effect_id"]),
            attempt_generation=int(payload["attempt_generation"]),
            correlation_key=payload["correlation_key"],
            status=payload["status"],
            guard_revision=int(payload["guard_revision"]),
            retry_contract_version=payload["retry_contract_version"],
        )


__all__ = [
    "PersonalCalendarExecutionServices",
    "require_current_calendar_create_execution_binding",
]
