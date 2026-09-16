from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    SetCredentialBindingStatusCommand,
)
from alsoul.domain.personal_calendar_execution import (
    AbandonPersonalCalendarCreateExecutionAttemptCommand,
)
from alsoul.storage import schema

import test_f5b_calendar_action_authority as action_cases
import test_f5b_calendar_execution_fence as execution_cases


def test_credential_rotation_cannot_silently_substitute_into_prepared_attempt(engine, now):
    (
        ids,
        _,
        _,
        _,
        action,
        approval,
        original_credential,
        service,
    ) = execution_cases._approved_action(engine, now)
    first = execution_cases._prepare(
        service, action, approval, original_credential
    )

    with engine.connect() as conn:
        identity_before = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()

    service.set_credential_status(
        SetCredentialBindingStatusCommand(
            operation_id=uuid4(),
            credential_binding_id=original_credential.credential_binding_id,
        )
    )
    replacement = service.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-calendar-writer",
            secret_ref="secret-ref:calendar-write-rotated",
            provider_scopes=(action_cases._CREATE_PROVIDER_SCOPE,),
        )
    )

    with pytest.raises(DomainError) as stale:
        execution_cases._fence(service, first)
    assert stale.value.code == "CALENDAR_CREATE_EXECUTION_CREDENTIAL_INVALID"

    released = service.abandon_prepared_attempt(
        AbandonPersonalCalendarCreateExecutionAttemptCommand(
            operation_id=uuid4(),
            execution_attempt_id=first.execution_attempt_id,
        )
    )
    assert released.status == "ABANDONED"

    second = execution_cases._prepare(service, action, approval, replacement)
    assert second.attempt_generation == first.attempt_generation + 1
    assert second.correlation_key == first.correlation_key
    fenced = execution_cases._fence(service, second)
    assert fenced.status == "DISPATCH_FENCED"

    with engine.connect() as conn:
        fence = conn.execute(
            select(schema.personal_calendar_create_execution_fence).where(
                schema.personal_calendar_create_execution_fence.c.execution_attempt_id
                == second.execution_attempt_id
            )
        ).mappings().one()
        identity_after = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()

    assert fence["credential_binding_id"] == replacement.credential_binding_id
    assert identity_after == identity_before
