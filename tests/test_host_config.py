from __future__ import annotations

import json

import pytest

from alsoul.host import (
    HostConfigurationError,
    assess_host_readiness,
    load_host_config,
    load_runtime_secrets,
)
from alsoul.storage import create_schema, create_sqlite_engine


def _payload(database_path: str = "alsoul.db") -> dict:
    return {
        "host_config_version": 1,
        "database": {"path": database_path},
        "world": {
            "locator": "https://source.invalid/requirements",
            "timeout_seconds": 4,
        },
        "model": {
            "endpoint": "https://model.invalid/generate",
            "provider_binding_ref": "configured-provider",
            "model_ref": "configured-model-v1",
            "timeout_seconds": 8,
        },
    }


def test_host_config_resolves_relative_database_path_without_creating_it(tmp_path):
    config_path = tmp_path / "host.json"
    config_path.write_text(json.dumps(_payload()), encoding="utf-8")

    config = load_host_config(config_path)

    assert config.database_path == (tmp_path / "alsoul.db").resolve()
    assert not config.database_path.exists()
    assert config.runtime.world.expected_origin == "https://source.invalid"
    assert config.runtime.model.provider_binding_ref == "configured-provider"


def test_host_config_rejects_secret_material_in_public_configuration(tmp_path):
    payload = _payload()
    payload["model"]["authorization_token"] = "must-not-live-here"
    config_path = tmp_path / "host.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HostConfigurationError, match="unsupported field"):
        load_host_config(config_path)


def test_runtime_secret_is_loaded_only_from_environment_and_hidden_from_repr():
    secret = "ephemeral-host-token"
    loaded = load_runtime_secrets({"ALSOUL_MODEL_AUTHORIZATION_TOKEN": secret})

    assert loaded.model_authorization_token == secret
    assert secret not in repr(loaded)


def test_readiness_fails_closed_for_missing_database_without_creating_it(tmp_path):
    config_path = tmp_path / "host.json"
    config_path.write_text(json.dumps(_payload()), encoding="utf-8")
    config = load_host_config(config_path)

    readiness = assess_host_readiness(config)

    assert not readiness.ready
    assert readiness.problems == ("DATABASE_MISSING",)
    assert not config.database_path.exists()


def test_readiness_accepts_structurally_compatible_f4_schema(tmp_path):
    db_path = tmp_path / "alsoul.db"
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    engine.dispose()

    config_path = tmp_path / "host.json"
    config_path.write_text(json.dumps(_payload()), encoding="utf-8")
    readiness = assess_host_readiness(load_host_config(config_path))

    assert readiness.ready
    assert readiness.database_accessible
    assert readiness.schema_compatible
    assert readiness.missing_tables == ()
    assert readiness.missing_columns == ()
