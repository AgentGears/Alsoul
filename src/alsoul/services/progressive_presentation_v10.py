from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.progressive_presentation import (
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    ProgressivePresentationSessionResult,
)
from alsoul.services.common import load_operation_receipt, request_digest, sha256_text
from alsoul.services.progressive_presentation_v8 import (
    ProgressivePresentationServices as ProgressivePresentationServicesV8,
)
from alsoul.storage import schema


_OPEN_SCOPE = "OpenProgressivePresentation"


class ProgressivePresentationServices(ProgressivePresentationServicesV8):
    """Current F6.A service with atomic session-open Timeline frontier capture.

    Session identity, deterministic frames, and the Timeline frontier that defines which
    later canonical counterpart inputs may interrupt are committed in one transaction.
    Recovery therefore never has to guess the original interrupt frontier.
    """

    def open_session(
        self, command: OpenProgressivePresentationCommand
    ) -> ProgressivePresentationSessionResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_OPEN_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    row = self._session(conn, replay["presentation_session_id"])
                    self._require_session_frontier(conn, row)
                    return self._session_result(conn, row)

                output = conn.execute(
                    select(schema.companion_output).where(
                        schema.companion_output.c.companion_output_id
                        == command.companion_output_id
                    )
                ).mappings().one_or_none()
                if output is None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_OUTPUT_NOT_FOUND",
                        "CompanionOutput does not exist",
                    )
                self._require_generic_progressive_eligibility(
                    conn, command.companion_output_id
                )
                self._require_route(
                    conn,
                    companion_person_id=output["companion_person_id"],
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                )
                if sha256_text(output["content_text"]) != output["content_digest"]:
                    fail(
                        "PROGRESSIVE_PRESENTATION_OUTPUT_DIGEST_MISMATCH",
                        "CompanionOutput content digest is invalid",
                    )

                target = conn.execute(
                    select(schema.output_target).where(
                        schema.output_target.c.output_target_id
                        == output["output_target_id"]
                    )
                ).mappings().one_or_none()
                source_event = None
                if target is not None and target["target_kind"] == "INTERACTION_EVENT":
                    source_event = conn.execute(
                        select(schema.interaction_event).where(
                            schema.interaction_event.c.event_id == target["target_ref"]
                        )
                    ).mappings().one_or_none()
                if (
                    target is None
                    or target["relationship_id"] != output["relationship_id"]
                    or target["target_kind"] != "INTERACTION_EVENT"
                    or source_event is None
                    or source_event["relationship_id"] != output["relationship_id"]
                    or source_event["surface_binding_id"] != command.surface_binding_id
                    or source_event["channel_binding_id"] != command.channel_binding_id
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_ROUTE_INVALID",
                        "progressive presentation must use the CompanionOutput's exact canonical interaction route",
                    )

                key = self._presentation_key(
                    command.companion_output_id,
                    command.surface_binding_id,
                    command.channel_binding_id,
                )
                existing = conn.execute(
                    select(schema.progressive_presentation_session).where(
                        schema.progressive_presentation_session.c.presentation_key == key
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    if (
                        existing["companion_output_id"] != command.companion_output_id
                        or existing["surface_binding_id"] != command.surface_binding_id
                        or existing["channel_binding_id"] != command.channel_binding_id
                        or existing["source_content_digest"] != output["content_digest"]
                        or existing["presentation_contract_version"]
                        != PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
                        or existing["frame_contract_version"]
                        != PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
                    ):
                        fail(
                            "PROGRESSIVE_PRESENTATION_SESSION_CONFLICT",
                            "presentation key resolves to conflicting durable lineage",
                        )
                    self._require_session_frontier(conn, existing)
                    self._save_open_receipt(conn, command, req, existing)
                    return self._session_result(conn, existing)

                existing_history = conn.execute(
                    select(schema.interaction_event.c.event_id)
                    .where(
                        schema.interaction_event.c.companion_output_id
                        == command.companion_output_id,
                        schema.interaction_event.c.event_kind
                        == "COMPANION_PRESENTED_OUTPUT",
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing_history is not None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_OUTPUT_ALREADY_PRESENTED",
                        "already-presented CompanionOutput cannot enter a new progressive presentation session",
                    )

                timeline = conn.execute(
                    select(schema.relationship_timeline_head).where(
                        schema.relationship_timeline_head.c.relationship_id
                        == output["relationship_id"]
                    )
                ).mappings().one_or_none()
                if timeline is None:
                    fail(
                        "RELATIONSHIP_NOT_FOUND",
                        "progressive presentation relationship Timeline head is missing",
                    )

                session_id = self.ids.new()
                now = self.clock.now()
                frames = self._render_frames(output["content_text"])
                conn.execute(
                    insert(schema.progressive_presentation_session).values(
                        presentation_session_id=session_id,
                        companion_output_id=command.companion_output_id,
                        relationship_id=output["relationship_id"],
                        surface_binding_id=command.surface_binding_id,
                        channel_binding_id=command.channel_binding_id,
                        presentation_key=key,
                        presentation_contract_version=PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
                        frame_contract_version=PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
                        source_content_digest=output["content_digest"],
                        opened_at=now,
                    )
                )
                for frame in frames:
                    conn.execute(
                        insert(schema.progressive_presentation_frame).values(
                            presentation_session_id=session_id,
                            **frame,
                        )
                    )
                conn.execute(
                    insert(schema.progressive_presentation_session_frontier).values(
                        presentation_session_id=session_id,
                        relationship_id=output["relationship_id"],
                        open_timeline_frontier=int(timeline["last_timeline_seq"]),
                        recorded_at=now,
                    )
                )
                row = self._session(conn, session_id)
                self._save_open_receipt(conn, command, req, row)
                return self._session_result(conn, row)
        except IntegrityError as exc:
            raise DomainError(
                "PROGRESSIVE_PRESENTATION_SESSION_CONFLICT",
                "progressive presentation session was created concurrently",
            ) from exc

    def _canonical_interrupt_event(self, conn, session, event_id):
        event = super()._canonical_interrupt_event(conn, session, event_id)
        frontier = self._require_session_frontier(conn, session)
        if int(event["timeline_seq"]) <= int(frontier["open_timeline_frontier"]):
            fail(
                "PROGRESSIVE_PRESENTATION_INTERRUPTION_EVENT_INVALID",
                "interrupting counterpart input must be canonically admitted after the presentation session opened",
            )
        return event

    @staticmethod
    def _require_session_frontier(conn, session):
        row = conn.execute(
            select(schema.progressive_presentation_session_frontier).where(
                schema.progressive_presentation_session_frontier.c.presentation_session_id
                == session["presentation_session_id"]
            )
        ).mappings().one_or_none()
        if (
            row is None
            or row["relationship_id"] != session["relationship_id"]
        ):
            fail(
                "PROGRESSIVE_PRESENTATION_SESSION_FRONTIER_REQUIRED",
                "progressive presentation session lacks its exact durable open Timeline frontier",
            )
        return row


__all__ = ["ProgressivePresentationServices"]
