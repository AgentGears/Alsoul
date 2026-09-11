from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar import (
    CALENDAR_EVENTS_READ,
    AuthorityStateRevisionResult,
    CalendarReadPageFenceResult,
    FencePersonalCalendarReadPageCommand,
    GrantCalendarReadPermissionCommand,
    GrantCalendarReadPermissionResult,
    PrepareCalendarObservationResult,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    RegisterPersonalCalendarResourceResult,
    SetCredentialBindingStatusCommand,
    SetPermissionStatusCommand,
    SetPersonalResourceBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.storage import schema

from ._personal_calendar_base import (
    PersonalCalendarReadServices as _BasePersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
    all_day_event_interval,
    parse_personal_calendar_question,
    timed_event_overlaps_day,
)

CALENDAR_READ_PERMISSION_GRANT_TEXT = "Allow my companion to read my calendar."
_CALENDAR_READ_PERMISSION_GRANT_CONTRACT = "CALENDAR_READ_PERMISSION_GRANT_V1"
_GRANT_SOURCE_CONSUMPTION_SCOPE = "ConsumeCalendarReadPermissionGrantEvent"
_RESOURCE_REGISTRATION_SCOPE = "RegisterPersonalCalendarResource"
_OBSERVATION_SOURCE_BINDING_SCOPE = "BindPersonalCalendarObservationRequest"
_PAGE_FENCE_ATTEMPT_SCOPE = "ReservePersonalCalendarReadPageAttempt"


@dataclass(frozen=True, slots=True)
class _PreparedCalendarObservationCommand:
    operation_id: UUID
    observation_id: UUID
    source_interaction_event_id: UUID
    question_text: str


@dataclass(frozen=True, slots=True)
class _RelationshipStatusCommand:
    operation_id: UUID
    companion_person_id: UUID
    counterpart_id: UUID
    relationship_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class _CredentialStatusCommand:
    operation_id: UUID
    credential_binding_id: UUID
    status: str
    provider_scopes: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _PermissionStatusCommand:
    operation_id: UUID
    permission_id: UUID
    status: str


class PersonalCalendarReadServices(_BasePersonalCalendarReadServices):
    """Hardened first-slice F5.A admission and revocation boundary.

    The lower-level implementation owns append-oriented authority state and read-page
    fencing. This public service requires canonical counterpart-authored grant evidence,
    derives calendar-question semantics from canonical first-party input, and prevents
    revoked authority from being reactivated under the same semantic identity.
    """

    def register_calendar_resource(
        self, command: RegisterPersonalCalendarResourceCommand
    ) -> RegisterPersonalCalendarResourceResult:
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_RESOURCE_REGISTRATION_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return RegisterPersonalCalendarResourceResult(
                    UUID(replay["personal_resource_binding_id"])
                )

            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            if command.timezone_rules_version != self.time_resolver.rules_version:
                fail(
                    "CALENDAR_TIME_RULES_VERSION_MISMATCH",
                    "resource timezone rules do not match the trusted resolver",
                )
            try:
                ZoneInfo(command.calendar_timezone)
            except ZoneInfoNotFoundError:
                fail(
                    "CALENDAR_TIMEZONE_UNTRUSTED",
                    "calendar timezone is not available to the trusted resolver",
                )
            if not command.external_system_ref.strip() or not command.external_resource_ref.strip():
                fail(
                    "PERSONAL_RESOURCE_TARGET_INVALID",
                    "external system and resource references must be non-empty",
                )

            now = self.clock.now()
            self._ensure_personal_world_relationship_active(
                conn,
                relationship_id=command.relationship_id,
                committed_at=now,
            )
            if self._active_calendar_bindings(conn, command.relationship_id):
                fail(
                    "PERSONAL_CALENDAR_RESOURCE_AMBIGUOUS",
                    "the first F5.A slice permits exactly one active calendar resource per relationship",
                )

            timeline_head = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == command.relationship_id
                )
            ).mappings().one_or_none()
            if timeline_head is None:
                fail(
                    "RELATIONSHIP_TIMELINE_HEAD_MISSING",
                    "calendar resource activation requires the canonical relationship Timeline frontier",
                )
            activation_timeline_frontier = int(timeline_head["last_timeline_seq"])

            binding_id = self.ids.new()
            try:
                conn.execute(
                    insert(schema.personal_resource_binding).values(
                        personal_resource_binding_id=binding_id,
                        counterpart_id=command.counterpart_id,
                        relationship_id=command.relationship_id,
                        resource_kind="CALENDAR",
                        external_system_ref=command.external_system_ref,
                        external_resource_ref=command.external_resource_ref,
                        calendar_timezone=command.calendar_timezone,
                        timezone_rules_version=command.timezone_rules_version,
                        created_at=now,
                    )
                )
            except IntegrityError:
                fail(
                    "PERSONAL_RESOURCE_TARGET_ALREADY_BOUND",
                    "external calendar target is already bound",
                )
            conn.execute(
                insert(schema.personal_resource_binding_state).values(
                    personal_resource_binding_id=binding_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.personal_resource_binding_head).values(
                    personal_resource_binding_id=binding_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=_RESOURCE_REGISTRATION_SCOPE,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalResourceBinding",
                result_ref=binding_id,
                result_json={
                    "personal_resource_binding_id": str(binding_id),
                    "activation_timeline_frontier": activation_timeline_frontier,
                },
                committed_at=now,
            )
            return RegisterPersonalCalendarResourceResult(binding_id)

    def set_relationship_status(
        self, command: SetPersonalWorldRelationshipStatusCommand
    ) -> AuthorityStateRevisionResult:
        return super().set_relationship_status(
            _RelationshipStatusCommand(
                operation_id=command.operation_id,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
                status="ENDED",
            )
        )

    def set_resource_status(
        self, command: SetPersonalResourceBindingStatusCommand
    ) -> AuthorityStateRevisionResult:
        scope = "SetPersonalResourceBindingStatus"
        req = request_digest(asdict(command))
        if command.status not in {"INACTIVE", "REVOKED"}:
            fail(
                "PERSONAL_RESOURCE_STATUS_INVALID",
                "first-slice resource state cannot be reactivated in place",
            )

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return AuthorityStateRevisionResult(
                    command.personal_resource_binding_id,
                    int(replay["revision"]),
                )

            entity = conn.execute(
                select(schema.personal_resource_binding).where(
                    schema.personal_resource_binding.c.personal_resource_binding_id
                    == command.personal_resource_binding_id
                )
            ).mappings().one_or_none()
            if entity is None:
                fail(
                    "AUTHORITY_ENTITY_NOT_FOUND",
                    "PersonalResourceBindingState target does not exist",
                )

            current, parent = self._current_state(
                conn,
                state_table=schema.personal_resource_binding_state,
                head_table=schema.personal_resource_binding_head,
                key_name="personal_resource_binding_id",
                key_value=command.personal_resource_binding_id,
            )
            if current["status"] == "REVOKED" and command.status != "REVOKED":
                fail(
                    "PERSONAL_RESOURCE_REVOCATION_TERMINAL",
                    "a revoked personal resource binding cannot become active or inactive again",
                )

            if current["status"] == command.status:
                revision = parent
            else:
                revision = parent + 1
                now = self.clock.now()
                conn.execute(
                    insert(schema.personal_resource_binding_state).values(
                        personal_resource_binding_id=command.personal_resource_binding_id,
                        revision=revision,
                        parent_revision=parent,
                        status=command.status,
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_resource_binding_head,
                    key_name="personal_resource_binding_id",
                    key_value=command.personal_resource_binding_id,
                    expected_revision=parent,
                    new_revision=revision,
                    conflict_code="PERSONAL_RESOURCE_BINDING_STATE_CONFLICT",
                )

            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalResourceBindingState",
                result_ref=command.personal_resource_binding_id,
                result_json={
                    "entity_id": str(command.personal_resource_binding_id),
                    "revision": revision,
                },
                committed_at=now,
            )
            return AuthorityStateRevisionResult(
                command.personal_resource_binding_id,
                revision,
            )

    def set_credential_status(
        self, command: SetCredentialBindingStatusCommand
    ) -> AuthorityStateRevisionResult:
        return super().set_credential_status(
            _CredentialStatusCommand(
                operation_id=command.operation_id,
                credential_binding_id=command.credential_binding_id,
                status="REVOKED",
                provider_scopes=None,
            )
        )

    def set_permission_status(
        self, command: SetPermissionStatusCommand
    ) -> AuthorityStateRevisionResult:
        return super().set_permission_status(
            _PermissionStatusCommand(
                operation_id=command.operation_id,
                permission_id=command.permission_id,
                status="REVOKED",
            )
        )

    def grant_read_permission(
        self, command: GrantCalendarReadPermissionCommand
    ) -> GrantCalendarReadPermissionResult:
        scope = "GrantCalendarReadPermission"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return GrantCalendarReadPermissionResult(UUID(replay["permission_id"]))

            relationship = self._require_relationship(
                conn,
                companion_person_id=command.holder_companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            if not command.capability_contract_version.strip() or not command.grant_policy_version.strip():
                fail(
                    "PERMISSION_PROVENANCE_INVALID",
                    "capability and grant policy versions must be explicit",
                )

            grant_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            if (
                grant_event is None
                or grant_event["event_kind"] != "COUNTERPART_INPUT"
                or grant_event["relationship_id"] != command.relationship_id
                or grant_event["actor_ref"] != command.counterpart_id
                or grant_event["surface_binding_id"] is None
                or grant_event["channel_binding_id"] is None
                or grant_event["content_text"] != CALENDAR_READ_PERMISSION_GRANT_TEXT
            ):
                fail(
                    "PERMISSION_PROVENANCE_INVALID",
                    "calendar read Permission lacks the exact trusted counterpart grant evidence",
                )

            relationship_state, _ = self._current_relationship_authority(
                conn, command.relationship_id
            )
            if relationship_state["status"] != "ACTIVE":
                fail(
                    "RELATIONSHIP_NOT_ACTIVE",
                    "personal-world relationship authority is not active",
                )

            binding, binding_state, _ = self._current_resource(
                conn, command.personal_resource_binding_id
            )
            active = self._active_calendar_bindings(conn, command.relationship_id)
            if (
                binding["relationship_id"] != command.relationship_id
                or binding["counterpart_id"] != command.counterpart_id
                or binding_state["status"] != "ACTIVE"
                or len(active) != 1
                or active[0]["personal_resource_binding_id"]
                != command.personal_resource_binding_id
            ):
                fail(
                    "PERMISSION_RESOURCE_MISMATCH",
                    "Permission target is not the unique active calendar for this relationship",
                )

            registration_receipt = conn.execute(
                select(schema.operation_receipt).where(
                    schema.operation_receipt.c.operation_scope
                    == _RESOURCE_REGISTRATION_SCOPE,
                    schema.operation_receipt.c.result_ref
                    == command.personal_resource_binding_id,
                )
            ).mappings().one_or_none()
            if registration_receipt is None:
                fail(
                    "PERMISSION_PROVENANCE_INVALID",
                    "calendar Permission requires trusted resource-activation provenance",
                )
            registration_result = registration_receipt["result_json"]
            if not isinstance(registration_result, dict) or "activation_timeline_frontier" not in registration_result:
                fail(
                    "PERMISSION_PROVENANCE_INVALID",
                    "calendar resource activation lacks a canonical Timeline frontier",
                )
            activation_timeline_frontier = int(
                registration_result["activation_timeline_frontier"]
            )
            if int(grant_event["timeline_seq"]) <= activation_timeline_frontier:
                fail(
                    "PERMISSION_PROVENANCE_INVALID",
                    "calendar grant evidence must follow activation of the selected resource",
                )

            source_event_ref = str(command.source_interaction_event_id)
            consumed = conn.execute(
                select(schema.operation_receipt).where(
                    schema.operation_receipt.c.operation_scope
                    == _GRANT_SOURCE_CONSUMPTION_SCOPE,
                    schema.operation_receipt.c.operation_id
                    == command.source_interaction_event_id,
                )
            ).mappings().one_or_none()
            if consumed is not None:
                fail(
                    "PERMISSION_PROVENANCE_REUSED",
                    "one counterpart grant event cannot mint another Permission",
                )

            grantor_ref = relationship["counterpart_id"]
            permission_id = self.ids.new()
            now = self.clock.now()
            consumption_digest = request_digest(
                {
                    "source_interaction_event_id": command.source_interaction_event_id,
                    "relationship_id": command.relationship_id,
                    "personal_resource_binding_id": command.personal_resource_binding_id,
                    "capability_semantic_operation": CALENDAR_EVENTS_READ,
                    "capability_contract_version": command.capability_contract_version,
                    "grant_policy_version": command.grant_policy_version,
                }
            )
            try:
                save_operation_receipt(
                    conn,
                    scope=_GRANT_SOURCE_CONSUMPTION_SCOPE,
                    operation_id=command.source_interaction_event_id,
                    req_digest=consumption_digest,
                    result_kind="ConsumedCalendarReadPermissionGrantEvent",
                    result_ref=permission_id,
                    result_json={
                        "source_interaction_event_id": source_event_ref,
                        "permission_id": str(permission_id),
                    },
                    committed_at=now,
                )
            except IntegrityError:
                fail(
                    "PERMISSION_PROVENANCE_REUSED",
                    "one counterpart grant event cannot mint another Permission",
                )

            conn.execute(
                insert(schema.permission_grant).values(
                    permission_id=permission_id,
                    holder_companion_person_id=command.holder_companion_person_id,
                    counterpart_id=command.counterpart_id,
                    relationship_id=command.relationship_id,
                    personal_resource_binding_id=command.personal_resource_binding_id,
                    capability_semantic_operation=CALENDAR_EVENTS_READ,
                    capability_contract_version=command.capability_contract_version,
                    operation_class="READ",
                    grantor_ref=grantor_ref,
                    grant_source="FIRST_PARTY_COUNTERPART",
                    grant_policy_version=command.grant_policy_version,
                    constraints_json={
                        "resource_kind": "CALENDAR",
                        "grant_contract_version": _CALENDAR_READ_PERMISSION_GRANT_CONTRACT,
                        "grant_source_event_id": source_event_ref,
                        "resource_activation_timeline_frontier": activation_timeline_frontier,
                    },
                    granted_at=now,
                    expires_at=None,
                )
            )
            conn.execute(
                insert(schema.permission_state).values(
                    permission_id=permission_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.permission_head).values(
                    permission_id=permission_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="Permission",
                result_ref=permission_id,
                result_json={"permission_id": str(permission_id)},
                committed_at=now,
            )
            return GrantCalendarReadPermissionResult(permission_id)

    def _bind_current_observation_request(
        self, command: PreparePersonalCalendarObservationCommand
    ) -> str:
        binding_req = request_digest(
            {
                "observation_id": command.observation_id,
                "source_interaction_event_id": command.source_interaction_event_id,
            }
        )
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_OBSERVATION_SOURCE_BINDING_SCOPE,
                operation_id=command.observation_id,
                expected_request_digest=binding_req,
            )
            if replay:
                return (
                    "What's on my calendar on "
                    f"{replay['requested_local_date']}?"
                )

            observation = conn.execute(
                select(schema.observation).where(
                    schema.observation.c.observation_id == command.observation_id
                )
            ).mappings().one_or_none()
            if observation is None or observation["status"] != "STARTED":
                fail(
                    "CALENDAR_OBSERVATION_NOT_OPEN",
                    "calendar observation must exist in STARTED state",
                )
            if observation["acquisition_kind"] != "PERSONAL_CALENDAR_READ":
                fail(
                    "CALENDAR_OBSERVATION_KIND_MISMATCH",
                    "observation is not a personal-calendar acquisition",
                )

            investigation = conn.execute(
                select(schema.investigation).where(
                    schema.investigation.c.investigation_id
                    == observation["investigation_id"]
                )
            ).mappings().one_or_none()
            source_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id
                    == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            relationship = None
            if investigation is not None and investigation["relationship_id"] is not None:
                relationship = conn.execute(
                    select(schema.relationship_identity).where(
                        schema.relationship_identity.c.relationship_id
                        == investigation["relationship_id"]
                    )
                ).mappings().one_or_none()

            if (
                investigation is None
                or relationship is None
                or source_event is None
                or source_event["event_kind"] != "COUNTERPART_INPUT"
                or source_event["actor_kind"] != "COUNTERPART"
                or source_event["relationship_id"] != investigation["relationship_id"]
                or source_event["actor_ref"] != relationship["counterpart_id"]
                or source_event["surface_binding_id"] is None
                or source_event["channel_binding_id"] is None
            ):
                fail(
                    "CALENDAR_SOURCE_INTERACTION_INVALID",
                    "calendar read must originate from the matching counterpart input",
                )

            requested_date = parse_personal_calendar_question(
                source_event["content_text"]
            )
            timeline_head = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id
                    == investigation["relationship_id"]
                )
            ).mappings().one_or_none()
            source_timeline_seq = int(source_event["timeline_seq"])
            if (
                timeline_head is None
                or source_timeline_seq != int(timeline_head["last_timeline_seq"])
            ):
                fail(
                    "CALENDAR_SOURCE_INTERACTION_NOT_CURRENT",
                    "calendar acquisition must bind the current relationship Timeline request",
                )

            # Linearize this observation's request binding against any newer Timeline
            # append. Once admitted, retries may resume the same bound acquisition, but
            # a fresh Observation cannot reuse this historical request.
            changed = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id
                    == investigation["relationship_id"],
                    schema.relationship_timeline_head.c.last_timeline_seq
                    == source_timeline_seq,
                )
                .values(last_timeline_seq=source_timeline_seq)
            )
            if changed.rowcount != 1:
                fail(
                    "CALENDAR_SOURCE_INTERACTION_NOT_CURRENT",
                    "calendar request stopped being the Timeline frontier before admission",
                )

            now = self.clock.now()
            try:
                save_operation_receipt(
                    conn,
                    scope=_OBSERVATION_SOURCE_BINDING_SCOPE,
                    operation_id=command.observation_id,
                    req_digest=binding_req,
                    result_kind="PersonalCalendarObservationRequestBinding",
                    result_ref=command.source_interaction_event_id,
                    result_json={
                        "observation_id": str(command.observation_id),
                        "source_interaction_event_id": str(
                            command.source_interaction_event_id
                        ),
                        "source_timeline_frontier": source_timeline_seq,
                        "requested_local_date": requested_date.isoformat(),
                    },
                    committed_at=now,
                )
            except IntegrityError:
                fail(
                    "CALENDAR_SOURCE_INTERACTION_BINDING_CONFLICT",
                    "calendar observation request binding was admitted concurrently",
                )

            return source_event["content_text"]

    def prepare_observation(
        self, command: PreparePersonalCalendarObservationCommand
    ) -> PrepareCalendarObservationResult:
        canonical_question = self._bind_current_observation_request(command)
        return super().prepare_observation(
            _PreparedCalendarObservationCommand(
                operation_id=command.operation_id,
                observation_id=command.observation_id,
                source_interaction_event_id=command.source_interaction_event_id,
                question_text=canonical_question,
            )
        )

    def fence_read_page(
        self, command: FencePersonalCalendarReadPageCommand
    ) -> CalendarReadPageFenceResult:
        if command.page_ordinal < 0:
            fail(
                "CALENDAR_PAGE_ORDINAL_INVALID",
                "page ordinal must be non-negative",
            )

        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_PAGE_FENCE_ATTEMPT_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                fail(
                    "CALENDAR_PAGE_FENCE_REPLAY_NOT_AUTHORIZING",
                    "a prior fence attempt cannot be replayed as current transport authority",
                )

            now = self.clock.now()
            try:
                save_operation_receipt(
                    conn,
                    scope=_PAGE_FENCE_ATTEMPT_SCOPE,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="PersonalCalendarReadPageAttemptReservation",
                    result_ref=command.observation_id,
                    result_json={
                        "observation_id": str(command.observation_id),
                        "page_ordinal": command.page_ordinal,
                        "permission_id": str(command.permission_id),
                        "credential_binding_id": str(
                            command.credential_binding_id
                        ),
                    },
                    committed_at=now,
                )
            except IntegrityError:
                fail(
                    "CALENDAR_PAGE_FENCE_REPLAY_NOT_AUTHORIZING",
                    "calendar page fence attempt was already reserved",
                )

        return super().fence_read_page(command)


__all__ = [
    "CALENDAR_READ_PERMISSION_GRANT_TEXT",
    "PersonalCalendarReadServices",
    "ZoneInfoCalendarTimeResolver",
    "all_day_event_interval",
    "parse_personal_calendar_question",
    "timed_event_overlaps_day",
]
