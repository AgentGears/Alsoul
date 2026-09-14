from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from alsoul.adapters.contracts import (
    AdapterOutcomeUnknown,
    CalendarApprovalPresentationAcceptance,
)
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar_action import SetCalendarCreatePermissionStatusCommand
from alsoul.domain.personal_calendar_approval import (
    AdmitPersonalCalendarCreateApprovalCommand,
    CALENDAR_CREATE_APPROVAL_TEXT,
    PresentPersonalCalendarCreateApprovalCommand,
    RevokePersonalCalendarCreateApprovalCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.personal_calendar import ZoneInfoCalendarTimeResolver
from alsoul.services.personal_calendar_approval import PersonalCalendarApprovalServices
from alsoul.storage import schema

import test_f5_personal_calendar_authority as authority_cases
import test_f5b_calendar_action_authority as action_cases


@dataclass(slots=True)
class _ApprovalAdapter:
    sink_binding_ref: str = "first-party:test-calendar-approval"
    presentation_contract_version: str = "calendar-create-approval.presentation.v1"
    calls: list[dict] = field(default_factory=list)
    outcome_unknown: bool = False
    return_wrong_digest: bool = False

    def present_calendar_create_approval(
        self,
        *,
        presentation_key,
        action_id,
        surface_binding_id,
        channel_binding_id,
        consent_text,
        consent_payload_digest,
    ):
        self.calls.append(
            {
                "presentation_key": presentation_key,
                "action_id": action_id,
                "surface_binding_id": surface_binding_id,
                "channel_binding_id": channel_binding_id,
                "consent_text": consent_text,
                "consent_payload_digest": consent_payload_digest,
            }
        )
        if self.outcome_unknown:
            raise AdapterOutcomeUnknown("lost acceptance")
        return CalendarApprovalPresentationAcceptance(
            presentation_key=presentation_key,
            receipt_ref=f"approval-receipt:{presentation_key[-16:]}",
            consent_payload_digest=(
                "0" * 64 if self.return_wrong_digest else consent_payload_digest
            ),
        )


def _assert_code(exc: pytest.ExceptionInfo[DomainError], code: str) -> None:
    assert exc.value.code == code


def _service(engine, now, adapter=None):
    return PersonalCalendarApprovalServices(
        engine,
        time_resolver=ZoneInfoCalendarTimeResolver(
            rules_version=authority_cases._RULES_VERSION
        ),
        approval_adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )


def _prepared_action(engine, now):
    ids, foundation, _, resource, _, write_permission, _ = (
        action_cases._bootstrap_write_authority(engine, now)
    )
    source = action_cases._append_create_request(foundation, ids, now)
    action = action_cases._prepare(
        action_cases._service(engine, now),
        ids,
        resource,
        write_permission.permission_id,
        source,
    )
    return ids, foundation, resource, write_permission, action


def _present(service, action, *, operation_id=None):
    return service.present_create_approval(
        PresentPersonalCalendarCreateApprovalCommand(
            operation_id=operation_id or uuid4(),
            action_id=action.action_id,
        )
    )


def _admit(service, presentation, source_event, *, operation_id=None):
    return service.admit_create_approval(
        AdmitPersonalCalendarCreateApprovalCommand(
            operation_id=operation_id or uuid4(),
            approval_presentation_id=presentation.approval_presentation_id,
            source_interaction_event_id=source_event.event_id,
        )
    )


def test_faithful_consent_presentation_pins_exact_action_semantics_and_acceptance(
    engine, now
):
    ids, _, resource, _, action = _prepared_action(engine, now)
    adapter = _ApprovalAdapter()
    service = _service(engine, now, adapter)

    result = _present(service, action)

    assert len(adapter.calls) == 1
    sent = adapter.calls[0]
    assert sent["action_id"] == action.action_id
    assert "Calendar: calendar.test:primary" in sent["consent_text"]
    assert "Title: Dentist" in sent["consent_text"]
    assert "Start: 2026-09-10T15:00:00+03:00" in sent["consent_text"]
    assert "End: 2026-09-10T15:30:00+03:00" in sent["consent_text"]
    assert "Capability: calendar.event.create" in sent["consent_text"]
    assert "Effect: WRITE" in sent["consent_text"]
    assert result.consent_payload_digest == sent["consent_payload_digest"]

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.personal_calendar_create_approval_presentation).where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == result.approval_presentation_id
            )
        ).mappings().one()
        timeline = conn.execute(
            select(schema.relationship_timeline_head).where(
                schema.relationship_timeline_head.c.relationship_id
                == ids.relationship_id
            )
        ).mappings().one()

    assert row["action_id"] == action.action_id
    assert row["action_digest"] == action.action_digest
    assert row["personal_resource_binding_id"] == resource.personal_resource_binding_id
    assert row["target_calendar_display_identity"] == "calendar.test:primary"
    assert row["summary"] == "Dentist"
    assert row["start_text"] == "2026-09-10T15:00:00+03:00"
    assert row["end_text"] == "2026-09-10T15:30:00+03:00"
    assert row["presented_to_counterpart_id"] == ids.counterpart_id
    assert row["presentation_acceptance_ref"] == result.acceptance_ref
    assert row["presentation_timeline_frontier"] == timeline["last_timeline_seq"]


def test_presentation_replay_is_sink_idempotent_and_survives_adapter_removal(engine, now):
    _, _, _, _, action = _prepared_action(engine, now)
    adapter = _ApprovalAdapter()
    service = _service(engine, now, adapter)
    operation_id = uuid4()

    first = _present(service, action, operation_id=operation_id)
    replay = _present(service, action, operation_id=operation_id)
    assert replay == first
    assert len(adapter.calls) == 1

    recovered = _present(_service(engine, now, None), action)
    assert recovered.approval_presentation_id == first.approval_presentation_id
    assert len(adapter.calls) == 1


def test_sink_acceptance_must_bind_exact_consent_digest(engine, now):
    _, _, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, _ApprovalAdapter(return_wrong_digest=True))

    with pytest.raises(DomainError) as invalid:
        _present(service, action)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PRESENTATION_INVALID")

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_approval_presentation)
        ).first() is None


def test_unknown_presentation_is_not_admitted_as_trusted_consent(engine, now):
    _, _, _, _, action = _prepared_action(engine, now)
    adapter = _ApprovalAdapter(outcome_unknown=True)
    service = _service(engine, now, adapter)

    with pytest.raises(DomainError) as unknown:
        _present(service, action)
    _assert_code(unknown, "CALENDAR_CREATE_APPROVAL_PRESENTATION_OUTCOME_UNKNOWN")

    with engine.connect() as conn:
        assert conn.execute(
            select(schema.personal_calendar_create_approval_presentation)
        ).first() is None


def test_exact_counterpart_approval_after_presentation_is_admitted_and_revocable(
    engine, now
):
    ids, foundation, resource, write_permission, action = _prepared_action(engine, now)
    service = _service(engine, now, _ApprovalAdapter())
    presentation = _present(service, action)
    approval_event = authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )
    operation_id = uuid4()

    approval = _admit(
        service, presentation, approval_event, operation_id=operation_id
    )
    replay = _admit(
        service, presentation, approval_event, operation_id=operation_id
    )
    assert replay == approval

    with engine.connect() as conn:
        row = conn.execute(
            select(schema.personal_calendar_create_approval).where(
                schema.personal_calendar_create_approval.c.approval_id
                == approval.approval_id
            )
        ).mappings().one()
        state = conn.execute(
            select(schema.personal_calendar_create_approval_state).where(
                schema.personal_calendar_create_approval_state.c.approval_id
                == approval.approval_id,
                schema.personal_calendar_create_approval_state.c.revision == 1,
            )
        ).mappings().one()

    assert row["action_id"] == action.action_id
    assert row["approval_presentation_id"] == presentation.approval_presentation_id
    assert row["action_digest"] == action.action_digest
    assert row["authorized_approver_ref"] == ids.counterpart_id
    assert row["relationship_id"] == ids.relationship_id
    assert row["personal_resource_binding_id"] == resource.personal_resource_binding_id
    assert row["write_permission_id"] == write_permission.permission_id
    assert row["capability_semantic_operation"] == "calendar.event.create"
    assert row["effect_class"] == "WRITE"
    assert row["approval_ceremony_source"] == "FIRST_PARTY_COUNTERPART_APPROVAL_V1"
    assert state["status"] == "ACTIVE"

    revoked = service.revoke_create_approval(
        RevokePersonalCalendarCreateApprovalCommand(
            operation_id=uuid4(), approval_id=approval.approval_id
        )
    )
    assert revoked.revision == 2
    with engine.connect() as conn:
        current = conn.execute(
            select(schema.personal_calendar_create_approval_state)
            .join(
                schema.personal_calendar_create_approval_head,
                schema.personal_calendar_create_approval_head.c.approval_id
                == schema.personal_calendar_create_approval_state.c.approval_id,
            )
            .where(
                schema.personal_calendar_create_approval_state.c.approval_id
                == approval.approval_id,
                schema.personal_calendar_create_approval_state.c.revision
                == schema.personal_calendar_create_approval_head.c.current_revision,
            )
        ).mappings().one()
    assert current["status"] == "REVOKED"


def test_approval_input_that_predates_presentation_cannot_be_reused(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    prior = authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )
    service = _service(engine, now, _ApprovalAdapter())
    presentation = _present(service, action)

    with pytest.raises(DomainError) as invalid:
        _admit(service, presentation, prior)
    _assert_code(invalid, "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID")


def test_historical_or_wrong_approval_input_cannot_authorize_action(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, _ApprovalAdapter())
    presentation = _present(service, action)

    wrong = authority_cases._append_counterpart_event(
        foundation, ids, now, "Yes, please."
    )
    with pytest.raises(DomainError) as wrong_text:
        _admit(service, presentation, wrong)
    _assert_code(wrong_text, "CALENDAR_CREATE_APPROVAL_PROVENANCE_INVALID")

    approval_event = authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )
    authority_cases._append_counterpart_event(foundation, ids, now, "Hello")
    with pytest.raises(DomainError) as historical:
        _admit(service, presentation, approval_event)
    _assert_code(historical, "CALENDAR_CREATE_APPROVAL_SOURCE_NOT_CURRENT")


def test_tampered_presentation_semantics_cannot_mint_approval(engine, now):
    ids, foundation, _, _, action = _prepared_action(engine, now)
    service = _service(engine, now, _ApprovalAdapter())
    presentation = _present(service, action)
    with engine.begin() as conn:
        conn.execute(
            update(schema.personal_calendar_create_approval_presentation)
            .where(
                schema.personal_calendar_create_approval_presentation.c.approval_presentation_id
                == presentation.approval_presentation_id
            )
            .values(summary="Different event")
        )
    approval_event = authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )

    with pytest.raises(DomainError) as mismatch:
        _admit(service, presentation, approval_event)
    _assert_code(mismatch, "CALENDAR_CREATE_APPROVAL_SEMANTIC_MISMATCH")


def test_permission_revocation_after_presentation_blocks_approval(engine, now):
    ids, foundation, _, write_permission, action = _prepared_action(engine, now)
    service = _service(engine, now, _ApprovalAdapter())
    presentation = _present(service, action)
    service.set_create_permission_status(
        SetCalendarCreatePermissionStatusCommand(
            operation_id=uuid4(), permission_id=write_permission.permission_id
        )
    )
    approval_event = authority_cases._append_counterpart_event(
        foundation, ids, now, CALENDAR_CREATE_APPROVAL_TEXT
    )

    with pytest.raises(DomainError) as revoked:
        _admit(service, presentation, approval_event)
    _assert_code(revoked, "CALENDAR_CREATE_APPROVAL_PERMISSION_DENIED")
