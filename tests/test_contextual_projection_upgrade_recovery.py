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
from alsoul.services import FoundationConversationalResponseCoordinator
from alsoul.services.common import sha256_text
from alsoul.services.foundation_base import FoundationServices as LegacyFoundationServices
from alsoul.services.recovery import RecoveryCoordinator
from alsoul.storage import schema


@dataclass(slots=True)
class ContextModel:
    provider_binding_ref: str = "context-upgrade-provider"
    model_ref: str = "context-upgrade-model-v1"
    calls: int = 0

    def provider_request_digest(self, provider_context: dict) -> str:
        payload = json.dumps(
            provider_context,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def generate(self, provider_context: dict) -> FoundationResponseDraft:
        self.calls += 1
        assert "prior_timeline_context" in provider_context
        return FoundationResponseDraft(
            segments=(
                FoundationResponseSegment(
                    "COMPANION_EXPRESSION",
                    "I think that exchange was clear.",
                    None,
                ),
            )
        )


def _append_input(services, ids, now, *, key: str, text: str):
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
            conversation_id="upgrade-context-thread",
        )
    )


def test_recovery_rejects_legacy_one_event_projection_for_contextual_input(
    services, bootstrapper, now
):
    ids = bootstrapper.bootstrap(
        identity_namespace="context-upgrade",
        external_subject=str(uuid4()),
    )
    presentation = FakePresentationAdapter()

    first_input = _append_input(
        services,
        ids,
        now,
        key="upgrade-first-input",
        text="Hello.",
    )

    @dataclass(slots=True)
    class FirstModel:
        provider_binding_ref: str = "context-upgrade-provider"
        model_ref: str = "context-upgrade-model-v1"

        def provider_request_digest(self, provider_context: dict) -> str:
            payload = json.dumps(
                provider_context,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            return sha256(payload).hexdigest()

        def generate(self, provider_context: dict) -> FoundationResponseDraft:
            assert "prior_timeline_context" not in provider_context
            return FoundationResponseDraft(
                segments=(
                    FoundationResponseSegment(
                        "COMPANION_EXPRESSION",
                        "Hello. I'm here.",
                        None,
                    ),
                )
            )

    first = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=first_input.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=FirstModel(),
        presentation_adapter=presentation,
    )

    current = _append_input(
        services,
        ids,
        now,
        key="upgrade-contextual-input",
        text="What do you think about that?",
    )

    # Simulate state written by the previously exported projection behavior: the
    # contextual text was admitted, but its projection selected only the current
    # input and therefore had no bounded prior-Timeline context.
    legacy = LegacyFoundationServices(services.engine, clock=services.clock, ids=services.ids)
    legacy_projection = legacy.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            required_personal_predicates=(),
            required_world_result_ids=(),
        )
    )
    legacy_invocation = legacy.start_model_invocation(
        StartModelInvocationCommand(
            operation_id=uuid4(),
            context_projection_id=legacy_projection.projection_id,
            provider_binding_ref="legacy-context-provider",
            model_ref="legacy-context-model-v1",
            renderer_version="f4-renderer-v1",
            provider_request_digest="legacy-request",
        )
    )
    legacy_text = "Legacy contextual output without selected history."
    legacy_generated = legacy.complete_model_invocation(
        CompleteModelInvocationCommand(
            operation_id=uuid4(),
            model_invocation_id=legacy_invocation.model_invocation_id,
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
    assert assessment.projection_reuse_blocker == "CONTEXTUAL_HISTORY_SELECTION_INVALID"

    model = ContextModel()
    recovered = FoundationConversationalResponseCoordinator(services).respond(
        relationship_id=ids.relationship_id,
        current_input_event_id=current.event_id,
        surface_binding_id=ids.surface_binding_id,
        channel_binding_id=ids.channel_binding_id,
        model_adapter=model,
        presentation_adapter=presentation,
        after_process_loss=True,
    )

    assert model.calls == 1
    assert recovered.context_projection_id != legacy_projection.projection_id
    assert recovered.generated_output_id != legacy_generated.generated_output_id

    with services.engine.connect() as conn:
        selected = conn.execute(
            select(schema.context_projection_event)
            .where(
                schema.context_projection_event.c.projection_id
                == recovered.context_projection_id
            )
            .order_by(schema.context_projection_event.c.ordinal)
        ).mappings().all()
        adopted = conn.execute(
            select(schema.companion_output).where(
                schema.companion_output.c.companion_output_id
                == recovered.companion_output_id
            )
        ).mappings().one()

    assert [row["event_id"] for row in selected] == [
        first_input.event_id,
        first.presented_event_id,
        current.event_id,
    ]
    assert adopted["content_text"] == "I think that exchange was clear."
    assert adopted["source_generated_output_id"] == recovered.generated_output_id
    assert adopted["source_generated_output_id"] != legacy_generated.generated_output_id
