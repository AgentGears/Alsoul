from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_effect import (
    CALENDAR_CREATE_EFFECT_SCHEMA_VERSION,
    CALENDAR_CREATE_EFFECT_SUPPORT_KIND,
)
from alsoul.domain.personal_calendar_mutation_completion import (
    CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION,
    CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION,
    CALENDAR_MUTATION_RESULT_KIND_CREATED,
    CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION,
    AdoptPersonalCalendarMutationOutputCommand,
    BuildPersonalCalendarMutationCompletionProjectionCommand,
    GeneratePersonalCalendarMutationResultPlanCommand,
    PersonalCalendarMutationAdoptionResult,
    PersonalCalendarMutationCompletionProjectionResult,
    PersonalCalendarMutationGenerationResult,
)
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar_cognition_v2 import PersonalCalendarCognitionServices
from alsoul.storage import schema


_BUILD_SCOPE = "BuildPersonalCalendarMutationCompletionProjection"
_GENERATE_SCOPE = "GeneratePersonalCalendarMutationResultPlan"
_ADOPT_SCOPE = "AdoptPersonalCalendarMutationOutput"
_CONTEXT_PROJECTION_SCHEMA_VERSION = 3
_CONTEXT_PURPOSE = "CALENDAR_MUTATION_COMPLETION"
_OUTPUT_PURPOSE = "REPORT_CALENDAR_MUTATION_RESULT"
_OUTPUT_TARGET_KIND = "PERSONAL_CALENDAR_CREATE_ACTION"
_OUTPUT_ORIGIN_KIND = "PERSONAL_CALENDAR_MUTATION_RESULT"


class PersonalCalendarMutationCompletionServices(PersonalCalendarCognitionServices):
    """Mechanically constrain model-visible calendar mutation completion.

    The model receives only an opaque completion reference plus fixed result/rendering
    contract identifiers.  Calendar facts remain host-side and are deterministically
    rendered only after the exact Action, Effect, SUPPORTS edge, evidence semantics,
    and structured model plan are revalidated at adoption.
    """

    def build_completion_projection(
        self, command: BuildPersonalCalendarMutationCompletionProjectionCommand
    ) -> PersonalCalendarMutationCompletionProjectionResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_BUILD_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._projection_result_from_json(replay)

                lineage = self._load_confirmed_completion(conn, command.effect_id)
                existing = conn.execute(
                    select(schema.personal_calendar_mutation_completion_projection).where(
                        schema.personal_calendar_mutation_completion_projection.c.effect_id
                        == command.effect_id
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    result = self._projection_result(existing)
                    self._save_projection_receipt(conn, command, req, result)
                    return result

                action = lineage["action"]
                relationship = lineage["relationship"]
                effect = lineage["effect"]
                support = lineage["support"]

                self_head = conn.execute(
                    select(schema.self_head).where(
                        schema.self_head.c.person_id
                        == relationship["companion_person_id"]
                    )
                ).mappings().one_or_none()
                relationship_head = conn.execute(
                    select(schema.relationship_head).where(
                        schema.relationship_head.c.relationship_id
                        == action["relationship_id"]
                    )
                ).mappings().one_or_none()
                if self_head is None or relationship_head is None:
                    fail(
                        "CALENDAR_MUTATION_COMPLETION_IDENTITY_STATE_MISSING",
                        "mutation completion requires current canonical identity revisions",
                    )

                projection_id = self.ids.new()
                completion_ref = self.ids.new()
                now = self.clock.now()
                manifest_digest = sha256_text(
                    canonical_json(
                        {
                            "action_id": str(action["action_id"]),
                            "effect_id": str(effect["effect_id"]),
                            "effect_evidence_id": str(support["effect_evidence_id"]),
                            "mutation_completion_ref": str(completion_ref),
                            "result_kind": CALENDAR_MUTATION_RESULT_KIND_CREATED,
                            "plan_schema_version": CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION,
                            "rendering_contract_version": (
                                CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                            ),
                            "context_contract_version": (
                                CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION
                            ),
                        }
                    )
                )

                conn.execute(
                    insert(schema.context_projection).values(
                        projection_id=projection_id,
                        projection_schema_version=_CONTEXT_PROJECTION_SCHEMA_VERSION,
                        purpose=_CONTEXT_PURPOSE,
                        created_at=now,
                        companion_person_id=relationship["companion_person_id"],
                        relationship_id=action["relationship_id"],
                        current_input_event_id=action["source_interaction_event_id"],
                        source_self_revision=int(self_head["current_revision"]),
                        source_relationship_revision=int(
                            relationship_head["current_revision"]
                        ),
                        source_timeline_frontier=int(action["source_timeline_frontier"]),
                        manifest_digest=manifest_digest,
                    )
                )
                conn.execute(
                    insert(schema.context_projection_event).values(
                        projection_id=projection_id,
                        ordinal=0,
                        event_id=action["source_interaction_event_id"],
                    )
                )
                conn.execute(
                    insert(
                        schema.personal_calendar_mutation_completion_projection
                    ).values(
                        projection_id=projection_id,
                        mutation_completion_ref=completion_ref,
                        action_id=action["action_id"],
                        effect_id=effect["effect_id"],
                        effect_evidence_id=support["effect_evidence_id"],
                        result_kind=CALENDAR_MUTATION_RESULT_KIND_CREATED,
                        plan_schema_version=CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION,
                        rendering_contract_version=(
                            CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                        ),
                        context_contract_version=(
                            CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION
                        ),
                        created_at=now,
                    )
                )
                result = PersonalCalendarMutationCompletionProjectionResult(
                    projection_id=projection_id,
                    mutation_completion_ref=completion_ref,
                    action_id=action["action_id"],
                    effect_id=effect["effect_id"],
                    manifest_digest=manifest_digest,
                )
                self._save_projection_receipt(conn, command, req, result)
                return result
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_MUTATION_COMPLETION_PROJECTION_CONFLICT",
                "calendar mutation completion projection conflicted with durable state",
            ) from exc

    def generate_result_plan(
        self, command: GeneratePersonalCalendarMutationResultPlanCommand
    ) -> PersonalCalendarMutationGenerationResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_GENERATE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._recover_generation_replay(conn, replay)

                projection = self._load_completion_projection(
                    conn, command.projection_id, serialize=True
                )
                self._load_confirmed_completion(conn, projection["effect_id"])
                provider_context = self._provider_context(projection)
                adapter = self._require_adapter()

                route = conn.execute(
                    select(schema.personal_calendar_model_route_binding).where(
                        schema.personal_calendar_model_route_binding.c.route_binding_id
                        == command.route_binding_id
                    )
                ).mappings().one_or_none()
                if route is None:
                    fail(
                        "CALENDAR_MUTATION_MODEL_ROUTE_NOT_FOUND",
                        "calendar mutation completion model route does not exist",
                    )
                route_state, route_revision = self._current_route_state(
                    conn, command.route_binding_id
                )
                if route_state["status"] != "ACTIVE":
                    fail(
                        "CALENDAR_MUTATION_MODEL_ROUTE_REVOKED",
                        "calendar mutation completion model route is not active",
                    )
                if (
                    route["provider_binding_ref"] != adapter.provider_binding_ref
                    or route["model_ref"] != adapter.model_ref
                ):
                    fail(
                        "CALENDAR_MUTATION_MODEL_ROUTE_MISMATCH",
                        "configured model adapter does not match the selected durable route",
                    )
                for field_name in (
                    "route_contract_version",
                    "data_handling_contract_version",
                    "retention_class",
                    "residency_class",
                ):
                    value = route[field_name]
                    if not isinstance(value, str) or not value.strip():
                        fail(
                            "CALENDAR_MUTATION_MODEL_ROUTE_INVALID",
                            "calendar mutation completion model route contract is incomplete",
                        )

                existing_output = conn.execute(
                    select(schema.personal_calendar_mutation_generated_output).where(
                        schema.personal_calendar_mutation_generated_output.c.projection_id
                        == command.projection_id
                    )
                ).mappings().one_or_none()
                if existing_output is not None:
                    fail(
                        "CALENDAR_MUTATION_RESULT_OUTPUT_ALREADY_AVAILABLE",
                        "this mutation completion projection already has a validated result plan",
                    )
                unsettled = conn.execute(
                    select(
                        schema.model_invocation.c.outcome,
                        schema.personal_calendar_mutation_model_invocation.c.model_invocation_id,
                    )
                    .join(
                        schema.personal_calendar_mutation_model_invocation,
                        schema.model_invocation.c.model_invocation_id
                        == schema.personal_calendar_mutation_model_invocation.c.model_invocation_id,
                    )
                    .where(
                        schema.personal_calendar_mutation_model_invocation.c.projection_id
                        == command.projection_id,
                        schema.model_invocation.c.outcome.in_(("IN_PROGRESS", "UNKNOWN")),
                    )
                ).mappings().first()
                if unsettled is not None:
                    fail(
                        "CALENDAR_MUTATION_MODEL_RECOVERY_REQUIRED",
                        "an earlier mutation completion model dispatch remains unresolved",
                    )

                self._cas_revision_head(
                    conn,
                    table=schema.personal_calendar_model_route_head,
                    key_column=schema.personal_calendar_model_route_head.c.route_binding_id,
                    key_value=command.route_binding_id,
                    expected_revision=route_revision,
                    conflict_code="CALENDAR_MUTATION_MODEL_ROUTE_CHANGED",
                )

                model_invocation_id = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.model_invocation).values(
                        model_invocation_id=model_invocation_id,
                        context_projection_id=command.projection_id,
                        provider_binding_ref=route["provider_binding_ref"],
                        model_ref=route["model_ref"],
                        renderer_version=(
                            CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                        ),
                        provider_request_digest=sha256_text(
                            canonical_json(provider_context)
                        ),
                        started_at=now,
                        completed_at=None,
                        outcome="IN_PROGRESS",
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_mutation_model_invocation).values(
                        model_invocation_id=model_invocation_id,
                        projection_id=command.projection_id,
                        route_binding_id=command.route_binding_id,
                        route_state_revision=route_revision,
                        plan_schema_version=CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION,
                        rendering_contract_version=(
                            CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                        ),
                        dispatched_at=now,
                    )
                )
                save_operation_receipt(
                    conn,
                    scope=_GENERATE_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarMutationModelDispatch",
                    result_ref=model_invocation_id,
                    result_json={
                        "model_invocation_id": str(model_invocation_id),
                        "projection_id": str(command.projection_id),
                    },
                    committed_at=now,
                )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_DISPATCH_CONFLICT",
                "calendar mutation completion model dispatch conflicted with durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_DISPATCH_CONFLICT",
                "calendar mutation completion model dispatch conflicted with concurrent state",
            ) from exc

        try:
            plan = adapter.generate_plan(provider_context)
            validated = self._validate_plan(plan, projection)
        except DomainError:
            self._finish_invocation(model_invocation_id, "FAILED")
            raise
        except AdapterRejected as exc:
            self._finish_invocation(model_invocation_id, "FAILED")
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_PROVIDER_REJECTED",
                "mutation completion model provider rejected the structured-plan request",
            ) from exc
        except AdapterOutcomeUnknown as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_OUTCOME_UNKNOWN",
                "mutation completion model transport outcome is unknown",
            ) from exc
        except Exception as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_OUTCOME_UNKNOWN",
                "mutation completion model transport became unusable after dispatch",
            ) from exc

        generated_output_id = self.ids.new()
        received_at = self.clock.now()
        content_text = canonical_json(validated)
        try:
            with self.engine.begin() as conn:
                invocation = conn.execute(
                    select(schema.model_invocation).where(
                        schema.model_invocation.c.model_invocation_id
                        == model_invocation_id
                    )
                ).mappings().one_or_none()
                if invocation is None or invocation["outcome"] != "IN_PROGRESS":
                    fail(
                        "CALENDAR_MUTATION_MODEL_INVOCATION_NOT_OPEN",
                        "mutation completion model invocation is no longer open",
                    )
                current_projection = self._load_completion_projection(
                    conn, command.projection_id
                )
                self._load_confirmed_completion(conn, current_projection["effect_id"])
                self._validate_plan(validated, current_projection)
                conn.execute(
                    insert(schema.generated_output).values(
                        generated_output_id=generated_output_id,
                        model_invocation_id=model_invocation_id,
                        content_text=content_text,
                        content_digest=sha256_text(content_text),
                        semantic_payload_json=validated,
                        received_at=received_at,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_mutation_generated_output).values(
                        generated_output_id=generated_output_id,
                        projection_id=command.projection_id,
                        action_id=current_projection["action_id"],
                        effect_id=current_projection["effect_id"],
                        plan_schema_version=CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION,
                        rendering_contract_version=(
                            CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                        ),
                        validated_shape_at=received_at,
                    )
                )
                changed = conn.execute(
                    update(schema.model_invocation)
                    .where(
                        schema.model_invocation.c.model_invocation_id
                        == model_invocation_id,
                        schema.model_invocation.c.outcome == "IN_PROGRESS",
                    )
                    .values(outcome="SUCCEEDED", completed_at=received_at)
                )
                if changed.rowcount != 1:
                    fail(
                        "CALENDAR_MUTATION_MODEL_INVOCATION_CONFLICT",
                        "mutation completion model invocation changed during admission",
                    )
        except DomainError:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise
        except (IntegrityError, OperationalError) as exc:
            self._finish_invocation(model_invocation_id, "UNKNOWN")
            raise DomainError(
                "CALENDAR_MUTATION_MODEL_COMPLETION_CONFLICT",
                "mutation completion structured-plan admission conflicted with durable state",
            ) from exc

        return PersonalCalendarMutationGenerationResult(
            model_invocation_id=model_invocation_id,
            generated_output_id=generated_output_id,
            projection_id=command.projection_id,
        )

    def adopt_mutation_output(
        self, command: AdoptPersonalCalendarMutationOutputCommand
    ) -> PersonalCalendarMutationAdoptionResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_ADOPT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._adoption_result_from_json(replay)

                generated = conn.execute(
                    select(
                        schema.generated_output,
                        schema.personal_calendar_mutation_generated_output.c.projection_id,
                        schema.personal_calendar_mutation_generated_output.c.action_id,
                        schema.personal_calendar_mutation_generated_output.c.effect_id,
                        schema.personal_calendar_mutation_generated_output.c.plan_schema_version,
                        schema.personal_calendar_mutation_generated_output.c.rendering_contract_version,
                    )
                    .join(
                        schema.personal_calendar_mutation_generated_output,
                        schema.generated_output.c.generated_output_id
                        == schema.personal_calendar_mutation_generated_output.c.generated_output_id,
                    )
                    .where(
                        schema.generated_output.c.generated_output_id
                        == command.generated_output_id
                    )
                ).mappings().one_or_none()
                if generated is None:
                    fail(
                        "CALENDAR_MUTATION_GENERATED_OUTPUT_NOT_FOUND",
                        "mutation completion GeneratedOutput does not exist",
                    )
                invocation = conn.execute(
                    select(schema.model_invocation).where(
                        schema.model_invocation.c.model_invocation_id
                        == generated["model_invocation_id"]
                    )
                ).mappings().one_or_none()
                if invocation is None or invocation["outcome"] != "SUCCEEDED":
                    fail(
                        "CALENDAR_MUTATION_GENERATED_OUTPUT_UNSETTLED",
                        "mutation completion GeneratedOutput lacks a successful invocation",
                    )
                if sha256_text(generated["content_text"]) != generated["content_digest"]:
                    fail(
                        "CALENDAR_MUTATION_GENERATED_OUTPUT_DIGEST_MISMATCH",
                        "mutation completion GeneratedOutput digest is invalid",
                    )
                if generated["content_text"] != canonical_json(
                    generated["semantic_payload_json"]
                ):
                    fail(
                        "CALENDAR_MUTATION_GENERATED_OUTPUT_PAYLOAD_MISMATCH",
                        "mutation completion plan text and semantic payload differ",
                    )

                projection = self._load_completion_projection(
                    conn, generated["projection_id"], serialize=True
                )
                if (
                    generated["action_id"] != projection["action_id"]
                    or generated["effect_id"] != projection["effect_id"]
                    or generated["plan_schema_version"]
                    != CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION
                    or generated["rendering_contract_version"]
                    != CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                ):
                    fail(
                        "CALENDAR_MUTATION_GENERATED_OUTPUT_LINEAGE_MISMATCH",
                        "mutation completion output does not match its immutable projection",
                    )
                lineage = self._load_confirmed_completion(conn, projection["effect_id"])
                self._validate_plan(generated["semantic_payload_json"], projection)

                action = lineage["action"]
                relationship = lineage["relationship"]
                content_text = self._render_created(action)
                content_digest = sha256_text(content_text)
                semantic_payload = {
                    "mutation_completion_ref": str(
                        projection["mutation_completion_ref"]
                    ),
                    "result_kind": CALENDAR_MUTATION_RESULT_KIND_CREATED,
                    "rendering_contract_version": (
                        CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                    ),
                }

                target = conn.execute(
                    select(schema.output_target).where(
                        schema.output_target.c.relationship_id == action["relationship_id"],
                        schema.output_target.c.target_kind == _OUTPUT_TARGET_KIND,
                        schema.output_target.c.target_ref == action["action_id"],
                        schema.output_target.c.purpose == _OUTPUT_PURPOSE,
                    )
                ).mappings().one_or_none()
                if target is None:
                    output_target_id = self.ids.new()
                    conn.execute(
                        insert(schema.output_target).values(
                            output_target_id=output_target_id,
                            relationship_id=action["relationship_id"],
                            target_kind=_OUTPUT_TARGET_KIND,
                            target_ref=action["action_id"],
                            purpose=_OUTPUT_PURPOSE,
                            created_at=self.clock.now(),
                        )
                    )
                else:
                    output_target_id = target["output_target_id"]
                    settled = conn.execute(
                        select(schema.companion_output).where(
                            schema.companion_output.c.output_target_id
                            == output_target_id
                        )
                    ).mappings().one_or_none()
                    if settled is not None:
                        adopted = conn.execute(
                            select(schema.personal_calendar_mutation_adoption).where(
                                schema.personal_calendar_mutation_adoption.c.companion_output_id
                                == settled["companion_output_id"],
                                schema.personal_calendar_mutation_adoption.c.generated_output_id
                                == command.generated_output_id,
                            )
                        ).mappings().one_or_none()
                        if adopted is not None:
                            result = PersonalCalendarMutationAdoptionResult(
                                companion_output_id=settled["companion_output_id"],
                                output_target_id=output_target_id,
                                action_id=action["action_id"],
                                effect_id=projection["effect_id"],
                            )
                            self._save_adoption_receipt(conn, command, req, result)
                            return result
                        fail(
                            "CALENDAR_MUTATION_OUTPUT_TARGET_ALREADY_SETTLED",
                            "calendar mutation Action already has a different adopted output",
                        )

                companion_output_id = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.companion_output).values(
                        companion_output_id=companion_output_id,
                        companion_person_id=relationship["companion_person_id"],
                        relationship_id=action["relationship_id"],
                        output_target_id=output_target_id,
                        origin_kind=_OUTPUT_ORIGIN_KIND,
                        origin_ref=projection["effect_id"],
                        source_generated_output_id=command.generated_output_id,
                        content_text=content_text,
                        content_digest=content_digest,
                        semantic_payload_json=semantic_payload,
                        adopted_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_mutation_adoption).values(
                        companion_output_id=companion_output_id,
                        generated_output_id=command.generated_output_id,
                        projection_id=projection["projection_id"],
                        action_id=action["action_id"],
                        effect_id=projection["effect_id"],
                        effect_evidence_id=projection["effect_evidence_id"],
                        rendering_contract_version=(
                            CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
                        ),
                        deterministic_render_digest=content_digest,
                        validated_at=now,
                    )
                )
                result = PersonalCalendarMutationAdoptionResult(
                    companion_output_id=companion_output_id,
                    output_target_id=output_target_id,
                    action_id=action["action_id"],
                    effect_id=projection["effect_id"],
                )
                self._save_adoption_receipt(conn, command, req, result)
                return result
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_MUTATION_OUTPUT_ADOPTION_CONFLICT",
                "calendar mutation completion adoption conflicted with durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_MUTATION_OUTPUT_ADOPTION_CONFLICT",
                "calendar mutation completion adoption conflicted with concurrent state",
            ) from exc

    def _load_confirmed_completion(self, conn, effect_id: UUID) -> dict[str, Any]:
        effect = conn.execute(
            select(schema.personal_calendar_create_effect).where(
                schema.personal_calendar_create_effect.c.effect_id == effect_id
            )
        ).mappings().one_or_none()
        if effect is None:
            fail(
                "CALENDAR_MUTATION_CONFIRMED_EFFECT_NOT_FOUND",
                "mutation completion requires a durable confirmed calendar Effect",
            )
        if (
            effect["status"] != "CONFIRMED_EFFECT"
            or effect["effect_schema_version"] != CALENDAR_CREATE_EFFECT_SCHEMA_VERSION
        ):
            fail(
                "CALENDAR_MUTATION_CONFIRMED_EFFECT_INVALID",
                "mutation completion requires exact confirmed Effect semantics",
            )
        support = conn.execute(
            select(schema.personal_calendar_create_effect_support).where(
                schema.personal_calendar_create_effect_support.c.effect_id == effect_id
            )
        ).mappings().one_or_none()
        if support is None or support["support_kind"] != CALENDAR_CREATE_EFFECT_SUPPORT_KIND:
            fail(
                "CALENDAR_MUTATION_EFFECT_SUPPORT_MISSING",
                "confirmed calendar Effect lacks its exact SUPPORTS evidence lineage",
            )
        evidence = conn.execute(
            select(schema.personal_calendar_create_effect_evidence).where(
                schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                == support["effect_evidence_id"]
            )
        ).mappings().one_or_none()
        action = conn.execute(
            select(schema.personal_calendar_create_action).where(
                schema.personal_calendar_create_action.c.action_id == effect["action_id"]
            )
        ).mappings().one_or_none()
        attempt = conn.execute(
            select(schema.personal_calendar_create_execution_attempt).where(
                schema.personal_calendar_create_execution_attempt.c.execution_attempt_id
                == effect["execution_attempt_id"]
            )
        ).mappings().one_or_none()
        if evidence is None or action is None or attempt is None:
            fail(
                "CALENDAR_MUTATION_EFFECT_LINEAGE_INCOMPLETE",
                "confirmed calendar Effect lineage is incomplete",
            )
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id
                == action["personal_resource_binding_id"]
            )
        ).mappings().one_or_none()
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == action["relationship_id"]
            )
        ).mappings().one_or_none()
        fence = conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == effect["execution_attempt_id"]
            )
        ).mappings().one_or_none()
        if resource is None or relationship is None or fence is None:
            fail(
                "CALENDAR_MUTATION_EFFECT_LINEAGE_INCOMPLETE",
                "confirmed calendar Effect lacks immutable resource or fence lineage",
            )

        if (
            effect["action_id"] != attempt["action_id"]
            or evidence["execution_attempt_id"] != attempt["execution_attempt_id"]
            or evidence["action_id"] != action["action_id"]
            or evidence["validation_kind"] != "SEMANTIC_MATCH"
            or evidence["provider_status"] != "CREATED"
            or evidence["evidence_schema_version"]
            != CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION
            or evidence["correlation_key"] != attempt["correlation_key"]
            or fence["action_id"] != action["action_id"]
            or fence["attempt_generation"] != attempt["attempt_generation"]
            or fence["correlation_key"] != attempt["correlation_key"]
            or evidence["external_system_ref"] != resource["external_system_ref"]
            or evidence["external_resource_ref"] != resource["external_resource_ref"]
            or evidence["normalized_summary"] != action["summary"]
            or _aware_utc(evidence["normalized_start_at"])
            != _aware_utc(action["normalized_start_at"])
            or _aware_utc(evidence["normalized_end_at"])
            != _aware_utc(action["normalized_end_at"])
            or not evidence["external_effect_ref"]
            or not evidence["receipt_ref"]
        ):
            fail(
                "CALENDAR_MUTATION_EFFECT_LINEAGE_MISMATCH",
                "confirmed calendar Effect does not prove the exact immutable Action result",
            )

        attempt_head = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_head).where(
                schema.personal_calendar_create_execution_attempt_head.c.execution_attempt_id
                == attempt["execution_attempt_id"]
            )
        ).mappings().one_or_none()
        guard_head = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_head).where(
                schema.personal_calendar_create_action_dispatch_head.c.action_id
                == action["action_id"]
            )
        ).mappings().one_or_none()
        if attempt_head is None or guard_head is None:
            fail(
                "CALENDAR_MUTATION_EFFECT_TERMINAL_STATE_MISSING",
                "confirmed calendar Effect lacks terminal execution state",
            )
        attempt_state = conn.execute(
            select(schema.personal_calendar_create_execution_attempt_state).where(
                schema.personal_calendar_create_execution_attempt_state.c.execution_attempt_id
                == attempt["execution_attempt_id"],
                schema.personal_calendar_create_execution_attempt_state.c.revision
                == attempt_head["current_revision"],
            )
        ).mappings().one_or_none()
        guard = conn.execute(
            select(schema.personal_calendar_create_action_dispatch_state).where(
                schema.personal_calendar_create_action_dispatch_state.c.action_id
                == action["action_id"],
                schema.personal_calendar_create_action_dispatch_state.c.revision
                == guard_head["current_revision"],
            )
        ).mappings().one_or_none()
        if (
            attempt_state is None
            or guard is None
            or attempt_state["status"] != "CONFIRMED_EFFECT"
            or guard["status"] != "CONFIRMED_EFFECT"
            or guard["execution_attempt_id"] != attempt["execution_attempt_id"]
        ):
            fail(
                "CALENDAR_MUTATION_EFFECT_TERMINAL_STATE_INVALID",
                "confirmed calendar Effect is not paired with exact terminal Action state",
            )

        return {
            "effect": dict(effect),
            "support": dict(support),
            "evidence": dict(evidence),
            "action": dict(action),
            "attempt": dict(attempt),
            "resource": dict(resource),
            "relationship": dict(relationship),
            "fence": dict(fence),
        }

    def _load_completion_projection(self, conn, projection_id: UUID, *, serialize=False):
        if serialize:
            locked = conn.execute(
                update(schema.personal_calendar_mutation_completion_projection)
                .where(
                    schema.personal_calendar_mutation_completion_projection.c.projection_id
                    == projection_id
                )
                .values(
                    context_contract_version=(
                        schema.personal_calendar_mutation_completion_projection.c.context_contract_version
                    )
                )
            )
            if locked.rowcount != 1:
                fail(
                    "CALENDAR_MUTATION_COMPLETION_PROJECTION_NOT_FOUND",
                    "calendar mutation completion projection does not exist",
                )
        projection = conn.execute(
            select(schema.personal_calendar_mutation_completion_projection).where(
                schema.personal_calendar_mutation_completion_projection.c.projection_id
                == projection_id
            )
        ).mappings().one_or_none()
        if projection is None:
            fail(
                "CALENDAR_MUTATION_COMPLETION_PROJECTION_NOT_FOUND",
                "calendar mutation completion projection does not exist",
            )
        if (
            projection["result_kind"] != CALENDAR_MUTATION_RESULT_KIND_CREATED
            or projection["plan_schema_version"]
            != CALENDAR_MUTATION_RESULT_PLAN_SCHEMA_VERSION
            or projection["rendering_contract_version"]
            != CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
            or projection["context_contract_version"]
            != CALENDAR_MUTATION_COMPLETION_CONTEXT_VERSION
        ):
            fail(
                "CALENDAR_MUTATION_COMPLETION_PROJECTION_INVALID",
                "calendar mutation completion projection contract is invalid",
            )
        return dict(projection)

    def _require_adapter(self):
        adapter = self.adapter
        if adapter is None or not callable(getattr(adapter, "generate_plan", None)):
            fail(
                "CALENDAR_MUTATION_MODEL_ADAPTER_MISSING",
                "mutation completion requires an explicit structured-plan model adapter",
            )
        for value in (
            getattr(adapter, "provider_binding_ref", None),
            getattr(adapter, "model_ref", None),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                fail(
                    "CALENDAR_MUTATION_MODEL_ADAPTER_INVALID",
                    "mutation completion model adapter identity must be explicit and bounded",
                )
        return adapter

    @staticmethod
    def _provider_context(projection: dict[str, Any]) -> dict[str, str]:
        return {
            "mutation_completion_ref": str(projection["mutation_completion_ref"]),
            "result_kind": CALENDAR_MUTATION_RESULT_KIND_CREATED,
            "rendering_contract_version": (
                CALENDAR_CREATE_RESULT_RENDERING_CONTRACT_VERSION
            ),
        }

    @staticmethod
    def _validate_plan(plan: Any, projection: dict[str, Any]) -> dict[str, str]:
        if not isinstance(plan, dict) or set(plan) != {
            "mutation_completion_ref",
            "result_kind",
            "rendering_contract_version",
        }:
            fail(
                "CALENDAR_MUTATION_RESULT_PLAN_INVALID",
                "mutation result plan must contain only the trusted completion reference and fixed result contract",
            )
        expected = PersonalCalendarMutationCompletionServices._provider_context(projection)
        if any(plan.get(key) != value for key, value in expected.items()):
            fail(
                "CALENDAR_MUTATION_RESULT_PLAN_MISMATCH",
                "mutation result plan does not match the exact durable completion projection",
            )
        return expected

    @staticmethod
    def _render_created(action: dict[str, Any]) -> str:
        title = json.dumps(action["summary"], ensure_ascii=False)
        return (
            f"I created {title} on your calendar from "
            f"{action['start_text']} to {action['end_text']}."
        )

    def _recover_generation_replay(self, conn, replay):
        invocation_id = UUID(replay["model_invocation_id"])
        projection_id = UUID(replay["projection_id"])
        invocation = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id == invocation_id
            )
        ).mappings().one_or_none()
        if invocation is None:
            fail(
                "CALENDAR_MUTATION_MODEL_INVOCATION_NOT_FOUND",
                "recorded mutation completion invocation is missing",
            )
        output = conn.execute(
            select(schema.generated_output).where(
                schema.generated_output.c.model_invocation_id == invocation_id
            )
        ).mappings().one_or_none()
        if invocation["outcome"] == "SUCCEEDED" and output is not None:
            return PersonalCalendarMutationGenerationResult(
                model_invocation_id=invocation_id,
                generated_output_id=output["generated_output_id"],
                projection_id=projection_id,
            )
        if invocation["outcome"] == "FAILED":
            fail(
                "CALENDAR_MUTATION_MODEL_OPERATION_FAILED",
                "recorded mutation completion model operation failed",
            )
        fail(
            "CALENDAR_MUTATION_MODEL_RECOVERY_REQUIRED",
            "recorded mutation completion model operation is unresolved",
        )

    def _finish_invocation(self, invocation_id: UUID, outcome: str) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(schema.model_invocation)
                    .where(
                        schema.model_invocation.c.model_invocation_id == invocation_id,
                        schema.model_invocation.c.outcome == "IN_PROGRESS",
                    )
                    .values(outcome=outcome, completed_at=self.clock.now())
                )
        except Exception:
            return

    def _save_projection_receipt(self, conn, command, req, result) -> None:
        save_operation_receipt(
            conn,
            scope=_BUILD_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="PersonalCalendarMutationCompletionProjection",
            result_ref=result.projection_id,
            result_json={
                "projection_id": str(result.projection_id),
                "mutation_completion_ref": str(result.mutation_completion_ref),
                "action_id": str(result.action_id),
                "effect_id": str(result.effect_id),
                "manifest_digest": result.manifest_digest,
            },
            committed_at=self.clock.now(),
        )

    def _save_adoption_receipt(self, conn, command, req, result) -> None:
        save_operation_receipt(
            conn,
            scope=_ADOPT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req,
            result_kind="PersonalCalendarMutationCompanionOutput",
            result_ref=result.companion_output_id,
            result_json={
                "companion_output_id": str(result.companion_output_id),
                "output_target_id": str(result.output_target_id),
                "action_id": str(result.action_id),
                "effect_id": str(result.effect_id),
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _projection_result(row) -> PersonalCalendarMutationCompletionProjectionResult:
        generic_manifest = None
        # The caller loads the generic manifest when recovering through an operation
        # receipt; for cross-operation semantic reuse, recompute it from durable pins.
        manifest = sha256_text(
            canonical_json(
                {
                    "action_id": str(row["action_id"]),
                    "effect_id": str(row["effect_id"]),
                    "effect_evidence_id": str(row["effect_evidence_id"]),
                    "mutation_completion_ref": str(row["mutation_completion_ref"]),
                    "result_kind": row["result_kind"],
                    "plan_schema_version": row["plan_schema_version"],
                    "rendering_contract_version": row["rendering_contract_version"],
                    "context_contract_version": row["context_contract_version"],
                }
            )
        )
        del generic_manifest
        return PersonalCalendarMutationCompletionProjectionResult(
            projection_id=row["projection_id"],
            mutation_completion_ref=row["mutation_completion_ref"],
            action_id=row["action_id"],
            effect_id=row["effect_id"],
            manifest_digest=manifest,
        )

    @staticmethod
    def _projection_result_from_json(payload):
        return PersonalCalendarMutationCompletionProjectionResult(
            projection_id=UUID(payload["projection_id"]),
            mutation_completion_ref=UUID(payload["mutation_completion_ref"]),
            action_id=UUID(payload["action_id"]),
            effect_id=UUID(payload["effect_id"]),
            manifest_digest=payload["manifest_digest"],
        )

    @staticmethod
    def _adoption_result_from_json(payload):
        return PersonalCalendarMutationAdoptionResult(
            companion_output_id=UUID(payload["companion_output_id"]),
            output_target_id=UUID(payload["output_target_id"]),
            action_id=UUID(payload["action_id"]),
            effect_id=UUID(payload["effect_id"]),
        )


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        fail(
            "CALENDAR_MUTATION_COMPLETION_TIME_INVALID",
            "mutation completion evidence timestamps must be datetime values",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = ["PersonalCalendarMutationCompletionServices"]
