from __future__ import annotations

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.services.calendar_runtime_recovery import operation_id
from alsoul.storage import schema

_MAX_RUNTIME_OBSERVATION_GENERATIONS = 64


def select_observation_generation(engine, source_event_id) -> int:
    """Reuse open/succeeded coordinator state; advance only after terminal failure."""

    with engine.connect() as conn:
        for generation in range(1, _MAX_RUNTIME_OBSERVATION_GENERATIONS + 1):
            op_id = operation_id(source_event_id, f"observation:{generation}")
            receipt = conn.execute(
                select(schema.operation_receipt.c.result_ref).where(
                    schema.operation_receipt.c.operation_scope == "StartObservation",
                    schema.operation_receipt.c.operation_id == op_id,
                )
            ).scalar_one_or_none()
            if receipt is None:
                return generation
            observation = conn.execute(
                select(schema.observation.c.status).where(
                    schema.observation.c.observation_id == receipt
                )
            ).scalar_one_or_none()
            if observation is None:
                fail(
                    "PERSONAL_CALENDAR_RUNTIME_OBSERVATION_INCOMPLETE",
                    "calendar runtime receipt points to a missing Observation",
                )
            if observation in {"STARTED", "SUCCEEDED"}:
                return generation
            if observation != "FAILED":
                fail(
                    "PERSONAL_CALENDAR_RUNTIME_OBSERVATION_STATE_INVALID",
                    "calendar runtime Observation has an unsupported recovery state",
                )
    fail(
        "PERSONAL_CALENDAR_RUNTIME_RETRY_LIMIT",
        "calendar interaction exceeded the bounded Observation recovery generations",
    )


__all__ = ["select_observation_generation"]
