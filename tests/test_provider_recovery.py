from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.adapters import (
    AdapterOutcomeUnknown,
    AdapterRejected,
    FakeModelAdapter,
    FakeWorldAdapter,
)
from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AdmitWorldResultCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import (
    FoundationServices,
    ModelGenerationRunner,
    ProviderRecoveryCoordinator,
    WorldAcquisitionRunner,
)
from alsoul.services.foundation import RAM_PREDICATE, WORLD_MEMORY_REQUIREMENT_PREDICATE
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.storage import schema


@dataclass(slots=True)
class RejectingModelAdapter:
    provider_binding_ref: str
    model_ref: str
    unknown: bool = False

    def provider_request_digest(self, provider_context: dict) -> str:
        return FakeModelAdapter(
            provider_binding_ref=self.provider_binding_ref,
            model_ref=self.model_ref,
        ).provider_request_digest(provider_context)

    def generate(self, provider_context: dict):
        if self.unknown:
            raise AdapterOutcomeUnknown("provider outcome is unknown")
        raise AdapterRejected("provider rejected generation")


def _prepare_projection(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="provider-recovery",
        external_subject=str(uuid4()),
    )
    memory_input = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "memory",
            "My machine has 16 GB RAM.",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            RAM_PREDICATE,
            16,
            memory_input.event_id,
        )
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "question",
            "Would the current software run on my machine?",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )
    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            "Determine the current minimum memory requirement.",
        )
    )
    acquired = WorldAcquisitionRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).run(
        investigation_id=investigation.investigation_id,
        adapter=FakeWorldAdapter(minimum_memory_gb=24),
        acquisition_kind="FETCH",
        request_descriptor={"resource": "current requirements"},
    )
    world = services.admit_world_result(
        AdmitWorldResultCommand(
            uuid4(),
            investigation.investigation_id,
            "REQUIREMENT",
            WORLD_MEMORY_REQUIREMENT_PREDICATE,
            24,
            (acquired.evidence_id,),
            valid_as_of=now,
        )
    )
    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            current.event_id,
            (RAM_PREDICATE,),
            (world.world_result_id,),
        )
    )
    return ids, current, projection


def test_process_loss_reconciles_orphaned_model_attempt_before_retry(
    services, bootstrapper, now
):
    ids, current, projection = _prepare_projection(services, bootstrapper, now)
    adapter = FakeModelAdapter()
    provider_context = services.render_provider_context(projection.projection_id)
    orphaned = services.start_model_invocation(
        StartModelInvocationCommand(
            uuid4(),
            projection.projection_id,
            adapter.provider_binding_ref,
            adapter.model_ref,
            "f4-renderer-v1",
            adapter.provider_request_digest(provider_context),
        )
    )

    assessment = RecoveryCoordinator(services.engine).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "MODEL_ATTEMPT_UNRESOLVED"
    assert assessment.latest_model_invocation_id == orphaned.model_invocation_id
    assert assessment.latest_model_invocation_outcome == "IN_PROGRESS"

    with pytest.raises(DomainError) as excinfo:
        ModelGenerationRunner(
            services,
            clock=FixedClock(now),
            ids=UUIDGenerator(),
        ).run(
            context_projection_id=projection.projection_id,
            adapter=FakeModelAdapter(
                provider_binding_ref="replacement-before-reconcile",
                model_ref="replacement-before-reconcile",
            ),
        )
    assert excinfo.value.code == "MODEL_INVOCATION_ALREADY_IN_PROGRESS"

    restarted = FoundationServices(
        services.engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    recovery = ProviderRecoveryCoordinator(restarted)
    reconciled = recovery.reconcile_response_after_process_loss(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert reconciled.stage == "PROJECTION_READY"
    assert reconciled.reusable_projection_id == projection.projection_id
    assert reconciled.latest_model_invocation_id == orphaned.model_invocation_id
    assert reconciled.latest_model_invocation_outcome == "UNKNOWN"

    replacement = ModelGenerationRunner(
        restarted,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).run(
        context_projection_id=projection.projection_id,
        adapter=FakeModelAdapter(
            provider_binding_ref="replacement-route",
            model_ref="replacement-model",
        ),
    )
    assert replacement.model_invocation_id != orphaned.model_invocation_id

    with services.engine.connect() as conn:
        old_row = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id
                == orphaned.model_invocation_id
            )
        ).mappings().one()
        new_row = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id
                == replacement.model_invocation_id
            )
        ).mappings().one()
    assert old_row["outcome"] == "UNKNOWN"
    assert new_row["outcome"] == "SUCCEEDED"
    assert new_row["provider_binding_ref"] == "replacement-route"
    assert new_row["model_ref"] == "replacement-model"


@pytest.mark.parametrize(
    ("unknown", "expected_outcome", "expected_exception"),
    [
        (False, "FAILED", AdapterRejected),
        (True, "UNKNOWN", AdapterOutcomeUnknown),
    ],
)
def test_failed_or_unknown_attempt_retries_as_new_invocation_with_replacement_provider(
    services,
    bootstrapper,
    now,
    unknown,
    expected_outcome,
    expected_exception,
):
    ids, current, projection = _prepare_projection(services, bootstrapper, now)
    runner = ModelGenerationRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(expected_exception):
        runner.run(
            context_projection_id=projection.projection_id,
            adapter=RejectingModelAdapter(
                provider_binding_ref="first-route",
                model_ref="first-model",
                unknown=unknown,
            ),
        )

    assessment = RecoveryCoordinator(services.engine).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "PROJECTION_READY"
    assert assessment.reusable_projection_id == projection.projection_id
    assert assessment.latest_model_invocation_outcome == expected_outcome
    first_invocation_id = assessment.latest_model_invocation_id
    assert first_invocation_id is not None

    replacement = runner.run(
        context_projection_id=projection.projection_id,
        adapter=FakeModelAdapter(
            provider_binding_ref="second-route",
            model_ref="second-model",
        ),
    )
    assert replacement.model_invocation_id != first_invocation_id

    with services.engine.connect() as conn:
        first_row = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id == first_invocation_id
            )
        ).mappings().one()
        replacement_row = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id
                == replacement.model_invocation_id
            )
        ).mappings().one()
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()
    assert first_row["outcome"] == expected_outcome
    assert replacement_row["outcome"] == "SUCCEEDED"
    assert replacement_row["provider_binding_ref"] == "second-route"
    assert replacement_row["model_ref"] == "second-model"
    assert relationship["companion_person_id"] == ids.companion_person_id
    assert relationship["counterpart_id"] == ids.counterpart_id


def test_stale_projection_is_not_reused_after_timeline_advances(
    services, bootstrapper, now
):
    ids, current, projection = _prepare_projection(services, bootstrapper, now)
    services.append_counterpart_input(
        AppendCounterpartInputCommand(
            uuid4(),
            ids.companion_person_id,
            ids.counterpart_id,
            ids.relationship_id,
            "new-input",
            "One more thing.",
            now,
            ids.surface_binding_id,
            ids.channel_binding_id,
        )
    )

    assessment = RecoveryCoordinator(services.engine).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "INPUT_ADMITTED"
    assert assessment.reusable_projection_id is None
    assert assessment.projection_reuse_blocker == "TIMELINE_ADVANCED"

    with pytest.raises(DomainError) as excinfo:
        ModelGenerationRunner(
            services,
            clock=FixedClock(now),
            ids=UUIDGenerator(),
        ).run(
            context_projection_id=projection.projection_id,
            adapter=FakeModelAdapter(),
        )
    assert excinfo.value.code == "CONTEXT_PROJECTION_NOT_REUSABLE"


def test_existing_generated_output_is_recovered_instead_of_regenerated(
    services, bootstrapper, now
):
    ids, current, projection = _prepare_projection(services, bootstrapper, now)
    runner = ModelGenerationRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    first = runner.run(
        context_projection_id=projection.projection_id,
        adapter=FakeModelAdapter(),
    )

    assessment = RecoveryCoordinator(services.engine).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "GENERATED"
    assert assessment.reusable_generated_output_id == first.generated_output_id

    with pytest.raises(DomainError) as excinfo:
        runner.run(
            context_projection_id=projection.projection_id,
            adapter=FakeModelAdapter(
                provider_binding_ref="redundant-route",
                model_ref="redundant-model",
            ),
        )
    assert excinfo.value.code == "MODEL_OUTPUT_ALREADY_AVAILABLE"


def test_acquisition_retry_after_orphaned_start_creates_new_observation(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="acquisition-recovery",
        external_subject=str(uuid4()),
    )
    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(),
            ids.companion_person_id,
            ids.relationship_id,
            "Determine the current minimum memory requirement.",
        )
    )
    orphaned = services.start_observation(
        StartObservationCommand(
            uuid4(),
            investigation.investigation_id,
            "FETCH",
            {"resource": "current requirements"},
        )
    )

    restarted = FoundationServices(
        services.engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    retried = WorldAcquisitionRunner(
        restarted,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).run(
        investigation_id=investigation.investigation_id,
        adapter=FakeWorldAdapter(minimum_memory_gb=24),
        acquisition_kind="FETCH",
        request_descriptor={"resource": "current requirements"},
    )

    assert retried.observation_id != orphaned.observation_id
    with services.engine.connect() as conn:
        old_row = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == orphaned.observation_id
            )
        ).mappings().one()
        new_row = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == retried.observation_id
            )
        ).mappings().one()
        capture = conn.execute(
            select(schema.world_source_capture).where(
                schema.world_source_capture.c.source_capture_id
                == retried.source_capture_id
            )
        ).mappings().one()
    assert old_row["status"] == "STARTED"
    assert new_row["status"] == "SUCCEEDED"
    assert capture["observation_id"] == retried.observation_id
