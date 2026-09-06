from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from alsoul.domain.models import (
    CapturedWorldMaterial,
    ExtractedWorldResult,
    FoundationResponseDraft,
    WorldAcquisitionSuccess,
)


class AdapterError(RuntimeError):
    """Base error raised by a replaceable provider adapter."""


class AdapterRejected(AdapterError):
    """The provider or controlled interpreter returned a definite non-usable result."""


class AdapterOutcomeUnknown(AdapterError):
    """Dispatch may have occurred, but no trustworthy final result was recovered."""


@dataclass(frozen=True, slots=True)
class FirstPartyPresentationAcceptance:
    """Positive sink acceptance for one idempotent first-party presentation request.

    This receipt establishes that the configured first-party sink accepted the exact
    CompanionOutput content under the supplied presentation key. It does not establish
    that the counterpart read, heard, or understood the output.
    """

    presentation_key: str
    receipt_ref: str
    content_digest: str


@runtime_checkable
class FirstPartyPresentationAdapter(Protocol):
    """Provider-independent first-party presentation acceptance contract.

    Implementations must treat ``presentation_key`` as a semantic idempotency key:
    replaying the same key with the same content must not create a second logical
    presentation. Reusing the key with different content must be rejected.
    """

    def present(
        self,
        *,
        presentation_key: str,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        content_text: str,
        content_digest: str,
    ) -> FirstPartyPresentationAcceptance:
        ...


@runtime_checkable
class WorldAcquisitionAdapter(Protocol):
    """Provider-independent F4 world-acquisition contract."""

    def acquire(self, *, captured_at: datetime) -> WorldAcquisitionSuccess:
        ...


@runtime_checkable
class WorldResultExtractor(Protocol):
    """Interpret one recoverable source capture into a bounded proposition proposal.

    Extraction does not admit a WorldResult. The semantic application service still
    validates evidence lineage and performs the authoritative admission boundary.
    """

    def extract(self, material: CapturedWorldMaterial) -> ExtractedWorldResult:
        ...


@runtime_checkable
class ModelProviderAdapter(Protocol):
    """Provider-independent F4 final-expression contract."""

    provider_binding_ref: str
    model_ref: str

    def provider_request_digest(self, provider_context: dict[str, Any]) -> str:
        """Digest the canonical semantic request body that will be dispatched."""
        ...

    def generate(self, provider_context: dict[str, Any]) -> FoundationResponseDraft:
        ...


__all__ = [
    "AdapterError",
    "AdapterOutcomeUnknown",
    "AdapterRejected",
    "FirstPartyPresentationAcceptance",
    "FirstPartyPresentationAdapter",
    "ModelProviderAdapter",
    "WorldAcquisitionAdapter",
    "WorldResultExtractor",
]
