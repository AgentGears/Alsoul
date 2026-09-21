from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, update

from alsoul.domain.commands import (
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    ResolveOutputTargetCommand,
    StartModelInvocationCommand,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.models import FoundationResponseDraft, FoundationResponseSegment
from alsoul.domain.progressive_presentation import (
    DispatchProgressivePresentationFrameCommand,
    FenceProgressivePresentationAttemptCommand,
    OpenProgressivePresentationCommand,
    PROGRESSIVE_PRESENTATION_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION,
    PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION,
    ProgressivePresentationFrameTransportResult,
)
from alsoul.services import F4ConversationalOutputAdoption, ProgressivePresentationServices
from alsoul.services.common import canonical_json, sha256_text
from alsoul.storage import schema


def _adopt_output(services, bootstrapper, now):
    ids = bootstrapper.bootstrap(
        identity_namespace="f6a-authority-guard-test",
        external_subject=str(uuid4()),
    )
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key=str(uuid4()),
            content_text="Give me one bounded conversational response.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
            conversation_id="f6a-authority-guard-test",
        )
    )
    projection = services.build_context_projection(
        BuildContextProjectionCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            current_input_event_id=current.event_id,
            required_personal_predicates=(),
            required_world_result_ids=(),
        )
    )
    provider_context = services.render_provider_context(projection.projection_id)
    invocation = services.start_model_invocation(
        StartModelInvocationCommand(
            operation_id=uuid4(),
            context_projection_id=projection.projection_id,
            provider_binding_ref="f6a-authority-test-provider",
            model_ref="f6a-authority-test-model-v1",
            renderer_version="f6a-authority-test-renderer-v1",
            provider_request_digest=sha256_text(canonical_json(provider_context)),
        )
    )
    draft = FoundationResponseDraft(
        segments=(
            FoundationResponseSegment(
                epistemic_kind="COMPANION_EXPRESSION",
                text="Authority must remain fail closed.",
                source_ref=None,
            ),
        )
    )
    generated = services.complete_model_invocation(
        CompleteModelInvocationCommand(
            operation_id=uuid4(),
            model_invocation_id=invocation.model_invocation_id,
            content_text=draft.render_text(),
            content_digest=sha256_text(draft.render_text()),
            semantic_payload=draft.to_payload(),
            received_at=now,
        )
    )
    target = services.resolve_output_target(
        ResolveOutputTargetCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            target_kind="INTERACTION_EVENT",
            target_ref=current.event_id,
            purpose="FINAL_RESPONSE",
        )
    )
    adopted = F4ConversationalOutputAdoption(services).adopt(
        AdoptCompanionOutputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            relationship_id=ids.relationship_id,
            output_target_id=target.output_target_id,
            origin_kind="RESPONSE_TO_EVENT",
            origin_ref=current.event_id,
            generated_output_id=generated.generated_output_id,
        )
    )
    return ids, adopted


class _AcceptingAdapter:
    presentation_contract_version = PROGRESSIVE_PRESENTATION_CONTRACT_VERSION
    frame_contract_version = PROGRESSIVE_PRESENTATION_FRAME_CONTRACT_VERSION
    transport_contract_version = PROGRESSIVE_PRESENTATION_TRANSPORT_CONTRACT_VERSION

    def __init__(self, now):
        self.now = now
        self.calls = 0

    def dispatch_frame(self, **kwargs):
        self.calls += 1
        return ProgressivePresentationFrameTransportResult(
            presentation_key=kwargs["presentation_key"],
            attempt_generation=kwargs["attempt_generation"],
            presentation_transport_fence_scope_id=kwargs[
                "presentation_transport_fence_scope_id"
            ],
            frame_ordinal=kwargs["frame_ordinal"],
            frame_digest=kwargs["frame_digest"],
            acceptance_state="ACCEPTED",
            acceptance_ref="accepted",
            accepted_at=self.now,
        )


def test_governed_personal_calendar_origin_cannot_enter_generic_progressive_path(
    services, bootstrapper, engine, now
):
    ids, adopted = _adopt_output(services, bootstrapper, now)
    with engine.begin() as conn:
        conn.execute(
            update(schema.companion_output)
            .where(
                schema.companion_output.c.companion_output_id
                == adopted.companion_output_id
            )
            .values(origin_kind="PERSONAL_CALENDAR_SCHEDULE")
        )

    service = ProgressivePresentationServices(engine, clock=services.clock, ids=services.ids)
    with pytest.raises(DomainError) as exc:
        service.open_session(
            OpenProgressivePresentationCommand(
                operation_id=uuid4(),
                companion_output_id=adopted.companion_output_id,
                surface_binding_id=ids.surface_binding_id,
                channel_binding_id=ids.channel_binding_id,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_SPECIALIZED_AUTHORITY_REQUIRED"

    with engine.connect() as conn:
        session = conn.execute(
            select(schema.progressive_presentation_session).where(
                schema.progressive_presentation_session.c.companion_output_id
                == adopted.companion_output_id
            )
        ).mappings().one_or_none()
    assert session is None


def test_dispatch_rechecks_governed_output_before_payload_transport(
    services, bootstrapper, engine, now
):
    ids, adopted = _adopt_output(services, bootstrapper, now)
    adapter = _AcceptingAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=services.clock,
        ids=services.ids,
    )
    session = service.open_session(
        OpenProgressivePresentationCommand(
            operation_id=uuid4(),
            companion_output_id=adopted.companion_output_id,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    attempt = service.fence_attempt(
        FenceProgressivePresentationAttemptCommand(
            operation_id=uuid4(),
            presentation_session_id=session.presentation_session_id,
        )
    )

    with engine.begin() as conn:
        conn.execute(
            update(schema.companion_output)
            .where(
                schema.companion_output.c.companion_output_id
                == adopted.companion_output_id
            )
            .values(origin_kind="PERSONAL_CALENDAR_MUTATION_RESULT")
        )

    with pytest.raises(DomainError) as exc:
        service.dispatch_frame(
            DispatchProgressivePresentationFrameCommand(
                operation_id=uuid4(),
                presentation_attempt_id=attempt.presentation_attempt_id,
                frame_ordinal=1,
            )
        )
    assert exc.value.code == "PROGRESSIVE_PRESENTATION_SPECIALIZED_AUTHORITY_REQUIRED"
    assert adapter.calls == 0

    with engine.connect() as conn:
        transport = conn.execute(
            select(schema.progressive_presentation_frame_transport).where(
                schema.progressive_presentation_frame_transport.c.presentation_attempt_id
                == attempt.presentation_attempt_id
            )
        ).mappings().one_or_none()
    assert transport is None
