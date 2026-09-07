from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.domain.commands import (
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    BuildContextProjectionCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.models import (
    AdoptCompanionOutputResult,
    BuildContextProjectionResult,
    FoundationResponseDraft,
    StartModelInvocationResult,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.conversation_context import requires_prior_timeline_context
from alsoul.services.foundation_base import (
    FoundationServices as _FoundationServices,
    RAM_PREDICATE,
    WORLD_MEMORY_REQUIREMENT_PREDICATE,
)
from alsoul.services.projection_reuse import projection_reuse_blocker
from alsoul.storage import schema


class FoundationServices(_FoundationServices):
    """F4 semantic application services.

    Bootstrap is deliberately fenced out of this surface. Ordinary interaction,
    recovery, and work paths may advance already-existing canonical state, but
    they may not recreate missing Person/Relationship identity roots.
    """

    def bootstrap_foundation(self, *args: Any, **kwargs: Any) -> None:
        fail(
            "BOOTSTRAP_NOT_APPLICATION_SERVICE",
            "use FoundationBootstrapper only for explicit one-time foundation creation",
        )

    def build_context_projection(
        self, command: BuildContextProjectionCommand
    ) -> BuildContextProjectionResult:
        """Build the normal projection or the bounded immediate-prior-exchange form.

        F4 contextual conversation does not gain an unrestricted transcript window.
        Only the deterministic deictic grammar may request prior Timeline context, and
        that context is exactly one immediately preceding presented exchange on the
        same relationship, conversation, surface, and channel.
        """

        with self.engine.connect() as conn:
            current_input = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.current_input_event_id
                )
            ).mappings().one_or_none()

        if current_input is None or not requires_prior_timeline_context(
            current_input["content_text"]
        ):
            return super().build_context_projection(command)

        if command.required_personal_predicates or command.required_world_result_ids:
            fail(
                "CONVERSATIONAL_CONTEXT_PROJECTION_INVALID",
                "bounded prior-Timeline conversation cannot also project personal or world propositions",
            )
        return self._build_prior_timeline_context_projection(command)

    def _build_prior_timeline_context_projection(
        self, command: BuildContextProjectionCommand
    ) -> BuildContextProjectionResult:
        scope = "BuildContextProjection"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return BuildContextProjectionResult(
                    projection_id=UUID(replay["projection_id"]),
                    source_self_revision=int(replay["source_self_revision"]),
                    source_relationship_revision=int(
                        replay["source_relationship_revision"]
                    ),
                    source_timeline_frontier=int(replay["source_timeline_frontier"]),
                    manifest_digest=replay["manifest_digest"],
                )

            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "projection relationship does not exist")
            if relationship["companion_person_id"] != command.companion_person_id:
                fail(
                    "PROJECTION_RELATIONSHIP_REVISION_INVALID",
                    "projection companion does not own relationship",
                )

            self_head = conn.execute(
                select(schema.self_head).where(
                    schema.self_head.c.person_id == command.companion_person_id
                )
            ).mappings().one_or_none()
            if self_head is None:
                fail("SELF_HEAD_NOT_FOUND", "SelfHead missing")
            self_revision = conn.execute(
                select(schema.self_revision).where(
                    schema.self_revision.c.person_id == command.companion_person_id,
                    schema.self_revision.c.revision == self_head["current_revision"],
                )
            ).mappings().one_or_none()
            if self_revision is None:
                fail("SELF_REVISION_NOT_FOUND", "SelfHead points to missing SelfRevision")

            relationship_head = conn.execute(
                select(schema.relationship_head).where(
                    schema.relationship_head.c.relationship_id == command.relationship_id
                )
            ).mappings().one_or_none()
            if relationship_head is None:
                fail("RELATIONSHIP_HEAD_NOT_FOUND", "RelationshipHead missing")
            relationship_revision = conn.execute(
                select(schema.relationship_revision).where(
                    schema.relationship_revision.c.relationship_id
                    == command.relationship_id,
                    schema.relationship_revision.c.revision
                    == relationship_head["current_revision"],
                )
            ).mappings().one_or_none()
            if relationship_revision is None:
                fail(
                    "RELATIONSHIP_REVISION_NOT_FOUND",
                    "RelationshipHead points to missing revision",
                )

            input_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.current_input_event_id
                )
            ).mappings().one_or_none()
            if (
                input_event is None
                or input_event["relationship_id"] != command.relationship_id
                or input_event["event_kind"] != "COUNTERPART_INPUT"
                or input_event["actor_kind"] != "COUNTERPART"
                or input_event["actor_ref"] != relationship["counterpart_id"]
            ):
                fail(
                    "PROJECTION_CURRENT_INPUT_INVALID",
                    "current input is not a counterpart input in projection relationship",
                )
            if not requires_prior_timeline_context(input_event["content_text"]):
                fail(
                    "CONVERSATIONAL_CONTEXT_PROJECTION_INVALID",
                    "current input does not require bounded prior-Timeline context",
                )

            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            if timeline is None:
                fail("RELATIONSHIP_NOT_FOUND", "relationship Timeline head is missing")
            if int(input_event["timeline_seq"]) != int(timeline["last_timeline_seq"]):
                fail(
                    "PROJECTION_CONTEXTUAL_INPUT_NOT_FRONTIER",
                    "contextual conversation may project prior history only from the current Timeline frontier",
                )

            prior_input, prior_output = self._select_immediate_prior_exchange(
                conn,
                relationship=relationship,
                current_input=input_event,
            )
            selected_events = (prior_input, prior_output, input_event)

            manifest = {
                "projection_schema_version": 1,
                "purpose": "RESPOND_TO_INTERACTION",
                "companion_person_id": str(command.companion_person_id),
                "relationship_id": str(command.relationship_id),
                "current_input_event_id": str(command.current_input_event_id),
                "source_self_revision": int(self_head["current_revision"]),
                "source_relationship_revision": int(
                    relationship_head["current_revision"]
                ),
                "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                "selected_event_refs": [
                    str(event["event_id"]) for event in selected_events
                ],
                "timeline_context_selection": "IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE",
                "personal_context_items": [],
                "world_context_items": [],
            }
            digest = sha256_text(canonical_json(manifest))
            projection_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.context_projection).values(
                    projection_id=projection_id,
                    projection_schema_version=1,
                    purpose="RESPOND_TO_INTERACTION",
                    created_at=now,
                    companion_person_id=command.companion_person_id,
                    relationship_id=command.relationship_id,
                    current_input_event_id=command.current_input_event_id,
                    source_self_revision=self_head["current_revision"],
                    source_relationship_revision=relationship_head["current_revision"],
                    source_timeline_frontier=timeline["last_timeline_seq"],
                    manifest_digest=digest,
                )
            )
            for ordinal, event in enumerate(selected_events):
                conn.execute(
                    insert(schema.context_projection_event).values(
                        projection_id=projection_id,
                        ordinal=ordinal,
                        event_id=event["event_id"],
                    )
                )

            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ContextProjection",
                result_ref=projection_id,
                result_json={
                    "projection_id": str(projection_id),
                    "source_self_revision": int(self_head["current_revision"]),
                    "source_relationship_revision": int(
                        relationship_head["current_revision"]
                    ),
                    "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                    "manifest_digest": digest,
                },
                committed_at=now,
            )
            return BuildContextProjectionResult(
                projection_id,
                int(self_head["current_revision"]),
                int(relationship_head["current_revision"]),
                int(timeline["last_timeline_seq"]),
                digest,
            )

    def _select_immediate_prior_exchange(
        self,
        conn,
        *,
        relationship: dict[str, Any],
        current_input: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current_seq = int(current_input["timeline_seq"])
        if current_seq < 3:
            fail(
                "CONVERSATIONAL_CONTEXT_UNAVAILABLE",
                "bounded contextual conversation requires an immediately preceding presented exchange",
            )

        rows = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.relationship_id
                == current_input["relationship_id"],
                schema.interaction_event.c.timeline_seq.in_(
                    (current_seq - 2, current_seq - 1)
                ),
            )
        ).mappings().all()
        by_seq = {int(row["timeline_seq"]): row for row in rows}
        prior_input = by_seq.get(current_seq - 2)
        prior_output = by_seq.get(current_seq - 1)
        if prior_input is None or prior_output is None:
            fail(
                "CONVERSATIONAL_CONTEXT_UNAVAILABLE",
                "immediately preceding Timeline exchange is incomplete",
            )

        if (
            prior_input["event_kind"] != "COUNTERPART_INPUT"
            or prior_input["actor_kind"] != "COUNTERPART"
            or prior_input["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "CONVERSATIONAL_CONTEXT_UNAVAILABLE",
                "prior Timeline event is not the counterpart side of a completed exchange",
            )
        if (
            prior_output["event_kind"] != "COMPANION_PRESENTED_OUTPUT"
            or prior_output["actor_kind"] != "COMPANION"
            or prior_output["actor_ref"] != relationship["companion_person_id"]
            or prior_output["companion_output_id"] is None
            or prior_output["reply_to_event_id"] != prior_input["event_id"]
        ):
            fail(
                "CONVERSATIONAL_CONTEXT_UNAVAILABLE",
                "prior Timeline event is not a presented Companion response to the adjacent counterpart input",
            )

        if prior_input["conversation_id"] != current_input["conversation_id"]:
            fail(
                "CONVERSATIONAL_CONTEXT_BOUNDARY_MISMATCH",
                "bounded contextual reference does not cross conversation boundaries",
            )
        for event in (prior_input, prior_output):
            if (
                event["surface_binding_id"] != current_input["surface_binding_id"]
                or event["channel_binding_id"]
                != current_input["channel_binding_id"]
            ):
                fail(
                    "CONVERSATIONAL_CONTEXT_BOUNDARY_MISMATCH",
                    "bounded contextual reference does not cross surface or channel boundaries",
                )
        return dict(prior_input), dict(prior_output)

    def render_provider_context(self, projection_id: UUID) -> dict[str, Any]:
        """Render selected prior Timeline events as context, never as claim/world truth."""

        provider_context = super().render_provider_context(projection_id)
        with self.engine.connect() as conn:
            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id == projection_id
                )
            ).mappings().one_or_none()
            if projection is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            selected = conn.execute(
                select(
                    schema.context_projection_event.c.ordinal,
                    schema.interaction_event.c.event_id,
                    schema.interaction_event.c.timeline_seq,
                    schema.interaction_event.c.actor_kind,
                    schema.interaction_event.c.event_kind,
                    schema.interaction_event.c.content_text,
                )
                .join(
                    schema.interaction_event,
                    schema.context_projection_event.c.event_id
                    == schema.interaction_event.c.event_id,
                )
                .where(
                    schema.context_projection_event.c.projection_id == projection_id
                )
                .order_by(schema.context_projection_event.c.ordinal)
            ).mappings().all()

        if len(selected) <= 1:
            return provider_context
        if selected[-1]["event_id"] != projection["current_input_event_id"]:
            fail(
                "CONTEXT_PROJECTION_EVENT_ORDER_INVALID",
                "current input must be the final selected event in bounded contextual projection",
            )

        prior_events = selected[:-1]
        provider_context["prior_timeline_context"] = {
            "selection_policy": "IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE",
            "events": [
                {
                    "event_id": str(event["event_id"]),
                    "timeline_seq": int(event["timeline_seq"]),
                    "actor_kind": event["actor_kind"],
                    "event_kind": event["event_kind"],
                    "content_text": event["content_text"],
                }
                for event in prior_events
            ],
        }
        return provider_context

    def start_investigation(self, command: StartInvestigationCommand):
        if command.relationship_id is not None:
            with self.engine.connect() as conn:
                relationship = conn.execute(
                    select(schema.relationship_identity).where(
                        schema.relationship_identity.c.relationship_id == command.relationship_id
                    )
                ).mappings().one_or_none()
                if relationship is not None and (
                    relationship["companion_person_id"]
                    != command.initiated_by_companion_person_id
                ):
                    fail(
                        "INVESTIGATION_RELATIONSHIP_MISMATCH",
                        "investigation initiator does not own the supplied relationship",
                    )
        return super().start_investigation(command)

    def start_model_invocation(
        self, command: StartModelInvocationCommand
    ) -> StartModelInvocationResult:
        """Start one provider attempt only when retry semantics are safe.

        A model retry is always a new ModelInvocation. An existing IN_PROGRESS
        attempt must first be reconciled after process loss, and an existing
        successful GeneratedOutput must be recovered rather than regenerated.
        """

        scope = "StartModelInvocation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return StartModelInvocationResult(UUID(replay["model_invocation_id"]))

            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id
                    == command.context_projection_id
                )
            ).mappings().one_or_none()
            if projection is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")

            blocker = projection_reuse_blocker(conn, dict(projection))
            if blocker is not None:
                fail(
                    "CONTEXT_PROJECTION_NOT_REUSABLE",
                    f"ContextProjection is no longer eligible for provider execution: {blocker}",
                )

            attempts = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.context_projection_id
                    == command.context_projection_id
                )
            ).mappings().all()
            for attempt in attempts:
                if attempt["outcome"] == "IN_PROGRESS":
                    fail(
                        "MODEL_INVOCATION_ALREADY_IN_PROGRESS",
                        "an unresolved provider attempt already exists for this ContextProjection",
                    )
                if attempt["outcome"] == "SUCCEEDED":
                    generated = conn.execute(
                        select(schema.generated_output).where(
                            schema.generated_output.c.model_invocation_id
                            == attempt["model_invocation_id"]
                        )
                    ).mappings().one_or_none()
                    if generated is None:
                        fail(
                            "MODEL_INVOCATION_INCONSISTENT",
                            "successful ModelInvocation has no GeneratedOutput",
                        )
                    fail(
                        "MODEL_OUTPUT_ALREADY_AVAILABLE",
                        "recover the existing GeneratedOutput instead of starting another provider attempt",
                    )

            model_invocation_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.model_invocation).values(
                    model_invocation_id=model_invocation_id,
                    context_projection_id=command.context_projection_id,
                    provider_binding_ref=command.provider_binding_ref,
                    model_ref=command.model_ref,
                    renderer_version=command.renderer_version,
                    provider_request_digest=command.provider_request_digest,
                    started_at=now,
                    outcome="IN_PROGRESS",
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ModelInvocation",
                result_ref=model_invocation_id,
                result_json={"model_invocation_id": str(model_invocation_id)},
                committed_at=now,
            )
            return StartModelInvocationResult(model_invocation_id)

    def admit_world_result(self, command: AdmitWorldResultCommand):
        # Supporting evidence is validated by the base transaction through this
        # class's overridden validator. Contradiction evidence must cross the same
        # provenance boundary before the base transaction may link it.
        if command.contradiction_evidence_ids:
            with self.engine.connect() as conn:
                for evidence_id in command.contradiction_evidence_ids:
                    self._validate_world_evidence(
                        conn,
                        evidence_id,
                        command.investigation_id,
                        command.predicate,
                        command.value,
                        relation="CONTRADICTS",
                    )
        return super().admit_world_result(command)

    def adopt_companion_output(
        self, command: AdoptCompanionOutputCommand
    ) -> AdoptCompanionOutputResult:
        # Validate that the actual user-visible candidate bytes are the canonical
        # rendering of the provenance-bearing semantic payload. Valid metadata may
        # not be attached to unrelated prose.
        with self.engine.connect() as conn:
            generated = conn.execute(
                select(schema.generated_output).where(
                    schema.generated_output.c.generated_output_id
                    == command.generated_output_id
                )
            ).mappings().one_or_none()
            if generated is None:
                fail("GENERATED_OUTPUT_NOT_FOUND", "GeneratedOutput does not exist")
            invocation = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.model_invocation_id
                    == generated["model_invocation_id"]
                )
            ).mappings().one_or_none()
            if invocation is None:
                fail("MODEL_INVOCATION_NOT_FOUND", "ModelInvocation does not exist")
            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id
                    == invocation["context_projection_id"]
                )
            ).mappings().one_or_none()
            if projection is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            draft = self._validate_foundation_response_payload(
                conn,
                projection["projection_id"],
                generated["semantic_payload_json"],
            )
            if generated["content_text"] != draft.render_text():
                fail(
                    "OUTPUT_CONTENT_POLICY_REJECTED",
                    "generated text does not match the canonical rendering of its semantic payload",
                )
        return super().adopt_companion_output(command)

    def _validate_world_evidence(
        self,
        conn,
        evidence_id: UUID,
        investigation_id: UUID,
        predicate: str,
        value: Any,
        *,
        relation: str = "SUPPORTS",
    ) -> dict[str, Any]:
        ev = conn.execute(
            select(schema.evidence_item).where(
                schema.evidence_item.c.evidence_id == evidence_id
            )
        ).mappings().one_or_none()
        if (
            ev is None
            or ev["origin_kind"] != "SEARCH_RESULT"
            or ev["source_type"] != "WORLD_SOURCE_CAPTURE"
        ):
            fail(
                "WORLD_RESULT_SUPPORT_INVALID",
                "world-result evidence is not a world source capture EvidenceItem",
            )
        capture = conn.execute(
            select(schema.world_source_capture).where(
                schema.world_source_capture.c.source_capture_id == ev["source_id"]
            )
        ).mappings().one_or_none()
        if capture is None:
            fail("WORLD_RESULT_SUPPORT_INVALID", "WorldSourceCapture is missing")
        observation = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == capture["observation_id"]
            )
        ).mappings().one_or_none()
        if observation is None or observation["status"] != "SUCCEEDED":
            fail(
                "WORLD_RESULT_SUPPORT_INVALID",
                "world-result evidence Observation is not successful",
            )
        if observation["investigation_id"] != investigation_id:
            fail(
                "WORLD_RESULT_WRONG_INVESTIGATION",
                "world-result evidence came from another Investigation",
            )
        blob = conn.execute(
            select(schema.content_blob).where(
                schema.content_blob.c.content_digest == capture["content_digest"]
            )
        ).mappings().one_or_none()
        if blob is None:
            fail("CAPTURE_CONTENT_UNAVAILABLE", "captured source content is unavailable")
        if sha256_text(blob["content_text"]) != capture["content_digest"]:
            fail("CAPTURE_CONTENT_UNAVAILABLE", "captured source digest mismatch")

        if predicate == WORLD_MEMORY_REQUIREMENT_PREDICATE:
            try:
                payload = json.loads(blob["content_text"])
            except json.JSONDecodeError as exc:
                raise DomainError(
                    "WORLD_RESULT_SUPPORT_INVALID",
                    "captured world source is not valid JSON",
                ) from exc
            observed_value = payload.get("minimum_memory_gb")
            if relation == "SUPPORTS" and observed_value != value:
                fail(
                    "WORLD_RESULT_SUPPORT_INVALID",
                    "captured source does not support proposed world value",
                )
            if relation == "CONTRADICTS" and (
                observed_value is None or observed_value == value
            ):
                fail(
                    "WORLD_RESULT_SUPPORT_INVALID",
                    "captured source does not contradict proposed world value",
                )
        return dict(capture)

    def _validate_world_result_for_projection(
        self,
        conn,
        world_result_id: UUID,
        current_input_event: dict[str, Any],
    ) -> tuple[dict[str, Any], list[UUID]]:
        row, supports = super()._validate_world_result_for_projection(
            conn, world_result_id, current_input_event
        )
        investigation = conn.execute(
            select(schema.investigation).where(
                schema.investigation.c.investigation_id == row["investigation_id"]
            )
        ).mappings().one_or_none()
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == current_input_event["relationship_id"]
            )
        ).mappings().one_or_none()
        if (
            investigation is None
            or relationship is None
            or investigation["initiated_by_companion_person_id"]
            != relationship["companion_person_id"]
        ):
            fail(
                "PROJECTION_WORLD_RESULT_INELIGIBLE",
                "WorldResult Investigation was initiated by a different CompanionPerson",
            )

        if (
            row["valid_as_of"] is not None
            and row["valid_as_of"] < current_input_event["recorded_at"]
        ):
            fail(
                "PROJECTION_FRESHNESS_REQUIREMENT_FAILED",
                "WorldResult valid_as_of predates the current input",
            )

        for evidence_id in supports:
            capture = self._validate_world_evidence(
                conn,
                evidence_id,
                row["investigation_id"],
                row["predicate"],
                row["value_json"],
                relation="SUPPORTS",
            )
            if capture["captured_at"] < current_input_event["recorded_at"]:
                fail(
                    "PROJECTION_FRESHNESS_REQUIREMENT_FAILED",
                    "WorldSourceCapture predates the current input",
                )
        return row, supports

    def _validate_foundation_response_payload(
        self, conn, projection_id: UUID, payload: dict[str, Any]
    ) -> FoundationResponseDraft:
        validated = super()._validate_foundation_response_payload(
            conn, projection_id, payload
        )
        if isinstance(validated, FoundationResponseDraft):
            return validated
        return FoundationResponseDraft.from_payload(payload)


__all__ = [
    "FoundationServices",
    "RAM_PREDICATE",
    "WORLD_MEMORY_REQUIREMENT_PREDICATE",
]
