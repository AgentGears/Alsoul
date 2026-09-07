from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.errors import fail
from alsoul.services.conversation_open_loop_context import classify_open_loop_directive
from alsoul.services.foundation import FoundationServices as BaseFoundationServices
from alsoul.storage import schema

OpenLoopDisposition = Literal[
    "NO_ACTION",
    "OPENED",
    "RESOLVED",
    "CANCELLED",
]


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopResult:
    source_event_id: UUID
    disposition: OpenLoopDisposition
    open_loop_id: UUID | None = None
    loop_kind: str | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopSelection:
    open_loop_id: UUID
    relationship_id: UUID
    loop_kind: str
    opened_by_event_id: UUID


class F4ConversationOpenLoopService:
    """Persist the bounded F4 unresolved conversational dependency.

    ConversationOpenLoop is relationship-scoped state, not a remembered proposition,
    delegated task, commitment, trigger, or authority grant. Opening and terminal
    closure are append-only rows. Currentness is derived from the absence of a closure;
    no mutable status field exists.
    """

    def __init__(self, services: BaseFoundationServices) -> None:
        self.services = services

    def consider_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.connect() as conn:
            event, _relationship = self._load_source(conn, source_event_id)
        directive = classify_open_loop_directive(event["content_text"])
        if directive == "OPEN":
            return self._open_from_event(source_event_id)
        if directive == "RESOLVE":
            return self._close_from_event(source_event_id, "RESOLVED")
        if directive == "CANCEL":
            return self._close_from_event(source_event_id, "CANCELLED")
        return F4ConversationOpenLoopResult(
            source_event_id=source_event_id,
            disposition="NO_ACTION",
        )

    def select_current_decision_loop(
        self, relationship_id: UUID
    ) -> F4ConversationOpenLoopSelection:
        with self.services.engine.connect() as conn:
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id == relationship_id
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "open-loop relationship does not exist")
            rows = self._active_loops(
                conn,
                relationship_id=relationship_id,
                loop_kind="DECISION",
            )
        if not rows:
            fail(
                "CONVERSATION_OPEN_LOOP_UNAVAILABLE",
                "no unresolved decision loop exists in this relationship",
            )
        if len(rows) != 1:
            fail(
                "CONVERSATION_OPEN_LOOP_AMBIGUOUS",
                "multiple unresolved decision loops exist; bounded reference resolution fails closed",
            )
        row = rows[0]
        return F4ConversationOpenLoopSelection(
            open_loop_id=row["open_loop_id"],
            relationship_id=row["relationship_id"],
            loop_kind=row["loop_kind"],
            opened_by_event_id=row["opened_by_event_id"],
        )

    def _open_from_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])

            existing = conn.execute(
                select(schema.conversation_open_loop).where(
                    schema.conversation_open_loop.c.opened_by_event_id == source_event_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="OPENED",
                    open_loop_id=existing["open_loop_id"],
                    loop_kind=existing["loop_kind"],
                    idempotent_replay=True,
                )

            if classify_open_loop_directive(event["content_text"]) != "OPEN":
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_MISMATCH",
                    "canonical source no longer matches the bounded open-loop opening grammar",
                )

            open_loop_id = self.services.ids.new()
            conn.execute(
                insert(schema.conversation_open_loop).values(
                    open_loop_id=open_loop_id,
                    relationship_id=relationship["relationship_id"],
                    loop_kind="DECISION",
                    opened_by_event_id=source_event_id,
                    opened_at=self.services.clock.now(),
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition="OPENED",
                open_loop_id=open_loop_id,
                loop_kind="DECISION",
            )

    def _close_from_event(
        self,
        source_event_id: UUID,
        closure_kind: Literal["RESOLVED", "CANCELLED"],
    ) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])

            replay = conn.execute(
                select(
                    schema.conversation_open_loop_closure,
                    schema.conversation_open_loop.c.relationship_id,
                    schema.conversation_open_loop.c.loop_kind,
                )
                .join(
                    schema.conversation_open_loop,
                    schema.conversation_open_loop_closure.c.open_loop_id
                    == schema.conversation_open_loop.c.open_loop_id,
                )
                .where(
                    schema.conversation_open_loop_closure.c.source_event_id
                    == source_event_id
                )
            ).mappings().one_or_none()
            if replay is not None:
                if (
                    replay["relationship_id"] != relationship["relationship_id"]
                    or replay["closure_kind"] != closure_kind
                ):
                    fail(
                        "CONVERSATION_OPEN_LOOP_CLOSURE_CONFLICT",
                        "closure source event is already bound to a different loop transition",
                    )
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition=(
                        "RESOLVED" if closure_kind == "RESOLVED" else "CANCELLED"
                    ),
                    open_loop_id=replay["open_loop_id"],
                    loop_kind=replay["loop_kind"],
                    idempotent_replay=True,
                )

            expected_directive = (
                "RESOLVE" if closure_kind == "RESOLVED" else "CANCEL"
            )
            if classify_open_loop_directive(event["content_text"]) != expected_directive:
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_MISMATCH",
                    "canonical source does not match the requested bounded loop closure",
                )

            active = self._active_loops(
                conn,
                relationship_id=relationship["relationship_id"],
                loop_kind="DECISION",
            )
            if not active:
                fail(
                    "CONVERSATION_OPEN_LOOP_UNAVAILABLE",
                    "no unresolved decision loop exists to close",
                )
            if len(active) != 1:
                fail(
                    "CONVERSATION_OPEN_LOOP_AMBIGUOUS",
                    "multiple unresolved decision loops exist; closure fails closed",
                )
            loop = active[0]
            conn.execute(
                insert(schema.conversation_open_loop_closure).values(
                    open_loop_id=loop["open_loop_id"],
                    closure_kind=closure_kind,
                    source_event_id=source_event_id,
                    superseding_open_loop_id=None,
                    closed_at=self.services.clock.now(),
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition=("RESOLVED" if closure_kind == "RESOLVED" else "CANCELLED"),
                open_loop_id=loop["open_loop_id"],
                loop_kind=loop["loop_kind"],
            )

    def _load_source(self, conn, source_event_id: UUID):
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == source_event_id
            )
        ).mappings().one_or_none()
        if event is None:
            fail(
                "CONVERSATION_OPEN_LOOP_SOURCE_NOT_FOUND",
                "open-loop source event does not exist",
            )
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == event["relationship_id"]
            )
        ).mappings().one_or_none()
        if relationship is None:
            fail("RELATIONSHIP_NOT_FOUND", "open-loop source relationship does not exist")
        if (
            event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
        ):
            fail(
                "CONVERSATION_OPEN_LOOP_SOURCE_INVALID",
                "open-loop lifecycle accepts only counterpart input in its relationship",
            )
        return event, relationship

    @staticmethod
    def _active_loops(conn, *, relationship_id: UUID, loop_kind: str):
        return conn.execute(
            select(schema.conversation_open_loop)
            .select_from(
                schema.conversation_open_loop.outerjoin(
                    schema.conversation_open_loop_closure,
                    schema.conversation_open_loop.c.open_loop_id
                    == schema.conversation_open_loop_closure.c.open_loop_id,
                )
            )
            .where(
                schema.conversation_open_loop.c.relationship_id == relationship_id,
                schema.conversation_open_loop.c.loop_kind == loop_kind,
                schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
            )
            .order_by(
                schema.conversation_open_loop.c.opened_at,
                schema.conversation_open_loop.c.open_loop_id,
            )
        ).mappings().all()

    @staticmethod
    def _fence_relationship(conn, relationship_id: UUID) -> None:
        fenced = conn.execute(
            update(schema.relationship_timeline_head)
            .where(
                schema.relationship_timeline_head.c.relationship_id == relationship_id
            )
            .values(
                last_timeline_seq=schema.relationship_timeline_head.c.last_timeline_seq
            )
        )
        if fenced.rowcount != 1:
            fail(
                "CONVERSATION_OPEN_LOOP_FENCE_UNAVAILABLE",
                "relationship open-loop write fence is unavailable",
            )


__all__ = [
    "F4ConversationOpenLoopResult",
    "F4ConversationOpenLoopSelection",
    "F4ConversationOpenLoopService",
    "OpenLoopDisposition",
]
