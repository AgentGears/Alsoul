from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterError
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
    CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION,
    DispatchPersonalCalendarCreateMutationCommand,
    PersonalCalendarCreateMutationRequest,
    PersonalCalendarCreateMutationResponse,
    PersonalCalendarCreateMutationTransportResult,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_execution_v2 import (
    PersonalCalendarExecutionServices,
)
from alsoul.storage import schema


_DISPATCH_SCOPE = "DispatchPersonalCalendarCreateMutation"


class PersonalCalendarMutationTransportServices(PersonalCalendarExecutionServices):
    """F5.B one-shot provider transport and minimized effect-evidence boundary.

    This service consumes an already durable ``DISPATCH_FENCED`` attempt. It does not
    create an Effect and does not authorize completion language. Before an adapter call
    can exist, a one-shot structural dispatch marker is committed so process loss or a
    competing caller cannot cause the same ExecutionAttempt to be sent twice.
    """

    def __init__(
        self,
        engine,
        *,
        time_resolver,
        mutation_adapter,
        execution_binding,
        approval_adapter=None,
        clock=None,
        ids=None,
    ) -> None:
        super().__init__(
            engine,
            time_resolver=time_resolver,
            execution_binding=execution_binding,
            approval_adapter=approval_adapter,
            clock=clock,
            ids=ids,
        )
        self.mutation_adapter = mutation_adapter

    def dispatch_create_mutation(
        self, command: DispatchPersonalCalendarCreateMutationCommand
    ) -> PersonalCalendarCreateMutationTransportResult:
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._transport_result_from_json(replay)

        try:
            claimed = self._claim_transport(command=command, req_digest=req)
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_MUTATION_DISPATCH_CONFLICT",
                "calendar-create mutation transport was claimed concurrently",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_MUTATION_DISPATCH_CONFLICT",
                "calendar-create mutation transport conflicted with current durable state",
            ) from exc

        if isinstance(claimed, PersonalCalendarCreateMutationTransportResult):
            return claimed

        request = claimed["request"]
        try:
            response = self.mutation_adapter.create_event(request)
        except AdapterError:
            return self._record_unknown(
                command=command,
                req_digest=req,
                action_id=claimed["action_id"],
            )
        except Exception as exc:
            # The adapter call was reached. Even an implementation failure cannot prove
            # that the provider did not observe the request, so preserve uncertainty.
            self._record_unknown(
                command=command,
                req_digest=req,
                action_id=claimed["action_id"],
            )
            raise DomainError(
                "CALENDAR_CREATE_MUTATION_ADAPTER_FAILURE_UNKNOWN",
                "calendar-create adapter failed after the durable transport claim; external effect is unknown",
            ) from exc

        try:
            normalized = self._normalize_response(
                response=response,
                action=claimed["action"],
                resource=claimed["resource"],
                attempt=claimed["attempt"],
            )
        except DomainError:
            self._record_unknown(
                command=command,
                req_digest=req,
                action_id=claimed["action_id"],
            )
            raise

        try:
            return self._commit_effect_evidence(
                command=command,
                req_digest=req,
                action_id=claimed["action_id"],
                normalized=normalized,
            )
        except (IntegrityError, OperationalError) as exc:
            # The provider response cannot be treated as durable merely because it was
            # observed in memory. The pre-call dispatch marker prevents redispatch; a
            # later recovery path therefore remains conservative.
            raise DomainError(
                "CALENDAR_CREATE_MUTATION_EVIDENCE_PERSISTENCE_UNCERTAIN",
                "calendar-create provider response could not be committed as durable minimized evidence",
            ) from exc

    def _claim_transport(self, *, command, req_digest):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._transport_result_from_json(replay)

            attempt = self._load_attempt(conn, command.execution_attempt_id)
            fence = conn.execute(
                select(schema.personal_calendar_create_execution_fence).where(
                    schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if fence is None:
                fail(
                    "CALENDAR_CREATE_MUTATION_FENCE_MISSING",
                    "calendar-create mutation transport requires the exact durable dispatch fence",
                )

            evidence = conn.execute(
                select(schema.personal_calendar_create_effect_evidence).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if evidence is not None:
                result = self._result_from_evidence(evidence)
                self._save_transport_receipt(
                    conn,
                    command=command,
                    req_digest=req_digest,
                    result=result,
                )
                return result

            dispatch = conn.execute(
                select(schema.personal_calendar_create_mutation_dispatch).where(
                    schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if dispatch is not None:
                result = self._transition_unknown_locked(
                    conn,
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=attempt["action_id"],
                )
                self._save_transport_receipt(
                    conn,
                    command=command,
                    req_digest=req_digest,
                    result=result,
                )
                return result

            attempt_state, _ = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            head, guard = self._current_guard(conn, attempt["action_id"])
            if (
                attempt_state["status"] != "DISPATCH_FENCED"
                or head is None
                or guard["status"] != "DISPATCH_FENCED"
                or guard["execution_attempt_id"] != command.execution_attempt_id
            ):
                fail(
                    "CALENDAR_CREATE_MUTATION_NOT_DISPATCH_ELIGIBLE",
                    "only the current dispatch-fenced owner may cross the mutation transport boundary",
                )

            action, _, _, resource = self._load_action_lineage(conn, attempt["action_id"])
            credential = conn.execute(
                select(schema.credential_binding).where(
                    schema.credential_binding.c.credential_binding_id
                    == attempt["credential_binding_id"]
                )
            ).mappings().one_or_none()
            if (
                credential is None
                or credential["credential_binding_id"] != fence["credential_binding_id"]
                or credential["external_system_ref"] != resource["external_system_ref"]
            ):
                fail(
                    "CALENDAR_CREATE_MUTATION_CREDENTIAL_LINEAGE_INVALID",
                    "fenced mutation attempt no longer resolves its exact credential identity",
                )

            if (
                attempt["action_id"] != fence["action_id"]
                or attempt["attempt_generation"] != fence["attempt_generation"]
                or attempt["correlation_key"] != fence["correlation_key"]
            ):
                fail(
                    "CALENDAR_CREATE_MUTATION_FENCE_LINEAGE_INVALID",
                    "mutation attempt does not match its immutable dispatch-fence lineage",
                )

            self._qualify_pinned_transport(fence=fence, resource=resource)
            request = PersonalCalendarCreateMutationRequest(
                execution_attempt_id=command.execution_attempt_id,
                action_id=action["action_id"],
                external_system_ref=resource["external_system_ref"],
                external_resource_ref=resource["external_resource_ref"],
                summary=action["summary"],
                normalized_start_at=_aware_utc(action["normalized_start_at"]),
                normalized_end_at=_aware_utc(action["normalized_end_at"]),
                correlation_key=attempt["correlation_key"],
                credential_secret_ref=credential["secret_ref"],
                capability_contract_version=fence["capability_contract_version"],
                adapter_contract_version=fence["adapter_contract_version"],
            )

            conn.execute(
                insert(schema.personal_calendar_create_mutation_dispatch).values(
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=action["action_id"],
                    request_contract_version=CALENDAR_CREATE_MUTATION_REQUEST_CONTRACT_VERSION,
                    started_at=self.clock.now(),
                )
            )
            return {
                "request": request,
                "attempt": dict(attempt),
                "action": dict(action),
                "resource": dict(resource),
                "action_id": action["action_id"],
            }

    def _qualify_pinned_transport(self, *, fence, resource) -> None:
        binding = self.execution_binding
        adapter = self.mutation_adapter
        if binding is None or adapter is None or not callable(
            getattr(adapter, "create_event", None)
        ):
            fail(
                "CALENDAR_CREATE_MUTATION_ADAPTER_UNAVAILABLE",
                "calendar-create mutation transport requires the exact trusted pinned adapter",
            )

        pinned_pairs = (
            (binding.adapter_binding_ref, fence["adapter_binding_ref"]),
            (binding.adapter_contract_version, fence["adapter_contract_version"]),
            (binding.executor_contract_version, fence["executor_contract_version"]),
            (binding.correlation_contract_version, fence["correlation_contract_version"]),
            (
                binding.negative_confirmation_contract_version,
                fence["negative_confirmation_contract_version"],
            ),
            (binding.capability_contract_version, fence["capability_contract_version"]),
            (binding.external_system_ref, resource["external_system_ref"]),
        )
        if any(left != right for left, right in pinned_pairs):
            fail(
                "CALENDAR_CREATE_MUTATION_EXECUTION_PINS_MISMATCH",
                "current transport composition does not match the exact execution semantics pinned by the fence",
            )

        adapter_pairs = (
            (getattr(adapter, "adapter_binding_ref", None), fence["adapter_binding_ref"]),
            (
                getattr(adapter, "adapter_contract_version", None),
                fence["adapter_contract_version"],
            ),
            (
                getattr(adapter, "capability_contract_version", None),
                fence["capability_contract_version"],
            ),
            (
                getattr(adapter, "external_system_ref", None),
                resource["external_system_ref"],
            ),
        )
        if any(
            not isinstance(left, str) or not left.strip() or left != right
            for left, right in adapter_pairs
        ):
            fail(
                "CALENDAR_CREATE_MUTATION_ADAPTER_MISMATCH",
                "mutation adapter identity or contract does not match the exact durable fence",
            )

    def _normalize_response(self, *, response, action, resource, attempt):
        if not isinstance(response, PersonalCalendarCreateMutationResponse):
            fail(
                "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID",
                "calendar-create adapter returned material outside the trusted minimized response contract",
            )
        text_fields = (
            response.correlation_key,
            response.external_effect_ref,
            response.external_system_ref,
            response.external_resource_ref,
            response.summary,
            response.receipt_ref,
            response.evidence_schema_version,
        )
        if any(not isinstance(value, str) or not value for value in text_fields):
            fail(
                "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID",
                "calendar-create normalized response contains an empty or invalid required field",
            )
        if (
            response.provider_status != "CREATED"
            or response.evidence_schema_version
            != CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION
        ):
            fail(
                "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID",
                "calendar-create normalized response has unsupported status or evidence schema",
            )
        if any(
            len(value) > 4096
            for value in (
                response.correlation_key,
                response.external_effect_ref,
                response.external_system_ref,
                response.external_resource_ref,
                response.receipt_ref,
            )
        ) or len(response.summary) > 65536:
            fail(
                "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID",
                "calendar-create normalized response exceeds trusted first-slice bounds",
            )

        start = _require_aware(response.normalized_start_at)
        end = _require_aware(response.normalized_end_at)
        observed_at = _require_aware(response.observed_at)
        expected_start = _aware_utc(action["normalized_start_at"])
        expected_end = _aware_utc(action["normalized_end_at"])
        semantic_match = (
            response.correlation_key == attempt["correlation_key"]
            and response.external_system_ref == resource["external_system_ref"]
            and response.external_resource_ref == resource["external_resource_ref"]
            and response.summary == action["summary"]
            and start == expected_start
            and end == expected_end
        )
        return {
            "validation_kind": (
                "SEMANTIC_MATCH" if semantic_match else "SEMANTIC_DIVERGENCE"
            ),
            "correlation_key": response.correlation_key,
            "external_effect_ref": response.external_effect_ref,
            "external_system_ref": response.external_system_ref,
            "external_resource_ref": response.external_resource_ref,
            "normalized_summary": response.summary,
            "normalized_start_at": start,
            "normalized_end_at": end,
            "provider_status": response.provider_status,
            "receipt_ref": response.receipt_ref,
            "observed_at": observed_at,
            "evidence_schema_version": response.evidence_schema_version,
        }

    def _commit_effect_evidence(
        self, *, command, req_digest, action_id: UUID, normalized: dict[str, Any]
    ) -> PersonalCalendarCreateMutationTransportResult:
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._transport_result_from_json(replay)

            dispatch = conn.execute(
                select(schema.personal_calendar_create_mutation_dispatch).where(
                    schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if dispatch is None or dispatch["action_id"] != action_id:
                fail(
                    "CALENDAR_CREATE_MUTATION_DISPATCH_MISSING",
                    "provider response cannot become evidence without the exact durable transport claim",
                )

            existing = conn.execute(
                select(schema.personal_calendar_create_effect_evidence).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                result = self._result_from_evidence(existing)
                self._save_transport_receipt(
                    conn,
                    command=command,
                    req_digest=req_digest,
                    result=result,
                )
                return result

            evidence_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_create_effect_evidence).values(
                    effect_evidence_id=evidence_id,
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=action_id,
                    committed_at=now,
                    **normalized,
                )
            )

            if normalized["validation_kind"] == "SEMANTIC_DIVERGENCE":
                self._transition_unknown_locked(
                    conn,
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=action_id,
                )
                status = "DIVERGENT_EFFECT_EVIDENCE"
            else:
                status = "MATCHED_EFFECT_EVIDENCE"

            result = PersonalCalendarCreateMutationTransportResult(
                execution_attempt_id=command.execution_attempt_id,
                action_id=action_id,
                status=status,
                effect_evidence_id=evidence_id,
            )
            self._save_transport_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
            )
            return result

    def _record_unknown(self, *, command, req_digest, action_id: UUID):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._transport_result_from_json(replay)
            result = self._transition_unknown_locked(
                conn,
                execution_attempt_id=command.execution_attempt_id,
                action_id=action_id,
            )
            self._save_transport_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
            )
            return result

    def _transition_unknown_locked(
        self, conn, *, execution_attempt_id: UUID, action_id: UUID
    ) -> PersonalCalendarCreateMutationTransportResult:
        state, attempt_revision = self._current_attempt_state(conn, execution_attempt_id)
        head, guard = self._current_guard(conn, action_id)
        if head is None or guard["execution_attempt_id"] != execution_attempt_id:
            fail(
                "CALENDAR_CREATE_ACTION_DISPATCH_NOT_OWNED",
                "mutation attempt no longer owns the unresolved Action dispatch guard",
            )

        if state["status"] == "UNKNOWN_EFFECT" and guard["status"] == "UNKNOWN_EFFECT":
            return PersonalCalendarCreateMutationTransportResult(
                execution_attempt_id=execution_attempt_id,
                action_id=action_id,
                status="UNKNOWN_EFFECT",
                effect_evidence_id=None,
            )
        if state["status"] != "DISPATCH_FENCED" or guard["status"] != "DISPATCH_FENCED":
            fail(
                "CALENDAR_CREATE_MUTATION_STATE_INVALID",
                "mutation uncertainty can be admitted only from the unresolved fenced attempt",
            )

        now = self.clock.now()
        new_attempt_revision = attempt_revision + 1
        conn.execute(
            insert(schema.personal_calendar_create_execution_attempt_state).values(
                execution_attempt_id=execution_attempt_id,
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
            key_value=execution_attempt_id,
            expected_revision=attempt_revision,
            new_revision=new_attempt_revision,
            conflict_code="CALENDAR_CREATE_EXECUTION_ATTEMPT_STATE_CONFLICT",
        )
        guard_parent = int(head["current_revision"])
        guard_revision = guard_parent + 1
        conn.execute(
            insert(schema.personal_calendar_create_action_dispatch_state).values(
                action_id=action_id,
                revision=guard_revision,
                parent_revision=guard_parent,
                execution_attempt_id=execution_attempt_id,
                status="UNKNOWN_EFFECT",
                committed_at=now,
            )
        )
        self._advance_head(
            conn,
            head_table=schema.personal_calendar_create_action_dispatch_head,
            key_name="action_id",
            key_value=action_id,
            expected_revision=guard_parent,
            new_revision=guard_revision,
            conflict_code="CALENDAR_CREATE_ACTION_DISPATCH_CONFLICT",
        )
        return PersonalCalendarCreateMutationTransportResult(
            execution_attempt_id=execution_attempt_id,
            action_id=action_id,
            status="UNKNOWN_EFFECT",
            effect_evidence_id=None,
        )

    def _result_from_evidence(self, evidence):
        status = (
            "MATCHED_EFFECT_EVIDENCE"
            if evidence["validation_kind"] == "SEMANTIC_MATCH"
            else "DIVERGENT_EFFECT_EVIDENCE"
        )
        return PersonalCalendarCreateMutationTransportResult(
            execution_attempt_id=evidence["execution_attempt_id"],
            action_id=evidence["action_id"],
            status=status,
            effect_evidence_id=evidence["effect_evidence_id"],
        )

    def _save_transport_receipt(self, conn, *, command, req_digest, result) -> None:
        save_operation_receipt(
            conn,
            scope=_DISPATCH_SCOPE,
            operation_id=command.operation_id,
            req_digest=req_digest,
            result_kind="PersonalCalendarCreateMutationTransport",
            result_ref=result.effect_evidence_id or command.execution_attempt_id,
            result_json={
                "execution_attempt_id": str(result.execution_attempt_id),
                "action_id": str(result.action_id),
                "status": result.status,
                "effect_evidence_id": (
                    str(result.effect_evidence_id)
                    if result.effect_evidence_id is not None
                    else None
                ),
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _transport_result_from_json(payload):
        evidence_id = payload.get("effect_evidence_id")
        return PersonalCalendarCreateMutationTransportResult(
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            status=payload["status"],
            effect_evidence_id=UUID(evidence_id) if evidence_id else None,
        )


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        fail(
            "CALENDAR_CREATE_MUTATION_RESPONSE_INVALID",
            "calendar-create normalized response timestamps must be offset-aware",
        )
    return value.astimezone(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = ["PersonalCalendarMutationTransportServices"]
