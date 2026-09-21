from __future__ import annotations

from sqlalchemy import select

from alsoul.domain.commands import PresentCompanionOutputCommand
from alsoul.domain.errors import fail
from alsoul.services.foundation_v5 import FoundationServices as FoundationServicesV5
from alsoul.storage import schema


class FoundationServices(FoundationServicesV5):
    """Current foundation service with progressive-presentation Timeline truth guards.

    Once a CompanionOutput has entered a progressive presentation session, generic F4
    presentation may not fabricate a full ``COMPANION_PRESENTED_OUTPUT`` event. The F6
    history-commit boundary must first record the exact terminal presented extent. After
    that lineage exists, the established generic presentation call remains an idempotent
    compatibility read of the already-canonical event.
    """

    def present_companion_output(self, command: PresentCompanionOutputCommand):
        with self.engine.connect() as conn:
            session_id = conn.execute(
                select(schema.progressive_presentation_session.c.presentation_session_id)
                .where(
                    schema.progressive_presentation_session.c.companion_output_id
                    == command.companion_output_id
                )
                .limit(1)
            ).scalar_one_or_none()
            if session_id is not None:
                lineage = conn.execute(
                    select(
                        schema.progressive_presentation_timeline_lineage.c.interaction_event_id
                    ).where(
                        schema.progressive_presentation_timeline_lineage.c.presentation_session_id
                        == session_id
                    )
                ).scalar_one_or_none()
                if lineage is None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_HISTORY_COMMIT_REQUIRED",
                        "progressive CompanionOutput requires exact terminal presentation history before generic Timeline presentation can be observed",
                    )
        return super().present_companion_output(command)


__all__ = ["FoundationServices"]
