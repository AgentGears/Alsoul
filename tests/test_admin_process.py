from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from alsoul.admin import FoundationAdministrator


def _run_module(module: str, *args: str, input_text: str | None = None):
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=30,
    )


def _write_host_config(path: Path, *, database: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "host_config_version": 2,
                "database": {"path": str(database)},
                "world": {
                    "locator": "https://world.invalid/requirements",
                    "timeout_seconds": 5,
                },
                "model": {
                    "endpoint": "https://model.invalid/generate",
                    "provider_binding_ref": "admin-process-provider",
                    "model_ref": "admin-process-model-v1",
                    "timeout_seconds": 5,
                },
                "presentation": {
                    "endpoint": "https://presentation.invalid/accept",
                    "timeout_seconds": 5,
                },
            }
        ),
        encoding="utf-8",
    )


def test_admin_process_creates_store_then_explicitly_bootstraps_identity(tmp_path):
    database = tmp_path / "alsoul.db"

    initialized = _run_module(
        "alsoul.admin",
        "initialize-store",
        "--database",
        str(database),
    )
    assert initialized.returncode == 0, initialized.stderr
    init_payload = json.loads(initialized.stdout)
    assert init_payload["ok"] is True
    assert init_payload["result"]["schema_revision"] == "0001_f4_foundation"

    empty_status = _run_module(
        "alsoul.admin",
        "status",
        "--database",
        str(database),
    )
    assert empty_status.returncode == 0, empty_status.stderr
    assert json.loads(empty_status.stdout)["result"]["foundation_state"] == "EMPTY"

    bootstrap = _run_module(
        "alsoul.admin",
        "bootstrap-foundation",
        "--database",
        str(database),
        "--identity-namespace",
        "admin-process",
        "--external-subject",
        "counterpart-1",
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    bootstrap_payload = json.loads(bootstrap.stdout)
    assert bootstrap_payload["ok"] is True
    assert bootstrap_payload["result"]["companion_person_id"]
    assert bootstrap_payload["result"]["counterpart_id"]
    assert bootstrap_payload["result"]["relationship_id"]

    final_status = _run_module(
        "alsoul.admin",
        "status",
        "--database",
        str(database),
    )
    assert final_status.returncode == 0, final_status.stderr
    result = json.loads(final_status.stdout)["result"]
    assert result["foundation_state"] == "BOOTSTRAPPED"
    assert result["companion_person_count"] == 1
    assert result["counterpart_person_count"] == 1
    assert result["relationship_count"] == 1


def test_runtime_host_never_bootstraps_missing_identity(tmp_path, now):
    database = tmp_path / "alsoul.db"
    admin = FoundationAdministrator()
    admin.initialize_store(database)
    config = tmp_path / "host.json"
    _write_host_config(config, database=database)

    ready = _run_module(
        "alsoul.host",
        "--config",
        str(config),
        "ready",
    )
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["result"]["schema_compatible"] is True
    assert admin.status(database).foundation_state == "EMPTY"

    envelope = json.dumps(
        {
            "identity_namespace": "admin-process",
            "external_subject": "unknown-counterpart",
            "surface_namespace": "alsoul.first_party",
            "surface_ref": "primary-text-surface",
            "channel_namespace": "alsoul.first_party",
            "channel_ref": "primary-text-channel",
            "transport_event_id": "event-1",
            "content_text": "Hello",
            "occurred_at": now.isoformat(),
        }
    )
    ingest = _run_module(
        "alsoul.host",
        "--config",
        str(config),
        "ingest",
        input_text=envelope,
    )
    assert ingest.returncode == 4
    error = json.loads(ingest.stderr)["error"]
    assert error["code"] == "INGRESS_CHANNEL_BINDING_NOT_FOUND"

    after = admin.status(database)
    assert after.foundation_state == "EMPTY"
    assert after.companion_person_count == 0
    assert after.counterpart_person_count == 0
    assert after.relationship_count == 0
