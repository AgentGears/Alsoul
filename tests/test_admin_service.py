from __future__ import annotations

from uuid import uuid4

import pytest

from alsoul.admin import AdministrationError, FoundationAdministrator
from alsoul.domain.errors import DomainError
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.storage import create_sqlite_engine


def test_administrator_initializes_migrates_and_bootstraps_fresh_store(tmp_path):
    database = tmp_path / "alsoul.db"
    admin = FoundationAdministrator()

    missing = admin.status(database)
    assert not missing.database_exists
    assert missing.foundation_state == "NOT_READY"

    initialized = admin.initialize_store(database)
    assert initialized.database_path == database.resolve()
    assert initialized.schema_revision == "0003_open_loop_reference"

    empty = admin.status(database)
    assert empty.schema_at_head
    assert empty.foundation_state == "EMPTY"
    assert empty.companion_person_count == 0
    assert empty.counterpart_person_count == 0
    assert empty.relationship_count == 0

    migrated = admin.migrate_store(database)
    assert migrated.previous_revision == "0003_open_loop_reference"
    assert migrated.schema_revision == "0003_open_loop_reference"
    assert migrated.changed is False

    external_subject = str(uuid4())
    ids = admin.bootstrap_foundation(
        database,
        identity_namespace="admin-test",
        external_subject=external_subject,
    )

    bootstrapped = admin.status(database)
    assert bootstrapped.schema_at_head
    assert bootstrapped.foundation_state == "BOOTSTRAPPED"
    assert bootstrapped.companion_person_count == 1
    assert bootstrapped.counterpart_person_count == 1
    assert bootstrapped.relationship_count == 1

    engine = create_sqlite_engine(database)
    try:
        resolved = FoundationServices(engine).resolve_inbound_identity(
            channel_namespace="alsoul.first_party",
            channel_ref="primary-text-channel",
            identity_namespace="admin-test",
            external_subject=external_subject,
        )
    finally:
        engine.dispose()
    assert resolved == (
        ids.companion_person_id,
        ids.counterpart_id,
        ids.relationship_id,
    )


def test_initialize_store_never_overwrites_existing_path(tmp_path):
    database = tmp_path / "alsoul.db"
    database.write_text("existing", encoding="utf-8")
    admin = FoundationAdministrator()

    with pytest.raises(AdministrationError) as excinfo:
        admin.initialize_store(database)
    assert excinfo.value.code == "ADMIN_DATABASE_ALREADY_EXISTS"
    assert database.read_text(encoding="utf-8") == "existing"


def test_admin_bootstrap_refuses_nonempty_foundation(tmp_path):
    database = tmp_path / "alsoul.db"
    admin = FoundationAdministrator()
    admin.initialize_store(database)
    admin.bootstrap_foundation(
        database,
        identity_namespace="admin-test",
        external_subject="counterpart-a",
    )

    with pytest.raises(AdministrationError) as excinfo:
        admin.bootstrap_foundation(
            database,
            identity_namespace="admin-test",
            external_subject="counterpart-b",
        )
    assert excinfo.value.code == "ADMIN_FOUNDATION_NOT_EMPTY"


def test_foundation_bootstrapper_supports_explicit_empty_store_fence(tmp_path):
    database = tmp_path / "alsoul.db"
    admin = FoundationAdministrator()
    admin.initialize_store(database)

    engine = create_sqlite_engine(database)
    bootstrapper = FoundationBootstrapper(engine)
    try:
        bootstrapper.bootstrap(
            identity_namespace="direct-test",
            external_subject="counterpart-a",
            require_empty=True,
        )
        with pytest.raises(DomainError) as excinfo:
            bootstrapper.bootstrap(
                identity_namespace="direct-test",
                external_subject="counterpart-b",
                require_empty=True,
            )
    finally:
        engine.dispose()
    assert excinfo.value.code == "FOUNDATION_ALREADY_BOOTSTRAPPED"


def test_bootstrap_requires_schema_at_packaged_head(tmp_path):
    database = tmp_path / "empty.db"
    database.touch()
    admin = FoundationAdministrator()

    with pytest.raises(AdministrationError) as excinfo:
        admin.bootstrap_foundation(
            database,
            identity_namespace="admin-test",
            external_subject="counterpart-a",
        )
    assert excinfo.value.code == "ADMIN_SCHEMA_NOT_AT_HEAD"
