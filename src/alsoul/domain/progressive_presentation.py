from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


PROGRESSIVE_PRESENTATION_CONTRACT_VERSION = "PROGRESSIVE_PRESENTATION_V1"
PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION = "PROGRESSIVE_PRESENTATION_FRAME_V1"
PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION = (
    "PROGRESSIVE_PRESENTATION_TRANSPORT_V1"
)
PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION = (
    "PROGRESSIVE_PRESENTATION_RECEIPT_V1"
)
PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT = 256


@dataclass(frozen=True, slots=True)
class OpenProgressivePresentationCommand:
    operation_id: UUID
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID


@dataclass(frozen=True, slots=True)
class FenceProgressivePresentationAttemptCommand:
    operation_id: UUID
    presentation_session_id: UUID


@dataclass(frozen=True, slots=True)
class DispatchProgressivePresentationFrameCommand:
    operation_id: UUID
    presentation_attempt_id: UUID
    frame_ordinal: int


@dataclass(frozen=True, slots=True)
class RecordProgressivePresentationReceiptCommand:
    operation_id: UUID
    presentation_session_id: UUID
    presentation_attempt_id: UUID
    presentation_key: str
    attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    frame_ordinal: int
    frame_digest: str
    presentation_receipt_ref: str
    presented_at: datetime
    presentation_receipt_contract_version: str = (
        PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
    )


@dataclass(frozen=True, slots=True)
class ProgressivePresentationSessionResult:
    presentation_session_id: UUID
    companion_output_id: UUID
    presentation_key: str
    frame_count: int
    presentation_contract_version: str
    frame_contract_version: str


@dataclass(frozen=True, slots=True)
class ProgressivePresentationAttemptResult:
    presentation_attempt_id: UUID
    presentation_session_id: UUID
    attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    state: str


@dataclass(frozen=True, slots=True)
class ProgressivePresentationFrameTransportResult:
    presentation_key: str
    attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    frame_ordinal: int
    frame_digest: str
    acceptance_state: str
    acceptance_ref: str | None = None
    accepted_at: datetime | None = None
    transport_contract_version: str = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ProgressivePresentationFrameDispatchResult:
    presentation_attempt_id: UUID
    presentation_session_id: UUID
    frame_ordinal: int
    acceptance_state: str
    acceptance_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ProgressivePresentationReceiptResult:
    presentation_evidence_id: UUID
    presentation_session_id: UUID
    frame_ordinal: int
    presented_through_frame: int


@runtime_checkable
class ProgressivePresentationAdapter(Protocol):
    presentation_contract_version: str
    frame_contract_version: str
    transport_contract_version: str

    def dispatch_frame(
        self,
        *,
        presentation_key: str,
        attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        presentation_session_id: UUID,
        presentation_attempt_id: UUID,
        frame_ordinal: int,
        frame_digest: str,
        content_text: str,
    ) -> ProgressivePresentationFrameTransportResult:
        ...


__all__ = [
    "DispatchProgressivePresentationFrameCommand",
    "FenceProgressivePresentationAttemptCommand",
    "OpenProgressivePresentationCommand",
    "PROGRESSIVE_PRESENTATION_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT",
    "PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION",
    "ProgressivePresentationAdapter",
    "ProgressivePresentationAttemptResult",
    "ProgressivePresentationFrameDispatchResult",
    "ProgressivePresentationFrameTransportResult",
    "ProgressivePresentationReceiptResult",
    "ProgressivePresentationSessionResult",
    "RecordProgressivePresentationReceiptCommand",
]
