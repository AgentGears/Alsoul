from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import (
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    RecordProgressivePresentationReceiptCommand,
)
from alsoul.services import ProgressivePresentationServices
from alsoul.storage import schema


class _ReceiptAdapter:
    presentation_contract_version = PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    frame_contract_version = PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    transport_contract_version = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION
    receipt_contract_version = PROGRESSIVE_PRESENTATION_RECEIPT_CONTRACT_VERSION

    def __init__(self, *, validation_result=False, validation_error=None):
        self.validation_result = validation_result
        self.validation_error = validation_error
        self.receipt_calls: list[dict] = []

    def dispatch_frame(self, **_kwargs):
        raise AssertionError("receipt trust tests must not dispatch payload")

    def validate_presentation_receipt(self, **kwargs):
        self.receipt_calls.append(dict(kwargs))
        if self.validation_error is not None:
            raise self.validation_error
        return self.validation_result


def _command(now):
    return RecordProgressivePresentationReceiptCommand(
        operation_id=uuid4(),
        presentation_session_id=uuid4(),
        presentation_attempt_id=uuid4(),
        presentation_key="presentation-key",
        attempt_generation=1,
        presentation_transport_fence_scope_id=uuid4(),
        frame_ordinal=1,
        frame_digest="a" * 64,
        presentation_receipt_ref="sink-receipt-1",
        presented_at=now,
    )


def _evidence_count(engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(func.count()).select_from(
                    schema.progressive_presentation_frame_evidence
                )
            ).scalar_one()
        )


def test_unvalidated_receipt_cannot_become_presentation_evidence(engine, services, now):
    adapter = _ReceiptAdapter(validation_result=False)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    command = _command(now)

    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(command)

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED"
    assert len(adapter.receipt_calls) == 1
    call = adapter.receipt_calls[0]
    assert call["presentation_key"] == command.presentation_key
    assert call["presentation_session_id"] == command.presentation_session_id
    assert call["presentation_attempt_id"] == command.presentation_attempt_id
    assert call["presentation_transport_fence_scope_id"] == (
        command.presentation_transport_fence_scope_id
    )
    assert call["frame_ordinal"] == command.frame_ordinal
    assert call["frame_digest"] == command.frame_digest
    assert call["presentation_receipt_ref"] == command.presentation_receipt_ref
    assert _evidence_count(engine) == 0


def test_receipt_validator_failure_fails_closed(engine, services, now):
    adapter = _ReceiptAdapter(validation_error=RuntimeError("sink validation unavailable"))
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )

    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(_command(now))

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_RECEIPT_UNTRUSTED"
    assert _evidence_count(engine) == 0


def test_exact_receipt_adapter_contract_is_required(engine, services, now):
    adapter = _ReceiptAdapter(validation_result=True)
    adapter.receipt_contract_version = "unsupported-receipt-contract"
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )

    with pytest.raises(DomainError) as exc:
        service.record_presentation_receipt(_command(now))

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ADAPTER_INELIGIBLE"
    assert adapter.receipt_calls == []
    assert _evidence_count(engine) == 0
