from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alsoul.domain.commands import (
    AdoptCompanionOutputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    PresentCompanionOutputCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.errors import fail
from alsoul.services.foundation_v4 import FoundationServices as FoundationServicesV4
from alsoul.storage import schema


class FoundationServices(FoundationServicesV4):
    """Current foundation service with F5 personal-calendar generic-path guards.

    F4 generic projection/generation/adoption/presentation remains available for F4
    material. Personal-calendar state must use the specialized F5 services because its
    freshness, model-egress, deterministic-adoption, and first-presentation authority
    contracts are stronger than the generic F4 boundaries.
    """

    def _projection_contains_personal_calendar(self, conn, projection_id: UUID) -> bool:
        specialized = conn.execute(
            select(schema.personal_calendar_context_projection.c.projection_id).where(
                schema.personal_calendar_context_projection.c.projection_id == projection_id
            )
        ).scalar_one_or_none()
        if specialized is not None:
            return True
        return (
            conn.execute(
                select(schema.context_projection_world_item.c.world_result_id)
                .join(
                    schema.personal_calendar_world_result,
                    schema.context_projection_world_item.c.world_result_id
                    == schema.personal_calendar_world_result.c.world_result_id,
                )
                .where(
                    schema.context_projection_world_item.c.projection_id == projection_id
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def _generated_output_contains_personal_calendar(
        self, conn, generated_output_id: UUID
    ) -> bool:
        projection_id = conn.execute(
            select(schema.model_invocation.c.context_projection_id)
            .join(
                schema.generated_output,
                schema.generated_output.c.model_invocation_id
                == schema.model_invocation.c.model_invocation_id,
            )
            .where(schema.generated_output.c.generated_output_id == generated_output_id)
        ).scalar_one_or_none()
        return (
            projection_id is not None
            and self._projection_contains_personal_calendar(conn, projection_id)
        )

    def _companion_output_contains_personal_calendar(
        self, conn, companion_output_id: UUID
    ) -> bool:
        specialized = conn.execute(
            select(schema.personal_calendar_companion_output.c.companion_output_id).where(
                schema.personal_calendar_companion_output.c.companion_output_id
                == companion_output_id
            )
        ).scalar_one_or_none()
        if specialized is not None:
            return True
        generated_output_id = conn.execute(
            select(schema.companion_output.c.source_generated_output_id).where(
                schema.companion_output.c.companion_output_id == companion_output_id
            )
        ).scalar_one_or_none()
        return (
            generated_output_id is not None
            and self._generated_output_contains_personal_calendar(
                conn, generated_output_id
            )
        )

    def build_context_projection(self, command: BuildContextProjectionCommand):
        if command.required_world_result_ids:
            with self.engine.connect() as conn:
                personal = conn.execute(
                    select(schema.personal_calendar_world_result.c.world_result_id)
                    .where(
                        schema.personal_calendar_world_result.c.world_result_id.in_(
                            command.required_world_result_ids
                        )
                    )
                    .limit(1)
                ).scalar_one_or_none()
            if personal is not None:
                fail(
                    "PERSONAL_CALENDAR_SPECIALIZED_PROJECTION_REQUIRED",
                    "personal-calendar results require the F5 current-freshness projection boundary",
                )
        return super().build_context_projection(command)

    def render_provider_context(self, projection_id: UUID):
        with self.engine.connect() as conn:
            if self._projection_contains_personal_calendar(conn, projection_id):
                fail(
                    "PERSONAL_CALENDAR_SPECIALIZED_RENDERER_REQUIRED",
                    "personal-calendar projections require the minimized F5 model renderer",
                )
        return super().render_provider_context(projection_id)

    def start_model_invocation(self, command: StartModelInvocationCommand):
        with self.engine.connect() as conn:
            if self._projection_contains_personal_calendar(
                conn, command.context_projection_id
            ):
                fail(
                    "PERSONAL_CALENDAR_MODEL_EGRESS_REQUIRED",
                    "personal-calendar model transport requires a fresh F5 exact-route egress decision",
                )
        return super().start_model_invocation(command)

    def complete_model_invocation(self, command: CompleteModelInvocationCommand):
        with self.engine.connect() as conn:
            projection_id = conn.execute(
                select(schema.model_invocation.c.context_projection_id).where(
                    schema.model_invocation.c.model_invocation_id
                    == command.model_invocation_id
                )
            ).scalar_one_or_none()
            if (
                projection_id is not None
                and self._projection_contains_personal_calendar(conn, projection_id)
            ):
                fail(
                    "PERSONAL_CALENDAR_STRUCTURED_GENERATION_REQUIRED",
                    "personal-calendar generation must use the bounded F5 schedule-plan completion boundary",
                )
        return super().complete_model_invocation(command)

    def adopt_companion_output(self, command: AdoptCompanionOutputCommand):
        with self.engine.connect() as conn:
            if self._generated_output_contains_personal_calendar(
                conn, command.generated_output_id
            ):
                fail(
                    "PERSONAL_CALENDAR_DETERMINISTIC_ADOPTION_REQUIRED",
                    "personal-calendar GeneratedOutput requires F5 mechanical plan validation and deterministic adoption",
                )
        return super().adopt_companion_output(command)

    def present_companion_output(self, command: PresentCompanionOutputCommand):
        with self.engine.connect() as conn:
            if self._companion_output_contains_personal_calendar(
                conn, command.companion_output_id
            ):
                fail(
                    "PERSONAL_CALENDAR_PRESENTATION_AUTHORITY_REQUIRED",
                    "personal-calendar CompanionOutput cannot use generic presentation before F5 disclosure authority succeeds",
                )
        return super().present_companion_output(command)


__all__ = ["FoundationServices"]
