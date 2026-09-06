from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.commands import (
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    StartInvestigationCommand,
)
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.models import AdoptCompanionOutputResult, FoundationResponseDraft
from alsoul.services.common import sha256_text
from alsoul.services.foundation_base import (
    FoundationServices as _FoundationServices,
    RAM_PREDICATE,
    WORLD_MEMORY_REQUIREMENT_PREDICATE,
)
from alsoul.storage import schema


class FoundationServices(_FoundationServices):
    """F4 service hardening layered over the initial implementation.

    The base implementation remains unchanged for auditability. This class tightens
    the semantic admission/readiness boundaries identified during PR review.
    """

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
