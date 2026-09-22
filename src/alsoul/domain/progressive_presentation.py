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
PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION = (
    "PROGRESSIVE_PRESENTATION_RECEPTION_V1"
)
PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION = (
    "PROGRESSIVE_PRESENTATION_STATUS_V1"
)
PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION = (
    "PROGRESSIVE_PRESENTATION_CANCELLATION_V1"
)
PROGRESSIVE_PRESENTATION_RECEPTION_KIND = "PLAYBACK_CONFIRMED_THROUGH_FRAME"
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
class RecordProgressivePresentationReceptionCommand:
    operation_id: UUID
    presentation_session_id: UUID
    presentation_attempt_id: UUID
    presentation_key: str
    attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    received_through_frame: int
    reception_receipt_ref: str
    received_at: datetime
    reception_kind: str = PROGRESSIVE_PRESENTATION_RECEPTION_KIND
    reception_contract_version: str = PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ReconcileProgressivePresentationAttemptCommand:
    operation_id: UUID
    presentation_attempt_id: UUID


@dataclass(frozen=True, slots=True)
class InterruptProgressivePresentationCommand:
    operation_id: UUID
    presentation_attempt_id: UUID
    interrupting_event_id: UUID


@dataclass(frozen=True, slots=True)
class CommitProgressivePresentationHistoryCommand:
    operation_id: UUID
    presentation_attempt_id: UUID


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


@dataclass(frozen=True, slots=True)
class ProgressivePresentationReceptionResult:
    reception_evidence_id: UUID
    presentation_session_id: UUID
    received_through_frame: int


@dataclass(frozen=True, slots=True)
class ProgressivePresentationReconciliationStatus:
    presentation_key: str
    attempt_generation: int
    presentation_transport_fence_scope_id: UUID
    presentation_attempt_id: UUID
    presentation_session_id: UUID
    settlement_state: str
    status_ref: str
    last_authoritatively_presented_frame: int
    last_authoritatively_received_frame: int
    settled_through_ref: str | None = None
    settled_at: datetime | None = None
    status_contract_version: str = PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ProgressivePresentationReconciliationResult:
    presentation_status_evidence_id: UUID
    presentation_attempt_id: UUID
    presentation_session_id: UUID
    state: str
    last_authoritatively_presented_frame: int
    last_authoritatively_received_frame: int


@dataclass(frozen=True, slots=True)
class ProgressivePresentationInterruptionResult:
    interruption_id: UUID
    presentation_attempt_id: UUID
    presentation_session_id: UUID
    interrupting_event_id: UUID
    cancellation_request_state: str


@dataclass(frozen=True, slots=True)
class ProgressivePresentationHistoryResult:
    presentation_session_id: UUID
    presentation_attempt_id: UUID
    interaction_event_id: UUID | None
    timeline_seq: int | None
    last_presented_frame: int
    presented_content_digest: str | None
    idempotent_replay: bool = False


@runtime_checkable
class ProgressivePresentationAdapter(Protocol):
    """Trusted first-party frame transport, receipt, reception, cancellation, and status boundary."""

    presentation_contract_version: str
    frame_contract_version: str
    transport_contract_version: str
    receipt_contract_version: str
    reception_contract_version: str
    status_contract_version: str
    cancellation_contract_version: str

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

    def validate_presentation_receipt(
        self,
        *,
        presentation_key: str,
        attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        presentation_session_id: UUID,
        presentation_attempt_id: UUID,
        frame_ordinal: int,
        frame_digest: str,
        presentation_receipt_ref: str,
        presented_at: datetime,
    ) -> bool:
        """Validate one sink-issued receipt against the trusted first-party boundary."""
        ...

    def validate_reception_receipt(
        self,
        *,
        presentation_key: str,
        attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        presentation_session_id: UUID,
        presentation_attempt_id: UUID,
        received_through_frame: int,
        reception_receipt_ref: str,
        received_at: datetime,
        reception_kind: str,
    ) -> bool:
        """Validate one bounded sink-issued playback/read receipt."""
        ...

    def request_presentation_cancellation(
        self,
        *,
        presentation_key: str,
        attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        presentation_session_id: UUID,
        presentation_attempt_id: UUID,
        interruption_key: str,
        interrupting_event_id: UUID,
    ) -> bool:
        """Request cancellation/settling for one exact fenced generation.

        ``True`` only acknowledges the cancellation request. It is never terminal
        presentation proof; terminal truth still comes from status reconciliation.
        """
        ...

    def reconcile_presentation_status(
        self,
        *,
        presentation_key: str,
        attempt_generation: int,
        presentation_transport_fence_scope_id: UUID,
        presentation_session_id: UUID,
        presentation_attempt_id: UUID,
    ) -> ProgressivePresentationReconciliationStatus:
        """Return content-free status for one exact fenced presentation generation."""
        ...


__all__ = [
    "CommitProgressivePresentationHistoryCommand",
    "DispatchProgressivePresentationFrameCommand",
    "FenceProgressivePresentationAttemptCommand",
    "InterruptProgressivePresentationCommand",
    "OpenProgressivePresentationCommand",
    "PROGRESSIVE_PRESENTATION_CANCELLATION_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_FRAME_CODEPOINT_LIMIT",
    "PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_RECEPTION_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_RECEPTION_KIND",
    "PROGRESSIVE_PRESENTATION_STATUS_CONTRACT_VERSION",
    "PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION",
    "ProgressivePresentationAdapter",
    "ProgressivePresentationAttemptResult",
    "ProgressivePresentationFrameDispatchResult",
    "ProgressivePresentationFrameTransportResult",
    "ProgressivePresentationHistoryResult",
    "ProgressivePresentationInterruptionResult",
    "ProgressivePresentationReceiptResult",
    "ProgressivePresentationReceptionResult",
    "ProgressivePresentationReconciliationResult",
    "ProgressivePresentationReconciliationStatus",
    "ProgressivePresentationSessionResult",
    "ReconcileProgressivePresentationAttemptCommand",
    "RecordProgressivePresentationReceiptCommand",
    "RecordProgressivePresentationReceptionCommand",
]
