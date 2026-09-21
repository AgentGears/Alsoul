from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    OpenProgressivePresentationCommand,
    ProgressivePresentationFrameDispatchResult,
    ProgressivePresentationSessionResult,
)
from alsoul.domain.errors import fail
from alsoul.services.progressive_presentation import (
    ProgressivePresentationServices as ProgressivePresentationServicesV1,
)
from alsoul.storage import schema


_GOVERNED_ORIGIN_KINDS = frozenset(
    {
        "PERSONAL_CALENDAR_SCHEDULE",
        "PERSONAL_CALENDAR_MUTATION_RESULT",
    }
)


class ProgressivePresentationServices(ProgressivePresentationServicesV1):
    """Current F6.A core with inherited F5 disclosure authority preserved.

    This bounded increment does not yet implement the per-frame F5 freshness and
    disclosure re-evaluation required for personal-calendar payloads. Until that
    specialized integration exists, those governed outputs fail closed at both session
    admission and frame dispatch rather than acquiring a generic progressive path.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        with self.engine.connect() as conn:
            self._require_generic_progressive_eligibility(
                conn, command.companion_output_id
            )
        return super().open_session(command)

    def dispatch_frame(
        self, command: DispatchProgressivePresentationFrameCommand
    ) -> ProgressivePresentationFrameDispatchResult:
        with self.engine.connect() as conn:
            companion_output_id = conn.execute(
                select(schema.progressive_presentation_session.c.companion_output_id)
                .join(
                    schema.progressive_presentation_attempt,
                    schema.progressive_presentation_attempt.c.presentation_session_id
                    == schema.progressive_presentation_session.c.presentation_session_id,
                )
                .where(
                    schema.progressive_presentation_attempt.c.presentation_attempt_id
                    == command.presentation_attempt_id
                )
            ).scalar_one_or_none()
            if companion_output_id is not None:
                self._require_generic_progressive_eligibility(
                    conn, companion_output_id
                )
        return super().dispatch_frame(command)

    @staticmethod
    def _require_generic_progressive_eligibility(
        conn, companion_output_id: UUID
    ) -> None:
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id == companion_output_id
            )
        ).mappings().one_or_none()
        if output is None:
            return

        personal_schedule = conn.execute(
            select(schema.personal_calendar_companion_output.c.companion_output_id).where(
                schema.personal_calendar_companion_output.c.companion_output_id
                == companion_output_id
            )
        ).scalar_one_or_none()
        mutation_result = conn.execute(
            select(schema.personal_calendar_mutation_adoption.c.companion_output_id).where(
                schema.personal_calendar_mutation_adoption.c.companion_output_id
                == companion_output_id
            )
        ).scalar_one_or_none()

        if (
            output["origin_kind"] in _GOVERNED_ORIGIN_KINDS
            or personal_schedule is not None
            or mutation_result is not None
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_SPECIALIZED_AUTHORITY_REQUIRED",
                "F5-governed personal-calendar output requires current per-frame authority before progressive payload transport",
            )


__all__ = ["ProgressivePresentationServices"]
