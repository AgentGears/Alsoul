from __future__ import annotations

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    ProgressivePresentationReceiptResult,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services.progressive_presentation import _aware_utc, _required_text
from alsoul.services.progressive_presentation_v2 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV2,
)


class ProgressivePresentationServices(ProgressivePresentationServicesV2):
    """Current F6.A core with trusted first-party receipt validation.

    A caller-provided receipt reference is not presentation truth by itself. Before any
    presentation evidence is admitted, the configured first-party presentation adapter
    must validate the exact receipt against the pinned session/generation/frame lineage.
    """

    def record_presentation_receipt(
        self, command: RecordProgressivePresentationReceiptCommand
    ) -> ProgressivePresentationReceiptResult:
        adapter = self._require_receipt_adapter()
        if (
            command.presentation_receipt_contract_version
            != PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
                "presentation receipt contract version is unsupported",
            )
        receipt_ref = _required_text(
            command.presentation_receipt_ref,
            "PROGRESSIVE_PRESENTATION_RECEIPT_INVALID",
            "presentation receipt reference must be non-empty",
        )
        presented_at = _aware_utc(command.presented_at)

        try:
            trusted = adapter.validate_presentation_receipt(
                presentation_key=command.presentation_key,
                attempt_generation=command.attempt_generation,
                presentation_transport_fence_scope_id=(
                    command.presentation_transport_fence_scope_id
                ),
                presentation_session_id=command.presentation_session_id,
                presentation_attempt_id=command.presentation_attempt_id,
                frame_ordinal=command.frame_ordinal,
                frame_digest=command.frame_digest,
                presentation_receipt_ref=receipt_ref,
                presented_at=presented_at,
            )
        except Exception as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED",
                "trusted first-party presentation receipt validation failed",
            ) from exc
        if trusted is not True:
            fail(
                "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED",
                "presentation receipt was not validated by the trusted first-party sink boundary",
            )
        return super().record_presentation_receipt(command)

    def _require_receipt_adapter(self):
        adapter = self.adapter
        if (
            adapter is None
            or getattr(adapter, "receipt_contract_version", None)
            != PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION
            or not callable(getattr(adapter, "validate_presentation_receipt", None))
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE",
                "progressive presentation requires the exact trusted presentation-receipt contract",
            )
        return adapter


__all__ = ["ProgressivePresentationServices"]
