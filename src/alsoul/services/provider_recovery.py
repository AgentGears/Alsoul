from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.services.foundation import FoundationServices
from alsoul.services.recovery import RecoveryCoordinator, ResponseRecoveryAssessment
from alsoul.storage import schema


class ProviderRecoveryCoordinator:
    """Reconcile provider-attempt state after a known runtime loss.

    The caller invokes this boundary only after the process that owned an
    `IN_PROGRESS` provider attempt is known to be gone. Such attempts are
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
        # Reconcile every orphaned IN_PROGRESS attempt belonging to this response,
        # including attempts on projections that are now stale. Staleness affects
        # reuse eligibility, not the historical truth that the owning process died.
        with self.services.engine.connect() as conn:
            projection_ids = conn.execute(
                select(schema.context_projection.c.projection_id).where(
                    schema.context_projection.c.relationship_id == relationship_id,
                    schema.context_projection.c.current_input_event_id
                    == current_input_event_id,
                    schema.context_projection.c.purpose == "RESPOND_TO_INTERACTION",
                )
            ).scalars().all()

            if projection_ids:
                invocation_ids = conn.execute(
                    select(schema.model_invocation.c.model_invocation_id).where(
                        schema.model_invocation.c.context_projection_id.in_(
                            projection_ids
                        ),
                        schema.model_invocation.c.outcome == "IN_PROGRESS",
                    )
                ).scalars().all()
            else:
                invocation_ids = []

        for invocation_id in invocation_ids:
            try:
                self.services.fail_model_invocation(invocation_id, unknown=True)
            except DomainError as exc:
                # A concurrent durable completion may have won after the read.
                # Re-assessment below determines the authoritative state.
                if exc.code != "MODEL_INVOCATION_ALREADY_TERMINAL":
                    raise

        return self.assess_response(
            relationship_id=relationship_id,
            current_input_event_id=current_input_event_id,
        )


__all__ = ["ProviderRecoveryCoordinator"]
