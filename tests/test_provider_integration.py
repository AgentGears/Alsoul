from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import func, select

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
)
from alsoul.domain.models import FoundationResponseDraft, WorldAcquisitionSuccess
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import ModelGenerationRunner, WorldAcquisitionRunner
from alsoul.services.foundation import RAM_PREDICATE, WORLD_MEMORY_REQUIREMENT_PREDICATE
from alsoul.storage import schema


@dataclass(slots=True)
class InspectingWorldAdapter:
    engine: object
    now: object

    def acquire(self, *, captured_at) -> WorldAcquisitionSuccess:
        with self.engine.connect() as conn:
            started = conn.execute(
                select(func.count())
                .select_from(schema.observation)
                .where(schema.observation.c.status == "STARTED")
            ).scalar_one()
        assert started == 1
        return FakeWorldAdapter().acquire(captured_at=captured_at)


@dataclass(slots=True)
class FailingWorldAdapter:
    def acquire(self, *, captured_at) -> WorldAcquisitionSuccess:
        raise RuntimeError("acquisition failed")


@dataclass(slots=True)
class InspectingModelAdapter:
    engine: object
    provider_binding_ref: str = "configured-provider-binding"
    model_ref: str = "configured-model"

    def provider_request_digest(self, provider_context: dict) -> str:
        return FakeModelAdapter().provider_request_digest(provider_context)

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        with self.engine.connect() as conn:
            invocations = conn.execute(
                select(schema.model_invocation).where(
                    schema.model_invocation.c.outcome == "IN_PROGRESS"
                )
            ).mappings().all()
        assert len(invocations) == 1
        assert invocations[0]["provider_binding_ref"] == self.provider_binding_ref
        assert invocations[0]["model_ref"] == self.model_ref
        assert invocations[0]["provider_request_digest"] == self.provider_request_digest(
            provider_context
        )
        return FakeModelAdapter().generate(provider_context)


@dataclass(slots=True)
class UnknownModelAdapter:
    provider_binding_ref: str = "unknown-provider-binding"
    model_ref: str = "unknown-model"

    def provider_request_digest(self, provider_context: dict) -> str:
        return FakeModelAdapter().provider_request_digest(provider_context)

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        raise AdapterOutcomeUnknown("transport outcome unknown")


@dataclass(slots=True)
class RejectedModelAdapter:
    provider_binding_ref: str = "rejected-provider-binding"
    model_ref: str = "rejected-model"

    def provider_request_digest(self, provider_context: dict) -> str:
        return FakeModelAdapter().provider_request_digest(provider_context)

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        raise AdapterRejected("provider rejected request")


def _prepare_projection(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="provider-integration",
        external_subject="u1",
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
    return ids, projection


def test_world_runner_persists_observation_before_adapter_and_not_world_truth(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(identity_namespace="world-runner", external_subject="u1")
    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id, "current requirement"
        )
    )

    result = WorldAcquisitionRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).run(
        investigation_id=investigation.investigation_id,
        adapter=InspectingWorldAdapter(services.engine, now),
        acquisition_kind="FETCH",
        request_descriptor={"resource": "current requirements"},
    )

    with services.engine.connect() as conn:
        observation = conn.execute(
            select(schema.observation).where(
                schema.observation.c.observation_id == result.observation_id
            )
        ).mappings().one()
        world_count = conn.execute(
            select(func.count()).select_from(schema.world_result)
        ).scalar_one()
    assert observation["status"] == "SUCCEEDED"
    assert world_count == 0


def test_world_runner_marks_failed_acquisition_without_capture(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(identity_namespace="world-failure", external_subject="u1")
    investigation = services.start_investigation(
        StartInvestigationCommand(
            uuid4(), ids.companion_person_id, ids.relationship_id, "current requirement"
        )
    )
    runner = WorldAcquisitionRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(RuntimeError):
        runner.run(
            investigation_id=investigation.investigation_id,
            adapter=FailingWorldAdapter(),
            acquisition_kind="FETCH",
            request_descriptor={"resource": "current requirements"},
        )

    with services.engine.connect() as conn:
        observations = conn.execute(select(schema.observation)).mappings().all()
        captures = conn.execute(
            select(func.count()).select_from(schema.world_source_capture)
        ).scalar_one()
    assert len(observations) == 1
    assert observations[0]["status"] == "FAILED"
    assert captures == 0


def test_model_runner_persists_invocation_before_dispatch_and_only_generates_candidate(
    services, bootstrapper, now
):
    _, projection = _prepare_projection(services, bootstrapper, now)
    runner = ModelGenerationRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    result = runner.run(
        context_projection_id=projection.projection_id,
        adapter=InspectingModelAdapter(services.engine),
    )

    with services.engine.connect() as conn:
        invocation = conn.execute(
            select(schema.model_invocation).where(
                schema.model_invocation.c.model_invocation_id == result.model_invocation_id
            )
        ).mappings().one()
        generated = conn.execute(
            select(schema.generated_output).where(
                schema.generated_output.c.generated_output_id == result.generated_output_id
            )
        ).mappings().one()
        adopted_count = conn.execute(
            select(func.count()).select_from(schema.companion_output)
        ).scalar_one()
        presented_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT")
        ).scalar_one()
    assert invocation["outcome"] == "SUCCEEDED"
    assert generated["model_invocation_id"] == result.model_invocation_id
    assert adopted_count == 0
    assert presented_count == 0


def test_model_runner_records_unknown_transport_outcome(services, bootstrapper, now):
    _, projection = _prepare_projection(services, bootstrapper, now)
    runner = ModelGenerationRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(AdapterOutcomeUnknown):
        runner.run(
            context_projection_id=projection.projection_id,
            adapter=UnknownModelAdapter(),
        )

    with services.engine.connect() as conn:
        invocation = conn.execute(select(schema.model_invocation)).mappings().one()
        generated_count = conn.execute(
            select(func.count()).select_from(schema.generated_output)
        ).scalar_one()
    assert invocation["outcome"] == "UNKNOWN"
    assert generated_count == 0


def test_model_runner_records_definite_provider_rejection(services, bootstrapper, now):
    _, projection = _prepare_projection(services, bootstrapper, now)
    runner = ModelGenerationRunner(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(AdapterRejected):
        runner.run(
            context_projection_id=projection.projection_id,
            adapter=RejectedModelAdapter(),
        )

    with services.engine.connect() as conn:
        invocation = conn.execute(select(schema.model_invocation)).mappings().one()
    assert invocation["outcome"] == "FAILED"
