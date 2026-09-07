from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from alsoul.adapters import FakePresentationAdapter
from alsoul.domain.commands import (
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.services import (
    F4ConversationOpenLoopService,
    FoundationConversationalResponseCoordinator,
)
from alsoul.services.common import sha256_text
from alsoul.services.foundation_base import FoundationServices as LegacyFoundationServices
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.storage import schema


@dataclass(slots=True)
class OpenLoopRecoveryModel:
    provider_binding_ref: str = "open-loop-upgrade-provider"
    model_ref: str = "open-loop-upgrade-model-v1"
    calls: int = 0

    def provider_request_digest(self, provider_context: dict) -> str:
        return sha256(
            json.dumps(
                provider_context,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        self.calls += 1
        assert "conversation_open_loop_context" in provider_context
        return FoundationResponseDraft(
            segments=(
                FoundationResponseSegment(
                    "COMPANION_EXPRESSION",
                    "We can return to that decision.",
                    None,
                ),
            )
        )


def _append(services, ids, now, *, key: str, text: str):
    return services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=key,
            content_text=text,
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="open-loop-upgrade-thread",
        )
    )


def test_recovery_rejects_legacy_projection_without_open_loop_lineage(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="open-loop-upgrade",
        external_subject=str(uuid4()),
    )
    opening = _append(
        services,
        ids,
        now,
        key="open-loop-opening",
        text="I need to decide between A and B.",
    )
    F4ConversationOpenLoopService(services).consider_event(opening.event_id)

    current = _append(
        services,
        ids,
        now,
        key="open-loop-resume",
        text="Back to that decision.",
    )

    # Simulate a projection written before open-loop-aware selection existed. It
    # contains only the current input and may already have a durable generated
    # candidate, but that historical candidate is not eligible for adoption now.
    legacy = LegacyFoundationServices(
        services.engine,
        clock=services.clock,
        ids=services.ids,
    )
    projection = legacy.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            required_personal_predicates=(),
            required_world_result_ids=(),
        )
    )
    invocation = legacy.start_model_invocation(
        StartModelInvocationCommand(
            operation_id=uuid4(),
            context_projection_id=projection.projection_id,
            provider_binding_ref="legacy-open-loop-provider",
            model_ref="legacy-open-loop-model-v1",
            renderer_version="f4-renderer-v2",
            provider_request_digest="legacy-open-loop-request",
        )
    )
    legacy_text = "Legacy answer without durable open-loop selection."
    generated = legacy.complete_model_invocation(
        CompleteModelInvocationCommand(
            operation_id=uuid4(),
            model_invocation_id=invocation.model_invocation_id,
            content_text=legacy_text,
            content_digest=sha256_text(legacy_text),
            semantic_payload={
                "segments": [
                    {
                        "epistemic_kind": "COMPANION_EXPRESSION",
                        "text": legacy_text,
                        "source_ref": None,
                    }
                ]
            },
            received_at=now,
        )
    )

    assessment = RecoveryCoordinator(services.engine).assess_response(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
    )
    assert assessment.stage == "INPUT_ADMITTED"
    assert assessment.reusable_projection_id is None
    assert assessment.reusable_generated_output_id is None
    assert assessment.projection_reuse_blocker == (
        "CONVERSATION_OPEN_LOOP_SELECTION_INVALID"
    )

    model = OpenLoopRecoveryModel()
    recovered = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=FakePresentationAdapter(),
        after_process_loss=True,
    )

    assert model.calls == 1
    assert recovered.context_projection_id != projection.projection_id
    assert recovered.generated_output_id != generated.generated_output_id

    with services.engine.connect() as conn:
        item = conn.execute(
            select(schema.context_projection_open_loop_item).where(
                schema.context_projection_open_loop_item.c.projection_id
                == recovered.context_projection_id
            )
        ).mappings().one()
        output = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == recovered.companion_output_id
            )
        ).mappings().one()

    assert item["selection_basis"] == "CURRENT_OPEN_DECISION_LOOP"
    assert output["source_generated_output_id"] == recovered.generated_output_id
    assert output["source_generated_output_id"] != generated.generated_output_id
