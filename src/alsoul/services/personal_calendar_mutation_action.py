from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_mutation import (
    CALENDAR_CREATE_EFFECT_CLASS,
    CALENDAR_EVENT_CREATE,
    CalendarCreateActionResult,
    CreateCalendarActionCommand,
)
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar import PersonalCalendarReadServices
from alsoul.storage import schema

_CREATE_PATTERN = re.compile(
    r"^Add '(?P<title>[^'\n]{1,256})' to my calendar from "
    r"(?P<start>\S+) to (?P<end>\S+)\.$"
)
_ACTION_SCOPE = "CreatePersonalCalendarAction"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        fail("CALENDAR_CREATE_TIME_OFFSET_REQUIRED", "calendar-create timestamps must carry explicit offsets")
    return value.astimezone(timezone.utc)


def _aware_compare(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_calendar_create_request(text: str) -> tuple[str, str, str, datetime, datetime]:
    match = _CREATE_PATTERN.fullmatch(text)
    if match is None:
        fail("CALENDAR_CREATE_REQUEST_UNSUPPORTED", "request is outside the first F5.B explicit-offset create grammar")
    title, start_text, end_text = match.group("title"), match.group("start"), match.group("end")
    try:
        start, end = datetime.fromisoformat(start_text), datetime.fromisoformat(end_text)
    except ValueError:
        fail("CALENDAR_CREATE_TIME_INVALID", "calendar-create timestamps must be valid ISO offset-aware timestamps")
    start_utc, end_utc = _aware_utc(start), _aware_utc(end)
    if end_utc <= start_utc:
        fail("CALENDAR_CREATE_INTERVAL_INVALID", "calendar-create end must be after start")
    return title, start_text, end_text, start_utc, end_utc


class PersonalCalendarMutationActionServices(PersonalCalendarReadServices):
    def create_action(self, command: CreateCalendarActionCommand) -> CalendarCreateActionResult:
        req = request_digest(asdict(command))
        if not command.capability_contract_version.strip():
            fail(
                "CALENDAR_CREATE_CAPABILITY_INVALID",
                "calendar-create capability contract version must be explicit",
            )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ACTION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return CalendarCreateActionResult(
                    action_id=UUID(replay["action_id"]),
                    personal_resource_binding_id=UUID(
                        replay["personal_resource_binding_id"]
                    ),
                    action_digest=replay["action_digest"],
                )
            source = self._counterpart_event(
                conn,
                command.source_interaction_event_id,
                required_text=None,
                require_frontier=True,
            )
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id
                    == source["relationship_id"]
                )
            ).mappings().one()
            relationship_state, _ = self._current_relationship_authority(
                conn, source["relationship_id"]
            )
            if relationship_state["status"] != "ACTIVE":
                fail("RELATIONSHIP_NOT_ACTIVE", "calendar-create relationship is not active")
            active = self._active_calendar_bindings(conn, source["relationship_id"])
            if len(active) != 1:
                fail(
                    "PERSONAL_CALENDAR_RESOURCE_AMBIGUOUS",
                    "calendar-create requires exactly one active calendar resource",
                )
            resource = active[0]
            if resource["counterpart_id"] != relationship["counterpart_id"]:
                fail(
                    "PERSONAL_RESOURCE_BINDING_NOT_CURRENT",
                    "active calendar is not associated with the current counterpart",
                )
            existing = conn.execute(
                select(schema.personal_calendar_action).where(
                    schema.personal_calendar_action.c.source_interaction_event_id
                    == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            if existing is not None:
                fail(
                    "CALENDAR_CREATE_ACTION_SOURCE_REUSED",
                    "one mutation request cannot mint multiple Actions",
                )
            title, start_text, end_text, start_utc, end_utc = parse_calendar_create_request(
                source["content_text"]
            )
            action_id = self.ids.new()
            material = {
                "action_id": str(action_id),
                "relationship_id": str(source["relationship_id"]),
                "counterpart_id": str(relationship["counterpart_id"]),
                "personal_resource_binding_id": str(
                    resource["personal_resource_binding_id"]
                ),
                "source_interaction_event_id": str(command.source_interaction_event_id),
                "capability_semantic_operation": CALENDAR_EVENT_CREATE,
                "capability_contract_version": command.capability_contract_version,
                "effect_class": CALENDAR_CREATE_EFFECT_CLASS,
                "title": title,
                "start_timestamp_text": start_text,
                "end_timestamp_text": end_text,
                "normalized_start_at": start_utc.isoformat(),
                "normalized_end_at": end_utc.isoformat(),
            }
            action_digest = sha256_text(canonical_json(material))
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_action).values(
                    action_id=action_id,
                    relationship_id=source["relationship_id"],
                    counterpart_id=relationship["counterpart_id"],
                    personal_resource_binding_id=resource[
                        "personal_resource_binding_id"
                    ],
                    source_interaction_event_id=command.source_interaction_event_id,
                    capability_semantic_operation=CALENDAR_EVENT_CREATE,
                    capability_contract_version=command.capability_contract_version,
                    effect_class=CALENDAR_CREATE_EFFECT_CLASS,
                    title=title,
                    start_timestamp_text=start_text,
                    end_timestamp_text=end_text,
                    normalized_start_at=start_utc,
                    normalized_end_at=end_utc,
                    action_digest=action_digest,
                    created_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=_ACTION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarAction",
                result_ref=action_id,
                result_json={
                    "action_id": str(action_id),
                    "personal_resource_binding_id": str(
                        resource["personal_resource_binding_id"]
                    ),
                    "action_digest": action_digest,
                },
                committed_at=now,
            )
            return CalendarCreateActionResult(
                action_id,
                resource["personal_resource_binding_id"],
                action_digest,
            )

    def _counterpart_event(
        self,
        conn,
        event_id: UUID,
        *,
        required_text: str | None,
        require_frontier: bool,
    ):
        event = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == event_id
            )
        ).mappings().one_or_none()
        if event is None:
            fail("CALENDAR_CREATE_SOURCE_EVENT_MISSING", "source interaction does not exist")
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id
                == event["relationship_id"]
            )
        ).mappings().one_or_none()
        if (
            relationship is None
            or event["event_kind"] != "COUNTERPART_INPUT"
            or event["actor_kind"] != "COUNTERPART"
            or event["actor_ref"] != relationship["counterpart_id"]
            or event["surface_binding_id"] is None
            or event["channel_binding_id"] is None
            or (required_text is not None and event["content_text"] != required_text)
        ):
            fail(
                "CALENDAR_CREATE_SOURCE_EVENT_INVALID",
                "source interaction is not trusted counterpart input for this ceremony",
            )
        if require_frontier:
            frontier = conn.execute(
                select(schema.relationship_timeline_head.c.last_timeline_seq).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == event["relationship_id"]
                )
            ).scalar_one_or_none()
            if frontier is None or int(frontier) != int(event["timeline_seq"]):
                fail(
                    "CALENDAR_CREATE_SOURCE_EVENT_NOT_CURRENT",
                    "source interaction is not the current relationship Timeline frontier",
                )
        return event


__all__ = ["PersonalCalendarMutationActionServices", "parse_calendar_create_request", "_aware_compare"]
