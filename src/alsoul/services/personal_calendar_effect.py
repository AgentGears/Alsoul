from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.domain.errors import DomainError, fail
from alsoul.domain.personal_calendar_action import CALENDAR_EVENT_CREATE
from alsoul.domain.personal_calendar_effect import (
    AdmitPersonalCalendarCreateConfirmedEffectCommand,
    CALENDAR_CREATE_EFFECT_SCHEMA_VERSION,
    CALENDAR_CREATE_EFFECT_SUPPORT_KIND,
    PersonalCalendarCreateConfirmedEffectResult,
)
from alsoul.domain.personal_calendar_transport import (
    CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION,
)
from alsoul.services.common import (
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
)
from alsoul.services.personal_calendar_execution_v2 import PersonalCalendarExecutionServices
from alsoul.storage import schema


_ADMIT_SCOPE = "AdmitPersonalCalendarCreateConfirmedEffect"


class PersonalCalendarEffectServices(PersonalCalendarExecutionServices):
    """Admit terminal F5.B create Effect truth from durable matched evidence.

    Effect admission never performs provider transport and never reuses historical
    execution authority. It consumes only already-durable minimized mutation evidence,
    validates exact Action correlation and semantic equality, creates the Effect and
    its SUPPORTS lineage in the same transaction, and terminalizes the owning attempt
    and per-Action dispatch guard atomically with that admission.
    """

    def admit_confirmed_effect(
        self, command: AdmitPersonalCalendarCreateConfirmedEffectCommand
    ) -> PersonalCalendarCreateConfirmedEffectResult:
        req = request_digest(asdict(command))
        try:
            with self.engine.begin() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_ADMIT_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req,
                )
                if replay:
                    return self._result_from_json(replay)

                attempt = self._load_attempt(conn, command.execution_attempt_id)
                existing = conn.execute(
                    select(schema.personal_calendar_create_effect).where(
                        schema.personal_calendar_create_effect.c.execution_attempt_id
                        == command.execution_attempt_id
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    result = self._recover_existing_effect(
                        conn,
                        command=command,
                        attempt=attempt,
                        effect=existing,
                    )
                    self._save_receipt(
                        conn,
                        command=command,
                        req_digest=req,
                        result=result,
                    )
                    return result

                evidence = conn.execute(
                    select(schema.personal_calendar_create_effect_evidence).where(
                        schema.personal_calendar_create_effect_evidence.c.effect_evidence_id
                        == command.effect_evidence_id
                    )
                ).mappings().one_or_none()
                if evidence is None:
                    fail(
                        "CALENDAR_CREATE_EFFECT_EVIDENCE_NOT_FOUND",
                        "calendar-create confirmed Effect requires durable mutation evidence",
                    )

                action_id = attempt["action_id"]
                self._validate_matched_evidence(
                    conn,
                    attempt=attempt,
                    evidence=evidence,
                )

                state, attempt_revision = self._current_attempt_state(
                    conn, command.execution_attempt_id
                )
                head, guard = self._current_guard(conn, action_id)
                if head is None or guard["execution_attempt_id"] != command.execution_attempt_id:
                    fail(
                        "CALENDAR_CREATE_EFFECT_DISPATCH_NOT_OWNED",
                        "confirmed Effect can terminalize only the attempt that owns the Action dispatch guard",
                    )
                if state["status"] != guard["status"]:
                    fail(
                        "CALENDAR_CREATE_EFFECT_STATE_INCONSISTENT",
                        "execution attempt and Action guard disagree before Effect admission",
                    )
                if state["status"] not in {"DISPATCH_FENCED", "UNKNOWN_EFFECT"}:
                    fail(
                        "CALENDAR_CREATE_EFFECT_STATE_NOT_ADMISSIBLE",
                        "confirmed Effect may be admitted only from an unresolved may-have-dispatched attempt",
                    )

                now = self.clock.now()
                effect_id = self.ids.new()
                conn.execute(
                    insert(schema.personal_calendar_create_effect).values(
                        effect_id=effect_id,
                        execution_attempt_id=command.execution_attempt_id,
                        action_id=action_id,
                        capability_semantic_operation=CALENDAR_EVENT_CREATE,
                        status="CONFIRMED_EFFECT",
                        effect_schema_version=CALENDAR_CREATE_EFFECT_SCHEMA_VERSION,
                        admitted_at=now,
                    )
                )
                conn.execute(
                    insert(schema.personal_calendar_create_effect_support).values(
                        effect_id=effect_id,
                        effect_evidence_id=command.effect_evidence_id,
                        support_kind=CALENDAR_CREATE_EFFECT_SUPPORT_KIND,
                        committed_at=now,
                    )
                )

                new_attempt_revision = attempt_revision + 1
                conn.execute(
                    insert(schema.personal_calendar_create_execution_attempt_state).values(
                        execution_attempt_id=command.execution_attempt_id,
                        revision=new_attempt_revision,
                        parent_revision=attempt_revision,
                        status="CONFIRMED_EFFECT",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_execution_attempt_head,
                    key_name="execution_attempt_id",
                    key_value=command.execution_attempt_id,
                    expected_revision=attempt_revision,
                    new_revision=new_attempt_revision,
                    conflict_code="CALENDAR_CREATE_EFFECT_ATTEMPT_STATE_CONFLICT",
                )

                guard_parent = int(head["current_revision"])
                guard_revision = guard_parent + 1
                conn.execute(
                    insert(schema.personal_calendar_create_action_dispatch_state).values(
                        action_id=action_id,
                        revision=guard_revision,
                        parent_revision=guard_parent,
                        execution_attempt_id=command.execution_attempt_id,
                        status="CONFIRMED_EFFECT",
                        committed_at=now,
                    )
                )
                self._advance_head(
                    conn,
                    head_table=schema.personal_calendar_create_action_dispatch_head,
                    key_name="action_id",
                    key_value=action_id,
                    expected_revision=guard_parent,
                    new_revision=guard_revision,
                    conflict_code="CALENDAR_CREATE_EFFECT_GUARD_CONFLICT",
                )

                result = PersonalCalendarCreateConfirmedEffectResult(
                    effect_id=effect_id,
                    action_id=action_id,
                    execution_attempt_id=command.execution_attempt_id,
                    effect_evidence_id=command.effect_evidence_id,
                )
                self._save_receipt(
                    conn,
                    command=command,
                    req_digest=req,
                    result=result,
                )
                return result
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_EFFECT_ADMISSION_CONFLICT",
                "calendar-create confirmed Effect admission conflicted with concurrent durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_EFFECT_ADMISSION_CONFLICT",
                "calendar-create confirmed Effect admission conflicted with concurrent durable state",
            ) from exc

    def _validate_matched_evidence(self, conn, *, attempt, evidence) -> None:
        if (
            evidence["execution_attempt_id"] != attempt["execution_attempt_id"]
            or evidence["action_id"] != attempt["action_id"]
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_EVIDENCE_LINEAGE_MISMATCH",
                "mutation evidence does not belong to the requested execution attempt and Action",
            )
        if (
            evidence["validation_kind"] != "SEMANTIC_MATCH"
            or evidence["provider_status"] != "CREATED"
            or evidence["evidence_schema_version"]
            != CALENDAR_CREATE_EFFECT_EVIDENCE_SCHEMA_VERSION
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_EVIDENCE_NOT_SUFFICIENT",
                "only durable semantically matched create evidence can confirm the intended Action Effect",
            )

        fence = conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == attempt["execution_attempt_id"]
            )
        ).mappings().one_or_none()
        if fence is None:
            fail(
                "CALENDAR_CREATE_EFFECT_FENCE_MISSING",
                "confirmed Effect evidence must resolve to the exact durable execution fence",
            )
        if (
            fence["action_id"] != attempt["action_id"]
            or fence["attempt_generation"] != attempt["attempt_generation"]
            or fence["correlation_key"] != attempt["correlation_key"]
            or evidence["correlation_key"] != attempt["correlation_key"]
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_CORRELATION_MISMATCH",
                "confirmed Effect evidence does not uniquely correlate to the immutable Action attempt",
            )

        action, _, _, resource = self._load_action_lineage(conn, attempt["action_id"])
        if (
            evidence["external_system_ref"] != resource["external_system_ref"]
            or evidence["external_resource_ref"] != resource["external_resource_ref"]
            or evidence["normalized_summary"] != action["summary"]
            or _aware_utc(evidence["normalized_start_at"])
            != _aware_utc(action["normalized_start_at"])
            or _aware_utc(evidence["normalized_end_at"])
            != _aware_utc(action["normalized_end_at"])
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_SEMANTIC_MISMATCH",
                "durable mutation evidence is not semantically equal to the immutable calendar Action",
            )
        if not evidence["external_effect_ref"] or not evidence["receipt_ref"]:
            fail(
                "CALENDAR_CREATE_EFFECT_EVIDENCE_NOT_SUFFICIENT",
                "confirmed Effect evidence lacks required provider proof references",
            )

    def _recover_existing_effect(self, conn, *, command, attempt, effect):
        support = conn.execute(
            select(schema.personal_calendar_create_effect_support).where(
                schema.personal_calendar_create_effect_support.c.effect_id
                == effect["effect_id"]
            )
        ).mappings().one_or_none()
        if (
            support is None
            or support["effect_evidence_id"] != command.effect_evidence_id
            or support["support_kind"] != CALENDAR_CREATE_EFFECT_SUPPORT_KIND
            or effect["action_id"] != attempt["action_id"]
            or effect["status"] != "CONFIRMED_EFFECT"
            or effect["effect_schema_version"] != CALENDAR_CREATE_EFFECT_SCHEMA_VERSION
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_EXISTING_LINEAGE_MISMATCH",
                "existing calendar Effect does not match the requested durable evidence lineage",
            )
        state, _ = self._current_attempt_state(conn, command.execution_attempt_id)
        head, guard = self._current_guard(conn, attempt["action_id"])
        if (
            head is None
            or state["status"] != "CONFIRMED_EFFECT"
            or guard["status"] != "CONFIRMED_EFFECT"
            or guard["execution_attempt_id"] != command.execution_attempt_id
        ):
            fail(
                "CALENDAR_CREATE_EFFECT_EXISTING_STATE_INCONSISTENT",
                "existing confirmed Effect is not paired with terminal execution and Action state",
            )
        return PersonalCalendarCreateConfirmedEffectResult(
            effect_id=effect["effect_id"],
            action_id=effect["action_id"],
            execution_attempt_id=effect["execution_attempt_id"],
            effect_evidence_id=support["effect_evidence_id"],
        )

    def _save_receipt(self, conn, *, command, req_digest, result) -> None:
        save_operation_receipt(
            conn,
            scope=_ADMIT_SCOPE,
            operation_id=command.operation_id,
            req_digest=req_digest,
            result_kind="PersonalCalendarCreateConfirmedEffect",
            result_ref=result.effect_id,
            result_json={
                "effect_id": str(result.effect_id),
                "action_id": str(result.action_id),
                "execution_attempt_id": str(result.execution_attempt_id),
                "effect_evidence_id": str(result.effect_evidence_id),
                "status": result.status,
            },
            committed_at=self.clock.now(),
        )

    @staticmethod
    def _result_from_json(payload):
        return PersonalCalendarCreateConfirmedEffectResult(
            effect_id=UUID(payload["effect_id"]),
            action_id=UUID(payload["action_id"]),
            execution_attempt_id=UUID(payload["execution_attempt_id"]),
            effect_evidence_id=UUID(payload["effect_evidence_id"]),
        )


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        fail(
            "CALENDAR_CREATE_EFFECT_EVIDENCE_TIME_INVALID",
            "confirmed Effect evidence timestamps must be datetime values",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_transient_lock_collision(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = ["PersonalCalendarEffectServices"]
