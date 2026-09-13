from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

import test_f5_personal_calendar_authority as authority_cases
from alsoul.domain.errors import DomainError
from alsoul.domain.personal_calendar import (
    BindCalendarCredentialCommand,
    SetCredentialBindingStatusCommand,
)
from alsoul.storage import schema


def test_exit_credential_unusable_or_technically_under_scoped_blocks_dispatch(engine, now):
    (
        _ids,
        _foundation,
        calendar,
        observation,
        _resource,
        credential,
        permission,
        _prepared,
        _source_event,
        _grant_event,
    ) = authority_cases._bootstrap_calendar(engine, now)

    under_scoped = calendar.bind_credential(
        BindCalendarCredentialCommand(
            operation_id=uuid4(),
            external_system_ref="calendar.test",
            external_principal_ref="counterpart-account-under-scoped",
            secret_ref="secret://calendar/under-scoped",
            provider_scopes=("profile.read",),
        )
    )
    with pytest.raises(DomainError) as scope:
        calendar.fence_read_page(
            authority_cases.FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=permission.permission_id,
                credential_binding_id=under_scoped.credential_binding_id,
            )
        )
    assert scope.value.code == "PROVIDER_TECHNICAL_SCOPE_INSUFFICIENT"

    calendar.set_credential_status(
        SetCredentialBindingStatusCommand(
            operation_id=uuid4(),
            credential_binding_id=credential.credential_binding_id,
        )
    )
    with pytest.raises(DomainError) as revoked:
        calendar.fence_read_page(
            authority_cases.FencePersonalCalendarReadPageCommand(
                operation_id=uuid4(),
                observation_id=observation.observation_id,
                page_ordinal=0,
                permission_id=permission.permission_id,
                credential_binding_id=credential.credential_binding_id,
            )
        )
    assert revoked.value.code == "CREDENTIAL_BINDING_UNUSABLE"

    with engine.connect() as conn:
        assert conn.execute(
            select(func.count()).select_from(
                schema.personal_calendar_read_authority_fence
            )
        ).scalar_one() == 0
