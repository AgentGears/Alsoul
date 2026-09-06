from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine, select

from alsoul.storage import schema

RecoveryStage = Literal[
    "INPUT_ADMITTED",
    "PROJECTION_READY",
    "GENERATED",
    "ADOPTED",
    "PRESENTED",
]


@dataclass(frozen=True, slots=True)
class ResponseRecoveryAssessment:
    stage: RecoveryStage
    current_input_event_id: UUID
    output_target_id: UUID | None = None
    reusable_projection_id: UUID | None = None
    reusable_generated_output_id: UUID | None = None
    adopted_output_id: UUID | None = None
    presented_event_id: UUID | None = None


class RecoveryCoordinator:
    """Derives response progress from canonical rows; persists no turn-status aggregate."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def assess_response(self, *, relationship_id: UUID, current_input_event_id: UUID) -> ResponseRecoveryAssessment:
        with self.engine.connect() as conn:
            target = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.relationship_id == relationship_id,
                    schema.output_target.c.target_kind == "INTERACTION_EVENT",
                    schema.output_target.c.target_ref == current_input_event_id,
                    schema.output_target.c.purpose == "FINAL_RESPONSE",
                )
            ).mappings().one_or_none()
            if target is not None:
                co = conn.execute(
                    select(schema.companion_output).where(
                        schema.companion_output.c.output_target_id == target["output_target_id"]
                    )
                ).mappings().one_or_none()
                if co is not None:
                    event = conn.execute(
                        select(schema.interaction_event).where(
                            schema.interaction_event.c.companion_output_id == co["companion_output_id"]
                        )
                    ).mappings().one_or_none()
                    if event is not None:
                        return ResponseRecoveryAssessment(
                            "PRESENTED",
                            current_input_event_id,
                            target["output_target_id"],
                            adopted_output_id=co["companion_output_id"],
                            presented_event_id=event["event_id"],
                        )
                    return ResponseRecoveryAssessment(
                        "ADOPTED",
                        current_input_event_id,
                        target["output_target_id"],
                        adopted_output_id=co["companion_output_id"],
                    )
            projections = conn.execute(
                select(schema.context_projection)
                .where(
                    schema.context_projection.c.relationship_id == relationship_id,
                    schema.context_projection.c.current_input_event_id == current_input_event_id,
                    schema.context_projection.c.purpose == "RESPOND_TO_INTERACTION",
                )
                .order_by(schema.context_projection.c.created_at.desc())
            ).mappings().all()
            for cp in projections:
                mi_rows = conn.execute(
                    select(schema.model_invocation)
                    .where(schema.model_invocation.c.context_projection_id == cp["projection_id"])
                    .order_by(schema.model_invocation.c.started_at.desc())
                ).mappings().all()
                for mi in mi_rows:
                    if mi["outcome"] == "SUCCEEDED":
                        g = conn.execute(
                            select(schema.generated_output).where(
                                schema.generated_output.c.model_invocation_id == mi["model_invocation_id"]
                            )
                        ).mappings().one_or_none()
                        if g is not None:
                            return ResponseRecoveryAssessment(
                                "GENERATED",
                                current_input_event_id,
                                target["output_target_id"] if target else None,
                                reusable_projection_id=cp["projection_id"],
                                reusable_generated_output_id=g["generated_output_id"],
                            )
                return ResponseRecoveryAssessment(
                    "PROJECTION_READY",
                    current_input_event_id,
                    target["output_target_id"] if target else None,
                    reusable_projection_id=cp["projection_id"],
                )
            return ResponseRecoveryAssessment(
                "INPUT_ADMITTED",
                current_input_event_id,
                target["output_target_id"] if target else None,
            )
