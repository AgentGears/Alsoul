from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ, FencePersonalCalendarReadPageCommand
from alsoul.domain.personal_calendar_acquisition import (
    PERSONAL_CALENDAR_CAPTURE_SCHEMA_VERSION,
    PERSONAL_CALENDAR_DAY_EVENTS_PREDICATE,
    PERSONAL_CALENDAR_RESULT_SCHEMA_VERSION,
    PERSONAL_CALENDAR_SCHEDULE_RESULT_KIND,
    AcquirePersonalCalendarObservationCommand,
    AcquirePersonalCalendarObservationResult,
    CalendarReadCapabilityContract,
    NormalizedCalendarEvent,
    PersonalCalendarReadAdapter,
    PersonalCalendarReadPage,
    PersonalCalendarReadPageRequest,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.services.personal_calendar import (
    PersonalCalendarReadServices,
    ZoneInfoCalendarTimeResolver,
    all_day_event_interval,
    timed_event_overlaps_day,
)
from alsoul.storage import schema

_ACQUIRE_SCOPE = "AcquirePersonalCalendarObservation"
_CAPTURE_SOURCE_TYPE = "PERSONAL_CALENDAR_WORLD_SOURCE_CAPTURE"


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_provider_aware(value: datetime, *, code: str, message: str) -> datetime:
    if value.tzinfo is None:
        fail(code, message)
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _as_aware_utc(value).isoformat()


class PersonalCalendarAcquisitionServices:
    """Execute one bounded coherent F5.A calendar acquisition.

    Provider transport is reachable only through this service after a current page
    authority fence commits. The adapter contract exposes normalized, minimized event
    material rather than raw provider payloads. Only a complete coherent traversal may
    become canonical evidence/result state.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        capability_contract: CalendarReadCapabilityContract,
        adapter: PersonalCalendarReadAdapter,
        time_resolver: ZoneInfoCalendarTimeResolver,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.capability_contract = capability_contract
        self.adapter = adapter
        self.time_resolver = time_resolver
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()
        self.read_services = PersonalCalendarReadServices(
            engine,
            time_resolver=time_resolver,
            clock=self.clock,
            ids=self.ids,
        )

    def acquire(
        self, command: AcquirePersonalCalendarObservationCommand
    ) -> AcquirePersonalCalendarObservationResult:
        req = request_digest(
            {
                "operation_id": command.operation_id,
                "observation_id": command.observation_id,
                "permission_id": command.permission_id,
                "credential_binding_id": command.credential_binding_id,
            }
        )
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ACQUIRE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._result_from_receipt(replay)

        self._qualify_contract()
        context = self._load_acquisition_context(command)
        attempt_id = self._start_attempt(command, context)

        try:
            traversal = self._traverse(command, context, attempt_id)
            return self._commit_success(
                command,
                context,
                attempt_id,
                traversal,
                req_digest=req,
            )
        except DomainError as exc:
            self._mark_failed(
                attempt_id=attempt_id,
                observation_id=command.observation_id,
                investigation_id=context["investigation_id"],
                failure_code=exc.code,
            )
            raise
        except AdapterRejected as exc:
            self._mark_failed(
                attempt_id=attempt_id,
                observation_id=command.observation_id,
                investigation_id=context["investigation_id"],
                failure_code="CALENDAR_PROVIDER_REJECTED",
            )
            raise DomainError(
                "CALENDAR_PROVIDER_REJECTED",
                "calendar provider rejected the bounded read request",
            ) from exc
        except AdapterOutcomeUnknown as exc:
            self._mark_failed(
                attempt_id=attempt_id,
                observation_id=command.observation_id,
                investigation_id=context["investigation_id"],
                failure_code="CALENDAR_PROVIDER_OUTCOME_UNKNOWN",
            )
            raise DomainError(
                "CALENDAR_PROVIDER_OUTCOME_UNKNOWN",
                "calendar page transport outcome is unknown; the acquisition is not complete",
            ) from exc

    def _qualify_contract(self) -> None:
        contract = self.capability_contract
        required_text = (
            contract.contract_version,
            contract.pagination_contract_version,
            contract.snapshot_contract_version,
            contract.normalization_schema_version,
            contract.field_minimization_contract_version,
            contract.freshness_policy_version,
            self.adapter.adapter_binding_ref,
            self.adapter.adapter_version,
        )
        if any(not value.strip() for value in required_text):
            fail(
                "CALENDAR_CAPABILITY_CONTRACT_INVALID",
                "calendar acquisition contract and adapter version refs must be explicit",
            )
        if (
            contract.semantic_operation != CALENDAR_EVENTS_READ
            or contract.effect_class != "READ_ONLY"
            or contract.resource_kind != "CALENDAR"
        ):
            fail(
                "CALENDAR_CAPABILITY_CONTRACT_INVALID",
                "calendar acquisition requires trusted calendar.events.read READ_ONLY semantics",
            )
        if contract.pagination_mode != "OPAQUE_CURSOR":
            fail(
                "CALENDAR_PAGINATION_CONTRACT_UNSUPPORTED",
                "the first acquisition increment supports only opaque cursor pagination",
            )
        if contract.coherent_snapshot_mode != "STABLE_SNAPSHOT_REF":
            fail(
                "CALENDAR_SNAPSHOT_CONTRACT_UNSUPPORTED",
                "the first acquisition increment requires a stable provider snapshot reference",
            )
        if contract.recurrence_expansion_mode != "CONCRETE_OCCURRENCES":
            fail(
                "CALENDAR_RECURRENCE_CONTRACT_UNSUPPORTED",
                "calendar adapter must return concrete authoritative occurrences",
            )
        if contract.raw_response_minimization_mode != "EPHEMERAL_TO_ALLOWLIST":
            fail(
                "CALENDAR_MINIMIZATION_CONTRACT_UNTRUSTED",
                "calendar adapter must minimize raw provider material before host persistence or telemetry",
            )
        if (
            contract.max_pages <= 0
            or contract.max_events < 0
            or contract.max_events_per_page <= 0
            or contract.max_title_chars <= 0
        ):
            fail(
                "CALENDAR_CAPABILITY_BOUNDS_INVALID",
                "calendar capability bounds must be positive and finite",
            )

    def _load_acquisition_context(
        self, command: AcquirePersonalCalendarObservationCommand
    ) -> dict[str, Any]:
        with self.engine.connect() as conn:
            scope_row = conn.execute(
                select(schema.personal_calendar_observation_scope).where(
                    schema.personal_calendar_observation_scope.c.observation_id
                    == command.observation_id
                )
            ).mappings().one_or_none()
            if scope_row is None:
                fail(
                    "CALENDAR_OBSERVATION_SCOPE_MISSING",
                    "calendar observation must be prepared before acquisition",
                )
            observation = conn.execute(
                select(schema.observation).where(
                    schema.observation.c.observation_id == command.observation_id
                )
            ).mappings().one_or_none()
            if observation is None or observation["status"] != "STARTED":
                fail(
                    "CALENDAR_OBSERVATION_NOT_OPEN",
                    "calendar acquisition requires a STARTED observation",
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
            if investigation is None or investigation["status"] != "OPEN":
                fail(
                    "CALENDAR_INVESTIGATION_NOT_OPEN",
                    "calendar acquisition requires an open Investigation",
                )
            binding = conn.execute(
                select(schema.personal_resource_binding).where(
                    schema.personal_resource_binding.c.personal_resource_binding_id
                    == scope_row["personal_resource_binding_id"]
                )
            ).mappings().one_or_none()
            if binding is None:
                fail(
                    "PERSONAL_RESOURCE_BINDING_NOT_FOUND",
                    "prepared calendar resource binding no longer exists",
                )
            credential = conn.execute(
                select(schema.credential_binding).where(
                    schema.credential_binding.c.credential_binding_id
                    == command.credential_binding_id
                )
            ).mappings().one_or_none()
            if credential is None:
                fail("CREDENTIAL_BINDING_NOT_FOUND", "credential binding does not exist")
            policy_head = conn.execute(
                select(schema.personal_calendar_read_policy_head).where(
                    schema.personal_calendar_read_policy_head.c.relationship_id
                    == investigation["relationship_id"]
                )
            ).mappings().one_or_none()
            if policy_head is None:
                fail(
                    "CALENDAR_READ_POLICY_MISSING",
                    "current personal-calendar read policy is missing",
                )
            policy = conn.execute(
                select(schema.personal_calendar_read_policy_revision).where(
                    schema.personal_calendar_read_policy_revision.c.relationship_id
                    == investigation["relationship_id"],
                    schema.personal_calendar_read_policy_revision.c.revision
                    == policy_head["current_revision"],
                )
            ).mappings().one()
            if policy["capability_contract_version"] != self.capability_contract.contract_version:
                fail(
                    "CAPABILITY_CONTRACT_VERSION_MISMATCH",
                    "current policy and trusted acquisition capability versions differ",
                )

            requested_date = date.fromisoformat(scope_row["requested_local_date"])
            if scope_row["timezone_rules_version"] != self.time_resolver.rules_version:
                fail(
                    "CALENDAR_TIME_RULES_VERSION_MISMATCH",
                    "prepared calendar rules version is not executable by this host",
                )
            window = self.time_resolver.resolve_day(
                zone_name=scope_row["calendar_timezone"],
                local_date=requested_date,
            )
            if (
                _as_aware_utc(scope_row["window_start"]) != window.window_start
                or _as_aware_utc(scope_row["window_end"]) != window.window_end
            ):
                fail(
                    "CALENDAR_OBSERVATION_SCOPE_TIME_MISMATCH",
                    "persisted calendar scope does not match trusted time resolution",
                )
            acquisition_started_at = _as_aware_utc(scope_row["acquisition_started_at"])
            return {
                "scope": dict(scope_row),
                "observation": dict(observation),
                "investigation": dict(investigation),
                "investigation_id": investigation["investigation_id"],
                "binding": dict(binding),
                "credential": dict(credential),
                "window": window,
                "acquisition_started_at": acquisition_started_at,
            }

    def _start_attempt(
        self,
        command: AcquirePersonalCalendarObservationCommand,
        context: dict[str, Any],
    ) -> UUID:
        contract = self.capability_contract
        with self.engine.begin() as conn:
            started = conn.execute(
                select(schema.personal_calendar_acquisition_attempt).where(
                    schema.personal_calendar_acquisition_attempt.c.observation_id
                    == command.observation_id,
                    schema.personal_calendar_acquisition_attempt.c.status == "STARTED",
                )
            ).mappings().one_or_none()
            if started is not None:
                fail(
                    "CALENDAR_ACQUISITION_RECOVERY_REQUIRED",
                    "a prior calendar acquisition attempt is still STARTED and requires explicit recovery",
                )
            existing_capture = conn.execute(
                select(schema.personal_calendar_source_capture.c.source_capture_id).where(
                    schema.personal_calendar_source_capture.c.observation_id
                    == command.observation_id
                )
            ).scalar_one_or_none()
            if existing_capture is not None:
                fail(
                    "CALENDAR_CAPTURE_ALREADY_ACCEPTED",
                    "calendar observation already has a canonical personal-world capture",
                )
            maximum_generation = conn.execute(
                select(func.max(schema.personal_calendar_acquisition_attempt.c.generation)).where(
                    schema.personal_calendar_acquisition_attempt.c.observation_id
                    == command.observation_id
                )
            ).scalar_one()
            generation = int(maximum_generation or 0) + 1
            attempt_id = self.ids.new()
            now = self.clock.now()
            try:
                conn.execute(
                    insert(schema.personal_calendar_acquisition_attempt).values(
                        acquisition_attempt_id=attempt_id,
                        observation_id=command.observation_id,
                        generation=generation,
                        capability_contract_version=contract.contract_version,
                        adapter_binding_ref=self.adapter.adapter_binding_ref,
                        adapter_version=self.adapter.adapter_version,
                        pagination_contract_version=contract.pagination_contract_version,
                        snapshot_contract_version=contract.snapshot_contract_version,
                        normalization_schema_version=contract.normalization_schema_version,
                        field_minimization_contract_version=contract.field_minimization_contract_version,
                        freshness_policy_version=contract.freshness_policy_version,
                        started_at=now,
                        status="STARTED",
                    )
                )
            except IntegrityError:
                fail(
                    "CALENDAR_ACQUISITION_ATTEMPT_CONFLICT",
                    "calendar acquisition attempt generation was claimed concurrently",
                )
            return attempt_id

    def _traverse(
        self,
        command: AcquirePersonalCalendarObservationCommand,
        context: dict[str, Any],
        attempt_id: UUID,
    ) -> dict[str, Any]:
        contract = self.capability_contract
        page_token: str | None = None
        seen_tokens: set[str] = set()
        seen_occurrences: set[str] = set()
        included_events: list[NormalizedCalendarEvent] = []
        snapshot_ref: str | None = None
        snapshot_as_of: datetime | None = None
        page_count = 0

        for traversal_page_ordinal in range(contract.max_pages):
            transport_ordinal = self._next_transport_ordinal(command.observation_id)
            fence = self.read_services.fence_read_page(
                FencePersonalCalendarReadPageCommand(
                    operation_id=self.ids.new(),
                    observation_id=command.observation_id,
                    page_ordinal=transport_ordinal,
                    permission_id=command.permission_id,
                    credential_binding_id=command.credential_binding_id,
                )
            )
            request = PersonalCalendarReadPageRequest(
                authority_fence_id=fence.authority_fence_id,
                observation_id=command.observation_id,
                traversal_page_ordinal=traversal_page_ordinal,
                external_system_ref=context["binding"]["external_system_ref"],
                external_resource_ref=context["binding"]["external_resource_ref"],
                window_start=context["window"].window_start,
                window_end=context["window"].window_end,
                page_token=page_token,
                expected_snapshot_ref=snapshot_ref,
                credential_secret_ref=context["credential"]["secret_ref"],
                normalization_schema_version=contract.normalization_schema_version,
                field_minimization_contract_version=contract.field_minimization_contract_version,
                max_events_per_page=contract.max_events_per_page,
            )
            page = self.adapter.read_page(request)
            self._validate_page_shape(page)

            current_snapshot_as_of = (
                _require_provider_aware(
                    page.snapshot_as_of,
                    code="CALENDAR_SNAPSHOT_TIME_UNTRUSTED",
                    message="provider snapshot_as_of must be offset-aware",
                )
                if page.snapshot_as_of is not None
                else None
            )
            if snapshot_ref is None:
                snapshot_ref = page.snapshot_ref
                snapshot_as_of = current_snapshot_as_of
            else:
                if page.snapshot_ref != snapshot_ref:
                    fail(
                        "CALENDAR_SNAPSHOT_CHANGED_DURING_PAGINATION",
                        "calendar pages do not belong to one stable provider snapshot",
                    )
                if (snapshot_as_of is None) != (current_snapshot_as_of is None):
                    fail(
                        "CALENDAR_SNAPSHOT_TIME_INCONSISTENT",
                        "provider snapshot_as_of presence changed during pagination",
                    )
                if (
                    snapshot_as_of is not None
                    and current_snapshot_as_of is not None
                    and snapshot_as_of != current_snapshot_as_of
                ):
                    fail(
                        "CALENDAR_SNAPSHOT_TIME_INCONSISTENT",
                        "provider snapshot_as_of changed during pagination",
                    )

            if len(page.events) > contract.max_events_per_page:
                fail(
                    "CALENDAR_PAGE_EVENT_LIMIT_EXCEEDED",
                    "calendar page exceeds the trusted per-page event bound",
                )
            if page.result_cap_hit:
                fail(
                    "CALENDAR_PROVIDER_RESULT_CAP_REACHED",
                    "provider result cap prevents authoritative completeness",
                )

            page_included = 0
            for event in page.events:
                if event.occurrence_ref in seen_occurrences:
                    fail(
                        "CALENDAR_OCCURRENCE_DUPLICATED",
                        "one provider occurrence identity appeared more than once in the traversal",
                    )
                seen_occurrences.add(event.occurrence_ref)
                normalized = self._validate_event(event, context)
                if normalized is not None:
                    included_events.append(normalized)
                    page_included += 1
                    if len(included_events) > contract.max_events:
                        fail(
                            "CALENDAR_ACQUISITION_EVENT_LIMIT_EXCEEDED",
                            "calendar acquisition exceeds the trusted total event bound",
                        )

            self._record_page(
                attempt_id=attempt_id,
                traversal_page_ordinal=traversal_page_ordinal,
                transport_ordinal=transport_ordinal,
                authority_fence_id=fence.authority_fence_id,
                request_page_token=page_token,
                page=page,
                snapshot_as_of=current_snapshot_as_of,
                included_event_count=page_included,
            )
            page_count += 1

            if page.terminal:
                if snapshot_ref is None:
                    fail(
                        "CALENDAR_SNAPSHOT_MISSING",
                        "calendar terminal page lacks coherent snapshot identity",
                    )
                included_events.sort(key=self._event_sort_key)
                return {
                    "events": tuple(included_events),
                    "snapshot_ref": snapshot_ref,
                    "snapshot_as_of": snapshot_as_of,
                    "page_count": page_count,
                }

            assert page.next_page_token is not None
            if page.next_page_token in seen_tokens:
                fail(
                    "CALENDAR_PAGINATION_TOKEN_CYCLE",
                    "calendar pagination cursor repeated before terminal completeness",
                )
            seen_tokens.add(page.next_page_token)
            page_token = page.next_page_token

        fail(
            "CALENDAR_PAGINATION_LIMIT_EXCEEDED",
            "calendar traversal did not prove completeness within the trusted page bound",
        )

    def _validate_page_shape(self, page: PersonalCalendarReadPage) -> None:
        if not isinstance(page, PersonalCalendarReadPage):
            fail(
                "CALENDAR_ADAPTER_RESPONSE_INVALID",
                "calendar adapter must return normalized PersonalCalendarReadPage material",
            )
        if not page.snapshot_ref.strip():
            fail(
                "CALENDAR_SNAPSHOT_MISSING",
                "calendar page lacks a stable provider snapshot reference",
            )
        if page.terminal and page.next_page_token is not None:
            fail(
                "CALENDAR_PAGINATION_TERMINAL_INVALID",
                "terminal calendar page must not expose another cursor",
            )
        if not page.terminal and (
            page.next_page_token is None or not page.next_page_token.strip()
        ):
            fail(
                "CALENDAR_PAGINATION_INCOMPLETE",
                "non-terminal calendar page must expose a non-empty continuation cursor",
            )

    def _validate_event(
        self,
        event: NormalizedCalendarEvent,
        context: dict[str, Any],
    ) -> NormalizedCalendarEvent | None:
        contract = self.capability_contract
        if not isinstance(event, NormalizedCalendarEvent):
            fail(
                "CALENDAR_EVENT_NORMALIZATION_INVALID",
                "calendar adapter returned material outside the normalized event contract",
            )
        if event.record_kind != "OCCURRENCE":
            fail(
                "CALENDAR_RECURRENCE_EXPANSION_INCOMPLETE",
                "series masters cannot be admitted as concrete day occurrences",
            )
        if not event.occurrence_ref.strip():
            fail(
                "CALENDAR_OCCURRENCE_IDENTITY_MISSING",
                "normalized calendar occurrence requires a stable provider identity",
            )
        for optional_ref in (event.series_ref, event.exception_ref):
            if optional_ref is not None and not optional_ref.strip():
                fail(
                    "CALENDAR_OCCURRENCE_IDENTITY_INVALID",
                    "normalized recurrence provenance refs must be non-empty when present",
                )
        if len(event.title) > contract.max_title_chars:
            fail(
                "CALENDAR_EVENT_TITLE_LIMIT_EXCEEDED",
                "normalized calendar title exceeds the trusted field bound",
            )
        if event.occurrence_status == "CANCELLED":
            return None
        if event.occurrence_status != "ACTIVE":
            fail(
                "CALENDAR_OCCURRENCE_STATUS_INVALID",
                "normalized occurrence status is outside the first-slice contract",
            )
        event_start = _require_provider_aware(
            event.start_at,
            code="CALENDAR_EVENT_TIME_UNTRUSTED",
            message="normalized event start must be offset-aware",
        )
        event_end = _require_provider_aware(
            event.end_at,
            code="CALENDAR_EVENT_TIME_UNTRUSTED",
            message="normalized event end must be offset-aware",
        )
        if event_end <= event_start:
            fail(
                "CALENDAR_EVENT_DURATION_UNSUPPORTED",
                "zero or negative-duration calendar occurrences are outside the first slice",
            )

        if event.all_day:
            if (
                event.all_day_start_date is None
                or event.all_day_end_date_exclusive is None
            ):
                fail(
                    "CALENDAR_ALL_DAY_INTERVAL_INVALID",
                    "all-day occurrence requires explicit exclusive-end calendar dates",
                )
            expected_start, expected_end = all_day_event_interval(
                resolver=self.time_resolver,
                zone_name=context["scope"]["calendar_timezone"],
                start_date=event.all_day_start_date,
                end_date_exclusive=event.all_day_end_date_exclusive,
            )
            if event_start != expected_start or event_end != expected_end:
                fail(
                    "CALENDAR_ALL_DAY_TIME_MISMATCH",
                    "all-day occurrence instants do not match trusted calendar-date semantics",
                )
        elif (
            event.all_day_start_date is not None
            or event.all_day_end_date_exclusive is not None
        ):
            fail(
                "CALENDAR_EVENT_NORMALIZATION_INVALID",
                "timed occurrence cannot carry all-day calendar dates",
            )

        if not timed_event_overlaps_day(
            window=context["window"],
            event_start=event_start,
            event_end=event_end,
        ):
            return None

        return NormalizedCalendarEvent(
            occurrence_ref=event.occurrence_ref,
            title=event.title,
            start_at=event_start,
            end_at=event_end,
            all_day=event.all_day,
            series_ref=event.series_ref,
            exception_ref=event.exception_ref,
            all_day_start_date=event.all_day_start_date,
            all_day_end_date_exclusive=event.all_day_end_date_exclusive,
            occurrence_status="ACTIVE",
        )

    def _next_transport_ordinal(self, observation_id: UUID) -> int:
        with self.engine.connect() as conn:
            maximum = conn.execute(
                select(func.max(schema.personal_calendar_read_authority_fence.c.page_ordinal)).where(
                    schema.personal_calendar_read_authority_fence.c.observation_id
                    == observation_id
                )
            ).scalar_one()
        return int(maximum if maximum is not None else -1) + 1

    def _record_page(
        self,
        *,
        attempt_id: UUID,
        traversal_page_ordinal: int,
        transport_ordinal: int,
        authority_fence_id: UUID,
        request_page_token: str | None,
        page: PersonalCalendarReadPage,
        snapshot_as_of: datetime | None,
        included_event_count: int,
    ) -> None:
        with self.engine.begin() as conn:
            try:
                conn.execute(
                    insert(schema.personal_calendar_acquisition_page).values(
                        acquisition_attempt_id=attempt_id,
                        page_ordinal=traversal_page_ordinal,
                        authority_fence_id=authority_fence_id,
                        transport_ordinal=transport_ordinal,
                        request_cursor_digest=(
                            sha256_text(request_page_token)
                            if request_page_token is not None
                            else None
                        ),
                        next_cursor_digest=(
                            sha256_text(page.next_page_token)
                            if page.next_page_token is not None
                            else None
                        ),
                        snapshot_ref=page.snapshot_ref,
                        snapshot_as_of=snapshot_as_of,
                        event_count=included_event_count,
                        terminal=page.terminal,
                        result_cap_hit=page.result_cap_hit,
                        received_at=self.clock.now(),
                    )
                )
            except IntegrityError:
                fail(
                    "CALENDAR_ACQUISITION_PAGE_CONFLICT",
                    "calendar page lineage was committed concurrently",
                )

    def _event_sort_key(self, event: NormalizedCalendarEvent) -> tuple[str, str, str, str]:
        return (
            _iso_utc(event.start_at),
            _iso_utc(event.end_at),
            event.title,
            event.occurrence_ref,
        )

    def _event_payload(self, event: NormalizedCalendarEvent) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "occurrence_ref": event.occurrence_ref,
            "title": event.title,
            "start_at": _iso_utc(event.start_at),
            "end_at": _iso_utc(event.end_at),
            "all_day": event.all_day,
        }
        if event.series_ref is not None:
            payload["series_ref"] = event.series_ref
        if event.exception_ref is not None:
            payload["exception_ref"] = event.exception_ref
        if event.all_day:
            assert event.all_day_start_date is not None
            assert event.all_day_end_date_exclusive is not None
            payload["all_day_start_date"] = event.all_day_start_date.isoformat()
            payload["all_day_end_date_exclusive"] = (
                event.all_day_end_date_exclusive.isoformat()
            )
        return payload

    def _commit_success(
        self,
        command: AcquirePersonalCalendarObservationCommand,
        context: dict[str, Any],
        attempt_id: UUID,
        traversal: dict[str, Any],
        *,
        req_digest: str,
    ) -> AcquirePersonalCalendarObservationResult:
        contract = self.capability_contract
        snapshot_as_of: datetime | None = traversal["snapshot_as_of"]
        if snapshot_as_of is not None:
            freshness_anchor_at = snapshot_as_of
            freshness_anchor_basis = "PROVIDER_SNAPSHOT_AS_OF"
        else:
            freshness_anchor_at = context["acquisition_started_at"]
            freshness_anchor_basis = "ACQUISITION_STARTED_AT"

        event_payloads = [self._event_payload(event) for event in traversal["events"]]
        capture_payload = {
            "capture_schema_version": PERSONAL_CALENDAR_CAPTURE_SCHEMA_VERSION,
            "personal_resource_binding_id": str(
                context["scope"]["personal_resource_binding_id"]
            ),
            "external_resource_ref": context["binding"]["external_resource_ref"],
            "source_interaction_event_id": str(
                context["scope"]["source_interaction_event_id"]
            ),
            "requested_local_date": context["scope"]["requested_local_date"],
            "calendar_timezone": context["scope"]["calendar_timezone"],
            "timezone_rules_version": context["scope"]["timezone_rules_version"],
            "window_start": _iso_utc(context["window"].window_start),
            "window_end": _iso_utc(context["window"].window_end),
            "snapshot_ref": traversal["snapshot_ref"],
            "snapshot_as_of": (
                _iso_utc(snapshot_as_of) if snapshot_as_of is not None else None
            ),
            "freshness_anchor_at": _iso_utc(freshness_anchor_at),
            "freshness_anchor_basis": freshness_anchor_basis,
            "capability_contract_version": contract.contract_version,
            "adapter_binding_ref": self.adapter.adapter_binding_ref,
            "adapter_version": self.adapter.adapter_version,
            "pagination_contract_version": contract.pagination_contract_version,
            "snapshot_contract_version": contract.snapshot_contract_version,
            "normalization_schema_version": contract.normalization_schema_version,
            "field_minimization_contract_version": contract.field_minimization_contract_version,
            "page_count": traversal["page_count"],
            "events": event_payloads,
        }
        content_text = canonical_json(capture_payload)
        content_digest = sha256_text(content_text)
        source_capture_id = self.ids.new()
        evidence_id = self.ids.new()
        world_result_id = self.ids.new()
        now = self.clock.now()
        content_ref = f"sha256:{content_digest}"

        result_value = {
            "result_schema_version": PERSONAL_CALENDAR_RESULT_SCHEMA_VERSION,
            "personal_resource_binding_id": str(
                context["scope"]["personal_resource_binding_id"]
            ),
            "requested_local_date": context["scope"]["requested_local_date"],
            "calendar_timezone": context["scope"]["calendar_timezone"],
            "window_start": _iso_utc(context["window"].window_start),
            "window_end": _iso_utc(context["window"].window_end),
            "freshness_anchor_at": _iso_utc(freshness_anchor_at),
            "events": event_payloads,
        }

        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_ACQUIRE_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req_digest,
            )
            if replay:
                return self._result_from_receipt(replay)
            attempt = conn.execute(
                select(schema.personal_calendar_acquisition_attempt).where(
                    schema.personal_calendar_acquisition_attempt.c.acquisition_attempt_id
                    == attempt_id
                )
            ).mappings().one_or_none()
            if attempt is None or attempt["status"] != "STARTED":
                fail(
                    "CALENDAR_ACQUISITION_ATTEMPT_NOT_OPEN",
                    "calendar acquisition attempt is no longer open for canonical admission",
                )
            observation = conn.execute(
                select(schema.observation).where(
                    schema.observation.c.observation_id == command.observation_id
                )
            ).mappings().one_or_none()
            if observation is None or observation["status"] != "STARTED":
                fail(
                    "CALENDAR_OBSERVATION_NOT_OPEN",
                    "calendar observation became terminal before capture admission",
                )
            if conn.execute(
                select(schema.world_source_capture.c.source_capture_id).where(
                    schema.world_source_capture.c.observation_id == command.observation_id
                )
            ).scalar_one_or_none() is not None:
                fail(
                    "CALENDAR_CAPTURE_ALREADY_ACCEPTED",
                    "calendar observation already has an accepted source capture",
                )

            if conn.execute(
                select(schema.content_blob.c.content_digest).where(
                    schema.content_blob.c.content_digest == content_digest
                )
            ).scalar_one_or_none() is None:
                conn.execute(
                    insert(schema.content_blob).values(
                        content_digest=content_digest,
                        content_text=content_text,
                        recorded_at=now,
                    )
                )
            source_identity = (
                f"{context['binding']['external_system_ref']}:"
                f"{context['binding']['external_resource_ref']}"
            )
            conn.execute(
                insert(schema.world_source_capture).values(
                    source_capture_id=source_capture_id,
                    observation_id=command.observation_id,
                    capture_kind="PERSONAL_CALENDAR_SCHEDULE",
                    source_identity=source_identity,
                    requested_locator=context["scope"]["requested_local_date"],
                    resolved_locator=context["binding"]["external_resource_ref"],
                    source_version=traversal["snapshot_ref"],
                    source_published_at=None,
                    source_modified_at=None,
                    captured_at=now,
                    content_ref=content_ref,
                    content_digest=content_digest,
                )
            )
            conn.execute(
                insert(schema.personal_calendar_source_capture).values(
                    source_capture_id=source_capture_id,
                    observation_id=command.observation_id,
                    acquisition_attempt_id=attempt_id,
                    personal_resource_binding_id=context["scope"][
                        "personal_resource_binding_id"
                    ],
                    source_interaction_event_id=context["scope"][
                        "source_interaction_event_id"
                    ],
                    snapshot_ref=traversal["snapshot_ref"],
                    snapshot_as_of=snapshot_as_of,
                    freshness_anchor_at=freshness_anchor_at,
                    freshness_anchor_basis=freshness_anchor_basis,
                    freshness_policy_version_at_admission=contract.freshness_policy_version,
                    capability_contract_version=contract.contract_version,
                    adapter_binding_ref=self.adapter.adapter_binding_ref,
                    adapter_version=self.adapter.adapter_version,
                    pagination_contract_version=contract.pagination_contract_version,
                    snapshot_contract_version=contract.snapshot_contract_version,
                    normalization_schema_version=contract.normalization_schema_version,
                    field_minimization_contract_version=contract.field_minimization_contract_version,
                    page_count=traversal["page_count"],
                    event_count=len(event_payloads),
                    capture_committed_at=now,
                )
            )
            conn.execute(
                insert(schema.evidence_item).values(
                    evidence_id=evidence_id,
                    origin_kind="SEARCH_RESULT",
                    source_type=_CAPTURE_SOURCE_TYPE,
                    source_id=source_capture_id,
                    source_locator=context["binding"]["external_resource_ref"],
                    source_actor_ref=None,
                    recorded_at=now,
                )
            )
            conn.execute(
                insert(schema.world_result).values(
                    world_result_id=world_result_id,
                    investigation_id=context["investigation_id"],
                    result_kind=PERSONAL_CALENDAR_SCHEDULE_RESULT_KIND,
                    predicate=PERSONAL_CALENDAR_DAY_EVENTS_PREDICATE,
                    value_json=result_value,
                    valid_as_of=freshness_anchor_at,
                    derived_at=now,
                )
            )
            conn.execute(
                insert(schema.world_result_evidence).values(
                    world_result_id=world_result_id,
                    evidence_id=evidence_id,
                    relation="SUPPORTS",
                )
            )
            conn.execute(
                insert(schema.personal_calendar_world_result).values(
                    world_result_id=world_result_id,
                    source_capture_id=source_capture_id,
                    observation_id=command.observation_id,
                    personal_resource_binding_id=context["scope"][
                        "personal_resource_binding_id"
                    ],
                    source_interaction_event_id=context["scope"][
                        "source_interaction_event_id"
                    ],
                    requested_local_date=context["scope"]["requested_local_date"],
                    freshness_anchor_at=freshness_anchor_at,
                    freshness_policy_version_at_admission=contract.freshness_policy_version,
                    result_schema_version=PERSONAL_CALENDAR_RESULT_SCHEMA_VERSION,
                )
            )
            conn.execute(
                update(schema.observation)
                .where(schema.observation.c.observation_id == command.observation_id)
                .values(status="SUCCEEDED")
            )
            conn.execute(
                update(schema.investigation)
                .where(
                    schema.investigation.c.investigation_id
                    == context["investigation_id"]
                )
                .values(status="SUCCEEDED")
            )
            conn.execute(
                update(schema.personal_calendar_acquisition_attempt)
                .where(
                    schema.personal_calendar_acquisition_attempt.c.acquisition_attempt_id
                    == attempt_id,
                    schema.personal_calendar_acquisition_attempt.c.status == "STARTED",
                )
                .values(status="SUCCEEDED", ended_at=now, failure_code=None)
            )
            result_json = {
                "source_capture_id": str(source_capture_id),
                "evidence_id": str(evidence_id),
                "world_result_id": str(world_result_id),
                "page_count": traversal["page_count"],
                "event_count": len(event_payloads),
                "snapshot_ref": traversal["snapshot_ref"],
                "freshness_anchor_at": _iso_utc(freshness_anchor_at),
                "freshness_anchor_basis": freshness_anchor_basis,
            }
            save_operation_receipt(
                conn,
                scope=_ACQUIRE_SCOPE,
                operation_id=command.operation_id,
                req_digest=req_digest,
                result_kind="PersonalCalendarWorldResult",
                result_ref=world_result_id,
                result_json=result_json,
                committed_at=now,
            )
            return self._result_from_receipt(result_json)

    def _mark_failed(
        self,
        *,
        attempt_id: UUID,
        observation_id: UUID,
        investigation_id: UUID,
        failure_code: str,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(schema.personal_calendar_acquisition_attempt)
                .where(
                    schema.personal_calendar_acquisition_attempt.c.acquisition_attempt_id
                    == attempt_id,
                    schema.personal_calendar_acquisition_attempt.c.status == "STARTED",
                )
                .values(
                    status="FAILED",
                    ended_at=self.clock.now(),
                    failure_code=failure_code,
                )
            )
            conn.execute(
                update(schema.observation)
                .where(
                    schema.observation.c.observation_id == observation_id,
                    schema.observation.c.status == "STARTED",
                )
                .values(status="FAILED")
            )
            conn.execute(
                update(schema.investigation)
                .where(
                    schema.investigation.c.investigation_id == investigation_id,
                    schema.investigation.c.status == "OPEN",
                )
                .values(status="FAILED")
            )

    def _result_from_receipt(
        self, replay: dict[str, Any]
    ) -> AcquirePersonalCalendarObservationResult:
        return AcquirePersonalCalendarObservationResult(
            source_capture_id=UUID(replay["source_capture_id"]),
            evidence_id=UUID(replay["evidence_id"]),
            world_result_id=UUID(replay["world_result_id"]),
            page_count=int(replay["page_count"]),
            event_count=int(replay["event_count"]),
            snapshot_ref=replay["snapshot_ref"],
            freshness_anchor_at=datetime.fromisoformat(replay["freshness_anchor_at"]),
            freshness_anchor_basis=replay["freshness_anchor_basis"],
        )
