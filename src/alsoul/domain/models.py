from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FoundationIds:
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class AppendCounterpartInputResult:
    event_id: UUID
    timeline_seq: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class AdmitPersonMemoryClaimResult:
    claim_id: UUID
    corrected_claim_id: UUID | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class StartInvestigationResult:
    investigation_id: UUID


@dataclass(frozen=True, slots=True)
class StartObservationResult:
    observation_id: UUID


@dataclass(frozen=True, slots=True)
class RecordObservationSuccessResult:
    source_capture_id: UUID
    evidence_id: UUID


@dataclass(frozen=True, slots=True)
class AdmitWorldResultResult:
    world_result_id: UUID


@dataclass(frozen=True, slots=True)
class BuildContextProjectionResult:
    projection_id: UUID
    source_self_revision: int
    source_relationship_revision: int
    source_timeline_frontier: int
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class StartModelInvocationResult:
    model_invocation_id: UUID


@dataclass(frozen=True, slots=True)
class CompleteModelInvocationResult:
    generated_output_id: UUID


@dataclass(frozen=True, slots=True)
class ResolveOutputTargetResult:
    output_target_id: UUID
    created: bool


@dataclass(frozen=True, slots=True)
class AdoptCompanionOutputResult:
    companion_output_id: UUID


@dataclass(frozen=True, slots=True)
class PresentCompanionOutputResult:
    interaction_event_id: UUID
    timeline_seq: int
    idempotent_replay: bool = False


EpistemicKind = Literal[
    "REMEMBERED_COUNTERPART_STATEMENT",
    "CURRENT_CHECKED_WORLD",
    "COMPANION_INTERPRETATION",
]


@dataclass(frozen=True, slots=True)
class FoundationResponseSegment:
    epistemic_kind: EpistemicKind
    text: str
    source_ref: UUID | None = None


@dataclass(frozen=True, slots=True)
class FoundationResponseDraft:
    segments: tuple[FoundationResponseSegment, ...]

    def render_text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)

    def to_payload(self) -> dict[str, Any]:
        return {
            "segments": [
                {
                    "epistemic_kind": segment.epistemic_kind,
                    "text": segment.text,
                    "source_ref": str(segment.source_ref) if segment.source_ref else None,
                }
                for segment in self.segments
            ]
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FoundationResponseDraft":
        return cls(
            tuple(
                FoundationResponseSegment(
                    epistemic_kind=item["epistemic_kind"],
                    text=item["text"],
                    source_ref=UUID(item["source_ref"]) if item.get("source_ref") else None,
                )
                for item in payload["segments"]
            )
        )


@dataclass(frozen=True, slots=True)
class WorldAcquisitionSuccess:
    source_identity: str
    requested_locator: str | None
    resolved_locator: str | None
    content: str
    captured_at: datetime
    source_version: str | None = None
    source_published_at: datetime | None = None
    source_modified_at: datetime | None = None
