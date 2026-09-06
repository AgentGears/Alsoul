from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from alsoul.adapters import FakeModelAdapter, FakeWorldAdapter
from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AppendCounterpartInputCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationResponseCoordinator, FoundationServices
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.storage import create_sqlite_engine, schema


class InjectedProcessLoss(RuntimeError):
    pass


@dataclass
class CrashAt:
    target: str
    fired: bool = False

    def __call__(self, stage: str) -> None:
        if stage == self.target and not self.fired:
            self.fired = True
            raise InjectedProcessLoss(stage)


CHECKPOINTS = (
    "INPUT_ADMITTED",
    "INVESTIGATION_STARTED",
    "OBSERVATION_STARTED",
    "WORLD_CAPTURED",
    "WORLD_RESULT_ADMITTED",
    "CONTEXT_PROJECTION_BUILT",
    "MODEL_INVOCATION_STARTED",
    "GENERATED_OUTPUT_COMMITTED",
    "OUTPUT_TARGET_RESOLVED",
    "COMPANION_OUTPUT_ADOPTED",
    "PRESENTED",
)


def _prepare_current_input(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="runtime-coordinator",
        external_subject=str(uuid4()),
    )
    memory_input = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="memory-input",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="thread-a",
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=16,
            source_event_id=memory_input.event_id,
        )
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="current-input",
            content_text="Would the current software run on my machine?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="thread-b",
        )
    )
    return ids, current


@pytest.mark.parametrize("crash_stage", CHECKPOINTS)
def test_runtime_coordinator_resumes_after_process_loss_at_every_durable_boundary(
    services,
    bootstrapper,
    db_path,
    now,
    crash_stage,
):
    ids, current = _prepare_current_input(services, bootstrapper, now)
    first_runtime = FoundationResponseCoordinator(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(InjectedProcessLoss):
        first_runtime.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            world_adapter=FakeWorldAdapter(minimum_memory_gb=24),
            model_adapter=FakeModelAdapter(),
            checkpoint=CrashAt(crash_stage),
        )

    services.engine.dispose()

    restarted_engine = create_sqlite_engine(db_path)
    restarted_services = FoundationServices(
        restarted_engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    resumed = FoundationResponseCoordinator(
        restarted_services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        world_adapter=FakeWorldAdapter(minimum_memory_gb=24),
        model_adapter=FakeModelAdapter(),
        after_process_loss=True,
    )

    with restarted_engine.connect() as conn:
        presented = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == resumed.presented_event_id
            )
        ).mappings().one()
        counts = {
            "investigations": conn.execute(
                select(func.count()).select_from(schema.investigation)
            ).scalar_one(),
            "observations": conn.execute(
                select(func.count()).select_from(schema.observation)
            ).scalar_one(),
            "captures": conn.execute(
                select(func.count()).select_from(schema.world_source_capture)
            ).scalar_one(),
            "world_results": conn.execute(
                select(func.count()).select_from(schema.world_result)
            ).scalar_one(),
            "projections": conn.execute(
                select(func.count()).select_from(schema.context_projection)
            ).scalar_one(),
            "invocations": conn.execute(
                select(func.count()).select_from(schema.model_invocation)
            ).scalar_one(),
            "generated": conn.execute(
                select(func.count()).select_from(schema.generated_output)
            ).scalar_one(),
            "targets": conn.execute(
                select(func.count()).select_from(schema.output_target)
            ).scalar_one(),
            "outputs": conn.execute(
                select(func.count()).select_from(schema.companion_output)
            ).scalar_one(),
            "presentations": conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT"
                )
            ).scalar_one(),
        }
        invocation_outcomes = conn.execute(
            select(schema.model_invocation.c.outcome)
        ).scalars().all()
        observation_statuses = conn.execute(
            select(schema.observation.c.status)
        ).scalars().all()

    assert presented["companion_output_id"] == resumed.companion_output_id
    assert "You told me" in presented["content_text"]
    assert "I checked" in presented["content_text"]
    assert "My take" in presented["content_text"]

    assert counts["investigations"] == 1
    assert counts["captures"] == 1
    assert counts["world_results"] == 1
    assert counts["projections"] == 1
    assert counts["generated"] == 1
    assert counts["targets"] == 1
    assert counts["outputs"] == 1
    assert counts["presentations"] == 1

    if crash_stage == "OBSERVATION_STARTED":
        assert counts["observations"] == 2
        assert sorted(observation_statuses) == ["STARTED", "SUCCEEDED"]
    else:
        assert counts["observations"] == 1
        assert observation_statuses == ["SUCCEEDED"]

    if crash_stage == "MODEL_INVOCATION_STARTED":
        assert counts["invocations"] == 2
        assert sorted(invocation_outcomes) == ["SUCCEEDED", "UNKNOWN"]
    else:
        assert counts["invocations"] == 1
        assert invocation_outcomes == ["SUCCEEDED"]

    restarted_engine.dispose()


def test_runtime_coordinator_does_not_blindly_retry_unresolved_model_attempt(
    services,
    bootstrapper,
    now,
):
    ids, current = _prepare_current_input(services, bootstrapper, now)
    runtime = FoundationResponseCoordinator(
        services,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )

    with pytest.raises(InjectedProcessLoss):
        runtime.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            world_adapter=FakeWorldAdapter(minimum_memory_gb=24),
            model_adapter=FakeModelAdapter(),
            checkpoint=CrashAt("MODEL_INVOCATION_STARTED"),
        )

    with pytest.raises(DomainError) as excinfo:
        runtime.respond(
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            world_adapter=FakeWorldAdapter(minimum_memory_gb=24),
            model_adapter=FakeModelAdapter(),
            after_process_loss=False,
        )
    assert excinfo.value.code == "MODEL_ATTEMPT_UNRESOLVED"

    with services.engine.connect() as conn:
        invocation_rows = conn.execute(
            select(schema.model_invocation)
        ).mappings().all()
    assert len(invocation_rows) == 1
    assert invocation_rows[0]["outcome"] == "IN_PROGRESS"
