from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.errors import fail
from alsoul.services.conversation_open_loop_context import (
    DECISION_REFERENCE_CONTRACT_VERSION,
    DECISION_REFERENCE_KIND,
    F4OpenLoopDirective,
    parse_open_loop_directive,
)
from alsoul.services.foundation import FoundationServices as BaseFoundationServices
from alsoul.storage import schema

OpenLoopDisposition = Literal[
    "NO_ACTION",
    "OPENED",
    "RESOLVED",
    "CANCELLED",
]
OpenLoopSelectionBasis = Literal[
    "CURRENT_OPEN_DECISION_LOOP",
    "EXPLICIT_DECISION_REFERENCE",
]


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopResult:
    source_event_id: UUID
    disposition: OpenLoopDisposition
    open_loop_id: UUID | None = None
    loop_kind: str | None = None
    open_loop_reference_id: UUID | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopSelection:
    open_loop_id: UUID
    relationship_id: UUID
    loop_kind: str
    opened_by_event_id: UUID
    selection_basis: OpenLoopSelectionBasis
    open_loop_reference_id: UUID | None = None
    selector_contract_version: str | None = None
    selector_key: str | None = None


def _active_decision_rows(conn, *, relationship_id: UUID):
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
            schema.conversation_open_loop.c.loop_kind == "DECISION",
            schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
        )
        .order_by(
            schema.conversation_open_loop.c.opened_at,
            schema.conversation_open_loop.c.open_loop_id,
        )
    ).mappings().all()


def resolve_active_decision_loop(
    conn,
    *,
    relationship_id: UUID,
    directive: F4OpenLoopDirective,
) -> F4ConversationOpenLoopSelection:
    """Resolve one active decision loop by cardinality, never by ranking."""

    if directive.operation not in {"RESUME", "RESOLVE", "CANCEL"}:
        fail(
            "CONVERSATION_OPEN_LOOP_SELECTOR_INVALID",
            "open-loop target resolution requires a resume or terminal directive",
        )

    if directive.selector_kind == "UNQUALIFIED":
        rows = _active_decision_rows(conn, relationship_id=relationship_id)
        if not rows:
            fail(
                "CONVERSATION_OPEN_LOOP_UNAVAILABLE",
                "no unresolved decision loop exists in this relationship",
            )
        if len(rows) != 1:
            fail(
                "CONVERSATION_OPEN_LOOP_AMBIGUOUS",
                "multiple unresolved decision loops exist; unqualified resolution fails closed",
            )
        row = rows[0]
        return F4ConversationOpenLoopSelection(
            open_loop_id=row["open_loop_id"],
            relationship_id=row["relationship_id"],
            loop_kind=row["loop_kind"],
            opened_by_event_id=row["opened_by_event_id"],
            selection_basis="CURRENT_OPEN_DECISION_LOOP",
        )

    if directive.selector_kind != "DECISION_OPTION_PAIR":
        fail(
            "CONVERSATION_OPEN_LOOP_SELECTOR_INVALID",
            "bounded decision-loop directive has no supported selector",
        )
    if (
        directive.selector_contract_version != DECISION_REFERENCE_CONTRACT_VERSION
        or not directive.selector_key
    ):
        fail(
            "CONVERSATION_OPEN_LOOP_REFERENCE_CONTRACT_UNSUPPORTED",
            "decision-loop selector contract is not supported",
        )

    rows = conn.execute(
        select(
            schema.conversation_open_loop,
            schema.conversation_open_loop_reference.c.open_loop_reference_id,
            schema.conversation_open_loop_reference.c.reference_contract_version,
            schema.conversation_open_loop_reference.c.canonical_reference_key,
        )
        .select_from(
            schema.conversation_open_loop.join(
                schema.conversation_open_loop_reference,
                schema.conversation_open_loop.c.open_loop_id
                == schema.conversation_open_loop_reference.c.open_loop_id,
            ).outerjoin(
                schema.conversation_open_loop_closure,
                schema.conversation_open_loop.c.open_loop_id
                == schema.conversation_open_loop_closure.c.open_loop_id,
            )
        )
        .where(
            schema.conversation_open_loop.c.relationship_id == relationship_id,
            schema.conversation_open_loop.c.loop_kind == "DECISION",
            schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
            schema.conversation_open_loop_reference.c.reference_kind
            == DECISION_REFERENCE_KIND,
            schema.conversation_open_loop_reference.c.reference_contract_version
            == directive.selector_contract_version,
            schema.conversation_open_loop_reference.c.canonical_reference_key
            == directive.selector_key,
        )
        .order_by(
            schema.conversation_open_loop.c.opened_at,
            schema.conversation_open_loop.c.open_loop_id,
        )
    ).mappings().all()
    if not rows:
        fail(
            "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND",
            "no unresolved decision loop exactly matches the explicit reference",
        )
    if len(rows) != 1:
        fail(
            "CONVERSATION_OPEN_LOOP_AMBIGUOUS",
            "multiple unresolved decision loops exactly match the explicit reference",
        )
    row = rows[0]
    return F4ConversationOpenLoopSelection(
        open_loop_id=row["open_loop_id"],
        relationship_id=row["relationship_id"],
        loop_kind=row["loop_kind"],
        opened_by_event_id=row["opened_by_event_id"],
        selection_basis="EXPLICIT_DECISION_REFERENCE",
        open_loop_reference_id=row["open_loop_reference_id"],
        selector_contract_version=row["reference_contract_version"],
        selector_key=row["canonical_reference_key"],
    )


class F4ConversationOpenLoopService:
    """Persist and address bounded unresolved conversational dependencies.

    ConversationOpenLoop is relationship-scoped state, not memory, work, commitment,
    trigger, permission, or authority. References are immutable addressing metadata;
    they never replace open_loop_id as canonical identity.
    """

    def __init__(self, services: BaseFoundationServices) -> None:
        self.services = services

    def consider_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.connect() as conn:
            event, _relationship = self._load_source(conn, source_event_id)
        directive = parse_open_loop_directive(event["content_text"])
        if directive.operation == "OPEN":
            return self._open_from_event(source_event_id)
        if directive.operation == "RESOLVE":
            return self._close_from_event(source_event_id, "RESOLVED")
        if directive.operation == "CANCEL":
            return self._close_from_event(source_event_id, "CANCELLED")
        return F4ConversationOpenLoopResult(
            source_event_id=source_event_id,
            disposition="NO_ACTION",
        )

    def select_current_decision_loop(
        self, relationship_id: UUID
    ) -> F4ConversationOpenLoopSelection:
        return self.resolve_decision_loop(
            relationship_id,
            F4OpenLoopDirective(operation="RESUME", selector_kind="UNQUALIFIED"),
        )

    def resolve_decision_loop(
        self,
        relationship_id: UUID,
        directive: F4OpenLoopDirective,
    ) -> F4ConversationOpenLoopSelection:
        with self.services.engine.connect() as conn:
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id == relationship_id
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "open-loop relationship does not exist")
            return resolve_active_decision_loop(
                conn,
                relationship_id=relationship_id,
                directive=directive,
            )

    def _open_from_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])
            directive = parse_open_loop_directive(event["content_text"])
            if (
                directive.operation != "OPEN"
                or directive.selector_kind != "DECISION_OPTION_PAIR"
                or directive.selector_contract_version
                != DECISION_REFERENCE_CONTRACT_VERSION
                or not directive.selector_key
            ):
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_MISMATCH",
                    "canonical source no longer matches the bounded open-loop opening grammar",
                )

            existing = conn.execute(
                select(schema.conversation_open_loop).where(
                    schema.conversation_open_loop.c.opened_by_event_id == source_event_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                references = conn.execute(
                    select(schema.conversation_open_loop_reference).where(
                        schema.conversation_open_loop_reference.c.open_loop_id
                        == existing["open_loop_id"],
                        schema.conversation_open_loop_reference.c.reference_kind
                        == DECISION_REFERENCE_KIND,
                        schema.conversation_open_loop_reference.c.reference_contract_version
                        == DECISION_REFERENCE_CONTRACT_VERSION,
                    )
                ).mappings().all()
                if len(references) != 1:
                    fail(
                        "CONVERSATION_OPEN_LOOP_REFERENCE_MISSING",
                        "existing decision loop does not have exactly one bounded reference",
                    )
                reference = references[0]
                if (
                    reference["source_event_id"] != source_event_id
                    or reference["canonical_reference_key"] != directive.selector_key
                ):
                    fail(
                        "CONVERSATION_OPEN_LOOP_REFERENCE_CONFLICT",
                        "existing decision-loop reference does not match its canonical opening source",
                    )
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="OPENED",
                    open_loop_id=existing["open_loop_id"],
                    loop_kind=existing["loop_kind"],
                    open_loop_reference_id=reference["open_loop_reference_id"],
                    idempotent_replay=True,
                )

            now = self.services.clock.now()
            open_loop_id = self.services.ids.new()
            open_loop_reference_id = self.services.ids.new()
            conn.execute(
                insert(schema.conversation_open_loop).values(
                    open_loop_id=open_loop_id,
                    relationship_id=relationship["relationship_id"],
                    loop_kind="DECISION",
                    opened_by_event_id=source_event_id,
                    opened_at=now,
                )
            )
            conn.execute(
                insert(schema.conversation_open_loop_reference).values(
                    open_loop_reference_id=open_loop_reference_id,
                    open_loop_id=open_loop_id,
                    reference_kind=DECISION_REFERENCE_KIND,
                    reference_contract_version=DECISION_REFERENCE_CONTRACT_VERSION,
                    canonical_reference_key=directive.selector_key,
                    source_event_id=source_event_id,
                    created_at=now,
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition="OPENED",
                open_loop_id=open_loop_id,
                loop_kind="DECISION",
                open_loop_reference_id=open_loop_reference_id,
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

            directive = parse_open_loop_directive(event["content_text"])
            expected_operation = "RESOLVE" if closure_kind == "RESOLVED" else "CANCEL"
            if directive.operation != expected_operation:
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_MISMATCH",
                    "canonical source does not match the requested bounded loop closure",
                )

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=relationship["relationship_id"],
                directive=directive,
            )
            conn.execute(
                insert(schema.conversation_open_loop_closure).values(
                    open_loop_id=selection.open_loop_id,
                    closure_kind=closure_kind,
                    source_event_id=source_event_id,
                    superseding_open_loop_id=None,
                    closed_at=self.services.clock.now(),
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition=("RESOLVED" if closure_kind == "RESOLVED" else "CANCELLED"),
                open_loop_id=selection.open_loop_id,
                loop_kind=selection.loop_kind,
                open_loop_reference_id=selection.open_loop_reference_id,
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
    "OpenLoopSelectionBasis",
    "resolve_active_decision_loop",
]
