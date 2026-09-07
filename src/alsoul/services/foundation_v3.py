from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update

from alsoul.domain.commands import BuildContextProjectionCommand
from alsoul.domain.errors import fail
from alsoul.domain.models import BuildContextProjectionResult
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.conversation_open_loop import resolve_active_decision_loop
from alsoul.services.conversation_open_loop_context import (
    DECISION_REFERENCE_KIND,
    parse_open_loop_directive,
)
from alsoul.services.foundation_base import FoundationServices as FoundationServicesCore
from alsoul.services.foundation_v2 import FoundationServices as FoundationServicesV2
from alsoul.storage import schema


class FoundationServices(FoundationServicesV2):
    """Current F4 services with targetable open-loop cognition provenance."""

    def _build_open_loop_context_projection(
        self, command: BuildContextProjectionCommand
    ) -> BuildContextProjectionResult:
        scope = "BuildContextProjection"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return BuildContextProjectionResult(
                    projection_id=UUID(replay["projection_id"]),
                    source_self_revision=int(replay["source_self_revision"]),
                    source_relationship_revision=int(
                        replay["source_relationship_revision"]
                    ),
                    source_timeline_frontier=int(replay["source_timeline_frontier"]),
                    manifest_digest=replay["manifest_digest"],
                )

            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "projection relationship does not exist")
            if relationship["companion_person_id"] != command.companion_person_id:
                fail(
                    "PROJECTION_RELATIONSHIP_REVISION_INVALID",
                    "projection companion does not own relationship",
                )

            # Serialize Timeline/open-loop selection while the immutable projection is
            # admitted. This does not mutate the Timeline frontier.
            fenced = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
                .values(
                    last_timeline_seq=schema.relationship_timeline_head.c.last_timeline_seq
                )
            )
            if fenced.rowcount != 1:
                fail(
                    "CONVERSATION_OPEN_LOOP_FENCE_UNAVAILABLE",
                    "relationship projection fence is unavailable",
                )

            self_head = conn.execute(
                select(schema.self_head).where(
                    schema.self_head.c.person_id == command.companion_person_id
                )
            ).mappings().one_or_none()
            if self_head is None:
                fail("SELF_HEAD_NOT_FOUND", "SelfHead missing")
            self_revision = conn.execute(
                select(schema.self_revision).where(
                    schema.self_revision.c.person_id == command.companion_person_id,
                    schema.self_revision.c.revision == self_head["current_revision"],
                )
            ).mappings().one_or_none()
            if self_revision is None:
                fail("SELF_REVISION_NOT_FOUND", "SelfHead points to missing SelfRevision")

            relationship_head = conn.execute(
                select(schema.relationship_head).where(
                    schema.relationship_head.c.relationship_id == command.relationship_id
                )
            ).mappings().one_or_none()
            if relationship_head is None:
                fail("RELATIONSHIP_HEAD_NOT_FOUND", "RelationshipHead missing")
            relationship_revision = conn.execute(
                select(schema.relationship_revision).where(
                    schema.relationship_revision.c.relationship_id
                    == command.relationship_id,
                    schema.relationship_revision.c.revision
                    == relationship_head["current_revision"],
                )
            ).mappings().one_or_none()
            if relationship_revision is None:
                fail(
                    "RELATIONSHIP_REVISION_NOT_FOUND",
                    "RelationshipHead points to missing revision",
                )

            input_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.current_input_event_id
                )
            ).mappings().one_or_none()
            if (
                input_event is None
                or input_event["relationship_id"] != command.relationship_id
                or input_event["event_kind"] != "COUNTERPART_INPUT"
                or input_event["actor_kind"] != "COUNTERPART"
                or input_event["actor_ref"] != relationship["counterpart_id"]
            ):
                fail(
                    "PROJECTION_CURRENT_INPUT_INVALID",
                    "current input is not a counterpart input in projection relationship",
                )
            directive = parse_open_loop_directive(input_event["content_text"])
            if directive.operation != "RESUME":
                fail(
                    "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                    "current input does not require durable open-loop context",
                )

            timeline = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            if timeline is None:
                fail("RELATIONSHIP_NOT_FOUND", "relationship Timeline head is missing")
            if int(input_event["timeline_seq"]) != int(timeline["last_timeline_seq"]):
                fail(
                    "PROJECTION_OPEN_LOOP_INPUT_NOT_FRONTIER",
                    "open-loop conversation may project context only from the current Timeline frontier",
                )

            selection = resolve_active_decision_loop(
                conn,
                relationship_id=command.relationship_id,
                directive=directive,
            )
            opening_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == selection.opened_by_event_id
                )
            ).mappings().one_or_none()
            if (
                opening_event is None
                or opening_event["relationship_id"] != command.relationship_id
                or opening_event["event_kind"] != "COUNTERPART_INPUT"
                or opening_event["actor_kind"] != "COUNTERPART"
                or opening_event["actor_ref"] != relationship["counterpart_id"]
            ):
                fail(
                    "CONVERSATION_OPEN_LOOP_SOURCE_INVALID",
                    "selected open loop does not point to a valid counterpart Timeline source",
                )

            selected_events = (opening_event, input_event)
            manifest = {
                "projection_schema_version": 1,
                "purpose": "RESPOND_TO_INTERACTION",
                "companion_person_id": str(command.companion_person_id),
                "relationship_id": str(command.relationship_id),
                "current_input_event_id": str(command.current_input_event_id),
                "source_self_revision": int(self_head["current_revision"]),
                "source_relationship_revision": int(
                    relationship_head["current_revision"]
                ),
                "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                "selected_event_refs": [
                    str(event["event_id"]) for event in selected_events
                ],
                "conversation_open_loop_items": [
                    {
                        "open_loop_id": str(selection.open_loop_id),
                        "loop_kind": selection.loop_kind,
                        "opened_by_event_id": str(selection.opened_by_event_id),
                        "selection_basis": selection.selection_basis,
                        "open_loop_reference_id": (
                            str(selection.open_loop_reference_id)
                            if selection.open_loop_reference_id is not None
                            else None
                        ),
                        "selector_contract_version": selection.selector_contract_version,
                        "selector_key": selection.selector_key,
                    }
                ],
                "personal_context_items": [],
                "world_context_items": [],
            }
            digest = sha256_text(canonical_json(manifest))
            projection_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.context_projection).values(
                    projection_id=projection_id,
                    projection_schema_version=1,
                    purpose="RESPOND_TO_INTERACTION",
                    created_at=now,
                    companion_person_id=command.companion_person_id,
                    relationship_id=command.relationship_id,
                    current_input_event_id=command.current_input_event_id,
                    source_self_revision=self_head["current_revision"],
                    source_relationship_revision=relationship_head["current_revision"],
                    source_timeline_frontier=timeline["last_timeline_seq"],
                    manifest_digest=digest,
                )
            )
            for ordinal, event in enumerate(selected_events):
                conn.execute(
                    insert(schema.context_projection_event).values(
                        projection_id=projection_id,
                        ordinal=ordinal,
                        event_id=event["event_id"],
                    )
                )

            # Preserve the v2 durable open-loop lineage row. Schema v3 adds a separate
            # selector record so old projections remain readable without rewriting
            # the v2 table or its historical constraint.
            conn.execute(
                insert(schema.context_projection_open_loop_item).values(
                    projection_id=projection_id,
                    ordinal=0,
                    open_loop_id=selection.open_loop_id,
                    selection_basis="CURRENT_OPEN_DECISION_LOOP",
                )
            )
            conn.execute(
                insert(schema.context_projection_open_loop_selector).values(
                    projection_id=projection_id,
                    open_loop_id=selection.open_loop_id,
                    open_loop_reference_id=selection.open_loop_reference_id,
                    selection_basis=selection.selection_basis,
                    selector_contract_version=selection.selector_contract_version,
                    selector_key=selection.selector_key,
                )
            )

            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ContextProjection",
                result_ref=projection_id,
                result_json={
                    "projection_id": str(projection_id),
                    "source_self_revision": int(self_head["current_revision"]),
                    "source_relationship_revision": int(
                        relationship_head["current_revision"]
                    ),
                    "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                    "manifest_digest": digest,
                },
                committed_at=now,
            )
            return BuildContextProjectionResult(
                projection_id,
                int(self_head["current_revision"]),
                int(relationship_head["current_revision"]),
                int(timeline["last_timeline_seq"]),
                digest,
            )

    def render_provider_context(self, projection_id: UUID) -> dict[str, Any]:
        with self.engine.connect() as conn:
            open_loop_items = conn.execute(
                select(schema.context_projection_open_loop_item).where(
                    schema.context_projection_open_loop_item.c.projection_id
                    == projection_id
                )
            ).mappings().all()

        if not open_loop_items:
            return super().render_provider_context(projection_id)

        # Bypass the v2 open-loop renderer so target-selection semantics are rendered
        # from the immutable selector provenance rather than re-resolving history.
        provider_context = FoundationServicesCore.render_provider_context(
            self, projection_id
        )
        if len(open_loop_items) != 1:
            fail(
                "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                "F4 projection may contain exactly one selected conversation open loop",
            )
        item = open_loop_items[0]

        with self.engine.connect() as conn:
            projection = conn.execute(
                select(schema.context_projection).where(
                    schema.context_projection.c.projection_id == projection_id
                )
            ).mappings().one_or_none()
            loop = conn.execute(
                select(schema.conversation_open_loop).where(
                    schema.conversation_open_loop.c.open_loop_id
                    == item["open_loop_id"]
                )
            ).mappings().one_or_none()
            opening = (
                conn.execute(
                    select(schema.interaction_event).where(
                        schema.interaction_event.c.event_id
                        == loop["opened_by_event_id"]
                    )
                ).mappings().one_or_none()
                if loop is not None
                else None
            )
            selected = conn.execute(
                select(
                    schema.context_projection_event.c.ordinal,
                    schema.interaction_event.c.event_id,
                )
                .join(
                    schema.interaction_event,
                    schema.context_projection_event.c.event_id
                    == schema.interaction_event.c.event_id,
                )
                .where(
                    schema.context_projection_event.c.projection_id == projection_id
                )
                .order_by(schema.context_projection_event.c.ordinal)
            ).mappings().all()
            selector = conn.execute(
                select(schema.context_projection_open_loop_selector).where(
                    schema.context_projection_open_loop_selector.c.projection_id
                    == projection_id
                )
            ).mappings().one_or_none()

        if projection is None or loop is None or opening is None:
            fail(
                "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                "open-loop projection lineage is incomplete",
            )
        if (
            len(selected) != 2
            or selected[0]["event_id"] != opening["event_id"]
            or selected[1]["event_id"] != projection["current_input_event_id"]
            or item["selection_basis"] != "CURRENT_OPEN_DECISION_LOOP"
        ):
            fail(
                "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                "open-loop projection event membership does not match its durable loop lineage",
            )

        selection_policy = "CURRENT_OPEN_DECISION_LOOP"
        reference_kind = None
        if selector is not None:
            if selector["open_loop_id"] != loop["open_loop_id"]:
                fail(
                    "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                    "open-loop selector does not identify the projected loop",
                )
            selection_policy = selector["selection_basis"]
            if selection_policy == "CURRENT_OPEN_DECISION_LOOP":
                if any(
                    selector[name] is not None
                    for name in (
                        "open_loop_reference_id",
                        "selector_contract_version",
                        "selector_key",
                    )
                ):
                    fail(
                        "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                        "unqualified selector contains explicit-reference fields",
                    )
            elif selection_policy == "EXPLICIT_DECISION_REFERENCE":
                if any(
                    selector[name] is None
                    for name in (
                        "open_loop_reference_id",
                        "selector_contract_version",
                        "selector_key",
                    )
                ):
                    fail(
                        "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                        "explicit selector lineage is incomplete",
                    )
                with self.engine.connect() as conn:
                    reference = conn.execute(
                        select(schema.conversation_open_loop_reference).where(
                            schema.conversation_open_loop_reference.c.open_loop_reference_id
                            == selector["open_loop_reference_id"]
                        )
                    ).mappings().one_or_none()
                if (
                    reference is None
                    or reference["open_loop_id"] != loop["open_loop_id"]
                    or reference["reference_contract_version"]
                    != selector["selector_contract_version"]
                    or reference["canonical_reference_key"] != selector["selector_key"]
                ):
                    fail(
                        "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                        "explicit selector does not match its durable open-loop reference",
                    )
                reference_kind = reference["reference_kind"]
                if reference_kind != DECISION_REFERENCE_KIND:
                    fail(
                        "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                        "explicit selector uses an unsupported reference kind",
                    )
            else:
                fail(
                    "CONVERSATION_OPEN_LOOP_PROJECTION_INVALID",
                    "open-loop selector uses an unsupported selection basis",
                )

        loop_context = {
            "selection_policy": selection_policy,
            "open_loop_id": str(loop["open_loop_id"]),
            "loop_kind": loop["loop_kind"],
            "opened_by_event": {
                "event_id": str(opening["event_id"]),
                "timeline_seq": int(opening["timeline_seq"]),
                "actor_kind": opening["actor_kind"],
                "event_kind": opening["event_kind"],
                "content_text": opening["content_text"],
            },
        }
        if reference_kind is not None:
            loop_context["reference_kind"] = reference_kind
        provider_context["conversation_open_loop_context"] = loop_context
        provider_context.pop("prior_timeline_context", None)
        return provider_context


__all__ = ["FoundationServices"]
