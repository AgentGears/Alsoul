from __future__ import annotations

from dataclasses import replace

import pytest

from alsoul.domain.errors import DomainError
from test_f6a_progressive_presentation_core import _receipt_command
from test_f6a_progressive_presentation_reconciliation import (
    _reception_command,
    _setup_one_frame,
)


def test_reception_rejects_cross_generation_lineage_before_sink_validation(
    services, bootstrapper, engine, now
):
    service, adapter, session, attempt, frame = _setup_one_frame(
        services, bootstrapper, engine, now
    )
    service.record_presentation_receipt(_receipt_command(session, attempt, frame, now))
    command = _reception_command(session, attempt, now)

    with pytest.raises(DomainError) as exc:
        service.record_reception_receipt(
            replace(command, attempt_generation=attempt.attempt_generation + 1)
        )

    assert exc.value.code == "PROGRESSIVE_PRESENTATION_RECEPTION_LINEAGE_INVALID"
    assert adapter.reception_calls == []
