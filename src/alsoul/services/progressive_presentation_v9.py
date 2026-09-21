from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    OpenProgressivePresentationCommand,
    ProgressivePresentationSessionResult,
)
from alsoul.services.progressive_presentation_v8 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV8,
)
from alsoul.storage import schema


class ProgressivePresentationServices(ProgressivePresentationServicesV8):
    """Current F6.A service with a durable session-open Timeline frontier.

    Canonical counterpart input can interrupt a generation only when the input was
    admitted *after* that presentation session became active. The frontier is captured
    before session admission and then durably bound to the session. Existing pre-v20
    sessions can acquire a conservative current frontier when reopened; this can reject
    an otherwise valid historical interrupt but cannot promote an older input into a
    false interruption.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        with self.engine.connect() as conn:
            output = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == command.companion_output_id
                )
            ).mappings().one_or_none()
            if output is None:
                # Preserve the established error and validation order in the parent.
                return super().open_session(command)
            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == output["relationship_id"]
                )
            ).mappings().one()
            captured_frontier = int(timeline["last_timeline_seq"])
            relationship_id = output["relationship_id"]

        result = super().open_session(command)
        try:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    select(schema.progressive_presentation_session_frontier).where(
                        schema.progressive_presentation_session_frontier.c.presentation_session_id
                        == result.presentation_session_id
                    )
                ).mappings().one_or_none()
                if existing is None:
                    conn.execute(
                        insert(schema.progressive_presentation_session_frontier).values(
                            presentation_session_id=result.presentation_session_id,
                            relationship_id=relationship_id,
                            open_timeline_frontier=captured_frontier,
                            recorded_at=self.clock.now(),
                        )
                    )
                elif existing["relationship_id"] != relationship_id:
                    fail(
                        "PROGRESSIVE_PRESENTATION_SESSION_FRONTIER_CONFLICT",
                        "presentation session frontier belongs to another relationship",
                    )
        except IntegrityError as exc:
            with self.engine.connect() as conn:
                existing = conn.execute(
                    select(schema.progressive_presentation_session_frontier).where(
                        schema.progressive_presentation_session_frontier.c.presentation_session_id
                        == result.presentation_session_id
                    )
                ).mappings().one_or_none()
            if existing is None or existing["relationship_id"] != relationship_id:
                raise DomainError(
                    "PROGRESSIVE_PRESENTATION_SESSION_FRONTIER_CONFLICT",
                    "presentation session frontier conflicted with durable state",
                ) from exc
        return result

    def _canonical_interrupt_event(self, conn, session, event_id):
        event = super()._canonical_interrupt_event(conn, session, event_id)
        frontier = conn.execute(
            select(schema.progressive_presentation_session_frontier).where(
                schema.progressive_presentation_session_frontier.c.presentation_session_id
                == session["presentation_session_id"]
            )
        ).mappings().one_or_none()
        if frontier is None:
            fail(
                "PROGRESSIVE_PRESENTATION_SESSION_FRONTIER_REQUIRED",
                "canonical interruption requires the durable session-open Timeline frontier",
            )
        if (
            frontier["relationship_id"] != session["relationship_id"]
            or int(event["timeline_seq"]) <= int(frontier["open_timeline_frontier"])
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_EVENT_INVALID",
                "interrupting counterpart input must be canonically admitted after the presentation session opened",
            )
        return event


__all__ = ["ProgressivePresentationServices"]
