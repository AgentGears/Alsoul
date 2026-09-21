from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import PresentCompanionOutputCommand
from alsoul.domain.errors import DomainError
from alsoul.domain.progressive_presentation import CommitProgressivePresentationHistoryCommand
from alsoul.storage import schema
from test_f6a_progressive_presentation_interruption_history import (
    _append_interrupt,
    _interrupt,
    _setup,
    _settle_terminal,
)


def test_zero_extent_history_is_distinct_from_pending_history_commit(
    services, bootstrapper, engine, now
):
    ctx, adapter, service, _session, attempt = _setup(
        services, bootstrapper, engine, now, "never presented"
    )
    canonical = _append_interrupt(services, ctx, now)
    _interrupt(service, attempt, canonical.event_id)
    _settle_terminal(
        service,
        adapter,
        attempt,
        presented=0,
        received=0,
        suffix="zero-finalized",
    )
    history = service.commit_presentation_history(
        CommitProgressivePresentationHistoryCommand(
            operation_id=uuid4(),
            presentation_attempt_id=attempt.presentation_attempt_id,
        )
    )
    assert history.interaction_event_id is None
    assert history.last_presented_frame == 0

    with pytest.raises(DomainError) as exc:
        services.present_companion_output(
            PresentCompanionOutputCommand(
                operation_id=uuid4(),
                companion_output_id=ctx["adopted"].companion_output_id,
                surface_binding_id=ctx["ids"].surface_binding_id,
                channel_binding_id=ctx["ids"].channel_binding_id,
                presented_at=now,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_ZERO_EXTENT_FINALIZED"

    with engine.connect() as conn:
        presented_events = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(
                schema.interaction_event.c.companion_output_id
                == ctx["adopted"].companion_output_id,
                schema.interaction_event.c.event_kind
                == "COMPANION_PRESENTED_OUTPUT",
            )
        ).scalar_one()
        marker = conn.execute(
            select(schema.operation_receipt.c.operation_id).where(
                schema.operation_receipt.c.operation_scope
                == "CommitProgressivePresentationHistory",
                schema.operation_receipt.c.result_kind
                == "ProgressivePresentationHistoryNoEvent",
                schema.operation_receipt.c.result_ref
                == history.presentation_session_id,
            )
        ).scalar_one_or_none()
    assert int(presented_events) == 0
    assert marker is not None
