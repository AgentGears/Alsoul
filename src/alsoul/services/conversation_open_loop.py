from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.errors import fail
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.conversation_open_loop_context import (
    DECISION_REFERENCE_CONTRACT_VERSION,
    DECISION_REFERENCE_KIND,
    F4OpenLoopDirective,
    USER_ALIAS_CONTRACT_VERSION,
    USER_ALIAS_KIND,
    parse_open_loop_directive,
)
from alsoul.services.foundation import FoundationServices as BaseFoundationServices
from alsoul.storage import schema

OpenLoopDisposition = Literal[
    "NO_ACTION",
    "OPENED",
    "RESOLVED",
    "CANCELLED",
    "LABELED",
    "RENAMED",
    "ALIAS_REMOVED",
]
OpenLoopSelectionBasis = Literal[
    "CURRENT_OPEN_DECISION_LOOP",
    "EXPLICIT_DECISION_REFERENCE",
    "EXPLICIT_USER_ALIAS",
]

_ALIAS_ASSIGNMENT_RECEIPT_SCOPE = "ConversationOpenLoopAliasAssignment"
_OPEN_LOOP_CLOSURE_RECEIPT_SCOPE = "ConversationOpenLoopClosure"


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopResult:
    source_event_id: UUID
    disposition: OpenLoopDisposition
    open_loop_id: UUID | None = None
    loop_kind: str | None = None
    open_loop_reference_id: UUID | None = None
    open_loop_alias_id: UUID | None = None
    replacement_alias_id: UUID | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class F4ConversationOpenLoopSelection:
    open_loop_id: UUID
    relationship_id: UUID
    loop_kind: str
    opened_by_event_id: UUID
    selection_basis: OpenLoopSelectionBasis
    open_loop_reference_id: UUID | None = None
    open_loop_alias_id: UUID | None = None
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


def _active_alias_rows(
    conn,
    *,
    relationship_id: UUID,
    canonical_alias_key: str,
):
    return conn.execute(
        select(
            schema.conversation_open_loop,
            schema.conversation_open_loop_alias.c.open_loop_alias_id,
            schema.conversation_open_loop_alias.c.alias_contract_version,
            schema.conversation_open_loop_alias.c.canonical_alias_key,
        )
        .select_from(
            schema.conversation_open_loop.join(
                schema.conversation_open_loop_alias,
                schema.conversation_open_loop.c.open_loop_id
                == schema.conversation_open_loop_alias.c.open_loop_id,
            )
            .outerjoin(
                schema.conversation_open_loop_closure,
                schema.conversation_open_loop.c.open_loop_id
                == schema.conversation_open_loop_closure.c.open_loop_id,
            )
            .outerjoin(
                schema.conversation_open_loop_alias_retirement,
                schema.conversation_open_loop_alias.c.open_loop_alias_id
                == schema.conversation_open_loop_alias_retirement.c.open_loop_alias_id,
            )
        )
        .where(
            schema.conversation_open_loop.c.relationship_id == relationship_id,
            schema.conversation_open_loop.c.loop_kind == "DECISION",
            schema.conversation_open_loop_closure.c.open_loop_id.is_(None),
            schema.conversation_open_loop_alias_retirement.c.open_loop_alias_id.is_(None),
            schema.conversation_open_loop_alias.c.alias_kind == USER_ALIAS_KIND,
            schema.conversation_open_loop_alias.c.alias_contract_version
            == USER_ALIAS_CONTRACT_VERSION,
            schema.conversation_open_loop_alias.c.canonical_alias_key
            == canonical_alias_key,
        )
        .order_by(
            schema.conversation_open_loop.c.opened_at,
            schema.conversation_open_loop.c.open_loop_id,
            schema.conversation_open_loop_alias.c.created_at,
            schema.conversation_open_loop_alias.c.open_loop_alias_id,
        )
    ).mappings().all()


def resolve_active_decision_loop(
    conn,
    *,
    relationship_id: UUID,
    directive: F4OpenLoopDirective,
) -> F4ConversationOpenLoopSelection:
    """Resolve one active decision loop by exact cardinality, never by ranking."""

    if directive.operation not in {
        "RESUME",
        "RESOLVE",
        "CANCEL",
        "LABEL",
        "RENAME_ALIAS",
        "REMOVE_ALIAS",
    }:
        fail(
            "CONVERSATION_OPEN_LOOP_SELECTOR_INVALID",
            "open-loop target resolution requires a supported targeted directive",
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

    if directive.selector_kind == "DECISION_OPTION_PAIR":
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

    if directive.selector_kind == "USER_ALIAS":
        if (
            directive.selector_contract_version != USER_ALIAS_CONTRACT_VERSION
            or not directive.selector_key
        ):
            fail(
                "CONVERSATION_OPEN_LOOP_ALIAS_CONTRACT_UNSUPPORTED",
                "open-loop alias selector contract is not supported",
            )
        rows = _active_alias_rows(
            conn,
            relationship_id=relationship_id,
            canonical_alias_key=directive.selector_key,
        )
        if not rows:
            fail(
                "CONVERSATION_OPEN_LOOP_TARGET_NOT_FOUND",
                "no unresolved decision loop exactly matches the user alias",
            )
        loop_ids = {row["open_loop_id"] for row in rows}
        if len(loop_ids) != 1 or len(rows) != 1:
            fail(
                "CONVERSATION_OPEN_LOOP_AMBIGUOUS",
                "user alias does not resolve to exactly one active loop",
            )
        row = rows[0]
        return F4ConversationOpenLoopSelection(
            open_loop_id=row["open_loop_id"],
            relationship_id=row["relationship_id"],
            loop_kind=row["loop_kind"],
            opened_by_event_id=row["opened_by_event_id"],
            selection_basis="EXPLICIT_USER_ALIAS",
            open_loop_alias_id=row["open_loop_alias_id"],
            selector_contract_version=row["alias_contract_version"],
            selector_key=row["canonical_alias_key"],
        )

    fail(
        "CONVERSATION_OPEN_LOOP_SELECTOR_INVALID",
        "bounded decision-loop directive has no supported selector",
    )


class F4ConversationOpenLoopService:
    """Persist and address bounded unresolved conversational dependencies.

    ConversationOpenLoop is relationship-scoped state, not memory, work, commitment,
    trigger, permission, or authority. References and counterpart-authored aliases are
    addressing metadata; neither replaces open_loop_id as canonical identity.
    """

    def __init__(self, services: BaseFoundationServices) -> None:
        self.services = services

    def consider_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.connect() as conn:
            event, _relationship = self._load_source(conn, source_event_id)
        directive = parse_open_loop_directive(event["content_text"])
        if directive.operation == "OPEN":
            return self._open_from_event(source_event_id)
        if directive.operation == "LABEL":
            return self._label_from_event(source_event_id)
        if directive.operation == "RENAME_ALIAS":
            return self._rename_alias_from_event(source_event_id)
        if directive.operation == "REMOVE_ALIAS":
            return self._remove_alias_from_event(source_event_id)
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

    def _label_from_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])
            directive = parse_open_loop_directive(event["content_text"])
            if (
                directive.operation != "LABEL"
                or directive.selector_kind != "DECISION_OPTION_PAIR"
                or not directive.alias_label
                or not directive.alias_key
            ):
                fail(
                    "CONVERSATION_OPEN_LOOP_ALIAS_SOURCE_MISMATCH",
                    "canonical source does not match the bounded alias-assignment grammar",
                )

            req = request_digest(
                {
                    "source_event_id": source_event_id,
                    "relationship_id": relationship["relationship_id"],
                    "selector_contract_version": directive.selector_contract_version,
                    "selector_key": directive.selector_key,
                    "alias_contract_version": USER_ALIAS_CONTRACT_VERSION,
                    "alias_key": directive.alias_key,
                }
            )
            replay = load_operation_receipt(
                conn,
                scope=_ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                operation_id=source_event_id,
                expected_request_digest=req,
            )
            if replay is not None:
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="LABELED",
                    open_loop_id=UUID(replay["open_loop_id"]),
                    loop_kind=replay["loop_kind"],
                    open_loop_alias_id=UUID(replay["open_loop_alias_id"]),
                    idempotent_replay=True,
                )

            def persist_assignment_receipt(
                *, open_loop_id: UUID, loop_kind: str, open_loop_alias_id: UUID
            ) -> None:
                save_operation_receipt(
                    conn,
                    scope=_ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                    operation_id=source_event_id,
                    req_digest=req,
                    result_kind="ConversationOpenLoopAlias",
                    result_ref=open_loop_alias_id,
                    result_json={
                        "open_loop_id": str(open_loop_id),
                        "loop_kind": loop_kind,
                        "open_loop_alias_id": str(open_loop_alias_id),
                    },
                    committed_at=self.services.clock.now(),
                )

            source_alias = conn.execute(
                select(schema.conversation_open_loop_alias).where(
                    schema.conversation_open_loop_alias.c.source_event_id == source_event_id
                )
            ).mappings().one_or_none()
            if source_alias is not None:
                persist_assignment_receipt(
                    open_loop_id=source_alias["open_loop_id"],
                    loop_kind="DECISION",
                    open_loop_alias_id=source_alias["open_loop_alias_id"],
                )
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="LABELED",
                    open_loop_id=source_alias["open_loop_id"],
                    loop_kind="DECISION",
                    open_loop_alias_id=source_alias["open_loop_alias_id"],
                    idempotent_replay=True,
                )

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=relationship["relationship_id"],
                directive=directive,
            )
            existing = _active_alias_rows(
                conn,
                relationship_id=relationship["relationship_id"],
                canonical_alias_key=directive.alias_key,
            )
            if existing:
                if len(existing) == 1 and existing[0]["open_loop_id"] == selection.open_loop_id:
                    alias_id = existing[0]["open_loop_alias_id"]
                    persist_assignment_receipt(
                        open_loop_id=selection.open_loop_id,
                        loop_kind=selection.loop_kind,
                        open_loop_alias_id=alias_id,
                    )
                    return F4ConversationOpenLoopResult(
                        source_event_id=source_event_id,
                        disposition="LABELED",
                        open_loop_id=selection.open_loop_id,
                        loop_kind=selection.loop_kind,
                        open_loop_alias_id=alias_id,
                        idempotent_replay=True,
                    )
                fail(
                    "CONVERSATION_OPEN_LOOP_ALIAS_CONFLICT",
                    "alias is already assigned to another active loop",
                )

            alias_id = self.services.ids.new()
            now = self.services.clock.now()
            conn.execute(
                insert(schema.conversation_open_loop_alias).values(
                    open_loop_alias_id=alias_id,
                    open_loop_id=selection.open_loop_id,
                    alias_kind=USER_ALIAS_KIND,
                    alias_contract_version=USER_ALIAS_CONTRACT_VERSION,
                    display_label=directive.alias_label,
                    canonical_alias_key=directive.alias_key,
                    source_event_id=source_event_id,
                    created_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=_ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                operation_id=source_event_id,
                req_digest=req,
                result_kind="ConversationOpenLoopAlias",
                result_ref=alias_id,
                result_json={
                    "open_loop_id": str(selection.open_loop_id),
                    "loop_kind": selection.loop_kind,
                    "open_loop_alias_id": str(alias_id),
                },
                committed_at=now,
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition="LABELED",
                open_loop_id=selection.open_loop_id,
                loop_kind=selection.loop_kind,
                open_loop_alias_id=alias_id,
            )

    def _rename_alias_from_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])
            directive = parse_open_loop_directive(event["content_text"])
            if (
                directive.operation != "RENAME_ALIAS"
                or directive.selector_kind != "USER_ALIAS"
                or not directive.selector_key
                or not directive.new_alias_label
                or not directive.new_alias_key
            ):
                fail(
                    "CONVERSATION_OPEN_LOOP_ALIAS_SOURCE_MISMATCH",
                    "canonical source does not match the bounded alias-rename grammar",
                )
            if directive.selector_key == directive.new_alias_key:
                fail(
                    "CONVERSATION_OPEN_LOOP_ALIAS_RENAME_NOOP",
                    "alias rename must change the canonical alias key",
                )

            replay = conn.execute(
                select(
                    schema.conversation_open_loop_alias_retirement,
                    schema.conversation_open_loop_alias.c.open_loop_id,
                    schema.conversation_open_loop.c.loop_kind,
                )
                .join(
                    schema.conversation_open_loop_alias,
                    schema.conversation_open_loop_alias_retirement.c.open_loop_alias_id
                    == schema.conversation_open_loop_alias.c.open_loop_alias_id,
                )
                .join(
                    schema.conversation_open_loop,
                    schema.conversation_open_loop_alias.c.open_loop_id
                    == schema.conversation_open_loop.c.open_loop_id,
                )
                .where(
                    schema.conversation_open_loop_alias_retirement.c.source_event_id
                    == source_event_id
                )
            ).mappings().one_or_none()
            if replay is not None:
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="RENAMED",
                    open_loop_id=replay["open_loop_id"],
                    loop_kind=replay["loop_kind"],
                    open_loop_alias_id=replay["open_loop_alias_id"],
                    replacement_alias_id=replay["replacement_alias_id"],
                    idempotent_replay=True,
                )

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=relationship["relationship_id"],
                directive=directive,
            )
            assert selection.open_loop_alias_id is not None
            conflicts = _active_alias_rows(
                conn,
                relationship_id=relationship["relationship_id"],
                canonical_alias_key=directive.new_alias_key,
            )
            if conflicts:
                if len(conflicts) == 1 and conflicts[0]["open_loop_id"] == selection.open_loop_id:
                    replacement_alias_id = conflicts[0]["open_loop_alias_id"]
                else:
                    fail(
                        "CONVERSATION_OPEN_LOOP_ALIAS_CONFLICT",
                        "replacement alias is already assigned to another active loop",
                    )
            else:
                replacement_alias_id = self.services.ids.new()
                conn.execute(
                    insert(schema.conversation_open_loop_alias).values(
                        open_loop_alias_id=replacement_alias_id,
                        open_loop_id=selection.open_loop_id,
                        alias_kind=USER_ALIAS_KIND,
                        alias_contract_version=USER_ALIAS_CONTRACT_VERSION,
                        display_label=directive.new_alias_label,
                        canonical_alias_key=directive.new_alias_key,
                        source_event_id=source_event_id,
                        created_at=self.services.clock.now(),
                    )
                )

            retirement_id = self.services.ids.new()
            conn.execute(
                insert(schema.conversation_open_loop_alias_retirement).values(
                    alias_retirement_id=retirement_id,
                    open_loop_alias_id=selection.open_loop_alias_id,
                    retirement_kind="RENAMED",
                    source_event_id=source_event_id,
                    replacement_alias_id=replacement_alias_id,
                    retired_at=self.services.clock.now(),
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition="RENAMED",
                open_loop_id=selection.open_loop_id,
                loop_kind=selection.loop_kind,
                open_loop_alias_id=selection.open_loop_alias_id,
                replacement_alias_id=replacement_alias_id,
            )

    def _remove_alias_from_event(self, source_event_id: UUID) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])
            directive = parse_open_loop_directive(event["content_text"])
            if (
                directive.operation != "REMOVE_ALIAS"
                or directive.selector_kind != "USER_ALIAS"
                or not directive.selector_key
            ):
                fail(
                    "CONVERSATION_OPEN_LOOP_ALIAS_SOURCE_MISMATCH",
                    "canonical source does not match the bounded alias-removal grammar",
                )

            replay = conn.execute(
                select(
                    schema.conversation_open_loop_alias_retirement,
                    schema.conversation_open_loop_alias.c.open_loop_id,
                    schema.conversation_open_loop.c.loop_kind,
                )
                .join(
                    schema.conversation_open_loop_alias,
                    schema.conversation_open_loop_alias_retirement.c.open_loop_alias_id
                    == schema.conversation_open_loop_alias.c.open_loop_alias_id,
                )
                .join(
                    schema.conversation_open_loop,
                    schema.conversation_open_loop_alias.c.open_loop_id
                    == schema.conversation_open_loop.c.open_loop_id,
                )
                .where(
                    schema.conversation_open_loop_alias_retirement.c.source_event_id
                    == source_event_id
                )
            ).mappings().one_or_none()
            if replay is not None:
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition="ALIAS_REMOVED",
                    open_loop_id=replay["open_loop_id"],
                    loop_kind=replay["loop_kind"],
                    open_loop_alias_id=replay["open_loop_alias_id"],
                    idempotent_replay=True,
                )

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=relationship["relationship_id"],
                directive=directive,
            )
            assert selection.open_loop_alias_id is not None
            conn.execute(
                insert(schema.conversation_open_loop_alias_retirement).values(
                    alias_retirement_id=self.services.ids.new(),
                    open_loop_alias_id=selection.open_loop_alias_id,
                    retirement_kind="REMOVED",
                    source_event_id=source_event_id,
                    replacement_alias_id=None,
                    retired_at=self.services.clock.now(),
                )
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition="ALIAS_REMOVED",
                open_loop_id=selection.open_loop_id,
                loop_kind=selection.loop_kind,
                open_loop_alias_id=selection.open_loop_alias_id,
            )

    def _close_from_event(
        self,
        source_event_id: UUID,
        closure_kind: Literal["RESOLVED", "CANCELLED"],
    ) -> F4ConversationOpenLoopResult:
        with self.services.engine.begin() as conn:
            event, relationship = self._load_source(conn, source_event_id)
            self._fence_relationship(conn, relationship["relationship_id"])

            directive = parse_open_loop_directive(event["content_text"])
            expected_operation = "RESOLVE" if closure_kind == "RESOLVED" else "CANCEL"
            if directive.operation != expected_operation:
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_MISMATCH",
                    "canonical source does not match the requested bounded loop closure",
                )

            req = request_digest(
                {
                    "source_event_id": source_event_id,
                    "relationship_id": relationship["relationship_id"],
                    "closure_kind": closure_kind,
                    "selector_kind": directive.selector_kind,
                    "selector_contract_version": directive.selector_contract_version,
                    "selector_key": directive.selector_key,
                }
            )
            receipt = load_operation_receipt(
                conn,
                scope=_OPEN_LOOP_CLOSURE_RECEIPT_SCOPE,
                operation_id=source_event_id,
                expected_request_digest=req,
            )
            if receipt is not None:
                return F4ConversationOpenLoopResult(
                    source_event_id=source_event_id,
                    disposition=receipt["disposition"],
                    open_loop_id=UUID(receipt["open_loop_id"]),
                    loop_kind=receipt["loop_kind"],
                    open_loop_reference_id=(
                        UUID(receipt["open_loop_reference_id"])
                        if receipt.get("open_loop_reference_id")
                        else None
                    ),
                    open_loop_alias_id=(
                        UUID(receipt["open_loop_alias_id"])
                        if receipt.get("open_loop_alias_id")
                        else None
                    ),
                    idempotent_replay=True,
                )

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

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=relationship["relationship_id"],
                directive=directive,
            )
            disposition = "RESOLVED" if closure_kind == "RESOLVED" else "CANCELLED"
            now = self.services.clock.now()
            conn.execute(
                insert(schema.conversation_open_loop_closure).values(
                    open_loop_id=selection.open_loop_id,
                    closure_kind=closure_kind,
                    source_event_id=source_event_id,
                    superseding_open_loop_id=None,
                    closed_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=_OPEN_LOOP_CLOSURE_RECEIPT_SCOPE,
                operation_id=source_event_id,
                req_digest=req,
                result_kind="ConversationOpenLoopClosure",
                result_ref=selection.open_loop_id,
                result_json={
                    "disposition": disposition,
                    "open_loop_id": str(selection.open_loop_id),
                    "loop_kind": selection.loop_kind,
                    "open_loop_reference_id": (
                        str(selection.open_loop_reference_id)
                        if selection.open_loop_reference_id is not None
                        else None
                    ),
                    "open_loop_alias_id": (
                        str(selection.open_loop_alias_id)
                        if selection.open_loop_alias_id is not None
                        else None
                    ),
                },
                committed_at=now,
            )
            return F4ConversationOpenLoopResult(
                source_event_id=source_event_id,
                disposition=disposition,
                open_loop_id=selection.open_loop_id,
                loop_kind=selection.loop_kind,
                open_loop_reference_id=selection.open_loop_reference_id,
                open_loop_alias_id=selection.open_loop_alias_id,
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
