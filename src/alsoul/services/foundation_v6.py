from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.commands import PresentCompanionOutputCommand
from alsoul.domain.errors import fail
from alsoul.domain.models import PresentCompanionOutputResult
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.services.foundation_v5 import FoundationServices as FoundationServicesV5
from alsoul.storage import schema


class FoundationServices(FoundationServicesV5):
    """Current foundation service with progressive-presentation Timeline truth guards.

    Generic complete presentation and progressive-session admission share one durable
    CompanionOutput write fence. Exactly one side can establish presentation ownership:
    an already-open progressive session blocks generic full presentation until exact
    terminal history exists, while an already-committed generic presentation blocks a
    later progressive session.
    """

    def present_companion_output(
        self, command: PresentCompanionOutputCommand
    ) -> PresentCompanionOutputResult:
        scope = "PresentCompanionOutput"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return PresentCompanionOutputResult(
                    UUID(replay["interaction_event_id"]),
                    int(replay["timeline_seq"]),
                    True,
                )

            output_fence = conn.execute(
                update(schema.companion_output)
                .where(
                    schema.companion_output.c.companion_output_id
                    == command.companion_output_id
                )
                .values(
                    companion_output_id=schema.companion_output.c.companion_output_id
                )
            )
            if output_fence.rowcount != 1:
                fail("COMPANION_OUTPUT_NOT_FOUND", "CompanionOutput does not exist")
            co = conn.execute(
                select(schema.companion_output).where(
                    schema.companion_output.c.companion_output_id
                    == command.companion_output_id
                )
            ).mappings().one()

            if self._companion_output_contains_personal_calendar(
                conn, command.companion_output_id
            ):
                fail(
                    "PERSONAL_CALENDAR_PRESENTATION_AUTHORITY_REQUIRED",
                    "personal-calendar CompanionOutput cannot use generic presentation before F5 disclosure authority succeeds",
                )

            self._validate_presence(
                conn,
                co["companion_person_id"],
                command.surface_binding_id,
                command.channel_binding_id,
            )

            session = conn.execute(
                select(schema.progressive_presentation_session)
                .where(
                    schema.progressive_presentation_session.c.companion_output_id
                    == command.companion_output_id
                )
                .limit(1)
            ).mappings().one_or_none()
            lineage = None
            if session is not None:
                if (
                    session["surface_binding_id"] != command.surface_binding_id
                    or session["channel_binding_id"] != command.channel_binding_id
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_ROUTE_INVALID",
                        "generic compatibility observation must use the progressive session's exact canonical route",
                    )
                lineage = conn.execute(
                    select(schema.progressive_presentation_timeline_lineage).where(
                        schema.progressive_presentation_timeline_lineage.c.presentation_session_id
                        == session["presentation_session_id"]
                    )
                ).mappings().one_or_none()
                if lineage is None:
                    fail(
                        "PROGRESSIVE_PRESENTATION_HISTORY_COMMIT_REQUIRED",
                        "progressive CompanionOutput requires exact terminal presentation history before generic Timeline presentation can be observed",
                    )

            existing = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.companion_output_id
                    == command.companion_output_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                if (
                    lineage is not None
                    and lineage["interaction_event_id"] != existing["event_id"]
                ):
                    fail(
                        "PROGRESSIVE_PRESENTATION_HISTORY_CONFLICT",
                        "progressive presentation lineage does not match canonical Timeline history",
                    )
                save_operation_receipt(
                    conn,
                    scope=scope,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="InteractionEvent",
                    result_ref=existing["event_id"],
                    result_json={
                        "interaction_event_id": str(existing["event_id"]),
                        "timeline_seq": existing["timeline_seq"],
                    },
                    committed_at=self.clock.now(),
                )
                return PresentCompanionOutputResult(
                    existing["event_id"], existing["timeline_seq"], True
                )

            if lineage is not None:
                fail(
                    "PROGRESSIVE_PRESENTATION_HISTORY_CONFLICT",
                    "progressive presentation lineage exists without its canonical Timeline event",
                )

            target = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.output_target_id == co["output_target_id"]
                )
            ).mappings().one()

            timeline_fence = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == co["relationship_id"]
                )
                .values(
                    last_timeline_seq=schema.relationship_timeline_head.c.last_timeline_seq
                )
            )
            if timeline_fence.rowcount != 1:
                fail(
                    "RELATIONSHIP_NOT_FOUND",
                    "relationship Timeline head is missing",
                )
            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == co["relationship_id"]
                )
            ).mappings().one()
            next_seq = int(timeline["last_timeline_seq"]) + 1
            event_id = self.ids.new()
            recorded_at = self.clock.now()
            conn.execute(
                insert(schema.interaction_event).values(
                    event_id=event_id,
                    relationship_id=co["relationship_id"],
                    timeline_seq=next_seq,
                    actor_kind="COMPANION",
                    actor_ref=co["companion_person_id"],
                    event_kind="COMPANION_PRESENTED_OUTPUT",
                    content_text=co["content_text"],
                    occurred_at=command.presented_at,
                    recorded_at=recorded_at,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                    companion_output_id=command.companion_output_id,
                    reply_to_event_id=target["target_ref"],
                )
            )
            updated = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == co["relationship_id"],
                    schema.relationship_timeline_head.c.last_timeline_seq
                    == timeline["last_timeline_seq"],
                )
                .values(last_timeline_seq=next_seq)
            )
            if updated.rowcount != 1:
                fail(
                    "TIMELINE_SEQUENCE_CONFLICT",
                    "relationship Timeline advanced concurrently",
                )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="InteractionEvent",
                result_ref=event_id,
                result_json={
                    "interaction_event_id": str(event_id),
                    "timeline_seq": next_seq,
                },
                committed_at=recorded_at,
            )
            return PresentCompanionOutputResult(event_id, next_seq)


__all__ = ["FoundationServices"]
