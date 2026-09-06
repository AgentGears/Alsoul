from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from alsoul.domain.models import (
    FoundationResponseDraft,
    FoundationResponseSegment,
    WorldAcquisitionSuccess,
)


@dataclass(slots=True)
class FakeWorldAdapter:
    minimum_memory_gb: int = 24
    source_identity: str = "fixture://software/current-requirements"

    def acquire(self, *, captured_at: datetime) -> WorldAcquisitionSuccess:
        content = json.dumps(
            {
                "software": "current-suite",
                "minimum_memory_gb": self.minimum_memory_gb,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return WorldAcquisitionSuccess(
            source_identity=self.source_identity,
            requested_locator=self.source_identity,
            resolved_locator=self.source_identity,
            content=content,
            captured_at=captured_at,
        )


@dataclass(slots=True)
class FakeModelAdapter:
    """Deterministic final-expression adapter for the F4 acceptance slice."""

    provider_binding_ref: str = "fixture-model-provider"
    model_ref: str = "fixture-model-v1"

    def provider_request_digest(self, provider_context: dict) -> str:
        payload = json.dumps(
            provider_context,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        personal = provider_context["personal_context"]
        world = provider_context["world_context"]
        if len(personal) != 1 or len(world) != 1:
            raise ValueError("F4 fake model requires exactly one personal and one world context item")
        memory_gb = personal[0]["value"]
        required_gb = world[0]["value"]
        return FoundationResponseDraft(
            segments=(
                FoundationResponseSegment(
                    "REMEMBERED_COUNTERPART_STATEMENT",
                    f"You told me your machine has {memory_gb} GB RAM.",
                    UUID(personal[0]["claim_id"]),
                ),
                FoundationResponseSegment(
                    "CURRENT_CHECKED_WORLD",
                    f"I checked the current requirement; it is {required_gb} GB RAM.",
                    UUID(world[0]["world_result_id"]),
                ),
                FoundationResponseSegment(
                    "COMPANION_INTERPRETATION",
                    (
                        "My take is that this machine does not meet that requirement."
                        if memory_gb < required_gb
                        else "My take is that this machine meets that memory requirement."
                    ),
                    None,
                ),
            )
        )
