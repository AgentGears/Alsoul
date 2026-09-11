from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, Engine, and_, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar import (
    CALENDAR_EVENTS_READ,
    AuthorityStateRevisionResult,
    BindCalendarCredentialCommand,
    BindCalendarCredentialResult,
    CalendarDayWindow,
    CalendarReadPageFenceResult,
    FencePersonalCalendarReadPageCommand,
    GrantCalendarReadPermissionCommand,
    GrantCalendarReadPermissionResult,
    PrepareCalendarObservationResult,
    PreparePersonalCalendarObservationCommand,
    RegisterPersonalCalendarResourceCommand,
    RegisterPersonalCalendarResourceResult,
    SetCalendarReadPolicyCommand,
    SetCalendarReadPolicyResult,
    SetCredentialBindingStatusCommand,
    SetPermissionStatusCommand,
    SetPersonalResourceBindingStatusCommand,
    SetPersonalWorldRelationshipStatusCommand,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import load_operation_receipt, request_digest, save_operation_receipt
from alsoul.storage import schema

_CALENDAR_QUESTION = re.compile(
    r"^(?:What's on my calendar on|What do I have on my calendar on) "
    r"(?P<day>\d{4}-\d{2}-\d{2})\?$"
)


class ZoneInfoCalendarTimeResolver:
    """Resolve exact local calendar boundaries under one trusted rules-version label.

    The host is responsible for binding ``rules_version`` to the installed timezone
    rules before constructing this resolver. Resource metadata must match this exact
    label; the service never falls back to process-local timezone semantics.
    """

    def __init__(self, *, rules_version: str) -> None:
        if not rules_version.strip():
            raise ValueError("rules_version must be non-empty")
        self.rules_version = rules_version

    def resolve_midnight(self, *, zone_name: str, local_date: date) -> datetime:
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            fail("CALENDAR_TIMEZONE_UNTRUSTED", f"unknown calendar timezone: {zone_name}")

        naive = datetime.combine(local_date, time.min)
        candidates: dict[datetime, datetime] = {}
        for fold in (0, 1):
            local = naive.replace(tzinfo=zone, fold=fold)
            instant = local.astimezone(timezone.utc)
            round_trip = instant.astimezone(zone)
            if round_trip.replace(tzinfo=None) == naive:
                candidates[instant] = local

        if len(candidates) != 1:
            code = "CALENDAR_TIME_BOUNDARY_NONEXISTENT" if not candidates else "CALENDAR_TIME_BOUNDARY_AMBIGUOUS"
            fail(code, f"calendar midnight is not a unique instant for {zone_name} {local_date.isoformat()}")
        return next(iter(candidates)).astimezone(timezone.utc)

    def resolve_day(self, *, zone_name: str, local_date: date) -> CalendarDayWindow:
        start = self.resolve_midnight(zone_name=zone_name, local_date=local_date)
        end = self.resolve_midnight(zone_name=zone_name, local_date=date.fromordinal(local_date.toordinal() + 1))
        if end <= start:
            fail("CALENDAR_TIME_WINDOW_INVALID", "calendar day must have positive exact duration")
        return CalendarDayWindow(
            local_date=local_date,
            calendar_timezone=zone_name,
            timezone_rules_version=self.rules_version,
            window_start=start,
            window_end=end,
        )


def parse_personal_calendar_question(text: str) -> date:
    match = _CALENDAR_QUESTION.fullmatch(text)
    if match is None:
        fail("PERSONAL_CALENDAR_QUESTION_UNSUPPORTED", "question is outside the first F5.A absolute-date grammar")
    try:
        return date.fromisoformat(match.group("day"))
    except ValueError:
        fail("PERSONAL_CALENDAR_QUESTION_INVALID_DATE", "calendar question contains an invalid ISO date")


def timed_event_overlaps_day(*, window: CalendarDayWindow, event_start: datetime, event_end: datetime) -> bool:
    if event_start.tzinfo is None or event_end.tzinfo is None:
        fail("CALENDAR_EVENT_TIME_UNTRUSTED", "timed event boundaries must be offset-aware")
    if event_end <= event_start:
        fail("CALENDAR_EVENT_DURATION_UNSUPPORTED", "zero or negative-duration timed events are outside the first slice")
    return event_start < window.window_end and event_end > window.window_start


def all_day_event_interval(
    *,
    resolver: ZoneInfoCalendarTimeResolver,
    zone_name: str,
    start_date: date,
    end_date_exclusive: date,
) -> tuple[datetime, datetime]:
    if end_date_exclusive <= start_date:
        fail("CALENDAR_ALL_DAY_INTERVAL_INVALID", "all-day end date must be exclusive and after start date")
    start = resolver.resolve_midnight(zone_name=zone_name, local_date=start_date)
    end = resolver.resolve_midnight(zone_name=zone_name, local_date=end_date_exclusive)
    return start, end


def _normalized_scopes(scopes: tuple[str, ...]) -> list[str]:
    cleaned = sorted({scope.strip() for scope in scopes if scope.strip()})
    if not cleaned:
        fail("CREDENTIAL_PROVIDER_SCOPE_MISSING", "at least one provider technical scope is required")
    return cleaned


def _aware_for_comparison(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class PersonalCalendarReadServices:
    """Trusted F5.A authority, time, and per-page dispatch-fence boundary.

    This service deliberately stops before provider transport. A caller may issue a
    personal-calendar page request only after ``fence_read_page`` returns and commits.
    The returned fence identifies the exact authority state that won the ordering race
    against revocation/unbinding for that one prospective transport.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        time_resolver: ZoneInfoCalendarTimeResolver,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.time_resolver = time_resolver
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def register_calendar_resource(
        self, command: RegisterPersonalCalendarResourceCommand
    ) -> RegisterPersonalCalendarResourceResult:
        scope = "RegisterPersonalCalendarResource"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return RegisterPersonalCalendarResourceResult(UUID(replay["personal_resource_binding_id"]))

            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            if command.timezone_rules_version != self.time_resolver.rules_version:
                fail("CALENDAR_TIME_RULES_VERSION_MISMATCH", "resource timezone rules do not match the trusted resolver")
            try:
                ZoneInfo(command.calendar_timezone)
            except ZoneInfoNotFoundError:
                fail("CALENDAR_TIMEZONE_UNTRUSTED", "calendar timezone is not available to the trusted resolver")
            if not command.external_system_ref.strip() or not command.external_resource_ref.strip():
                fail("PERSONAL_RESOURCE_TARGET_INVALID", "external system and resource references must be non-empty")

            self._ensure_personal_world_relationship_active(
                conn,
                relationship_id=command.relationship_id,
                committed_at=self.clock.now(),
            )
            active = self._active_calendar_bindings(conn, command.relationship_id)
            if active:
                fail(
                    "PERSONAL_CALENDAR_RESOURCE_AMBIGUOUS",
                    "the first F5.A slice permits exactly one active calendar resource per relationship",
                )

            binding_id = self.ids.new()
            now = self.clock.now()
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
                fail("PERSONAL_RESOURCE_TARGET_ALREADY_BOUND", "external calendar target is already bound")
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
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalResourceBinding",
                result_ref=binding_id,
                result_json={"personal_resource_binding_id": str(binding_id)},
                committed_at=now,
            )
            return RegisterPersonalCalendarResourceResult(binding_id)

    def bind_credential(self, command: BindCalendarCredentialCommand) -> BindCalendarCredentialResult:
        scope = "BindCalendarCredential"
        req = request_digest(asdict(command))
        scopes = _normalized_scopes(command.provider_scopes)
        if not command.secret_ref.strip():
            fail("CREDENTIAL_SECRET_REF_INVALID", "credential binding requires a non-secret reference")
        if not command.external_system_ref.strip() or not command.external_principal_ref.strip():
            fail("CREDENTIAL_TARGET_INVALID", "credential external system/principal references must be non-empty")
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return BindCalendarCredentialResult(UUID(replay["credential_binding_id"]))
            credential_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.credential_binding).values(
                    credential_binding_id=credential_id,
                    external_system_ref=command.external_system_ref,
                    external_principal_ref=command.external_principal_ref,
                    secret_ref=command.secret_ref,
                    created_at=now,
                )
            )
            conn.execute(
                insert(schema.credential_binding_state).values(
                    credential_binding_id=credential_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    provider_scopes_json=scopes,
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.credential_binding_head).values(
                    credential_binding_id=credential_id,
                    current_revision=1,
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="CredentialBinding",
                result_ref=credential_id,
                result_json={"credential_binding_id": str(credential_id)},
                committed_at=now,
            )
            return BindCalendarCredentialResult(credential_id)

    def grant_read_permission(
        self, command: GrantCalendarReadPermissionCommand
    ) -> GrantCalendarReadPermissionResult:
        scope = "GrantCalendarReadPermission"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return GrantCalendarReadPermissionResult(UUID(replay["permission_id"]))
            self._require_relationship(
                conn,
                companion_person_id=command.holder_companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            if command.grantor_ref != command.counterpart_id:
                fail("PERMISSION_GRANTOR_UNAUTHORIZED", "first-slice read Permission must be granted by the bound counterpart")
            if not command.capability_contract_version.strip() or not command.grant_policy_version.strip():
                fail("PERMISSION_PROVENANCE_INVALID", "capability and grant policy versions must be explicit")
            relationship_state, _ = self._current_relationship_authority(conn, command.relationship_id)
            if relationship_state["status"] != "ACTIVE":
                fail("RELATIONSHIP_NOT_ACTIVE", "personal-world relationship authority is not active")
            binding, binding_state, _ = self._current_resource(conn, command.personal_resource_binding_id)
            if (
                binding["relationship_id"] != command.relationship_id
                or binding["counterpart_id"] != command.counterpart_id
                or binding_state["status"] != "ACTIVE"
            ):
                fail("PERMISSION_RESOURCE_MISMATCH", "Permission target is not the active calendar resource for this relationship")
            permission_id = self.ids.new()
            now = self.clock.now()
            if command.expires_at is not None and _aware_for_comparison(command.expires_at) <= _aware_for_comparison(now):
                fail("PERMISSION_EXPIRY_INVALID", "Permission expiry must be in the future at grant time")
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
                    grantor_ref=command.grantor_ref,
                    grant_source="FIRST_PARTY_COUNTERPART",
                    grant_policy_version=command.grant_policy_version,
                    constraints_json={"resource_kind": "CALENDAR"},
                    granted_at=now,
                    expires_at=command.expires_at,
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
            conn.execute(insert(schema.permission_head).values(permission_id=permission_id, current_revision=1))
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

    def set_read_policy(self, command: SetCalendarReadPolicyCommand) -> SetCalendarReadPolicyResult:
        scope = "SetPersonalCalendarReadPolicy"
        req = request_digest(asdict(command))
        if command.status not in {"ALLOW", "DENY"}:
            fail("CALENDAR_READ_POLICY_INVALID", "unsupported calendar read policy status")
        if not all(
            value.strip()
            for value in (
                command.capability_contract_version,
                command.ai_policy_version,
                command.resource_scope_version,
                command.required_provider_scope,
                command.permission_grant_policy_version,
            )
        ):
            fail("CALENDAR_READ_POLICY_INVALID", "all calendar read policy versions/scopes must be explicit")
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return SetCalendarReadPolicyResult(command.relationship_id, int(replay["revision"]))
            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            relationship_state, _ = self._current_relationship_authority(conn, command.relationship_id)
            if relationship_state["status"] != "ACTIVE" and command.status == "ALLOW":
                fail("RELATIONSHIP_NOT_ACTIVE", "cannot allow personal-calendar reading on an ended relationship")
            allowed = []
            for binding_id in command.allowed_resource_binding_ids:
                binding, _, _ = self._current_resource(conn, binding_id)
                if binding["relationship_id"] != command.relationship_id or binding["counterpart_id"] != command.counterpart_id:
                    fail("RESOURCE_SCOPE_MISMATCH", "read policy references a calendar outside this relationship")
                allowed.append(str(binding_id))
            if command.status == "ALLOW" and not allowed:
                fail("RESOURCE_SCOPE_EMPTY", "allow policy must name at least one calendar resource")

            head = conn.execute(
                select(schema.personal_calendar_read_policy_head).where(
                    schema.personal_calendar_read_policy_head.c.relationship_id == command.relationship_id
                )
            ).mappings().one_or_none()
            parent = int(head["current_revision"]) if head else None
            revision = 1 if parent is None else parent + 1
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_read_policy_revision).values(
                    relationship_id=command.relationship_id,
                    revision=revision,
                    parent_revision=parent,
                    capability_semantic_operation=CALENDAR_EVENTS_READ,
                    capability_contract_version=command.capability_contract_version,
                    capability_effect_class="READ_ONLY",
                    ai_policy_version=command.ai_policy_version,
                    resource_scope_version=command.resource_scope_version,
                    required_provider_scope=command.required_provider_scope,
                    permission_grant_policy_version=command.permission_grant_policy_version,
                    allowed_resource_binding_ids_json=allowed,
                    status=command.status,
                    committed_at=now,
                )
            )
            if head is None:
                conn.execute(
                    insert(schema.personal_calendar_read_policy_head).values(
                        relationship_id=command.relationship_id,
                        current_revision=revision,
                    )
                )
            else:
                changed = conn.execute(
                    update(schema.personal_calendar_read_policy_head)
                    .where(
                        schema.personal_calendar_read_policy_head.c.relationship_id == command.relationship_id,
                        schema.personal_calendar_read_policy_head.c.current_revision == parent,
                    )
                    .values(current_revision=revision)
                )
                if changed.rowcount != 1:
                    fail("CALENDAR_READ_POLICY_CONFLICT", "calendar read policy advanced concurrently")
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarReadPolicyRevision",
                result_ref=command.relationship_id,
                result_json={"relationship_id": str(command.relationship_id), "revision": revision},
                committed_at=now,
            )
            return SetCalendarReadPolicyResult(command.relationship_id, revision)

    def set_relationship_status(
        self, command: SetPersonalWorldRelationshipStatusCommand
    ) -> AuthorityStateRevisionResult:
        scope = "SetPersonalWorldRelationshipStatus"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return AuthorityStateRevisionResult(command.relationship_id, int(replay["revision"]))
            self._require_relationship(
                conn,
                companion_person_id=command.companion_person_id,
                counterpart_id=command.counterpart_id,
                relationship_id=command.relationship_id,
            )
            revision = self._append_relationship_authority_state(conn, command.relationship_id, command.status)
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalWorldRelationshipState",
                result_ref=command.relationship_id,
                result_json={"entity_id": str(command.relationship_id), "revision": revision},
                committed_at=now,
            )
            return AuthorityStateRevisionResult(command.relationship_id, revision)

    def set_resource_status(
        self, command: SetPersonalResourceBindingStatusCommand
    ) -> AuthorityStateRevisionResult:
        return self._set_entity_status(
            command=command,
            scope="SetPersonalResourceBindingStatus",
            entity_table=schema.personal_resource_binding,
            entity_key="personal_resource_binding_id",
            state_table=schema.personal_resource_binding_state,
            head_table=schema.personal_resource_binding_head,
            state_status=command.status,
            result_kind="PersonalResourceBindingState",
        )

    def set_credential_status(
        self, command: SetCredentialBindingStatusCommand
    ) -> AuthorityStateRevisionResult:
        scope = "SetCredentialBindingStatus"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return AuthorityStateRevisionResult(command.credential_binding_id, int(replay["revision"]))
            credential = conn.execute(
                select(schema.credential_binding).where(
                    schema.credential_binding.c.credential_binding_id == command.credential_binding_id
                )
            ).mappings().one_or_none()
            if credential is None:
                fail("CREDENTIAL_BINDING_NOT_FOUND", "credential binding does not exist")
            current, parent = self._current_state(
                conn,
                state_table=schema.credential_binding_state,
                head_table=schema.credential_binding_head,
                key_name="credential_binding_id",
                key_value=command.credential_binding_id,
            )
            scopes = (
                _normalized_scopes(command.provider_scopes)
                if command.provider_scopes is not None
                else list(current["provider_scopes_json"])
            )
            revision = parent + 1
            now = self.clock.now()
            conn.execute(
                insert(schema.credential_binding_state).values(
                    credential_binding_id=command.credential_binding_id,
                    revision=revision,
                    parent_revision=parent,
                    status=command.status,
                    provider_scopes_json=scopes,
                    committed_at=now,
                )
            )
            self._advance_head(
                conn,
                head_table=schema.credential_binding_head,
                key_name="credential_binding_id",
                key_value=command.credential_binding_id,
                expected_revision=parent,
                new_revision=revision,
                conflict_code="CREDENTIAL_BINDING_STATE_CONFLICT",
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="CredentialBindingState",
                result_ref=command.credential_binding_id,
                result_json={"entity_id": str(command.credential_binding_id), "revision": revision},
                committed_at=now,
            )
            return AuthorityStateRevisionResult(command.credential_binding_id, revision)

    def set_permission_status(self, command: SetPermissionStatusCommand) -> AuthorityStateRevisionResult:
        return self._set_entity_status(
            command=command,
            scope="SetPermissionStatus",
            entity_table=schema.permission_grant,
            entity_key="permission_id",
            state_table=schema.permission_state,
            head_table=schema.permission_head,
            state_status=command.status,
            result_kind="PermissionState",
        )

    def prepare_observation(
        self, command: PreparePersonalCalendarObservationCommand
    ) -> PrepareCalendarObservationResult:
        scope = "PreparePersonalCalendarObservation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                window = CalendarDayWindow(
                    local_date=date.fromisoformat(replay["local_date"]),
                    calendar_timezone=replay["calendar_timezone"],
                    timezone_rules_version=replay["timezone_rules_version"],
                    window_start=datetime.fromisoformat(replay["window_start"]),
                    window_end=datetime.fromisoformat(replay["window_end"]),
                )
                return PrepareCalendarObservationResult(
                    command.observation_id,
                    UUID(replay["personal_resource_binding_id"]),
                    window,
                )

            requested_date = parse_personal_calendar_question(command.question_text)
            observation = conn.execute(
                select(schema.observation).where(schema.observation.c.observation_id == command.observation_id)
            ).mappings().one_or_none()
            if observation is None or observation["status"] != "STARTED":
                fail("CALENDAR_OBSERVATION_NOT_OPEN", "calendar observation must exist in STARTED state")
            if observation["acquisition_kind"] != "PERSONAL_CALENDAR_READ":
                fail("CALENDAR_OBSERVATION_KIND_MISMATCH", "observation is not a personal-calendar acquisition")
            investigation = conn.execute(
                select(schema.investigation).where(
                    schema.investigation.c.investigation_id == observation["investigation_id"]
                )
            ).mappings().one()
            if investigation["relationship_id"] is None:
                fail("CALENDAR_OBSERVATION_RELATIONSHIP_REQUIRED", "personal-calendar acquisition requires a relationship")
            source_event = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.event_id == command.source_interaction_event_id
                )
            ).mappings().one_or_none()
            if (
                source_event is None
                or source_event["event_kind"] != "COUNTERPART_INPUT"
                or source_event["relationship_id"] != investigation["relationship_id"]
            ):
                fail("CALENDAR_SOURCE_INTERACTION_INVALID", "calendar read must originate from the matching counterpart input")

            active = self._active_calendar_bindings(conn, investigation["relationship_id"])
            if not active:
                fail("PERSONAL_CALENDAR_RESOURCE_UNAVAILABLE", "no active calendar resource is configured")
            if len(active) != 1:
                fail("PERSONAL_CALENDAR_RESOURCE_AMBIGUOUS", "more than one active calendar resource is configured")
            binding = active[0]
            if binding["timezone_rules_version"] != self.time_resolver.rules_version:
                fail("CALENDAR_TIME_RULES_VERSION_MISMATCH", "calendar rules version is not executable by this host")
            window = self.time_resolver.resolve_day(
                zone_name=binding["calendar_timezone"],
                local_date=requested_date,
            )
            now = self.clock.now()
            conn.execute(
                insert(schema.personal_calendar_observation_scope).values(
                    observation_id=command.observation_id,
                    source_interaction_event_id=command.source_interaction_event_id,
                    personal_resource_binding_id=binding["personal_resource_binding_id"],
                    requested_local_date=requested_date.isoformat(),
                    calendar_timezone=binding["calendar_timezone"],
                    timezone_rules_version=binding["timezone_rules_version"],
                    window_start=window.window_start,
                    window_end=window.window_end,
                    acquisition_started_at=now,
                    created_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarObservationScope",
                result_ref=command.observation_id,
                result_json={
                    "observation_id": str(command.observation_id),
                    "personal_resource_binding_id": str(binding["personal_resource_binding_id"]),
                    "local_date": requested_date.isoformat(),
                    "calendar_timezone": binding["calendar_timezone"],
                    "timezone_rules_version": binding["timezone_rules_version"],
                    "window_start": window.window_start.isoformat(),
                    "window_end": window.window_end.isoformat(),
                },
                committed_at=now,
            )
            return PrepareCalendarObservationResult(
                command.observation_id,
                binding["personal_resource_binding_id"],
                window,
            )

    def fence_read_page(
        self, command: FencePersonalCalendarReadPageCommand
    ) -> CalendarReadPageFenceResult:
        scope = "FencePersonalCalendarReadPage"
        req = request_digest(asdict(command))
        if command.page_ordinal < 0:
            fail("CALENDAR_PAGE_ORDINAL_INVALID", "page ordinal must be non-negative")
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return self._fence_result_from_json(replay)
            existing_page = conn.execute(
                select(schema.personal_calendar_read_authority_fence).where(
                    schema.personal_calendar_read_authority_fence.c.observation_id == command.observation_id,
                    schema.personal_calendar_read_authority_fence.c.page_ordinal == command.page_ordinal,
                )
            ).mappings().one_or_none()
            if existing_page is not None:
                fail("CALENDAR_PAGE_ALREADY_FENCED", "this logical page already has an authority fence")
            scope_row = conn.execute(
                select(schema.personal_calendar_observation_scope).where(
                    schema.personal_calendar_observation_scope.c.observation_id == command.observation_id
                )
            ).mappings().one_or_none()
            if scope_row is None:
                fail("CALENDAR_OBSERVATION_SCOPE_MISSING", "calendar observation has not been prepared")
            observation = conn.execute(
                select(schema.observation).where(schema.observation.c.observation_id == command.observation_id)
            ).mappings().one()
            if observation["status"] != "STARTED":
                fail("CALENDAR_OBSERVATION_NOT_OPEN", "cannot fence a page for a settled observation")
            investigation = conn.execute(
                select(schema.investigation).where(
                    schema.investigation.c.investigation_id == observation["investigation_id"]
                )
            ).mappings().one()
            relationship_id = investigation["relationship_id"]
            if relationship_id is None:
                fail("CALENDAR_OBSERVATION_RELATIONSHIP_REQUIRED", "personal-calendar read lacks a relationship")
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.relationship_id == relationship_id
                )
            ).mappings().one()

            relationship_state, relationship_revision = self._current_relationship_authority(conn, relationship_id)
            if relationship_state["status"] != "ACTIVE":
                fail("RELATIONSHIP_NOT_ACTIVE", "relationship authority was ended before read dispatch")
            binding, binding_state, binding_revision = self._current_resource(
                conn, scope_row["personal_resource_binding_id"]
            )
            if (
                binding_state["status"] != "ACTIVE"
                or binding["relationship_id"] != relationship_id
                or binding["counterpart_id"] != relationship["counterpart_id"]
            ):
                fail("PERSONAL_RESOURCE_BINDING_NOT_CURRENT", "calendar binding is not active/current for this relationship")

            permission = conn.execute(
                select(schema.permission_grant).where(schema.permission_grant.c.permission_id == command.permission_id)
            ).mappings().one_or_none()
            if permission is None:
                fail("CALENDAR_READ_PERMISSION_MISSING", "calendar read Permission does not exist")
            permission_state, permission_revision = self._current_state(
                conn,
                state_table=schema.permission_state,
                head_table=schema.permission_head,
                key_name="permission_id",
                key_value=command.permission_id,
            )
            now = self.clock.now()
            if permission_state["status"] != "ACTIVE":
                fail("CALENDAR_READ_PERMISSION_REVOKED", "calendar read Permission is not active")
            if permission["expires_at"] is not None and _aware_for_comparison(permission["expires_at"]) <= _aware_for_comparison(now):
                fail("CALENDAR_READ_PERMISSION_EXPIRED", "calendar read Permission has expired")
            if (
                permission["holder_companion_person_id"] != relationship["companion_person_id"]
                or permission["counterpart_id"] != relationship["counterpart_id"]
                or permission["relationship_id"] != relationship_id
                or permission["personal_resource_binding_id"] != binding["personal_resource_binding_id"]
                or permission["capability_semantic_operation"] != CALENDAR_EVENTS_READ
                or permission["operation_class"] != "READ"
                or permission["grantor_ref"] != relationship["counterpart_id"]
                or permission["grant_source"] != "FIRST_PARTY_COUNTERPART"
            ):
                fail("CALENDAR_READ_PERMISSION_MISMATCH", "Permission does not authorize this companion/relationship/calendar read")

            credential = conn.execute(
                select(schema.credential_binding).where(
                    schema.credential_binding.c.credential_binding_id == command.credential_binding_id
                )
            ).mappings().one_or_none()
            if credential is None:
                fail("CREDENTIAL_BINDING_NOT_FOUND", "credential binding does not exist")
            credential_state, credential_revision = self._current_state(
                conn,
                state_table=schema.credential_binding_state,
                head_table=schema.credential_binding_head,
                key_name="credential_binding_id",
                key_value=command.credential_binding_id,
            )
            if credential_state["status"] != "ACTIVE":
                fail("CREDENTIAL_BINDING_UNUSABLE", "credential binding is revoked")
            if credential["external_system_ref"] != binding["external_system_ref"]:
                fail("CREDENTIAL_BINDING_MISMATCH", "credential binding targets a different external system")

            policy, policy_revision = self._current_policy(conn, relationship_id)
            if policy["status"] != "ALLOW":
                fail("AI_CAPABILITY_POLICY_DENIED", "current personal-calendar read policy denies dispatch")
            if policy["capability_semantic_operation"] != CALENDAR_EVENTS_READ or policy["capability_effect_class"] != "READ_ONLY":
                fail("CAPABILITY_METADATA_INVALID", "calendar capability metadata is not trusted READ_ONLY semantics")
            if permission["capability_contract_version"] != policy["capability_contract_version"]:
                fail("CAPABILITY_CONTRACT_VERSION_MISMATCH", "Permission and executable capability versions differ")
            if permission["grant_policy_version"] != policy["permission_grant_policy_version"]:
                fail("PERMISSION_GRANT_POLICY_UNRECOGNIZED", "Permission grant policy version is not currently recognized")
            allowed_ids = {str(value) for value in policy["allowed_resource_binding_ids_json"]}
            if str(binding["personal_resource_binding_id"]) not in allowed_ids:
                fail("RESOURCE_SCOPE_DENIED", "selected calendar is outside current Resource Scope")
            scopes = {str(value) for value in credential_state["provider_scopes_json"]}
            if policy["required_provider_scope"] not in scopes:
                fail("PROVIDER_TECHNICAL_SCOPE_INSUFFICIENT", "credential lacks the provider scope required by the capability")

            # Authority linearization point. These compare-and-swap writes deliberately
            # touch every mutable authority head inside the same transaction that admits
            # the fence. A revocation/unbinding/policy change that wins first changes a
            # head and prevents the fence; a fence that wins first authorizes only this
            # exact may-have-dispatched page attempt.
            self._cas_head_same(
                conn,
                schema.personal_world_relationship_head,
                "relationship_id",
                relationship_id,
                relationship_revision,
                "RELATIONSHIP_AUTHORITY_CHANGED",
            )
            self._cas_head_same(
                conn,
                schema.personal_resource_binding_head,
                "personal_resource_binding_id",
                binding["personal_resource_binding_id"],
                binding_revision,
                "PERSONAL_RESOURCE_BINDING_CHANGED",
            )
            self._cas_head_same(
                conn,
                schema.permission_head,
                "permission_id",
                command.permission_id,
                permission_revision,
                "CALENDAR_READ_PERMISSION_CHANGED",
            )
            self._cas_head_same(
                conn,
                schema.credential_binding_head,
                "credential_binding_id",
                command.credential_binding_id,
                credential_revision,
                "CREDENTIAL_BINDING_CHANGED",
            )
            self._cas_head_same(
                conn,
                schema.personal_calendar_read_policy_head,
                "relationship_id",
                relationship_id,
                policy_revision,
                "CALENDAR_READ_POLICY_CHANGED",
            )

            fence_id = self.ids.new()
            conn.execute(
                insert(schema.personal_calendar_read_authority_fence).values(
                    authority_fence_id=fence_id,
                    observation_id=command.observation_id,
                    page_ordinal=command.page_ordinal,
                    relationship_id=relationship_id,
                    relationship_authority_revision=relationship_revision,
                    personal_resource_binding_id=binding["personal_resource_binding_id"],
                    resource_binding_state_revision=binding_revision,
                    permission_id=command.permission_id,
                    permission_state_revision=permission_revision,
                    credential_binding_id=command.credential_binding_id,
                    credential_state_revision=credential_revision,
                    policy_revision=policy_revision,
                    capability_contract_version=policy["capability_contract_version"],
                    ai_policy_version=policy["ai_policy_version"],
                    resource_scope_version=policy["resource_scope_version"],
                    authorized_at=now,
                )
            )
            payload = {
                "authority_fence_id": str(fence_id),
                "observation_id": str(command.observation_id),
                "page_ordinal": command.page_ordinal,
                "personal_resource_binding_id": str(binding["personal_resource_binding_id"]),
                "relationship_authority_revision": relationship_revision,
                "resource_binding_state_revision": binding_revision,
                "permission_state_revision": permission_revision,
                "credential_state_revision": credential_revision,
                "policy_revision": policy_revision,
            }
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="PersonalCalendarReadAuthorityFence",
                result_ref=fence_id,
                result_json=payload,
                committed_at=now,
            )
            return self._fence_result_from_json(payload)

    def _ensure_personal_world_relationship_active(
        self, conn: Connection, *, relationship_id: UUID, committed_at: datetime
    ) -> None:
        head = conn.execute(
            select(schema.personal_world_relationship_head).where(
                schema.personal_world_relationship_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            conn.execute(
                insert(schema.personal_world_relationship_state).values(
                    relationship_id=relationship_id,
                    revision=1,
                    parent_revision=None,
                    status="ACTIVE",
                    committed_at=committed_at,
                )
            )
            conn.execute(
                insert(schema.personal_world_relationship_head).values(
                    relationship_id=relationship_id,
                    current_revision=1,
                )
            )
            return
        state, _ = self._current_relationship_authority(conn, relationship_id)
        if state["status"] != "ACTIVE":
            fail("RELATIONSHIP_NOT_ACTIVE", "personal-world relationship authority is ended")

    def _append_relationship_authority_state(self, conn: Connection, relationship_id: UUID, status: str) -> int:
        current, parent = self._current_relationship_authority(conn, relationship_id)
        if current["status"] == status:
            return parent
        revision = parent + 1
        now = self.clock.now()
        conn.execute(
            insert(schema.personal_world_relationship_state).values(
                relationship_id=relationship_id,
                revision=revision,
                parent_revision=parent,
                status=status,
                committed_at=now,
            )
        )
        self._advance_head(
            conn,
            head_table=schema.personal_world_relationship_head,
            key_name="relationship_id",
            key_value=relationship_id,
            expected_revision=parent,
            new_revision=revision,
            conflict_code="RELATIONSHIP_AUTHORITY_STATE_CONFLICT",
        )
        return revision

    def _set_entity_status(
        self,
        *,
        command: Any,
        scope: str,
        entity_table: Any,
        entity_key: str,
        state_table: Any,
        head_table: Any,
        state_status: str,
        result_kind: str,
    ) -> AuthorityStateRevisionResult:
        req = request_digest(asdict(command))
        entity_id: UUID = getattr(command, entity_key)
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req
            )
            if replay:
                return AuthorityStateRevisionResult(entity_id, int(replay["revision"]))
            entity = conn.execute(select(entity_table).where(getattr(entity_table.c, entity_key) == entity_id)).mappings().one_or_none()
            if entity is None:
                fail("AUTHORITY_ENTITY_NOT_FOUND", f"{result_kind} target does not exist")
            current, parent = self._current_state(
                conn,
                state_table=state_table,
                head_table=head_table,
                key_name=entity_key,
                key_value=entity_id,
            )
            if current["status"] == state_status:
                revision = parent
            else:
                revision = parent + 1
                now = self.clock.now()
                conn.execute(
                    insert(state_table).values(
                        **{
                            entity_key: entity_id,
                            "revision": revision,
                            "parent_revision": parent,
                            "status": state_status,
                            "committed_at": now,
                        }
                    )
                )
                self._advance_head(
                    conn,
                    head_table=head_table,
                    key_name=entity_key,
                    key_value=entity_id,
                    expected_revision=parent,
                    new_revision=revision,
                    conflict_code="AUTHORITY_STATE_CONFLICT",
                )
            now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind=result_kind,
                result_ref=entity_id,
                result_json={"entity_id": str(entity_id), "revision": revision},
                committed_at=now,
            )
            return AuthorityStateRevisionResult(entity_id, revision)

    def _require_relationship(
        self,
        conn: Connection,
        *,
        companion_person_id: UUID,
        counterpart_id: UUID,
        relationship_id: UUID,
    ) -> dict[str, Any]:
        row = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == relationship_id,
                schema.relationship_identity.c.companion_person_id == companion_person_id,
                schema.relationship_identity.c.counterpart_id == counterpart_id,
            )
        ).mappings().one_or_none()
        if row is None:
            fail("RELATIONSHIP_MISMATCH", "companion/counterpart/relationship identity does not match")
        return dict(row)

    def _active_calendar_bindings(self, conn: Connection, relationship_id: UUID) -> list[dict[str, Any]]:
        rows = conn.execute(
            select(schema.personal_resource_binding)
            .join(
                schema.personal_resource_binding_head,
                schema.personal_resource_binding_head.c.personal_resource_binding_id
                == schema.personal_resource_binding.c.personal_resource_binding_id,
            )
            .join(
                schema.personal_resource_binding_state,
                and_(
                    schema.personal_resource_binding_state.c.personal_resource_binding_id
                    == schema.personal_resource_binding_head.c.personal_resource_binding_id,
                    schema.personal_resource_binding_state.c.revision
                    == schema.personal_resource_binding_head.c.current_revision,
                ),
            )
            .where(
                schema.personal_resource_binding.c.relationship_id == relationship_id,
                schema.personal_resource_binding.c.resource_kind == "CALENDAR",
                schema.personal_resource_binding_state.c.status == "ACTIVE",
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    def _current_relationship_authority(self, conn: Connection, relationship_id: UUID) -> tuple[dict[str, Any], int]:
        return self._current_state(
            conn,
            state_table=schema.personal_world_relationship_state,
            head_table=schema.personal_world_relationship_head,
            key_name="relationship_id",
            key_value=relationship_id,
        )

    def _current_resource(
        self, conn: Connection, binding_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any], int]:
        binding = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id == binding_id
            )
        ).mappings().one_or_none()
        if binding is None:
            fail("PERSONAL_RESOURCE_BINDING_NOT_FOUND", "personal calendar binding does not exist")
        state, revision = self._current_state(
            conn,
            state_table=schema.personal_resource_binding_state,
            head_table=schema.personal_resource_binding_head,
            key_name="personal_resource_binding_id",
            key_value=binding_id,
        )
        return dict(binding), state, revision

    def _current_policy(self, conn: Connection, relationship_id: UUID) -> tuple[dict[str, Any], int]:
        head = conn.execute(
            select(schema.personal_calendar_read_policy_head).where(
                schema.personal_calendar_read_policy_head.c.relationship_id == relationship_id
            )
        ).mappings().one_or_none()
        if head is None:
            fail("CALENDAR_READ_POLICY_MISSING", "calendar read policy is not configured")
        revision = int(head["current_revision"])
        row = conn.execute(
            select(schema.personal_calendar_read_policy_revision).where(
                schema.personal_calendar_read_policy_revision.c.relationship_id == relationship_id,
                schema.personal_calendar_read_policy_revision.c.revision == revision,
            )
        ).mappings().one()
        return dict(row), revision

    def _current_state(
        self,
        conn: Connection,
        *,
        state_table: Any,
        head_table: Any,
        key_name: str,
        key_value: UUID,
    ) -> tuple[dict[str, Any], int]:
        key_column = getattr(head_table.c, key_name)
        head = conn.execute(select(head_table).where(key_column == key_value)).mappings().one_or_none()
        if head is None:
            fail("AUTHORITY_STATE_MISSING", f"current authority state is missing for {key_name}")
        revision = int(head["current_revision"])
        state_key = getattr(state_table.c, key_name)
        row = conn.execute(
            select(state_table).where(state_key == key_value, state_table.c.revision == revision)
        ).mappings().one()
        return dict(row), revision

    def _advance_head(
        self,
        conn: Connection,
        *,
        head_table: Any,
        key_name: str,
        key_value: UUID,
        expected_revision: int,
        new_revision: int,
        conflict_code: str,
    ) -> None:
        changed = conn.execute(
            update(head_table)
            .where(
                getattr(head_table.c, key_name) == key_value,
                head_table.c.current_revision == expected_revision,
            )
            .values(current_revision=new_revision)
        )
        if changed.rowcount != 1:
            fail(conflict_code, "authority state advanced concurrently")

    def _cas_head_same(
        self,
        conn: Connection,
        head_table: Any,
        key_name: str,
        key_value: UUID,
        revision: int,
        conflict_code: str,
    ) -> None:
        changed = conn.execute(
            update(head_table)
            .where(
                getattr(head_table.c, key_name) == key_value,
                head_table.c.current_revision == revision,
            )
            .values(current_revision=revision)
        )
        if changed.rowcount != 1:
            fail(conflict_code, "authority changed before dispatch fence could linearize")

    def _fence_result_from_json(self, payload: dict[str, Any]) -> CalendarReadPageFenceResult:
        return CalendarReadPageFenceResult(
            authority_fence_id=UUID(payload["authority_fence_id"]),
            observation_id=UUID(payload["observation_id"]),
            page_ordinal=int(payload["page_ordinal"]),
            personal_resource_binding_id=UUID(payload["personal_resource_binding_id"]),
            relationship_authority_revision=int(payload["relationship_authority_revision"]),
            resource_binding_state_revision=int(payload["resource_binding_state_revision"]),
            permission_state_revision=int(payload["permission_state_revision"]),
            credential_state_revision=int(payload["credential_state_revision"]),
            policy_revision=int(payload["policy_revision"]),
        )


__all__ = [
    "PersonalCalendarReadServices",
    "ZoneInfoCalendarTimeResolver",
    "all_day_event_interval",
    "parse_personal_calendar_question",
    "timed_event_overlaps_day",
]
