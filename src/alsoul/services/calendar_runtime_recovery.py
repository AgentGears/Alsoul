from __future__ import annotations

from uuid import UUID, uuid5

from sqlalchemy import select

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_cognition import (
    GeneratePersonalCalendarAnswerPlanCommand,
    PersonalCalendarGenerationResult,
)
from alsoul.domain.personal_calendar_presentation import (
    PresentPersonalCalendarOutputCommand,
    RecoverPersonalCalendarPresentationCommand,
)
from alsoul.storage import schema

_RUNTIME_NAMESPACE = UUID("c6019051-a97b-4fea-85b4-17a74c12cb47")


def operation_id(source_event_id: UUID, stage: str) -> UUID:
    return uuid5(_RUNTIME_NAMESPACE, f"{source_event_id}:{stage}")


def generate_or_recover(
    engine,
    cognition,
    *,
    source_event_id: UUID,
    projection_id: UUID,
    permission_provider,
    route_provider,
) -> PersonalCalendarGenerationResult:
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                schema.personal_calendar_model_invocation.c.model_invocation_id,
                schema.personal_calendar_model_invocation.c.egress_decision_id,
                schema.model_invocation.c.outcome,
            )
            .join(
                schema.model_invocation,
                schema.personal_calendar_model_invocation.c.model_invocation_id
                == schema.model_invocation.c.model_invocation_id,
            )
            .where(
                schema.personal_calendar_model_invocation.c.projection_id
                == projection_id
            )
        ).mappings().all()
        succeeded = [row for row in rows if row["outcome"] == "SUCCEEDED"]
        if len(succeeded) > 1:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_GENERATION_AMBIGUOUS",
                "calendar projection has multiple successful model generations",
            )
        if succeeded:
            row = succeeded[0]
            generated = conn.execute(
                select(schema.generated_output.c.generated_output_id).where(
                    schema.generated_output.c.model_invocation_id
                    == row["model_invocation_id"]
                )
            ).scalar_one_or_none()
            if generated is None:
                fail(
                    "PERSONAL_CALENDAR_RUNTIME_GENERATION_INCOMPLETE",
                    "successful calendar model invocation lacks durable GeneratedOutput",
                )
            return PersonalCalendarGenerationResult(
                row["model_invocation_id"], generated, row["egress_decision_id"]
            )
        if any(row["outcome"] == "IN_PROGRESS" for row in rows):
            fail(
                "CALENDAR_MODEL_INVOCATION_RECOVERY_REQUIRED",
                "an unresolved personal-calendar model transport must be reconciled before retry",
            )
        generation = len(rows) + 1

    return cognition.generate_answer_plan(
        GeneratePersonalCalendarAnswerPlanCommand(
            operation_id=operation_id(source_event_id, f"generate:{generation}"),
            projection_id=projection_id,
            permission_id=permission_provider(),
            route_binding_id=route_provider(),
        )
    )


def present_or_recover(
    engine,
    presentation,
    *,
    source_event_id: UUID,
    companion_output_id: UUID,
    permission_provider,
    surface_binding_id: UUID,
    channel_binding_id: UUID,
):
    recover = RecoverPersonalCalendarPresentationCommand(
        companion_output_id=companion_output_id,
        surface_binding_id=surface_binding_id,
        channel_binding_id=channel_binding_id,
    )
    with engine.connect() as conn:
        latest = conn.execute(
            select(schema.personal_calendar_presentation_attempt)
            .where(
                schema.personal_calendar_presentation_attempt.c.companion_output_id
                == companion_output_id
            )
            .order_by(
                schema.personal_calendar_presentation_attempt.c.presentation_attempt_generation.desc()
            )
            .limit(1)
        ).mappings().one_or_none()

    if latest is not None and latest["sink_acceptance_state"] in {"UNKNOWN", "ACCEPTED"}:
        reconciled = presentation.recover_presentation(recover)
        if reconciled.state != "NOT_ACCEPTED":
            return reconciled
        generation = reconciled.presentation_attempt_generation + 1
    elif latest is not None:
        generation = int(latest["presentation_attempt_generation"]) + 1
    else:
        generation = 1

    try:
        return presentation.present_output(
            PresentPersonalCalendarOutputCommand(
                operation_id=operation_id(source_event_id, f"present:{generation}"),
                companion_output_id=companion_output_id,
                permission_id=permission_provider(),
                surface_binding_id=surface_binding_id,
                channel_binding_id=channel_binding_id,
            )
        )
    except DomainError as exc:
        if exc.code != "CALENDAR_PRESENTATION_OUTCOME_UNKNOWN":
            raise
        return presentation.recover_presentation(recover)


__all__ = ["generate_or_recover", "operation_id", "present_or_recover"]
