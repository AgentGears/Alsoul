from __future__ import annotations

import pytest

from alsoul.domain.errors import DomainError


def test_application_services_cannot_bootstrap_identity(services):
    with pytest.raises(DomainError) as exc:
        services.bootstrap_foundation(
            identity_namespace="test",
            external_subject="u1",
        )
    assert exc.value.code == "BOOTSTRAP_NOT_APPLICATION_SERVICE"


def test_explicit_bootstrap_creates_resolvable_identity(services, bootstrapper):
    ids = bootstrapper.bootstrap(
        identity_namespace="test",
        external_subject="u1",
    )

    resolved = services.resolve_inbound_identity(
        channel_namespace="alsoul.first_party",
        channel_ref="primary-text-channel",
        identity_namespace="test",
        external_subject="u1",
    )

    assert resolved == (
        ids.companion_person_id,
        ids.counterpart_id,
        ids.relationship_id,
    )
