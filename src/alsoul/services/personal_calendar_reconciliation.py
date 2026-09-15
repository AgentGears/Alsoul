from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ
from alsoul.domain.personal_calendar_reconciliation import (
    CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION,
    CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION,
    CalendarCreateReconciliationContract,
    PersonalCalendarCreateReconciliationAdapter,
    PersonalCalendarCreateReconciliationObservation,
    PersonalCalendarCreateReconciliationRequest,
    PersonalCalendarCreateReconciliationResult,
    ReconcilePersonalCalendarCreateUnknownEffectCommand,
)
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_effect import PersonalCalendarEffectServices
from alsoul.storage import schema


_RECONCILE_SCOPE = "ReconcilePersonalCalendarCreateUnknownEffect"


class PersonalCalendarReconciliationServices(PersonalCalendarEffectServices):
    """Current-authorized positive reconciliation for an uncertain create attempt.

    Each provider lookup is a separately fenced READ_ONLY transport. A successful
    lookup may create the same minimized Action-correlated evidence shape used by the
    mutation transport, but it does not itself admit terminal Effect truth. A negative
    lookup remains UNKNOWN_EFFECT because ordinary absence is not terminal no-effect
    proof and never releases the per-Action dispatch lock.
    """

    def __init__(
        self,
        engine,
        *,
        time_resolver,
        reconciliation_contract: CalendarCreateReconciliationContract,
        reconciliation_adapter: PersonalCalendarCreateReconciliationAdapter,
        execution_binding=None,
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
        self.reconciliation_contract = reconciliation_contract
        self.reconciliation_adapter = reconciliation_adapter

    def reconcile_unknown_effect(
        self, command: ReconcilePersonalCalendarCreateUnknownEffectCommand
    ) -> PersonalCalendarCreateReconciliationResult:
        req_digest = request_digest(asdict(command))
        try:
            with self.engine.connect() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECONCILE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req_digest,
                )
                if replay:
                    return self._result_from_json(replay)

            self._qualify_contract()
            context = self._start_probe(command, req_digest=req_digest)
            try:
                observation = self.reconciliation_adapter.lookup_create_effect(
                    context["request"]
                )
                normalized = self._normalize_observation(
                    observation=observation,
                    attempt=context["attempt"],
                    action=context["action"],
                    resource=context["resource"],
                )
            except DomainError:
                self._record_unknown(
                    command=command,
                    req_digest=req_digest,
                    context=context,
                )
                raise
            except (AdapterOutcomeUnknown, AdapterRejected):
                return self._record_unknown(
                    command=command,
                    req_digest=req_digest,
                    context=context,
                )

            return self._commit_probe(
                command=command,
                req_digest=req_digest,
                context=context,
                normalized=normalized,
            )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_RECONCILIATION_CONFLICT",
                "calendar-create reconciliation conflicted with concurrent durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_RECONCILIATION_CONFLICT",
                "calendar-create reconciliation conflicted with concurrent durable state",
            ) from exc

    def _qualify_contract(self) -> None:
        contract = self.reconciliation_contract
        adapter = self.reconciliation_adapter
        required_contract_text = (
            contract.contract_version,
            contract.response_schema_version,
            contract.read_capability_contract_version,
            contract.correlation_contract_version,
            contract.semantic_operation,
            contract.effect_class,
            contract.lookup_mode,
            contract.raw_response_minimization_mode,
        )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in required_contract_text
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_CONTRACT_INVALID",
                "calendar-create reconciliation contract must be explicit",
            )
        if (
            contract.contract_version
            != CALENDAR_CREATE_RECONCILIATION_CONTRACT_VERSION
            or contract.response_schema_version
            != CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION
            or contract.semantic_operation != CALENDAR_EVENTS_READ
            or contract.effect_class != "READ_ONLY"
            or contract.lookup_mode != "ACTION_CORRELATION"
            or contract.raw_response_minimization_mode != "EPHEMERAL_TO_ALLOWLIST"
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_CONTRACT_INVALID",
                "calendar-create reconciliation requires the trusted bounded read-side correlation contract",
            )
        if (
            not isinstance(contract.max_probes, int)
            or isinstance(contract.max_probes, bool)
            or contract.max_probes <= 0
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_PROBE_BOUND_INVALID",
                "reconciliation probe bound must be a finite positive integer",
            )
        if adapter is None or not isinstance(
            adapter, PersonalCalendarCreateReconciliationAdapter
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_ADAPTER_INELIGIBLE",
                "trusted calendar-create reconciliation adapter is required",
            )
        adapter_text = (
            adapter.adapter_binding_ref,
            adapter.adapter_version,
            adapter.read_capability_contract_version,
            adapter.correlation_contract_version,
            adapter.external_system_ref,
        )
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 128
            for value in adapter_text
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_ADAPTER_INELIGIBLE",
                "reconciliation adapter must expose bounded stable contract identity",
            )
        if not callable(getattr(adapter, "lookup_create_effect", None)):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_ADAPTER_INELIGIBLE",
                "reconciliation adapter does not implement the trusted lookup contract",
            )
        if (
            adapter.read_capability_contract_version
            != contract.read_capability_contract_version
            or adapter.correlation_contract_version
            != contract.correlation_contract_version
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_ADAPTER_MISMATCH",
                "reconciliation adapter does not match the trusted read/correlation contract",
            )

    def _start_probe(self, command, *, req_digest):
        contract = self.reconciliation_contract
        adapter = self.reconciliation_adapter
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECONCILE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return {"replay": self._result_from_json(replay)}

            attempt = self._load_attempt(conn, command.execution_attempt_id)
            locked = conn.execute(
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
            if locked.rowcount != 1:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_ATTEMPT_NOT_FOUND",
                    "calendar-create execution attempt disappeared before reconciliation",
                )

            state, _ = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            head, guard = self._current_guard(conn, attempt["action_id"])
            if (
                head is None
                or guard["execution_attempt_id"] != command.execution_attempt_id
                or state["status"] != "UNKNOWN_EFFECT"
                or guard["status"] != "UNKNOWN_EFFECT"
            ):
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_STATE_INVALID",
                    "reconciliation requires the exact unresolved UNKNOWN_EFFECT attempt to own the Action guard",
                )

            existing_evidence = conn.execute(
                select(schema.personal_calendar_create_effect_evidence).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if existing_evidence is not None:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_EVIDENCE_ALREADY_PRESENT",
                    "this unresolved attempt already has durable effect evidence requiring admission or explicit compensation handling",
                )

            fence = conn.execute(
                select(schema.personal_calendar_create_execution_fence).where(
                    schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if fence is None:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_FENCE_MISSING",
                    "reconciliation requires the exact durable mutation dispatch fence",
                )
            if (
                fence["action_id"] != attempt["action_id"]
                or fence["attempt_generation"] != attempt["attempt_generation"]
                or fence["correlation_key"] != attempt["correlation_key"]
                or fence["correlation_contract_version"]
                != contract.correlation_contract_version
            ):
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_LINEAGE_INVALID",
                    "reconciliation correlation does not match the immutable fenced execution lineage",
                )

            action, _, relationship, resource = self._load_action_lineage(
                conn, attempt["action_id"]
            )
            relationship_state, relationship_revision = (
                self._current_relationship_authority(
                    conn, action["relationship_id"]
                )
            )
            if relationship_state["status"] != "ACTIVE":
                fail(
                    "RELATIONSHIP_NOT_ACTIVE",
                    "relationship authority ended before reconciliation read dispatch",
                )
            current_resource, resource_state, resource_revision = self._current_resource(
                conn, action["personal_resource_binding_id"]
            )
            active = self._active_calendar_bindings(conn, action["relationship_id"])
            if (
                resource_state["status"] != "ACTIVE"
                or current_resource["relationship_id"] != action["relationship_id"]
                or current_resource["counterpart_id"] != action["counterpart_id"]
                or len(active) != 1
                or active[0]["personal_resource_binding_id"]
                != action["personal_resource_binding_id"]
            ):
                fail(
                    "PERSONAL_RESOURCE_BINDING_NOT_CURRENT",
                    "reconciliation target is not the unique active calendar for this relationship",
                )

            permission = conn.execute(
                select(schema.permission_grant).where(
                    schema.permission_grant.c.permission_id == command.permission_id
                )
            ).mappings().one_or_none()
            if permission is None:
                fail(
                    "CALENDAR_READ_PERMISSION_MISSING",
                    "reconciliation requires current calendar read Permission",
                )
            permission_state, permission_revision = self._current_state(
                conn,
                state_table=schema.permission_state,
                head_table=schema.permission_head,
                key_name="permission_id",
                key_value=command.permission_id,
            )
            now = self.clock.now()
            now_utc = _aware_utc(now)
            if permission_state["status"] != "ACTIVE":
                fail(
                    "CALENDAR_READ_PERMISSION_REVOKED",
                    "calendar read Permission is not active for reconciliation",
                )
            if (
                permission["expires_at"] is not None
                and _aware_utc(permission["expires_at"]) <= now_utc
            ):
                fail(
                    "CALENDAR_READ_PERMISSION_EXPIRED",
                    "calendar read Permission expired before reconciliation",
                )
            if (
                permission["holder_companion_person_id"]
                != relationship["companion_person_id"]
                or permission["counterpart_id"] != relationship["counterpart_id"]
                or permission["relationship_id"] != action["relationship_id"]
                or permission["personal_resource_binding_id"]
                != action["personal_resource_binding_id"]
                or permission["capability_semantic_operation"] != CALENDAR_EVENTS_READ
                or permission["operation_class"] != "READ"
                or permission["grantor_ref"] != relationship["counterpart_id"]
                or permission["grant_source"] != "FIRST_PARTY_COUNTERPART"
            ):
                fail(
                    "CALENDAR_READ_PERMISSION_MISMATCH",
                    "calendar read Permission does not authorize this reconciliation target",
                )

            credential = conn.execute(
                select(schema.credential_binding).where(
                    schema.credential_binding.c.credential_binding_id
                    == command.credential_binding_id
                )
            ).mappings().one_or_none()
            if credential is None:
                fail(
                    "CREDENTIAL_BINDING_NOT_FOUND",
                    "reconciliation credential binding does not exist",
                )
            credential_state, credential_revision = self._current_state(
                conn,
                state_table=schema.credential_binding_state,
                head_table=schema.credential_binding_head,
                key_name="credential_binding_id",
                key_value=command.credential_binding_id,
            )
            if credential_state["status"] != "ACTIVE":
                fail(
                    "CREDENTIAL_BINDING_UNUSABLE",
                    "reconciliation credential binding is revoked",
                )
            if credential["external_system_ref"] != resource["external_system_ref"]:
                fail(
                    "CREDENTIAL_BINDING_MISMATCH",
                    "reconciliation credential targets another external system",
                )

            policy, policy_revision = self._current_policy(
                conn, action["relationship_id"]
            )
            if (
                policy["status"] != "ALLOW"
                or policy["capability_semantic_operation"] != CALENDAR_EVENTS_READ
                or policy["capability_effect_class"] != "READ_ONLY"
            ):
                fail(
                    "AI_CAPABILITY_POLICY_DENIED",
                    "current personal-calendar read policy denies reconciliation",
                )
            if (
                permission["capability_contract_version"]
                != policy["capability_contract_version"]
                or permission["grant_policy_version"]
                != policy["permission_grant_policy_version"]
            ):
                fail(
                    "CALENDAR_READ_PERMISSION_MISMATCH",
                    "reconciliation read Permission no longer matches current read policy",
                )
            if (
                policy["capability_contract_version"]
                != contract.read_capability_contract_version
                or adapter.read_capability_contract_version
                != policy["capability_contract_version"]
            ):
                fail(
                    "CAPABILITY_CONTRACT_VERSION_MISMATCH",
                    "reconciliation adapter and current read capability versions differ",
                )
            allowed_ids = {
                str(value) for value in policy["allowed_resource_binding_ids_json"]
            }
            if str(action["personal_resource_binding_id"]) not in allowed_ids:
                fail(
                    "RESOURCE_SCOPE_DENIED",
                    "calendar-create target is outside current reconciliation read scope",
                )
            scopes = {
                str(value) for value in credential_state["provider_scopes_json"]
            }
            if policy["required_provider_scope"] not in scopes:
                fail(
                    "PROVIDER_TECHNICAL_SCOPE_INSUFFICIENT",
                    "reconciliation credential lacks the current required provider scope",
                )
            if adapter.external_system_ref != resource["external_system_ref"]:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_ADAPTER_MISMATCH",
                    "reconciliation adapter targets another external system",
                )

            maximum_generation = conn.execute(
                select(
                    func.max(
                        schema.personal_calendar_create_reconciliation_probe.c.generation
                    )
                ).where(
                    schema.personal_calendar_create_reconciliation_probe.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).scalar_one()
            generation = int(maximum_generation or 0) + 1
            if generation > contract.max_probes:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_PROBE_LIMIT_EXCEEDED",
                    "calendar-create reconciliation exhausted the trusted bounded probe count",
                )

            self._cas_head_same(
                conn,
                table=schema.personal_world_relationship_head,
                key_name="relationship_id",
                key_value=action["relationship_id"],
                expected_revision=relationship_revision,
                conflict_code="CALENDAR_CREATE_RECONCILIATION_RELATIONSHIP_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_resource_binding_head,
                key_name="personal_resource_binding_id",
                key_value=action["personal_resource_binding_id"],
                expected_revision=resource_revision,
                conflict_code="CALENDAR_CREATE_RECONCILIATION_RESOURCE_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.permission_head,
                key_name="permission_id",
                key_value=command.permission_id,
                expected_revision=permission_revision,
                conflict_code="CALENDAR_CREATE_RECONCILIATION_PERMISSION_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.credential_binding_head,
                key_name="credential_binding_id",
                key_value=command.credential_binding_id,
                expected_revision=credential_revision,
                conflict_code="CALENDAR_CREATE_RECONCILIATION_CREDENTIAL_CHANGED",
            )
            self._cas_head_same(
                conn,
                table=schema.personal_calendar_read_policy_head,
                key_name="relationship_id",
                key_value=action["relationship_id"],
                expected_revision=policy_revision,
                conflict_code="CALENDAR_CREATE_RECONCILIATION_POLICY_CHANGED",
            )

            probe_id = self.ids.new()
            authority_fence_id = self.ids.new()
            conn.execute(
                insert(schema.personal_calendar_create_reconciliation_probe).values(
                    reconciliation_probe_id=probe_id,
                    authority_fence_id=authority_fence_id,
                    execution_attempt_id=command.execution_attempt_id,
                    action_id=attempt["action_id"],
                    generation=generation,
                    correlation_key=attempt["correlation_key"],
                    relationship_id=action["relationship_id"],
                    relationship_authority_revision=relationship_revision,
                    personal_resource_binding_id=action["personal_resource_binding_id"],
                    resource_binding_state_revision=resource_revision,
                    permission_id=command.permission_id,
                    permission_state_revision=permission_revision,
                    credential_binding_id=command.credential_binding_id,
                    credential_state_revision=credential_revision,
                    read_policy_revision=policy_revision,
                    read_capability_contract_version=policy[
                        "capability_contract_version"
                    ],
                    ai_policy_version=policy["ai_policy_version"],
                    resource_scope_version=policy["resource_scope_version"],
                    adapter_binding_ref=adapter.adapter_binding_ref,
                    adapter_version=adapter.adapter_version,
                    correlation_contract_version=adapter.correlation_contract_version,
                    reconciliation_contract_version=contract.contract_version,
                    status="STARTED",
                    effect_evidence_id=None,
                    started_at=now,
                    completed_at=None,
                )
            )
            request = PersonalCalendarCreateReconciliationRequest(
                authority_fence_id=authority_fence_id,
                reconciliation_probe_id=probe_id,
                execution_attempt_id=command.execution_attempt_id,
                action_id=attempt["action_id"],
                external_system_ref=resource["external_system_ref"],
                external_resource_ref=resource["external_resource_ref"],
                correlation_key=attempt["correlation_key"],
                credential_secret_ref=credential["secret_ref"],
                correlation_contract_version=adapter.correlation_contract_version,
            )
            return {
                "probe_id": probe_id,
                "attempt": dict(attempt),
                "action": dict(action),
                "resource": dict(resource),
                "request": request,
            }

    def _normalize_observation(self, *, observation, attempt, action, resource):
        if not isinstance(
            observation, PersonalCalendarCreateReconciliationObservation
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "reconciliation adapter returned material outside the trusted minimized response contract",
            )
        if (
            observation.response_schema_version
            != CALENDAR_CREATE_RECONCILIATION_RESPONSE_SCHEMA_VERSION
            or observation.status not in {"FOUND", "NOT_FOUND"}
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "reconciliation response has an unsupported status or schema version",
            )
        if (
            not isinstance(observation.correlation_key, str)
            or not observation.correlation_key
            or len(observation.correlation_key) > 256
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "reconciliation response correlation is invalid",
            )
        if observation.correlation_key != attempt["correlation_key"]:
            fail(
                "CALENDAR_CREATE_RECONCILIATION_CORRELATION_MISMATCH",
                "reconciliation response does not belong to the exact Action correlation",
            )
        observed_at = _require_aware(observation.observed_at)

        effect_fields = (
            observation.external_effect_ref,
            observation.external_system_ref,
            observation.external_resource_ref,
            observation.summary,
            observation.normalized_start_at,
            observation.normalized_end_at,
            observation.provider_status,
            observation.receipt_ref,
        )
        if observation.status == "NOT_FOUND":
            if any(value is not None for value in effect_fields):
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                    "NOT_FOUND reconciliation responses cannot carry unrelated effect material",
                )
            return {
                "probe_status": "NOT_FOUND",
                "observed_at": observed_at,
                "evidence": None,
            }

        text_fields = (
            observation.external_effect_ref,
            observation.external_system_ref,
            observation.external_resource_ref,
            observation.summary,
            observation.provider_status,
            observation.receipt_ref,
        )
        if any(
            not isinstance(value, str) or not value
            for value in text_fields
        ):
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "FOUND reconciliation response lacks required minimized effect fields",
            )
        if observation.provider_status != "CREATED":
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "FOUND reconciliation response does not establish provider-created status",
            )
        if any(
            len(value) > 4096
            for value in (
                observation.external_effect_ref,
                observation.external_system_ref,
                observation.external_resource_ref,
                observation.receipt_ref,
            )
        ) or len(observation.summary) > 65536:
            fail(
                "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
                "reconciliation response exceeds trusted first-slice bounds",
            )
        start = _require_aware(observation.normalized_start_at)
        end = _require_aware(observation.normalized_end_at)
        semantic_match = (
            observation.external_system_ref == resource["external_system_ref"]
            and observation.external_resource_ref == resource["external_resource_ref"]
            and observation.summary == action["summary"]
            and start == _aware_utc(action["normalized_start_at"])
            and end == _aware_utc(action["normalized_end_at"])
        )
        return {
            "probe_status": (
                "MATCHED_EFFECT_EVIDENCE"
                if semantic_match
                else "DIVERGENT_EFFECT_EVIDENCE"
            ),
            "observed_at": observed_at,
            "evidence": {
                "validation_kind": (
                    "SEMANTIC_MATCH" if semantic_match else "SEMANTIC_DIVERGENCE"
                ),
                "correlation_key": observation.correlation_key,
                "external_effect_ref": observation.external_effect_ref,
                "external_system_ref": observation.external_system_ref,
                "external_resource_ref": observation.external_resource_ref,
                "normalized_summary": observation.summary,
                "normalized_start_at": start,
                "normalized_end_at": end,
                "provider_status": observation.provider_status,
                "receipt_ref": observation.receipt_ref,
                "observed_at": observed_at,
                "evidence_schema_version": (
                    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION
                ),
            },
        }

    def _commit_probe(self, *, command, req_digest, context, normalized):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECONCILE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._result_from_json(replay)

            probe = conn.execute(
                select(schema.personal_calendar_create_reconciliation_probe).where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"]
                )
            ).mappings().one_or_none()
            if probe is None or probe["status"] != "STARTED":
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_PROBE_STATE_INVALID",
                    "reconciliation observation cannot commit without its exact STARTED authority fence",
                )
            state, _ = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            head, guard = self._current_guard(conn, context["attempt"]["action_id"])
            if (
                head is None
                or guard["execution_attempt_id"] != command.execution_attempt_id
                or state["status"] != "UNKNOWN_EFFECT"
                or guard["status"] != "UNKNOWN_EFFECT"
            ):
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_STATE_CHANGED",
                    "unresolved Action state changed before reconciliation evidence could commit",
                )
            existing = conn.execute(
                select(schema.personal_calendar_create_effect_evidence).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_EVIDENCE_CONFLICT",
                    "another durable effect-evidence lineage won before this reconciliation commit",
                )

            effect_evidence_id = None
            if normalized["evidence"] is not None:
                effect_evidence_id = self.ids.new()
                conn.execute(
                    insert(schema.personal_calendar_create_effect_evidence).values(
                        effect_evidence_id=effect_evidence_id,
                        execution_attempt_id=command.execution_attempt_id,
                        action_id=context["attempt"]["action_id"],
                        committed_at=self.clock.now(),
                        **normalized["evidence"],
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
                .values(
                    status=normalized["probe_status"],
                    effect_evidence_id=effect_evidence_id,
                    completed_at=self.clock.now(),
                )
            )
            result_status = (
                normalized["probe_status"]
                if normalized["evidence"] is not None
                else "UNKNOWN_EFFECT"
            )
            result = PersonalCalendarCreateReconciliationResult(
                reconciliation_probe_id=context["probe_id"],
                execution_attempt_id=command.execution_attempt_id,
                action_id=context["attempt"]["action_id"],
                status=result_status,
                effect_evidence_id=effect_evidence_id,
            )
            self._save_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
            )
            return result

    def _record_unknown(self, *, command, req_digest, context):
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RECONCILE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._result_from_json(replay)
            probe = conn.execute(
                select(schema.personal_calendar_create_reconciliation_probe).where(
                    schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                    == context["probe_id"]
                )
            ).mappings().one_or_none()
            if probe is None:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_PROBE_MISSING",
                    "reconciliation uncertainty cannot be recorded without its durable authority fence",
                )
            if probe["status"] == "STARTED":
                conn.execute(
                    update(schema.personal_calendar_create_reconciliation_probe)
                    .where(
                        schema.personal_calendar_create_reconciliation_probe.c.reconciliation_probe_id
                        == context["probe_id"],
                        schema.personal_calendar_create_reconciliation_probe.c.status
                        == "STARTED",
                    )
                    .values(status="UNKNOWN", completed_at=self.clock.now())
                )
            result = PersonalCalendarCreateReconciliationResult(
                reconciliation_probe_id=context["probe_id"],
                execution_attempt_id=command.execution_attempt_id,
                action_id=context["attempt"]["action_id"],
                status="UNKNOWN_EFFECT",
                effect_evidence_id=None,
            )
            self._save_receipt(
                conn,
                command=command,
                req_digest=req_digest,
                result=result,
            )
            return result

    def _save_receipt(self, conn, *, command, req_digest, result) -> None:
        save_operation_receipt(
            conn,
            scope=_RECONCILE_SCOPE,
            operation_id=command.operation_id,
            req_digest=req_digest,
            result_kind="PersonalCalendarCreateReconciliation",
            result_ref=result.effect_evidence_id or result.reconciliation_probe_id,
            result_json={
                "reconciliation_probe_id": str(result.reconciliation_probe_id),
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
    def _result_from_json(payload):
        evidence_id = payload.get("effect_evidence_id")
        return PersonalCalendarCreateReconciliationResult(
            reconciliation_probe_id=UUID(payload["reconciliation_probe_id"]),
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            action_id=UUID(payload["action_id"]),
            status=payload["status"],
            effect_evidence_id=UUID(evidence_id) if evidence_id else None,
        )


def _require_aware(value: datetime | None) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        fail(
            "CALENDAR_CREATE_RECONCILIATION_RESPONSE_INVALID",
            "reconciliation response timestamps must be offset-aware",
        )
    return value.astimezone(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = ["PersonalCalendarReconciliationServices"]
