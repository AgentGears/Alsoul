from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from alsoul.domain.models import FoundationResponseDraft, WorldAcquisitionSuccess


@runtime_checkable
class WorldAcquisitionAdapter(Protocol):
    """Provider-independent F4 world-acquisition contract."""

    def acquire(self, *, captured_at: datetime) -> WorldAcquisitionSuccess:
        ...


@runtime_checkable
class ModelProviderAdapter(Protocol):
    """Provider-independent F4 final-expression contract."""

    def generate(self, provider_context: dict[str, Any]) -> FoundationResponseDraft:
        ...


__all__ = ["ModelProviderAdapter", "WorldAcquisitionAdapter"]
