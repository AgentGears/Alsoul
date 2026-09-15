from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError, fail
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.personal_calendar_reconciliation import (
    PersonalCalendarReconciliationServices as PersonalCalendarReconciliationServicesV1,
    _RECONCILE_SCOPE,
    _is_transient_lock_collision,
)
from alsoul.storage import schema


class PersonalCalendarReconciliationServices(PersonalCalendarReconciliationServicesV1):
    """Current reconciliation service with deterministic same-operation replay."""

    def reconcile_unknown_effect(self, command):
        req_digest = request_digest(asdict(command))
        try:
            with self.engine.connect() as conn:
                replay = load_operation_receipt(
                    conn,
                    scope=_RECONCILE_SCOPE,
                    operation_id=command.operation_id,
                    expected_request_digest=req_digest,
                )
                if replay:
                    return self._result_from_json(replay)

            self._qualify_contract()
            context = self._start_probe(command, req_digest=req_digest)
            if "replay" in context:
                return context["replay"]
            try:
                observation = self.reconciliation_adapter.lookup_create_effect(
                    context["request"]
                )
                normalized = self._normalize_observation(
                    observation=observation,
                    attempt=context["attempt"],
                    action=context["action"],
                    resource=context["resource"],
                )
            except DomainError:
                self._record_unknown(
                    command=command,
                    req_digest=req_digest,
                    context=context,
                )
                raise
            except (AdapterOutcomeUnknown, AdapterRejected):
                return self._record_unknown(
                    command=command,
                    req_digest=req_digest,
                    context=context,
                )

            return self._commit_probe(
                command=command,
                req_digest=req_digest,
                context=context,
                normalized=normalized,
            )
        except IntegrityError as exc:
            raise DomainError(
                "CALENDAR_CREATE_RECONCILIATION_CONFLICT",
                "calendar-create reconciliation conflicted with concurrent durable state",
            ) from exc
        except OperationalError as exc:
            if not _is_transient_lock_collision(exc):
                raise
            raise DomainError(
                "CALENDAR_CREATE_RECONCILIATION_CONFLICT",
                "calendar-create reconciliation conflicted with concurrent durable state",
            ) from exc

    def _normalize_observation(self, *, observation, attempt, action, resource):
        if getattr(observation, "status", None) == "FOUND":
            with self.engine.connect() as conn:
                dispatch_claim = conn.execute(
                    select(
                        schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                    ).where(
                        schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                        == attempt["execution_attempt_id"]
                    )
                ).scalar_one_or_none()
            if dispatch_claim is None:
                fail(
                    "CALENDAR_CREATE_RECONCILIATION_FOUND_WITHOUT_DISPATCH_CLAIM",
                    "positive reconciliation cannot be Action-linked when the one-shot mutation dispatch claim never existed",
                )
        return super()._normalize_observation(
            observation=observation,
            attempt=attempt,
            action=action,
            resource=resource,
        )


__all__ = ["PersonalCalendarReconciliationServices"]
