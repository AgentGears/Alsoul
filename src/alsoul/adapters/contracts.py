from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from alsoul.domain.models import FoundationResponseDraft, WorldAcquisitionSuccess


class AdapterError(RuntimeError):
    """Base error raised by a replaceable provider adapter."""


class AdapterRejected(AdapterError):
    """The provider returned a definite non-usable result for this attempt."""


class AdapterOutcomeUnknown(AdapterError):
    """Dispatch may have occurred, but no trustworthy final result was recovered."""


@runtime_checkable
class WorldAcquisitionAdapter(Protocol):
    """Provider-independent F4 world-acquisition contract."""

    def acquire(self, *, captured_at: datetime) -> WorldAcquisitionSuccess:
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
    "ModelProviderAdapter",
    "WorldAcquisitionAdapter",
]
