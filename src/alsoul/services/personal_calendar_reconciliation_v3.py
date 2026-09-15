from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ
from alsoul.domain.personal_calendar_no_effect import (
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION,
    CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION,
    CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION,
    CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION,
    CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND,
    CalendarCreateNegativeConfirmationContract,
    PersonalCalendarCreateNegativeConfirmationAdapter,
    PersonalCalendarCreateNegativeConfirmationRequest,
    PersonalCalendarCreateNoEffectReconciliationResult,
    PersonalCalendarCreateTerminalNoEffectObservation,
    ReconcilePersonalCalendarCreateNoEffectCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_reconciliation import _is_transient_lock_collision
from alsoul.services.personal_calendar_reconciliation_v2 import (
    PersonalCalendarReconciliationServices as PersonalCalendarReconciliationServicesV2,
)
from alsoul.storage import schema


_NO_EFFECT_SCOPE = "ReconcilePersonalCalendarCreateNoEffect"


class PersonalCalendarReconciliationServices(PersonalCalendarReconciliationServicesV2):
    """Current reconciliation boundary including terminal negative proof.

    Ordinary absence remains UNKNOWN_EFFECT. CONFIRMED_NO_EFFECT is admitted only from
    a separately qualified terminal-negative contract proving both authoritative
    Action-correlated absence and terminal non-application for the exact fenced
    ExecutionAttempt whose mutation dispatch claim actually crossed the one-shot
    provider boundary.
    """

    def __init__(
        self,
        engine,
        *,
        time_resolver,
        reconciliation_contract,
        reconciliation_adapter,
        negative_confirmation_contract: CalendarCreateNegativeConfirmationContract
        | None = None,
        execution_binding=None,
        approval_adapter=None,
        clock=None,
        ids=None,
    ) -> None:
        super().__init__(
            engine,
            time_resolver=time_resolver,
            reconciliation_contract=reconciliation_contract,
            reconciliation_adapter=reconciliation_adapter,
            execution_binding=execution_binding,
            approval_adapter=approval_adapter,
            clock=clock,
            ids=ids,
        )
        self.negative_confirmation_contract = negative_confirmation_contract

    def reconcile_confirmed_no_effect(
        self, command: ReconcilePersonalCalendarCreateNoEffectCommand
    ) -> PersonalCalendarCreateNoEffectReconciliationResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.connect() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_NO_EFFECT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._no_effect_result_from_json(replay)

            self._qualify_contract()
            self._qualify_negative_confirmation_contract()
            self._preflight_terminal_no_effect(command)
            replay = self._claim_no_effect_operation(command, req_digest=req)
            if replay is not None:
                return replay

            # The inherited probe boundary has its own legacy operation-replay scope.
            # Use an internal structural operation id so the user-visible no-effect
            # operation cannot collide with a prior positive-reconciliation receipt.
            probe_command = replace(command, operation_id=self.ids.new())
            probe_req = request_digest(asdict(probe_command))
            context = self._start_probe(probe_command, req_digest=probe_req)
            if "replay" in context:
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_PROBE_REPLAY_INVALID",
                    "terminal no-effect probe unexpectedly resolved through another reconciliation operation",
                )
            self._bind_operation_probe(
                command.operation_id, context["probe_id"]
            )

            request = PersonalCalendarCreateNegativeConfirmationRequest.from_reconciliation_request(
                context["request"]
            )
            adapter = self.reconciliation_adapter
            try:
                observation = adapter.lookup_terminal_no_effect(request)
                normalized = self._normalize_terminal_no_effect_observation(
                    observation=observation,
                    attempt=context["attempt"],
                )
            except (AdapterOutcomeUnknown, AdapterRejected):
                return self._commit_no_effect_unknown(
                    command=command,
                    req_digest=req,
                    context=context,
                )
            except DomainError:
                self._mark_no_effect_probe_unknown(
                    command=command,
                    context=context,
                )
                raise

            if normalized is None:
                return self._commit_no_effect_unknown(
                    command=command,
                    req_digest=req,
                    context=context,
                )
            return self._commit_confirmed_no_effect(
                command=command,
                req_digest=req,
                context=context,
                normalized=normalized,
            )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_NO_EFFECT_CONFLICT",
                "calendar-create terminal no-effect reconciliation conflicted with concurrent durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_NO_EFFECT_CONFLICT",
                "calendar-create terminal no-effect reconciliation conflicted with concurrent durable state",
            ) from exc

    def _qualify_negative_confirmation_contract(self) -> None:
        contract = self.negative_confirmation_contract
        adapter = self.reconciliation_adapter
        if contract is None or not isinstance(
            contract, CalendarCreateNegativeConfirmationContract
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_MISSING",
                "authoritative no-effect reconciliation requires an explicit trusted terminal-negative contract",
            )
        required = (
            contract.contract_version,
            contract.response_schema_version,
            contract.read_capability_contract_version,
            contract.correlation_contract_version,
            contract.semantic_operation,
            contract.effect_class,
            contract.lookup_mode,
            contract.terminal_operation_status,
            contract.terminality_scope,
            contract.delayed_application_mode,
            contract.intended_effect_absence_mode,
            contract.retry_correlation_mode,
            contract.raw_response_minimization_mode,
        )
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 128
            for value in required
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_INVALID",
                "terminal-negative contract metadata must be explicit and bounded",
            )
        if (
            contract.contract_version
            != CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_VERSION
            or contract.response_schema_version
            != CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_SCHEMA_VERSION
            or contract.semantic_operation != CALENDAR_EVENTS_READ
            or contract.effect_class != "READ_ONLY"
            or contract.lookup_mode != "ACTION_CORRELATION_TERMINAL_STATUS"
            or contract.terminal_operation_status != "TERMINAL_NOT_APPLIED"
            or contract.terminality_scope != "EXACT_EXECUTION_ATTEMPT"
            or contract.delayed_application_mode != "PROHIBITED_AFTER_TERMINAL"
            or contract.intended_effect_absence_mode
            != "ACTION_CORRELATION_AUTHORITATIVE"
            or contract.retry_correlation_mode
            != "REUSE_ACTION_CORRELATION_AFTER_TERMINAL"
            or contract.raw_response_minimization_mode != "EPHEMERAL_TO_ALLOWLIST"
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_INVALID",
                "negative confirmation must prove exact-attempt terminal non-application before retry can ever become eligible",
            )
        if (
            contract.read_capability_contract_version
            != self.reconciliation_contract.read_capability_contract_version
            or contract.correlation_contract_version
            != self.reconciliation_contract.correlation_contract_version
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CONTRACT_MISMATCH",
                "terminal-negative and reconciliation read/correlation contracts disagree",
            )
        if adapter is None or not isinstance(
            adapter, PersonalCalendarCreateNegativeConfirmationAdapter
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_ADAPTER_INELIGIBLE",
                "terminal no-effect proof requires a trusted negative-confirmation adapter",
            )
        if (
            adapter.read_capability_contract_version
            != contract.read_capability_contract_version
            or adapter.correlation_contract_version
            != contract.correlation_contract_version
            or adapter.negative_confirmation_contract_version
            != contract.contract_version
            or not callable(getattr(adapter, "lookup_terminal_no_effect", None))
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_ADAPTER_MISMATCH",
                "negative-confirmation adapter does not implement the exact trusted terminal contract",
            )

    def _preflight_terminal_no_effect(self, command) -> None:
        contract = self.negative_confirmation_contract
        with self.engine.connect() as conn:
            attempt = self._load_attempt(conn, command.execution_attempt_id)
            fence = conn.execute(
                select(schema.personal_calendar_create_execution_fence).where(
                    schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            dispatch = conn.execute(
                select(schema.personal_calendar_create_mutation_dispatch).where(
                    schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
        if fence is None or (
            fence["action_id"] != attempt["action_id"]
            or fence["correlation_key"] != attempt["correlation_key"]
            or fence["negative_confirmation_contract_version"]
            != contract.contract_version
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_FENCE_MISMATCH",
                "terminal no-effect proof must use the exact negative-confirmation semantics pinned by the mutation dispatch fence",
            )
        if (
            dispatch is None
            or dispatch["action_id"] != attempt["action_id"]
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_DISPATCH_CLAIM_MISSING",
                "terminal no-effect truth cannot be established for an attempt that never acquired the durable provider mutation dispatch claim",
            )

    def _claim_no_effect_operation(self, command, *, req_digest):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_NO_EFFECT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._no_effect_result_from_json(replay)
            existing = conn.execute(
                select(schema.personal_calendar_create_no_effect_operation_claim).where(
                    schema.personal_calendar_create_no_effect_operation_claim.c.operation_id
                    == command.operation_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                if existing["request_digest"] != req_digest:
                    fail(
                        "CALENDAR_CREATE_NO_EFFECT_OPERATION_ID_REUSED",
                        "no-effect reconciliation operation id was reused with a different request",
                    )
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_OPERATION_RECOVERY_REQUIRED",
                    "the same no-effect reconciliation operation is already in progress or requires explicit recovery",
                )
            conn.execute(
                insert(schema.personal_calendar_create_no_effect_operation_claim).values(
                    operation_id=command.operation_id,
                    execution_attempt_id=command.execution_attempt_id,
                    request_digest=req_digest,
                    reconciliation_probe_id=None,
                    status="STARTED",
                    created_at=self.clock.now(),
                    completed_at=None,
                )
            )
        return None

    def _bind_operation_probe(self, operation_id: UUID, probe_id: UUID) -> None:
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(schema.personal_calendar_create_no_effect_operation_claim)
                .where(
                    schema.personal_calendar_create_no_effect_operation_claim.c.operation_id
                    == operation_id,
                    schema.personal_calendar_create_no_effect_operation_claim.c.status
                    == "STARTED",
                    schema.personal_calendar_create_no_effect_operation_claim.c.reconciliation_probe_id.is_(
                        None
                    ),
                )
                .values(reconciliation_probe_id=probe_id)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_OPERATION_CLAIM_INVALID",
                    "terminal no-effect probe cannot bind to its exact durable operation claim",
                )

    def _normalize_terminal_no_effect_observation(self, *, observation, attempt):
        contract = self.negative_confirmation_contract
        if not isinstance(
            observation, PersonalCalendarCreateTerminalNoEffectObservation
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_INVALID",
                "negative-confirmation adapter returned material outside the trusted minimized response contract",
            )
        if (
            observation.response_schema_version != contract.response_schema_version
            or observation.status not in {"TERMINAL_NO_EFFECT", "INCONCLUSIVE"}
            or not isinstance(observation.correlation_key, str)
            or not observation.correlation_key
            or len(observation.correlation_key) > 256
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_INVALID",
                "negative-confirmation response has invalid schema, status, or correlation material",
            )
        if observation.correlation_key != attempt["correlation_key"]:
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_CORRELATION_MISMATCH",
                "negative-confirmation response does not belong to the exact Action correlation",
            )
        observed_at = _require_aware(observation.observed_at)
        if observation.status == "INCONCLUSIVE":
            return None
        if (
            observation.intended_effect_absent is not True
            or observation.terminal_non_application is not True
            or observation.terminality_scope != contract.terminality_scope
            or observation.operation_status != contract.terminal_operation_status
            or not _bounded_proof_ref(observation.terminality_proof_ref)
            or not _bounded_proof_ref(observation.absence_proof_ref)
        ):
            fail(
                "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_NOT_TERMINAL",
                "provider observation does not prove both authoritative absence and terminal non-application for the exact attempt",
            )
        return {
            "correlation_key": observation.correlation_key,
            "operation_status": observation.operation_status,
            "terminality_scope": observation.terminality_scope,
            "intended_effect_absent": True,
            "terminal_non_application": True,
            "terminality_proof_ref": observation.terminality_proof_ref,
            "absence_proof_ref": observation.absence_proof_ref,
            "negative_confirmation_contract_version": contract.contract_version,
            "observed_at": observed_at,
            "evidence_schema_version": CALENDAR_CREATE_NO_EFFECT_EVIDENCE_SCHEMA_VERSION,
        }

    def _commit_confirmed_no_effect(
        self, *, command, req_digest, context, normalized
    ):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_NO_EFFECT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._no_effect_result_from_json(replay)

            attempt = self._load_attempt(conn, command.execution_attempt_id)
            conn.execute(
                update(schema.personal_calendar_create_execution_attempt)
                .where(
                    schema.personal_calendar_create_execution_attempt.c.execution_attempt_id
                    == command.execution_attempt_id
                )
                .values(
                    correlation_key=(
                        schema.personal_calendar_create_execution_attempt.c.correlation_key
                    )
                )
            )
            state, attempt_revision = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            guard_head, guard = self._current_guard(conn, attempt["action_id"])
            if (
                guard_head is None
                or state["status"] != "UNKNOWN_EFFECT"
                or guard["status"] != "UNKNOWN_EFFECT"
                or guard["execution_attempt_id"] != command.execution_attempt_id
            ):
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_STATE_CHANGED",
                    "unresolved Action state changed before terminal no-effect truth could commit",
                )
            probe = conn.execute(
                select(schema.personal_calendar_create_reconciliation_probe).where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"]
                )
            ).mappings().one_or_none()
            if probe is None or probe["status"] != "STARTED":
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_PROBE_STATE_INVALID",
                    "terminal no-effect evidence requires its exact STARTED reconciliation authority fence",
                )
            positive_evidence = conn.execute(
                select(schema.personal_calendar_create_effect_evidence.c.effect_evidence_id).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).scalar_one_or_none()
            positive_effect = conn.execute(
                select(schema.personal_calendar_create_effect.c.effect_id).where(
                    schema.personal_calendar_create_effect.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).scalar_one_or_none()
            existing_no_effect = conn.execute(
                select(schema.personal_calendar_create_no_effect.c.no_effect_id).where(
                    schema.personal_calendar_create_no_effect.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).scalar_one_or_none()
            if (
                positive_evidence is not None
                or positive_effect is not None
                or existing_no_effect is not None
            ):
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_EVIDENCE_CONFLICT",
                    "terminal no-effect truth conflicts with another durable effect lineage for this attempt",
                )

            now = self.clock.now()
            evidence_id = self.ids.new()
            no_effect_id = self.ids.new()
            conn.execute(
                insert(schema.personal_calendar_create_no_effect_evidence).values(
                    no_effect_evidence_id=evidence_id,
                    reconciliation_probe_id=context["probe_id"],
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=attempt["action_id"],
                    committed_at=now,
                    **normalized,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_create_no_effect).values(
                    no_effect_id=no_effect_id,
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=attempt["action_id"],
                    status="CONFIRMED_NO_EFFECT",
                    no_effect_schema_version=CALENDAR_CREATE_NO_EFFECT_SCHEMA_VERSION,
                    admitted_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_create_no_effect_support).values(
                    no_effect_id=no_effect_id,
                    no_effect_evidence_id=evidence_id,
                    support_kind=CALENDAR_CREATE_NO_EFFECT_SUPPORT_KIND,
                    committed_at=now,
                )
            )
            conn.execute(
                update(schema.personal_calendar_create_reconciliation_probe)
                .where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"],
                    schema.personal_calendar_create_reconciliation_probe.c.status
                    == "STARTED",
                )
                .values(status="NOT_FOUND", completed_at=now)
            )

            new_attempt_revision = attempt_revision + 1
            conn.execute(
                insert(schema.personal_calendar_create_execution_attempt_state).values(
                    execution_attempt_id=command.execution_attempt_id,
                    revision=new_attempt_revision,
                    parent_revision=attempt_revision,
                    status="CONFIRMED_NO_EFFECT",
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
                conflict_code="CALENDAR_CREATE_NO_EFFECT_ATTEMPT_STATE_CONFLICT",
            )
            guard_parent = int(guard_head["current_revision"])
            guard_revision = guard_parent + 1
            conn.execute(
                insert(schema.personal_calendar_create_action_dispatch_state).values(
                    action_id=attempt["action_id"],
                    revision=guard_revision,
                    parent_revision=guard_parent,
                    execution_attempt_id=command.execution_attempt_id,
                    status="CONFIRMED_NO_EFFECT",
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
                conflict_code="CALENDAR_CREATE_NO_EFFECT_GUARD_CONFLICT",
            )

            result = PersonalCalendarCreateNoEffectReconciliationResult(
                reconciliation_probe_id=context["probe_id"],
                execution_attempt_id=command.execution_attempt_id,
                action_id=attempt["action_id"],
                status="CONFIRMED_NO_EFFECT",
                no_effect_id=no_effect_id,
                no_effect_evidence_id=evidence_id,
            )
            self._complete_no_effect_operation(
                conn,
                operation_id=command.operation_id,
                probe_id=context["probe_id"],
                completed_at=now,
            )
            self._save_no_effect_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
                committed_at=now,
            )
            return result

    def _commit_no_effect_unknown(self, *, command, req_digest, context):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_NO_EFFECT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._no_effect_result_from_json(replay)
            now = self.clock.now()
            changed = conn.execute(
                update(schema.personal_calendar_create_reconciliation_probe)
                .where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"],
                    schema.personal_calendar_create_reconciliation_probe.c.status
                    == "STARTED",
                )
                .values(status="UNKNOWN", completed_at=now)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_CREATE_NO_EFFECT_PROBE_STATE_INVALID",
                    "inconclusive terminal reconciliation lost ownership of its exact probe",
                )
            result = PersonalCalendarCreateNoEffectReconciliationResult(
                reconciliation_probe_id=context["probe_id"],
                execution_attempt_id=command.execution_attempt_id,
                action_id=context["attempt"]["action_id"],
                status="UNKNOWN_EFFECT",
            )
            self._complete_no_effect_operation(
                conn,
                operation_id=command.operation_id,
                probe_id=context["probe_id"],
                completed_at=now,
            )
            self._save_no_effect_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
                committed_at=now,
            )
            return result

    def _mark_no_effect_probe_unknown(self, *, command, context) -> None:
        with self.engine.begin() as conn:
            now = self.clock.now()
            conn.execute(
                update(schema.personal_calendar_create_reconciliation_probe)
                .where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"],
                    schema.personal_calendar_create_reconciliation_probe.c.status
                    == "STARTED",
                )
                .values(status="UNKNOWN", completed_at=now)
            )
            self._complete_no_effect_operation(
                conn,
                operation_id=command.operation_id,
                probe_id=context["probe_id"],
                completed_at=now,
            )

    @staticmethod
    def _complete_no_effect_operation(
        conn, *, operation_id: UUID, probe_id: UUID, completed_at
    ) -> None:
        changed = conn.execute(
            update(schema.personal_calendar_create_no_effect_operation_claim)
            .where(
                schema.personal_calendar_create_no_effect_operation_claim.c.operation_id
                == operation_id,
                schema.personal_calendar_create_no_effect_operation_claim.c.status
                == "STARTED",
                schema.personal_calendar_create_no_effect_operation_claim.c.reconciliation_probe_id
                == probe_id,
            )
            .values(status="COMPLETED", completed_at=completed_at)
        )
        if changed.rowcount != 1:
            fail(
                "CALENDAR_CREATE_NO_EFFECT_OPERATION_CLAIM_INVALID",
                "terminal no-effect operation claim did not match the completing probe",
            )

    def _save_no_effect_receipt(
        self, conn, *, command, req_digest, result, committed_at
    ) -> None:
        save_operation_receipt(
            conn,
            scope=_NO_EFFECT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req_digest,
            result_kind="PersonalCalendarCreateNoEffectReconciliation",
            result_ref=result.no_effect_id or result.reconciliation_probe_id,
            result_json={
                "reconciliation_probe_id": str(result.reconciliation_probe_id),
                "execution_attempt_id": str(result.execution_attempt_id),
                "action_id": str(result.action_id),
                "status": result.status,
                "no_effect_id": (
                    str(result.no_effect_id) if result.no_effect_id is not None else None
                ),
                "no_effect_evidence_id": (
                    str(result.no_effect_evidence_id)
                    if result.no_effect_evidence_id is not None
                    else None
                ),
            },
            committed_at=committed_at,
        )

    @staticmethod
    def _no_effect_result_from_json(payload):
        no_effect_id = payload.get("no_effect_id")
        evidence_id = payload.get("no_effect_evidence_id")
        return PersonalCalendarCreateNoEffectReconciliationResult(
            reconciliation_probe_id=UUID(payload["reconciliation_probe_id"]),
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            status=payload["status"],
            no_effect_id=UUID(no_effect_id) if no_effect_id else None,
            no_effect_evidence_id=UUID(evidence_id) if evidence_id else None,
        )


def _require_aware(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        fail(
            "CALENDAR_CREATE_NEGATIVE_CONFIRMATION_RESPONSE_INVALID",
            "negative-confirmation observation timestamp must be offset-aware",
        )
    return value.astimezone(timezone.utc)


def _bounded_proof_ref(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4096


__all__ = ["PersonalCalendarReconciliationServices"]
