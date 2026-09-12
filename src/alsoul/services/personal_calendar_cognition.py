from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ
from alsoul.domain.personal_calendar_acquisition import (
    PERSONAL_CALENDAR_DAY_EVENTS_PREDICATE,
    PERSONAL_CALENDAR_SCHEDULE_RESULT_KIND,
)
from alsoul.domain.personal_calendar_cognition import (
    CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
    CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
    AdoptPersonalCalendarScheduleOutputCommand,
    BuildPersonalCalendarProjectionCommand,
    GeneratePersonalCalendarAnswerPlanCommand,
    PersonalCalendarAdoptionResult,
    PersonalCalendarGenerationResult,
    PersonalCalendarModelAdapter,
    PersonalCalendarModelRouteResult,
    PersonalCalendarPolicyRevisionResult,
    PersonalCalendarProjectionResult,
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
    SetPersonalCalendarModelRouteStatusCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.storage import schema

_FRESHNESS_POLICY_SCOPE = "SetPersonalCalendarFreshnessPolicy"
_REGISTER_ROUTE_SCOPE = "RegisterPersonalCalendarModelRoute"
_ROUTE_STATUS_SCOPE = "SetPersonalCalendarModelRouteStatus"
_EGRESS_POLICY_SCOPE = "SetPersonalCalendarModelEgressPolicy"
_BUILD_PROJECTION_SCOPE = "BuildPersonalCalendarProjection"
_GENERATE_SCOPE = "GeneratePersonalCalendarAnswerPlan"
_ADOPT_SCOPE = "AdoptPersonalCalendarScheduleOutput"
_PROJECTION_CONTRACT_VERSION = "PERSONAL_CALENDAR_CONTEXT_V1"
_SOURCE_TYPE = "PERSONAL_CALENDAR_WORLD_SOURCE_CAPTURE"


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        fail("CALENDAR_TIME_VALUE_INVALID", "calendar time value must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_text(value: Any, *, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(code, message)
    return value


class PersonalCalendarCognitionServices:
    """Current-policy personal-calendar projection, model egress, and adoption.

    This service deliberately stops before first-party presentation.  It turns one
    acquisition-specific personal-calendar WorldResult into a minimized immutable
    ContextProjection, evaluates current exact-route model-egress authority before
    every model transport, admits only a bounded structured schedule plan, and renders
    schedule facts deterministically from the projection before CompanionOutput
    adoption.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        adapter: PersonalCalendarModelAdapter | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.adapter = adapter
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def set_freshness_policy(
        self, command: SetPersonalCalendarFreshnessPolicyCommand
    ) -> PersonalCalendarPolicyRevisionResult:
        req = request_digest(asdict(command))
        _require_text(
            command.policy_version,
            code="CALENDAR_FRESHNESS_POLICY_INVALID",
            message="freshness policy version must be explicit",
        )
        if (
            not isinstance(command.max_age_seconds, int)
            or isinstance(command.max_age_seconds, bool)
            or command.max_age_seconds < 0
            or command.status not in {"ALLOW", "DENY"}
        ):
            fail(
                "CALENDAR_FRESHNESS_POLICY_INVALID",
                "freshness policy requires a non-negative integer age bound and explicit status",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_FRESHNESS_POLICY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarPolicyRevisionResult(
                    command.relationship_id, int(replay["revision"])
                )
            self._require_relationship(conn, command.relationship_id)
            revision = self._append_relationship_policy_revision(
                conn,
                revision_table=schema.personal_calendar_freshness_policy_revision,
                head_table=schema.personal_calendar_freshness_policy_head,
                relationship_id=command.relationship_id,
                values={
                    "policy_version": command.policy_version,
                    "max_age_seconds": command.max_age_seconds,
                    "status": command.status,
                },
                conflict_code="CALENDAR_FRESHNESS_POLICY_CONFLICT",
            )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=_FRESHNESS_POLICY_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarFreshnessPolicy",
                result_ref=command.relationship_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return PersonalCalendarPolicyRevisionResult(command.relationship_id, revision)

    def register_model_route(
        self, command: RegisterPersonalCalendarModelRouteCommand
    ) -> PersonalCalendarModelRouteResult:
        req = request_digest(asdict(command))
        for value in (
            command.provider_binding_ref,
            command.model_ref,
            command.route_contract_version,
            command.data_handling_contract_version,
            command.retention_class,
            command.residency_class,
        ):
            _require_text(
                value,
                code="CALENDAR_MODEL_ROUTE_INVALID",
                message="calendar model route metadata must be explicit",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_REGISTER_ROUTE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarModelRouteResult(
                    UUID(replay["route_binding_id"]), int(replay["revision"])
                )
            route_id = self.ids.new()
            now = self.clock.now()
            try:
                conn.execute(
                    insert(schema.personal_calendar_model_route_binding).values(
                        route_binding_id=route_id,
                        provider_binding_ref=command.provider_binding_ref,
                        model_ref=command.model_ref,
                        route_contract_version=command.route_contract_version,
                        data_handling_contract_version=command.data_handling_contract_version,
                        retention_class=command.retention_class,
                        residency_class=command.residency_class,
                        created_at=now,
                    )
                )
            except IntegrityError:
                fail(
                    "CALENDAR_MODEL_ROUTE_ALREADY_REGISTERED",
                    "the exact calendar model route contract is already registered",
                )
            conn.execute(
                insert(schema.personal_calendar_model_route_state).values(
                    route_binding_id=route_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_model_route_head).values(
                    route_binding_id=route_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=_REGISTER_ROUTE_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarModelRoute",
                result_ref=route_id,
                result_json={"route_binding_id": str(route_id), "revision": 1},
                committed_at=now,
            )
            return PersonalCalendarModelRouteResult(route_id, 1)

    def set_model_route_status(
        self, command: SetPersonalCalendarModelRouteStatusCommand
    ) -> PersonalCalendarModelRouteResult:
        req = request_digest(asdict(command))
        if command.status != "REVOKED":
            fail(
                "CALENDAR_MODEL_ROUTE_STATUS_INVALID",
                "the first slice permits route revocation but not in-place reactivation",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ROUTE_STATUS_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarModelRouteResult(
                    command.route_binding_id, int(replay["revision"])
                )
            route = conn.execute(
                select(schema.personal_calendar_model_route_binding).where(
                    schema.personal_calendar_model_route_binding.c.route_binding_id
                    == command.route_binding_id
                )
            ).mappings().one_or_none()
            if route is None:
                fail("CALENDAR_MODEL_ROUTE_NOT_FOUND", "calendar model route does not exist")
            state, revision = self._current_route_state(conn, command.route_binding_id)
            if state["status"] == "REVOKED":
                new_revision = revision
            else:
                new_revision = revision + 1
                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_calendar_model_route_state).values(
                        route_binding_id=command.route_binding_id,
                        revision=new_revision,
                        parent_revision=revision,
                        status="REVOKED",
                        committed_at=now,
                    )
                )
                changed = conn.execute(
                    update(schema.personal_calendar_model_route_head)
                    .where(
                        schema.personal_calendar_model_route_head.c.route_binding_id
                        == command.route_binding_id,
                        schema.personal_calendar_model_route_head.c.current_revision
                        == revision,
                    )
                    .values(current_revision=new_revision)
                )
                if changed.rowcount != 1:
                    fail(
                        "CALENDAR_MODEL_ROUTE_STATE_CONFLICT",
                        "calendar model route state advanced concurrently",
                    )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=_ROUTE_STATUS_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarModelRouteState",
                result_ref=command.route_binding_id,
                result_json={"revision": new_revision},
                committed_at=now,
            )
            return PersonalCalendarModelRouteResult(command.route_binding_id, new_revision)

    def set_model_egress_policy(
        self, command: SetPersonalCalendarModelEgressPolicyCommand
    ) -> PersonalCalendarPolicyRevisionResult:
        req = request_digest(asdict(command))
        for value in (
            command.policy_version,
            command.required_retention_class,
            command.required_residency_class,
        ):
            _require_text(
                value,
                code="CALENDAR_MODEL_EGRESS_POLICY_INVALID",
                message="model-egress policy metadata must be explicit",
            )
        if command.status not in {"ALLOW", "DENY"}:
            fail(
                "CALENDAR_MODEL_EGRESS_POLICY_INVALID",
                "model-egress policy status is invalid",
            )
        if len(set(command.allowed_route_binding_ids)) != len(
            command.allowed_route_binding_ids
        ):
            fail(
                "CALENDAR_MODEL_EGRESS_POLICY_INVALID",
                "allowed model routes must not contain duplicates",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_EGRESS_POLICY_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarPolicyRevisionResult(
                    command.relationship_id, int(replay["revision"])
                )
            self._require_relationship(conn, command.relationship_id)
            for route_id in command.allowed_route_binding_ids:
                exists = conn.execute(
                    select(schema.personal_calendar_model_route_binding.c.route_binding_id).where(
                        schema.personal_calendar_model_route_binding.c.route_binding_id == route_id
                    )
                ).scalar_one_or_none()
                if exists is None:
                    fail(
                        "CALENDAR_MODEL_ROUTE_NOT_FOUND",
                        "model-egress policy references an unknown route",
                    )
            revision = self._append_relationship_policy_revision(
                conn,
                revision_table=schema.personal_calendar_model_egress_policy_revision,
                head_table=schema.personal_calendar_model_egress_policy_head,
                relationship_id=command.relationship_id,
                values={
                    "policy_version": command.policy_version,
                    "allowed_route_binding_ids_json": [
                        str(value) for value in command.allowed_route_binding_ids
                    ],
                    "required_retention_class": command.required_retention_class,
                    "required_residency_class": command.required_residency_class,
                    "status": command.status,
                },
                conflict_code="CALENDAR_MODEL_EGRESS_POLICY_CONFLICT",
            )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=_EGRESS_POLICY_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarModelEgressPolicy",
                result_ref=command.relationship_id,
                result_json={"revision": revision},
                committed_at=now,
            )
            return PersonalCalendarPolicyRevisionResult(command.relationship_id, revision)

    def build_projection(
        self, command: BuildPersonalCalendarProjectionCommand
    ) -> PersonalCalendarProjectionResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_BUILD_PROJECTION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarProjectionResult(
                    UUID(replay["projection_id"]),
                    UUID(replay["freshness_decision_id"]),
                    replay["manifest_digest"],
                )

            context = self._load_result_context(
                conn,
                world_result_id=command.world_result_id,
                current_input_event_id=command.current_input_event_id,
            )
            projection_id = self.ids.new()
            freshness_decision_id = self.ids.new()
            freshness = self._record_freshness_decision(
                conn,
                decision_id=freshness_decision_id,
                relationship_id=context["relationship_id"],
                world_result_id=command.world_result_id,
                freshness_anchor_at=context["personal_result"]["freshness_anchor_at"],
                purpose="BUILD_PROJECTION",
            )
            occurrences = self._projection_occurrences(context["world_result"]["value_json"])
            manifest = {
                "projection_contract_version": _PROJECTION_CONTRACT_VERSION,
                "purpose": "RESPOND_TO_INTERACTION",
                "companion_person_id": str(context["companion_person_id"]),
                "relationship_id": str(context["relationship_id"]),
                "current_input_event_id": str(command.current_input_event_id),
                "world_result_id": str(command.world_result_id),
                "personal_resource_binding_id": str(
                    context["personal_result"]["personal_resource_binding_id"]
                ),
                "requested_local_date": context["personal_result"]["requested_local_date"],
                "freshness_decision_id": str(freshness_decision_id),
                "occurrences": [
                    {
                        "occurrence_ref": item["occurrence_ref"],
                        "source_occurrence_ref": item["source_occurrence_ref"],
                        "title": item["title"],
                        "start_at": item["start_at"].isoformat(),
                        "end_at": item["end_at"].isoformat(),
                        "all_day": item["all_day"],
                        "all_day_start_date": item["all_day_start_date"],
                        "all_day_end_date_exclusive": item[
                            "all_day_end_date_exclusive"
                        ],
                    }
                    for item in occurrences
                ],
            }
            manifest_digest = sha256_text(canonical_json(manifest))
            now = self.clock.now()
            conn.execute(
                insert(schema.context_projection).values(
                    projection_id=projection_id,
                    projection_schema_version=2,
                    purpose="RESPOND_TO_INTERACTION",
                    created_at=now,
                    companion_person_id=context["companion_person_id"],
                    relationship_id=context["relationship_id"],
                    current_input_event_id=command.current_input_event_id,
                    source_self_revision=context["self_revision"],
                    source_relationship_revision=context["relationship_revision"],
                    source_timeline_frontier=context["timeline_frontier"],
                    manifest_digest=manifest_digest,
                )
            )
            conn.execute(
                insert(schema.context_projection_event).values(
                    projection_id=projection_id,
                    ordinal=0,
                    event_id=command.current_input_event_id,
                )
            )
            conn.execute(
                insert(schema.context_projection_world_item).values(
                    projection_id=projection_id,
                    ordinal=0,
                    world_result_id=command.world_result_id,
                    investigation_id=context["world_result"]["investigation_id"],
                    epistemic_mode="CURRENT_PERSONAL_OBSERVATION",
                )
            )
            for evidence_id in context["support_evidence_ids"]:
                conn.execute(
                    insert(schema.context_projection_world_support).values(
                        projection_id=projection_id,
                        world_ordinal=0,
                        evidence_id=evidence_id,
                    )
                )
            conn.execute(
                insert(schema.personal_calendar_context_projection).values(
                    projection_id=projection_id,
                    world_result_id=command.world_result_id,
                    source_interaction_event_id=command.current_input_event_id,
                    personal_resource_binding_id=context["personal_result"][
                        "personal_resource_binding_id"
                    ],
                    freshness_decision_id=freshness["freshness_decision_id"],
                    requested_local_date=context["personal_result"]["requested_local_date"],
                    calendar_timezone=context["world_result"]["value_json"][
                        "calendar_timezone"
                    ],
                    projection_contract_version=_PROJECTION_CONTRACT_VERSION,
                    created_at=now,
                )
            )
            for ordinal, item in enumerate(occurrences):
                conn.execute(
                    insert(schema.personal_calendar_projection_occurrence).values(
                        projection_id=projection_id,
                        ordinal=ordinal,
                        **item,
                    )
                )
            save_operation_receipt(
                conn,
                scope=_BUILD_PROJECTION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarContextProjection",
                result_ref=projection_id,
                result_json={
                    "projection_id": str(projection_id),
                    "freshness_decision_id": str(freshness_decision_id),
                    "manifest_digest": manifest_digest,
                },
                committed_at=now,
            )
            return PersonalCalendarProjectionResult(
                projection_id, freshness_decision_id, manifest_digest
            )

    def render_model_context(self, projection_id: UUID) -> dict[str, Any]:
        with self.engine.connect() as conn:
            return self._render_model_context_conn(conn, projection_id)

    def generate_answer_plan(
        self, command: GeneratePersonalCalendarAnswerPlanCommand
    ) -> PersonalCalendarGenerationResult:
        if self.adapter is None or not callable(getattr(self.adapter, "generate_plan", None)):
            fail(
                "CALENDAR_MODEL_ADAPTER_UNAVAILABLE",
                "a qualified personal-calendar model adapter is required",
            )
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_GENERATE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._recover_generation_replay(conn, replay)

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_GENERATE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._recover_generation_replay(conn, replay)
            projection = self._load_personal_projection(conn, command.projection_id)
            prior = conn.execute(
                select(
                    schema.personal_calendar_model_invocation.c.model_invocation_id,
                    schema.model_invocation.c.outcome,
                )
                .join(
                    schema.model_invocation,
                    schema.personal_calendar_model_invocation.c.model_invocation_id
                    == schema.model_invocation.c.model_invocation_id,
                )
                .where(
                    schema.personal_calendar_model_invocation.c.projection_id
                    == command.projection_id
                )
            ).mappings().all()
            if any(row["outcome"] == "IN_PROGRESS" for row in prior):
                fail(
                    "CALENDAR_MODEL_INVOCATION_RECOVERY_REQUIRED",
                    "an unresolved personal-calendar model transport must be reconciled before retry",
                )
            if any(row["outcome"] == "SUCCEEDED" for row in prior):
                fail(
                    "CALENDAR_MODEL_OUTPUT_ALREADY_AVAILABLE",
                    "recover the durable personal-calendar GeneratedOutput instead of regenerating it",
                )

            freshness_decision_id = self.ids.new()
            freshness = self._record_freshness_decision(
                conn,
                decision_id=freshness_decision_id,
                relationship_id=projection["relationship_id"],
                world_result_id=projection["world_result_id"],
                freshness_anchor_at=projection["freshness_anchor_at"],
                purpose="MODEL_EGRESS",
            )
            authority = self._evaluate_model_egress(
                conn,
                projection=projection,
                permission_id=command.permission_id,
                route_binding_id=command.route_binding_id,
            )
            provider_context = self._render_model_context_conn(conn, command.projection_id)
            request_body = canonical_json(provider_context)
            provider_request_digest = sha256_text(request_body)
            model_invocation_id = self.ids.new()
            egress_decision_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_model_egress_decision).values(
                    egress_decision_id=egress_decision_id,
                    projection_id=command.projection_id,
                    freshness_decision_id=freshness["freshness_decision_id"],
                    relationship_id=projection["relationship_id"],
                    relationship_authority_revision=authority[
                        "relationship_authority_revision"
                    ],
                    personal_resource_binding_id=projection[
                        "personal_resource_binding_id"
                    ],
                    resource_binding_state_revision=authority[
                        "resource_binding_state_revision"
                    ],
                    permission_id=command.permission_id,
                    permission_state_revision=authority["permission_state_revision"],
                    read_policy_revision=authority["read_policy_revision"],
                    egress_policy_revision=authority["egress_policy_revision"],
                    route_binding_id=command.route_binding_id,
                    route_state_revision=authority["route_state_revision"],
                    route_contract_version=authority["route"]["route_contract_version"],
                    data_handling_contract_version=authority["route"][
                        "data_handling_contract_version"
                    ],
                    evaluated_at=now,
                )
            )
            conn.execute(
                insert(schema.model_invocation).values(
                    model_invocation_id=model_invocation_id,
                    context_projection_id=command.projection_id,
                    provider_binding_ref=authority["route"]["provider_binding_ref"],
                    model_ref=authority["route"]["model_ref"],
                    renderer_version=CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
                    provider_request_digest=provider_request_digest,
                    started_at=now,
                    outcome="IN_PROGRESS",
                )
            )
            conn.execute(
                insert(schema.personal_calendar_model_invocation).values(
                    model_invocation_id=model_invocation_id,
                    projection_id=command.projection_id,
                    egress_decision_id=egress_decision_id,
                    route_binding_id=command.route_binding_id,
                    plan_schema_version=CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
                    rendering_contract_version=CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
                    dispatched_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=_GENERATE_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarModelDispatch",
                result_ref=model_invocation_id,
                result_json={
                    "model_invocation_id": str(model_invocation_id),
                    "egress_decision_id": str(egress_decision_id),
                },
                committed_at=now,
            )

        try:
            plan = self.adapter.generate_plan(provider_context)
            validated_plan = self._validate_plan_shape(
                plan,
                maximum_occurrences=len(provider_context["occurrences"]),
            )
        except DomainError:
            self._finish_invocation(model_invocation_id, "FAILED")
            raise
        except AdapterRejected as exc:
            self._finish_invocation(model_invocation_id, "FAILED")
            raise DomainError(
                "CALENDAR_MODEL_PROVIDER_REJECTED",
                "personal-calendar model provider rejected the structured-plan request",
            ) from exc
        except AdapterOutcomeUnknown as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MODEL_OUTCOME_UNKNOWN",
                "personal-calendar model transport outcome is unknown",
            ) from exc
        except Exception as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MODEL_OUTCOME_UNKNOWN",
                "personal-calendar model transport became unusable after dispatch",
            ) from exc

        generated_output_id = self.ids.new()
        received_at = self.clock.now()
        content_text = canonical_json(validated_plan)
        content_digest = sha256_text(content_text)
        try:
            with self.engine.begin() as conn:
                invocation = conn.execute(
                    select(schema.model_invocation).where(
                        schema.model_invocation.c.model_invocation_id == model_invocation_id
                    )
                ).mappings().one_or_none()
                if invocation is None or invocation["outcome"] != "IN_PROGRESS":
                    fail(
                        "CALENDAR_MODEL_INVOCATION_NOT_OPEN",
                        "model invocation is no longer open for structured-plan admission",
                    )
                projection = self._load_personal_projection(conn, command.projection_id)
                conn.execute(
                    insert(schema.generated_output).values(
                        generated_output_id=generated_output_id,
                        model_invocation_id=model_invocation_id,
                        content_text=content_text,
                        content_digest=content_digest,
                        semantic_payload_json=validated_plan,
                        received_at=received_at,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_generated_output).values(
                        generated_output_id=generated_output_id,
                        projection_id=command.projection_id,
                        world_result_id=projection["world_result_id"],
                        plan_schema_version=CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
                        rendering_contract_version=CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
                        validated_shape_at=received_at,
                    )
                )
                changed = conn.execute(
                    update(schema.model_invocation)
                    .where(
                        schema.model_invocation.c.model_invocation_id == model_invocation_id,
                        schema.model_invocation.c.outcome == "IN_PROGRESS",
                    )
                    .values(outcome="SUCCEEDED", completed_at=received_at)
                )
                if changed.rowcount != 1:
                    fail(
                        "CALENDAR_MODEL_INVOCATION_CONFLICT",
                        "model invocation changed concurrently during plan admission",
                    )
        except DomainError:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise
        except IntegrityError as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MODEL_COMPLETION_CONFLICT",
                "structured plan admission conflicted with concurrent durable state",
            ) from exc
        return PersonalCalendarGenerationResult(
            model_invocation_id, generated_output_id, egress_decision_id
        )

    def adopt_schedule_output(
        self, command: AdoptPersonalCalendarScheduleOutputCommand
    ) -> PersonalCalendarAdoptionResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ADOPT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PersonalCalendarAdoptionResult(
                    UUID(replay["companion_output_id"]),
                    UUID(replay["output_target_id"]),
                )
            generated = conn.execute(
                select(
                    schema.generated_output,
                    schema.personal_calendar_generated_output.c.projection_id,
                    schema.personal_calendar_generated_output.c.world_result_id,
                    schema.personal_calendar_generated_output.c.plan_schema_version,
                    schema.personal_calendar_generated_output.c.rendering_contract_version,
                )
                .join(
                    schema.personal_calendar_generated_output,
                    schema.generated_output.c.generated_output_id
                    == schema.personal_calendar_generated_output.c.generated_output_id,
                )
                .where(
                    schema.generated_output.c.generated_output_id
                    == command.generated_output_id
                )
            ).mappings().one_or_none()
            if generated is None:
                fail(
                    "CALENDAR_GENERATED_OUTPUT_NOT_FOUND",
                    "personal-calendar GeneratedOutput does not exist",
                )
            invocation = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.model_invocation_id
                    == generated["model_invocation_id"]
                )
            ).mappings().one_or_none()
            if invocation is None or invocation["outcome"] != "SUCCEEDED":
                fail(
                    "CALENDAR_GENERATED_OUTPUT_UNSETTLED",
                    "personal-calendar GeneratedOutput lacks a successful model invocation",
                )
            if sha256_text(generated["content_text"]) != generated["content_digest"]:
                fail(
                    "CALENDAR_GENERATED_OUTPUT_DIGEST_MISMATCH",
                    "personal-calendar GeneratedOutput content digest is invalid",
                )
            if generated["content_text"] != canonical_json(generated["semantic_payload_json"]):
                fail(
                    "CALENDAR_GENERATED_OUTPUT_PAYLOAD_MISMATCH",
                    "stored structured plan text and semantic payload differ",
                )
            projection = self._load_personal_projection(conn, generated["projection_id"])
            occurrences = conn.execute(
                select(schema.personal_calendar_projection_occurrence)
                .where(
                    schema.personal_calendar_projection_occurrence.c.projection_id
                    == generated["projection_id"]
                )
                .order_by(schema.personal_calendar_projection_occurrence.c.ordinal)
            ).mappings().all()
            ordered_refs = self._validate_plan_semantics(
                generated["semantic_payload_json"], projection, occurrences
            )
            content_text = self._render_schedule(projection, occurrences, ordered_refs)
            content_digest = sha256_text(content_text)
            semantic_payload = {
                "rendering_contract_version": CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
                "source_context_projection_id": str(generated["projection_id"]),
                "source_world_result_id": str(generated["world_result_id"]),
                "requested_date": projection["requested_local_date"],
                "ordered_occurrence_refs": ordered_refs,
                "source_classification": "CURRENT_PERSONAL_OBSERVATION",
            }

            target = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.relationship_id == projection["relationship_id"],
                    schema.output_target.c.target_kind == "INTERACTION_EVENT",
                    schema.output_target.c.target_ref == projection["source_interaction_event_id"],
                    schema.output_target.c.purpose == "RESPOND_TO_INTERACTION",
                )
            ).mappings().one_or_none()
            if target is None:
                output_target_id = self.ids.new()
                conn.execute(
                    insert(schema.output_target).values(
                        output_target_id=output_target_id,
                        relationship_id=projection["relationship_id"],
                        target_kind="INTERACTION_EVENT",
                        target_ref=projection["source_interaction_event_id"],
                        purpose="RESPOND_TO_INTERACTION",
                        created_at=self.clock.now(),
                    )
                )
            else:
                output_target_id = target["output_target_id"]
                settled = conn.execute(
                    select(schema.companion_output).where(
                        schema.companion_output.c.output_target_id == output_target_id
                    )
                ).mappings().one_or_none()
                if settled is not None:
                    specialized = conn.execute(
                        select(schema.personal_calendar_companion_output).where(
                            schema.personal_calendar_companion_output.c.companion_output_id
                            == settled["companion_output_id"],
                            schema.personal_calendar_companion_output.c.generated_output_id
                            == command.generated_output_id,
                        )
                    ).scalar_one_or_none()
                    if specialized is not None:
                        return PersonalCalendarAdoptionResult(
                            settled["companion_output_id"], output_target_id
                        )
                    fail(
                        "CALENDAR_OUTPUT_TARGET_ALREADY_SETTLED",
                        "the interaction already has a different adopted CompanionOutput",
                    )

            companion_output_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.companion_output).values(
                    companion_output_id=companion_output_id,
                    companion_person_id=projection["companion_person_id"],
                    relationship_id=projection["relationship_id"],
                    output_target_id=output_target_id,
                    origin_kind="PERSONAL_CALENDAR_SCHEDULE",
                    origin_ref=generated["world_result_id"],
                    source_generated_output_id=command.generated_output_id,
                    content_text=content_text,
                    content_digest=content_digest,
                    semantic_payload_json=semantic_payload,
                    adopted_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_companion_output).values(
                    companion_output_id=companion_output_id,
                    generated_output_id=command.generated_output_id,
                    projection_id=generated["projection_id"],
                    world_result_id=generated["world_result_id"],
                    rendering_contract_version=CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
                    deterministic_render_digest=content_digest,
                )
            )
            save_operation_receipt(
                conn,
                scope=_ADOPT_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarCompanionOutput",
                result_ref=companion_output_id,
                result_json={
                    "companion_output_id": str(companion_output_id),
                    "output_target_id": str(output_target_id),
                },
                committed_at=now,
            )
            return PersonalCalendarAdoptionResult(companion_output_id, output_target_id)

    def _require_relationship(self, conn, relationship_id: UUID) -> dict[str, Any]:
        row = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if row is None:
            fail("RELATIONSHIP_NOT_FOUND", "relationship does not exist")
        return dict(row)

    def _append_relationship_policy_revision(
        self,
        conn,
        *,
        revision_table,
        head_table,
        relationship_id: UUID,
        values: dict[str, Any],
        conflict_code: str,
    ) -> int:
        head = conn.execute(
            select(head_table).where(head_table.c.relationship_id == relationship_id)
        ).mappings().one_or_none()
        parent = int(head["current_revision"]) if head is not None else None
        revision = 1 if parent is None else parent + 1
        now = self.clock.now()
        conn.execute(
            insert(revision_table).values(
                relationship_id=relationship_id,
                revision=revision,
                parent_revision=parent,
                committed_at=now,
                **values,
            )
        )
        if parent is None:
            try:
                conn.execute(
                    insert(head_table).values(
                        relationship_id=relationship_id, current_revision=revision
                    )
                )
            except IntegrityError:
                fail(conflict_code, "policy head was created concurrently")
        else:
            changed = conn.execute(
                update(head_table)
                .where(
                    head_table.c.relationship_id == relationship_id,
                    head_table.c.current_revision == parent,
                )
                .values(current_revision=revision)
            )
            if changed.rowcount != 1:
                fail(conflict_code, "policy revision advanced concurrently")
        return revision

    def _current_route_state(self, conn, route_binding_id: UUID) -> tuple[dict[str, Any], int]:
        head = conn.execute(
            select(schema.personal_calendar_model_route_head).where(
                schema.personal_calendar_model_route_head.c.route_binding_id
                == route_binding_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail("CALENDAR_MODEL_ROUTE_STATE_MISSING", "calendar model route state is missing")
        revision = int(head["current_revision"])
        state = conn.execute(
            select(schema.personal_calendar_model_route_state).where(
                schema.personal_calendar_model_route_state.c.route_binding_id
                == route_binding_id,
                schema.personal_calendar_model_route_state.c.revision == revision,
            )
        ).mappings().one_or_none()
        if state is None:
            fail("CALENDAR_MODEL_ROUTE_STATE_MISSING", "calendar model route head is invalid")
        return dict(state), revision

    def _record_freshness_decision(
        self,
        conn,
        *,
        decision_id: UUID,
        relationship_id: UUID,
        world_result_id: UUID,
        freshness_anchor_at: datetime,
        purpose: str,
    ) -> dict[str, Any]:
        head = conn.execute(
            select(schema.personal_calendar_freshness_policy_head).where(
                schema.personal_calendar_freshness_policy_head.c.relationship_id
                == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail(
                "CALENDAR_FRESHNESS_POLICY_MISSING",
                "current personal-calendar freshness policy is missing",
            )
        revision = int(head["current_revision"])
        policy = conn.execute(
            select(schema.personal_calendar_freshness_policy_revision).where(
                schema.personal_calendar_freshness_policy_revision.c.relationship_id
                == relationship_id,
                schema.personal_calendar_freshness_policy_revision.c.revision == revision,
            )
        ).mappings().one_or_none()
        if policy is None or policy["status"] != "ALLOW":
            fail(
                "CALENDAR_FRESHNESS_POLICY_DENIED",
                "current personal-calendar freshness policy is unavailable or denied",
            )
        evaluated_at = _aware_utc(self.clock.now())
        anchor = _aware_utc(freshness_anchor_at)
        age = int((evaluated_at - anchor).total_seconds())
        if age < 0:
            fail(
                "CALENDAR_FRESHNESS_CLOCK_INVALID",
                "freshness anchor lies after the trusted evaluation clock",
            )
        if age > int(policy["max_age_seconds"]):
            fail(
                "CALENDAR_RESULT_STALE",
                "personal-calendar result is stale under the current freshness policy",
            )
        conn.execute(
            insert(schema.personal_calendar_freshness_decision).values(
                freshness_decision_id=decision_id,
                relationship_id=relationship_id,
                world_result_id=world_result_id,
                decision_purpose=purpose,
                policy_revision=revision,
                policy_version=policy["policy_version"],
                freshness_anchor_at=anchor,
                evaluated_at=evaluated_at,
                max_age_seconds=int(policy["max_age_seconds"]),
                age_seconds=age,
                eligible=True,
            )
        )
        return {
            "freshness_decision_id": decision_id,
            "policy_revision": revision,
            "policy_version": policy["policy_version"],
        }

    def _load_result_context(
        self,
        conn,
        *,
        world_result_id: UUID,
        current_input_event_id: UUID,
    ) -> dict[str, Any]:
        personal_result = conn.execute(
            select(schema.personal_calendar_world_result).where(
                schema.personal_calendar_world_result.c.world_result_id == world_result_id
            )
        ).mappings().one_or_none()
        world_result = conn.execute(
            select(schema.world_result).where(
                schema.world_result.c.world_result_id == world_result_id
            )
        ).mappings().one_or_none()
        if personal_result is None or world_result is None:
            fail(
                "CALENDAR_WORLD_RESULT_NOT_FOUND",
                "world result is not an admitted personal-calendar result",
            )
        if (
            world_result["result_kind"] != PERSONAL_CALENDAR_SCHEDULE_RESULT_KIND
            or world_result["predicate"] != PERSONAL_CALENDAR_DAY_EVENTS_PREDICATE
        ):
            fail(
                "CALENDAR_WORLD_RESULT_INVALID",
                "world result is outside the personal-calendar schedule contract",
            )
        if personal_result["source_interaction_event_id"] != current_input_event_id:
            fail(
                "CALENDAR_RESULT_INTERACTION_MISMATCH",
                "personal-calendar result is not reusable by another interaction",
            )
        source_input = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == current_input_event_id
            )
        ).mappings().one_or_none()
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == personal_result["personal_resource_binding_id"]
            )
        ).mappings().one_or_none()
        if source_input is None or resource is None:
            fail(
                "CALENDAR_RESULT_LINEAGE_INVALID",
                "personal-calendar result source interaction or resource is missing",
            )
        relationship = self._require_relationship(conn, resource["relationship_id"])
        if (
            source_input["relationship_id"] != resource["relationship_id"]
            or source_input["event_kind"] != "COUNTERPART_INPUT"
            or source_input["actor_kind"] != "COUNTERPART"
            or source_input["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "CALENDAR_RESULT_LINEAGE_INVALID",
                "personal-calendar result is not bound to a trusted counterpart input",
            )
        timeline = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id == resource["relationship_id"]
            )
        ).mappings().one_or_none()
        if timeline is None or int(timeline["last_timeline_seq"]) != int(
            source_input["timeline_seq"]
        ):
            fail(
                "CALENDAR_RESULT_INTERACTION_NOT_CURRENT",
                "personal-calendar cognition requires the originating interaction at the Timeline frontier",
            )
        investigation = conn.execute(
            select(schema.investigation).where(
                schema.investigation.c.investigation_id == world_result["investigation_id"]
            )
        ).mappings().one_or_none()
        if (
            investigation is None
            or investigation["relationship_id"] != resource["relationship_id"]
            or investigation["initiated_by_companion_person_id"]
            != relationship["companion_person_id"]
        ):
            fail(
                "CALENDAR_RESULT_LINEAGE_INVALID",
                "personal-calendar result Investigation lineage is invalid",
            )
        self_head = conn.execute(
            select(schema.self_head).where(
                schema.self_head.c.person_id == relationship["companion_person_id"]
            )
        ).mappings().one_or_none()
        relationship_head = conn.execute(
            select(schema.relationship_head).where(
                schema.relationship_head.c.relationship_id == resource["relationship_id"]
            )
        ).mappings().one_or_none()
        if self_head is None or relationship_head is None:
            fail(
                "CALENDAR_RESULT_LINEAGE_INVALID",
                "current Person or Relationship revision is unavailable",
            )
        supports = conn.execute(
            select(schema.world_result_evidence.c.evidence_id).where(
                schema.world_result_evidence.c.world_result_id == world_result_id,
                schema.world_result_evidence.c.relation == "SUPPORTS",
            )
        ).scalars().all()
        if not supports:
            fail(
                "CALENDAR_RESULT_SUPPORT_MISSING",
                "personal-calendar result has no supporting evidence",
            )
        for evidence_id in supports:
            evidence = conn.execute(
                select(schema.evidence_item).where(
                    schema.evidence_item.c.evidence_id == evidence_id
                )
            ).mappings().one_or_none()
            if (
                evidence is None
                or evidence["origin_kind"] != "PERSONAL_WORLD_CAPTURE"
                or evidence["source_type"] != _SOURCE_TYPE
                or evidence["source_id"] != personal_result["source_capture_id"]
            ):
                fail(
                    "CALENDAR_RESULT_SUPPORT_INVALID",
                    "personal-calendar result support is not its admitted personal-world capture",
                )
        value = world_result["value_json"]
        if not isinstance(value, dict) or not isinstance(value.get("events"), list):
            fail(
                "CALENDAR_WORLD_RESULT_INVALID",
                "personal-calendar result payload is malformed",
            )
        if value.get("requested_local_date") != personal_result["requested_local_date"]:
            fail(
                "CALENDAR_WORLD_RESULT_INVALID",
                "personal-calendar result date does not match specialized lineage",
            )
        _require_text(
            value.get("calendar_timezone"),
            code="CALENDAR_WORLD_RESULT_INVALID",
            message="personal-calendar result lacks trusted calendar timezone",
        )
        return {
            "personal_result": dict(personal_result),
            "world_result": dict(world_result),
            "relationship_id": resource["relationship_id"],
            "companion_person_id": relationship["companion_person_id"],
            "counterpart_id": relationship["counterpart_id"],
            "self_revision": int(self_head["current_revision"]),
            "relationship_revision": int(relationship_head["current_revision"]),
            "timeline_frontier": int(timeline["last_timeline_seq"]),
            "support_evidence_ids": list(supports),
        }

    def _projection_occurrences(self, value: dict[str, Any]) -> list[dict[str, Any]]:
        events = value.get("events")
        if not isinstance(events, list):
            fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result events must be a list")
        occurrences: list[dict[str, Any]] = []
        source_refs: set[str] = set()
        for ordinal, event in enumerate(events):
            if not isinstance(event, dict):
                fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result event is malformed")
            source_ref = _require_text(
                event.get("occurrence_ref"),
                code="CALENDAR_WORLD_RESULT_INVALID",
                message="calendar result occurrence identity is missing",
            )
            if source_ref in source_refs:
                fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result occurrence identity is duplicated")
            source_refs.add(source_ref)
            title = event.get("title")
            if not isinstance(title, str):
                fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result title is malformed")
            try:
                start_at = _aware_utc(datetime.fromisoformat(event["start_at"]))
                end_at = _aware_utc(datetime.fromisoformat(event["end_at"]))
            except (KeyError, TypeError, ValueError):
                fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result event time is malformed")
            all_day = event.get("all_day")
            if not isinstance(all_day, bool):
                fail("CALENDAR_WORLD_RESULT_INVALID", "calendar result all-day marker is malformed")
            occurrences.append(
                {
                    "occurrence_ref": f"schedule-item-{ordinal + 1:04d}",
                    "source_occurrence_ref": source_ref,
                    "title": title,
                    "start_at": start_at,
                    "end_at": end_at,
                    "all_day": all_day,
                    "all_day_start_date": event.get("all_day_start_date") if all_day else None,
                    "all_day_end_date_exclusive": event.get("all_day_end_date_exclusive") if all_day else None,
                }
            )
        return occurrences

    def _load_personal_projection(self, conn, projection_id: UUID) -> dict[str, Any]:
        row = conn.execute(
            select(
                schema.personal_calendar_context_projection,
                schema.context_projection.c.companion_person_id,
                schema.context_projection.c.relationship_id,
                schema.context_projection.c.current_input_event_id,
                schema.context_projection.c.source_timeline_frontier,
                schema.personal_calendar_world_result.c.freshness_anchor_at,
            )
            .join(
                schema.context_projection,
                schema.personal_calendar_context_projection.c.projection_id
                == schema.context_projection.c.projection_id,
            )
            .join(
                schema.personal_calendar_world_result,
                schema.personal_calendar_context_projection.c.world_result_id
                == schema.personal_calendar_world_result.c.world_result_id,
            )
            .where(schema.personal_calendar_context_projection.c.projection_id == projection_id)
        ).mappings().one_or_none()
        if row is None:
            fail(
                "CALENDAR_CONTEXT_PROJECTION_NOT_FOUND",
                "personal-calendar ContextProjection does not exist",
            )
        result = dict(row)
        result["source_interaction_event_id"] = row["source_interaction_event_id"]
        return result

    def _render_model_context_conn(self, conn, projection_id: UUID) -> dict[str, Any]:
        projection = self._load_personal_projection(conn, projection_id)
        occurrences = conn.execute(
            select(schema.personal_calendar_projection_occurrence)
            .where(
                schema.personal_calendar_projection_occurrence.c.projection_id == projection_id
            )
            .order_by(schema.personal_calendar_projection_occurrence.c.ordinal)
        ).mappings().all()
        return {
            "task": "PERSONAL_CALENDAR_DAY_SCHEDULE",
            "plan_schema_version": CALENDAR_ANSWER_PLAN_SCHEMA_VERSION,
            "rendering_contract_version": CALENDAR_DAY_RENDERING_CONTRACT_VERSION,
            "source_context_projection_id": str(projection_id),
            "source_world_result_id": str(projection["world_result_id"]),
            "requested_date": projection["requested_local_date"],
            "calendar_timezone": projection["calendar_timezone"],
            "source_classification": "CURRENT_PERSONAL_OBSERVATION",
            "occurrences": [
                {
                    "occurrence_ref": row["occurrence_ref"],
                    "title": row["title"],
                    "start_at": _aware_utc(row["start_at"]).isoformat(),
                    "end_at": _aware_utc(row["end_at"]).isoformat(),
                    "all_day": bool(row["all_day"]),
                    **(
                        {
                            "all_day_start_date": row["all_day_start_date"],
                            "all_day_end_date_exclusive": row[
                                "all_day_end_date_exclusive"
                            ],
                        }
                        if row["all_day"]
                        else {}
                    ),
                }
                for row in occurrences
            ],
        }

    def _evaluate_model_egress(
        self,
        conn,
        *,
        projection: dict[str, Any],
        permission_id: UUID,
        route_binding_id: UUID,
    ) -> dict[str, Any]:
        relationship = self._require_relationship(conn, projection["relationship_id"])
        timeline = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id
                == projection["relationship_id"]
            )
        ).mappings().one_or_none()
        if timeline is None or int(timeline["last_timeline_seq"]) != int(
            projection["source_timeline_frontier"]
        ):
            fail(
                "CALENDAR_MODEL_EGRESS_INTERACTION_NOT_CURRENT",
                "personal-calendar model egress requires the originating interaction frontier",
            )

        relationship_head = conn.execute(
            select(schema.personal_world_relationship_head).where(
                schema.personal_world_relationship_head.c.relationship_id
                == projection["relationship_id"]
            )
        ).mappings().one_or_none()
        if relationship_head is None:
            fail("CALENDAR_MODEL_EGRESS_DENIED", "personal-world relationship state is missing")
        relationship_revision = int(relationship_head["current_revision"])
        relationship_state = conn.execute(
            select(schema.personal_world_relationship_state).where(
                schema.personal_world_relationship_state.c.relationship_id
                == projection["relationship_id"],
                schema.personal_world_relationship_state.c.revision == relationship_revision,
            )
        ).mappings().one_or_none()
        if relationship_state is None or relationship_state["status"] != "ACTIVE":
            fail("CALENDAR_MODEL_EGRESS_DENIED", "personal-world relationship is not active")

        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == projection["personal_resource_binding_id"]
            )
        ).mappings().one_or_none()
        resource_head = conn.execute(
            select(schema.personal_resource_binding_head).where(
                schema.personal_resource_binding_head.c.personal_resource_binding_id
                == projection["personal_resource_binding_id"]
            )
        ).mappings().one_or_none()
        if resource is None or resource_head is None:
            fail("CALENDAR_MODEL_EGRESS_DENIED", "calendar resource binding is unavailable")
        resource_revision = int(resource_head["current_revision"])
        resource_state = conn.execute(
            select(schema.personal_resource_binding_state).where(
                schema.personal_resource_binding_state.c.personal_resource_binding_id
                == projection["personal_resource_binding_id"],
                schema.personal_resource_binding_state.c.revision == resource_revision,
            )
        ).mappings().one_or_none()
        if (
            resource_state is None
            or resource_state["status"] != "ACTIVE"
            or resource["relationship_id"] != projection["relationship_id"]
            or resource["counterpart_id"] != relationship["counterpart_id"]
        ):
            fail("CALENDAR_MODEL_EGRESS_DENIED", "calendar resource is not currently associated")

        grant = conn.execute(
            select(schema.permission_grant).where(
                schema.permission_grant.c.permission_id == permission_id
            )
        ).mappings().one_or_none()
        permission_head = conn.execute(
            select(schema.permission_head).where(schema.permission_head.c.permission_id == permission_id)
        ).mappings().one_or_none()
        if grant is None or permission_head is None:
            fail("CALENDAR_MODEL_EGRESS_DENIED", "current calendar read Permission is missing")
        permission_revision = int(permission_head["current_revision"])
        permission_state = conn.execute(
            select(schema.permission_state).where(
                schema.permission_state.c.permission_id == permission_id,
                schema.permission_state.c.revision == permission_revision,
            )
        ).mappings().one_or_none()
        now = _aware_utc(self.clock.now())
        if (
            permission_state is None
            or permission_state["status"] != "ACTIVE"
            or grant["holder_companion_person_id"] != relationship["companion_person_id"]
            or grant["counterpart_id"] != relationship["counterpart_id"]
            or grant["relationship_id"] != projection["relationship_id"]
            or grant["personal_resource_binding_id"]
            != projection["personal_resource_binding_id"]
            or grant["capability_semantic_operation"] != CALENDAR_EVENTS_READ
            or grant["operation_class"] != "READ"
            or grant["grantor_ref"] != relationship["counterpart_id"]
            or grant["grant_source"] != "FIRST_PARTY_COUNTERPART"
            or (
                grant["expires_at"] is not None
                and _aware_utc(grant["expires_at"]) <= now
            )
        ):
            fail(
                "CALENDAR_MODEL_EGRESS_DENIED",
                "current trusted read Permission is revoked, expired, or mismatched",
            )

        read_head = conn.execute(
            select(schema.personal_calendar_read_policy_head).where(
                schema.personal_calendar_read_policy_head.c.relationship_id
                == projection["relationship_id"]
            )
        ).mappings().one_or_none()
        if read_head is None:
            fail("CALENDAR_MODEL_EGRESS_DENIED", "current calendar read policy is missing")
        read_revision = int(read_head["current_revision"])
        read_policy = conn.execute(
            select(schema.personal_calendar_read_policy_revision).where(
                schema.personal_calendar_read_policy_revision.c.relationship_id
                == projection["relationship_id"],
                schema.personal_calendar_read_policy_revision.c.revision == read_revision,
            )
        ).mappings().one_or_none()
        if (
            read_policy is None
            or read_policy["status"] != "ALLOW"
            or read_policy["capability_semantic_operation"] != CALENDAR_EVENTS_READ
            or read_policy["capability_effect_class"] != "READ_ONLY"
            or read_policy["capability_contract_version"]
            != grant["capability_contract_version"]
            or read_policy["permission_grant_policy_version"] != grant["grant_policy_version"]
            or str(projection["personal_resource_binding_id"])
            not in read_policy["allowed_resource_binding_ids_json"]
        ):
            fail("CALENDAR_MODEL_EGRESS_DENIED", "current calendar read policy denies egress lineage")

        route = conn.execute(
            select(schema.personal_calendar_model_route_binding).where(
                schema.personal_calendar_model_route_binding.c.route_binding_id
                == route_binding_id
            )
        ).mappings().one_or_none()
        if route is None:
            fail("CALENDAR_MODEL_ROUTE_NOT_FOUND", "calendar model route does not exist")
        route_state, route_revision = self._current_route_state(conn, route_binding_id)
        if route_state["status"] != "ACTIVE":
            fail("CALENDAR_MODEL_ROUTE_INELIGIBLE", "calendar model route is revoked")
        if (
            route["provider_binding_ref"] != getattr(self.adapter, "provider_binding_ref", None)
            or route["model_ref"] != getattr(self.adapter, "model_ref", None)
        ):
            fail(
                "CALENDAR_MODEL_ROUTE_MISMATCH",
                "configured adapter does not match the exact authorized model route",
            )

        egress_head = conn.execute(
            select(schema.personal_calendar_model_egress_policy_head).where(
                schema.personal_calendar_model_egress_policy_head.c.relationship_id
                == projection["relationship_id"]
            )
        ).mappings().one_or_none()
        if egress_head is None:
            fail("CALENDAR_MODEL_EGRESS_POLICY_MISSING", "current model-egress policy is missing")
        egress_revision = int(egress_head["current_revision"])
        egress_policy = conn.execute(
            select(schema.personal_calendar_model_egress_policy_revision).where(
                schema.personal_calendar_model_egress_policy_revision.c.relationship_id
                == projection["relationship_id"],
                schema.personal_calendar_model_egress_policy_revision.c.revision
                == egress_revision,
            )
        ).mappings().one_or_none()
        if (
            egress_policy is None
            or egress_policy["status"] != "ALLOW"
            or str(route_binding_id) not in egress_policy["allowed_route_binding_ids_json"]
            or route["retention_class"] != egress_policy["required_retention_class"]
            or route["residency_class"] != egress_policy["required_residency_class"]
        ):
            fail(
                "CALENDAR_MODEL_EGRESS_DENIED",
                "current personal-data model-egress policy denies the exact route",
            )
        return {
            "relationship_authority_revision": relationship_revision,
            "resource_binding_state_revision": resource_revision,
            "permission_state_revision": permission_revision,
            "read_policy_revision": read_revision,
            "egress_policy_revision": egress_revision,
            "route_state_revision": route_revision,
            "route": dict(route),
        }

    def _validate_plan_shape(
        self, plan: Any, *, maximum_occurrences: int
    ) -> dict[str, Any]:
        if not isinstance(plan, dict):
            fail("CALENDAR_ANSWER_PLAN_INVALID", "calendar model must return a structured plan object")
        required = {
            "plan_schema_version",
            "source_context_projection_id",
            "source_world_result_id",
            "requested_date",
            "ordered_occurrence_refs",
            "rendering_contract_version",
        }
        allowed = required | {"framing_mode"}
        if set(plan) - allowed or not required.issubset(plan):
            fail(
                "CALENDAR_ANSWER_PLAN_INVALID",
                "structured calendar plan contains missing or unauthorized fields",
            )
        if plan["plan_schema_version"] != CALENDAR_ANSWER_PLAN_SCHEMA_VERSION:
            fail("CALENDAR_ANSWER_PLAN_INVALID", "calendar plan schema version is untrusted")
        if plan["rendering_contract_version"] != CALENDAR_DAY_RENDERING_CONTRACT_VERSION:
            fail("CALENDAR_ANSWER_PLAN_INVALID", "calendar rendering contract is untrusted")
        for key in (
            "source_context_projection_id",
            "source_world_result_id",
            "requested_date",
        ):
            _require_text(
                plan[key],
                code="CALENDAR_ANSWER_PLAN_INVALID",
                message="calendar plan lineage fields must be text",
            )
        refs = plan["ordered_occurrence_refs"]
        if (
            not isinstance(refs, list)
            or len(refs) > maximum_occurrences
            or any(not isinstance(ref, str) or not ref for ref in refs)
        ):
            fail(
                "CALENDAR_ANSWER_PLAN_INVALID",
                "calendar plan occurrence references are outside the bounded contract",
            )
        if "framing_mode" in plan and plan["framing_mode"] != "NEUTRAL":
            fail(
                "CALENDAR_ANSWER_PLAN_INVALID",
                "calendar plan framing mode is outside the trusted bounded enum",
            )
        return dict(plan)

    def _validate_plan_semantics(
        self,
        plan: dict[str, Any],
        projection: dict[str, Any],
        occurrences: list[dict[str, Any]],
    ) -> list[str]:
        self._validate_plan_shape(plan, maximum_occurrences=len(occurrences))
        if (
            plan["source_context_projection_id"] != str(projection["projection_id"])
            or plan["source_world_result_id"] != str(projection["world_result_id"])
            or plan["requested_date"] != projection["requested_local_date"]
        ):
            fail(
                "CALENDAR_ANSWER_PLAN_LINEAGE_MISMATCH",
                "calendar plan does not bind the exact selected projection/result/date",
            )
        refs = list(plan["ordered_occurrence_refs"])
        expected = [row["occurrence_ref"] for row in occurrences]
        if len(refs) != len(expected) or len(set(refs)) != len(refs) or set(refs) != set(expected):
            fail(
                "CALENDAR_ANSWER_PLAN_OCCURRENCE_SET_INVALID",
                "calendar plan must represent every selected occurrence exactly once",
            )
        return refs

    def _render_schedule(
        self,
        projection: dict[str, Any],
        occurrences: list[dict[str, Any]],
        ordered_refs: list[str],
    ) -> str:
        by_ref = {row["occurrence_ref"]: row for row in occurrences}
        lines = [f"From your calendar for {projection['requested_local_date']}:"]
        if not ordered_refs:
            lines.append("No events are scheduled in the selected calendar for that day.")
            return "\n".join(lines)
        zone = ZoneInfo(projection["calendar_timezone"])
        for ref in ordered_refs:
            row = by_ref[ref]
            quoted_title = json.dumps(row["title"], ensure_ascii=False)
            if row["all_day"]:
                lines.append(f"- All day — {quoted_title}")
                continue
            start = _aware_utc(row["start_at"]).astimezone(zone)
            end = _aware_utc(row["end_at"]).astimezone(zone)
            lines.append(
                f"- {start.isoformat(timespec='minutes')} → {end.isoformat(timespec='minutes')} "
                f"({projection['calendar_timezone']}) — {quoted_title}"
            )
        return "\n".join(lines)

    def _recover_generation_replay(
        self, conn, replay: dict[str, Any]
    ) -> PersonalCalendarGenerationResult:
        model_invocation_id = UUID(replay["model_invocation_id"])
        egress_decision_id = UUID(replay["egress_decision_id"])
        generated = conn.execute(
            select(schema.generated_output.c.generated_output_id).where(
                schema.generated_output.c.model_invocation_id == model_invocation_id
            )
        ).scalar_one_or_none()
        if generated is None:
            fail(
                "CALENDAR_MODEL_DISPATCH_REPLAY_NOT_AUTHORIZING",
                "a prior model dispatch attempt cannot authorize another personal-data transport",
            )
        return PersonalCalendarGenerationResult(
            model_invocation_id, generated, egress_decision_id
        )

    def _finish_invocation(self, model_invocation_id: UUID, outcome: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(schema.model_invocation)
                .where(
                    schema.model_invocation.c.model_invocation_id == model_invocation_id,
                    schema.model_invocation.c.outcome == "IN_PROGRESS",
                )
                .values(outcome=outcome, completed_at=self.clock.now())
            )
