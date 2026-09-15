from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.exc import IntegrityError, OperationalError

from alsoul.adapters.contracts import AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.personal_calendar_reconciliation import (
    PersonalCalendarReconciliationServices as PersonalCalendarReconciliationServicesV1,
    _RECONCILE_SCOPE,
    _is_transient_lock_collision,
)


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


__all__ = ["PersonalCalendarReconciliationServices"]
