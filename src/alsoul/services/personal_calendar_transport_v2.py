from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_execution import (
    FencePersonalCalendarCreateExecutionAttemptCommand,
)
from alsoul.domain.personal_calendar_transport import (
    DispatchPersonalCalendarCreateMutationCommand,
    PersonalCalendarCreateMutationTransportResult,
)
from alsoul.services.common import load_operation_receipt, request_digest
from alsoul.services.personal_calendar_transport import (
    PersonalCalendarMutationTransportServices as PersonalCalendarMutationTransportServicesV1,
    _DISPATCH_SCOPE,
)
from alsoul.storage import schema


class PersonalCalendarMutationTransportServices(
    PersonalCalendarMutationTransportServicesV1
):
    """Current mutation boundary with a non-replayable fence-to-transport handoff.

    A dispatch fence that already exists when a fresh transport command begins is a
    surviving may-have-dispatched fence, not a reusable authority token. Only a
    PREPARED attempt that this same call advances through the current authority gate
    may proceed to the provider adapter. Completed evidence/receipts remain replayable
    without provider transport.
    """

    def dispatch_create_mutation(
        self, command: DispatchPersonalCalendarCreateMutationCommand
    ) -> PersonalCalendarCreateMutationTransportResult:
        req = request_digest(asdict(command))
        with self.engine.connect() as conn:
            replay = load_operation_receipt(
                conn,
                scope=_DISPATCH_SCOPE,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return self._transport_result_from_json(replay)

        entry = self._classify_transport_entry(command)
        if entry["kind"] in {"EVIDENCE", "DISPATCH_CLAIM"}:
            # V1 recovery is safe here: evidence is returned without transport, while
            # a surviving one-shot claim becomes UNKNOWN and is never sent again.
            return super().dispatch_create_mutation(command)
        if entry["kind"] in {"SURVIVING_FENCE", "UNKNOWN"}:
            return self._record_unknown(
                command=command,
                req_digest=req,
                action_id=entry["action_id"],
            )

        self.fence_execution_attempt(
            FencePersonalCalendarCreateExecutionAttemptCommand(
                operation_id=command.operation_id,
                execution_attempt_id=command.execution_attempt_id,
            )
        )
        return super().dispatch_create_mutation(command)

    def _classify_transport_entry(self, command):
        with self.engine.connect() as conn:
            attempt = self._load_attempt(conn, command.execution_attempt_id)
            evidence = conn.execute(
                select(schema.personal_calendar_create_effect_evidence).where(
                    schema.personal_calendar_create_effect_evidence.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if evidence is not None:
                return {"kind": "EVIDENCE", "action_id": attempt["action_id"]}

            dispatch = conn.execute(
                select(schema.personal_calendar_create_mutation_dispatch).where(
                    schema.personal_calendar_create_mutation_dispatch.c.execution_attempt_id
                    == command.execution_attempt_id
                )
            ).mappings().one_or_none()
            if dispatch is not None:
                return {
                    "kind": "DISPATCH_CLAIM",
                    "action_id": attempt["action_id"],
                }

            state, _ = self._current_attempt_state(
                conn, command.execution_attempt_id
            )
            if state["status"] == "DISPATCH_FENCED":
                return {
                    "kind": "SURVIVING_FENCE",
                    "action_id": attempt["action_id"],
                }
            if state["status"] == "UNKNOWN_EFFECT":
                return {"kind": "UNKNOWN", "action_id": attempt["action_id"]}
            if state["status"] != "PREPARED":
                fail(
                    "CALENDAR_CREATE_MUTATION_NOT_DISPATCH_ELIGIBLE",
                    "calendar-create mutation transport requires a current PREPARED attempt",
                )

            action, _, _, resource = self._load_action_lineage(
                conn, attempt["action_id"]
            )
            binding = self._require_execution_binding(action=action, resource=resource)
            adapter = self.mutation_adapter
            if adapter is None or not callable(getattr(adapter, "create_event", None)):
                fail(
                    "CALENDAR_CREATE_MUTATION_ADAPTER_UNAVAILABLE",
                    "calendar-create mutation transport requires a trusted current adapter before fencing",
                )
            exact_pairs = (
                (getattr(adapter, "adapter_binding_ref", None), binding.adapter_binding_ref),
                (
                    getattr(adapter, "adapter_contract_version", None),
                    binding.adapter_contract_version,
                ),
                (
                    getattr(adapter, "capability_contract_version", None),
                    binding.capability_contract_version,
                ),
                (
                    getattr(adapter, "external_system_ref", None),
                    binding.external_system_ref,
                ),
            )
            if any(
                not isinstance(left, str) or not left.strip() or left != right
                for left, right in exact_pairs
            ):
                fail(
                    "CALENDAR_CREATE_MUTATION_ADAPTER_MISMATCH",
                    "mutation adapter does not match the current execution binding selected for a fresh fence",
                )
            return {"kind": "PREPARED", "action_id": attempt["action_id"]}


__all__ = ["PersonalCalendarMutationTransportServices"]
