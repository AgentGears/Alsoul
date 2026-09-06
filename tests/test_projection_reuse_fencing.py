from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import (
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.storage import schema


def test_reactive_projection_for_non_frontier_input_cannot_start_provider_attempt(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="projection-frontier",
        external_subject=str(uuid4()),
    )
    old_input = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "old-input",
            "First question.",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )
    services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "new-input",
            "Second question.",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )

    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            old_input.event_id,
            (),
            (),
        )
    )

    with pytest.raises(DomainError) as excinfo:
        services.start_model_invocation(
            StartModelInvocationCommand(
                uuid4(),
                projection.projection_id,
                "configured-route",
                "configured-model",
                "f4-renderer-v1",
                "0" * 64,
            )
        )
    assert excinfo.value.code == "CONTEXT_PROJECTION_NOT_REUSABLE"
    assert "CURRENT_INPUT_NOT_AT_FRONTIER" in excinfo.value.message

    with services.engine.connect() as conn:
        invocation_count = conn.execute(
            select(func.count()).select_from(schema.model_invocation)
        ).scalar_one()
    assert invocation_count == 0
