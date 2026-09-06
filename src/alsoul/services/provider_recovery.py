from __future__ import annotations

from uuid import UUID

from alsoul.services.foundation import FoundationServices
from alsoul.services.recovery import RecoveryCoordinator, ResponseRecoveryAssessment


class ProviderRecoveryCoordinator:
    """Reconcile provider-attempt state after a known runtime loss.

    The caller invokes this boundary only after the process that owned an
    `IN_PROGRESS` provider attempt is known to be gone. The attempt is then
    conservatively classified as `UNKNOWN`; no retry is dispatched automatically.
    """

    def __init__(self, services: FoundationServices) -> None:
        self.services = services
        self.recovery = RecoveryCoordinator(services.engine)

    def assess_response(
        self, *, relationship_id: UUID, current_input_event_id: UUID
    ) -> ResponseRecoveryAssessment:
        return self.recovery.assess_response(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )

    def reconcile_response_after_process_loss(
        self, *, relationship_id: UUID, current_input_event_id: UUID
    ) -> ResponseRecoveryAssessment:
        assessment = self.assess_response(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )
        if (
            assessment.stage != "MODEL_ATTEMPT_UNRESOLVED"
            or assessment.latest_model_invocation_outcome != "IN_PROGRESS"
            or assessment.latest_model_invocation_id is None
        ):
            return assessment

        self.services.fail_model_invocation(
            assessment.latest_model_invocation_id,
            unknown=True,
        )
        return self.assess_response(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )


__all__ = ["ProviderRecoveryCoordinator"]
