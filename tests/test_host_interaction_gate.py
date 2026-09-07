from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.host import HOST_CONFIG_VERSION
from alsoul.services import FoundationBootstrapper
from alsoul.storage import create_schema, create_sqlite_engine, schema


def _prepare_identity(db_path: Path, now):
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    bootstrapper = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    external_subject = str(uuid4())
    ids = bootstrapper.bootstrap(
        identity_namespace="host-interaction-gate",
        external_subject=external_subject,
    )
    engine.dispose()
    return ids, external_subject


def _write_config(path: Path, db_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "host_config_version": HOST_CONFIG_VERSION,
                "database": {"path": str(db_path)},
                "world": {
                    "locator": "https://world.invalid/requirements",
                    "timeout_seconds": 1,
                },
                "model": {
                    "endpoint": "https://model.invalid/generate",
                    "provider_binding_ref": "host-interaction-gate-provider",
                    "model_ref": "host-interaction-gate-model-v1",
                    "timeout_seconds": 1,
                },
                "presentation": {
                    "endpoint": "https://presentation.invalid/present",
                    "timeout_seconds": 1,
                },
            }
        ),
        encoding="utf-8",
    )


def _envelope(now, *, external_subject: str, transport_event_id: str, content_text: str):
    return json.dumps(
        {
            "identity_namespace": "host-interaction-gate",
            "external_subject": external_subject,
            "surface_namespace": "alsoul.first_party",
            "surface_ref": "primary-text-surface",
            "channel_namespace": "alsoul.first_party",
            "channel_ref": "primary-text-channel",
            "transport_event_id": transport_event_id,
            "content_text": content_text,
            "occurred_at": now.isoformat(),
            "conversation_id": "host-interaction-gate",
        }
    )


def _run(config_path: Path, input_text: str):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alsoul.host",
            "--config",
            str(config_path),
            "interact",
        ],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=10,
    )


def test_host_interact_admits_memory_without_provider_work_and_replays_safely(tmp_path, now):
    db_path = tmp_path / "alsoul.db"
    ids, external_subject = _prepare_identity(db_path, now)
    config_path = tmp_path / "host.json"
    _write_config(config_path, db_path)
    envelope = _envelope(
        now,
        external_subject=external_subject,
        transport_event_id="memory-only-1",
        content_text="My machine has 16 GB RAM.",
    )

    first = _run(config_path, envelope)
    assert first.returncode == 0, first.stderr
    first_result = json.loads(first.stdout)["result"]
    assert first_result["interaction_purpose"] == "MEMORY_STATEMENT"
    assert first_result["response"] is None
    assert first_result["memory"]["disposition"] == "ADMITTED"
    claim_id = first_result["memory"]["claim_id"]
    assert claim_id is not None

    replay = _run(config_path, envelope)
    assert replay.returncode == 0, replay.stderr
    replay_result = json.loads(replay.stdout)["result"]
    assert replay_result["ingress"]["idempotent_replay"] is True
    assert replay_result["interaction_purpose"] == "MEMORY_STATEMENT"
    assert replay_result["response"] is None
    assert replay_result["memory"]["claim_id"] == claim_id

    engine = create_sqlite_engine(db_path)
    with engine.connect() as conn:
        counts = {
            "claims": conn.execute(select(func.count()).select_from(schema.claim)).scalar_one(),
            "evidence": conn.execute(
                select(func.count()).select_from(schema.evidence_item)
            ).scalar_one(),
            "investigations": conn.execute(
                select(func.count()).select_from(schema.investigation)
            ).scalar_one(),
            "model_invocations": conn.execute(
                select(func.count()).select_from(schema.model_invocation)
            ).scalar_one(),
            "companion_outputs": conn.execute(
                select(func.count()).select_from(schema.companion_output)
            ).scalar_one(),
            "presented": conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(
                    schema.interaction_event.c.event_kind
                    == "COMPANION_PRESENTED_OUTPUT"
                )
            ).scalar_one(),
        }
        relationship = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()
    engine.dispose()

    assert relationship["counterpart_id"] == ids.counterpart_id
    assert counts == {
        "claims": 1,
        "evidence": 1,
        "investigations": 0,
        "model_invocations": 0,
        "companion_outputs": 0,
        "presented": 0,
    }


def test_host_interact_unsupported_input_fails_before_provider_work(tmp_path, now):
    db_path = tmp_path / "alsoul.db"
    _ids, external_subject = _prepare_identity(db_path, now)
    config_path = tmp_path / "host.json"
    _write_config(config_path, db_path)

    result = _run(
        config_path,
        _envelope(
            now,
            external_subject=external_subject,
            transport_event_id="unsupported-1",
            content_text="Tell me a joke.",
        ),
    )

    assert result.returncode == 4
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "INTERACTION_PURPOSE_UNSUPPORTED"

    engine = create_sqlite_engine(db_path)
    with engine.connect() as conn:
        input_count = conn.execute(
            select(func.count())
            .select_from(schema.interaction_event)
            .where(schema.interaction_event.c.event_kind == "COUNTERPART_INPUT")
        ).scalar_one()
        investigation_count = conn.execute(
            select(func.count()).select_from(schema.investigation)
        ).scalar_one()
        invocation_count = conn.execute(
            select(func.count()).select_from(schema.model_invocation)
        ).scalar_one()
    engine.dispose()

    assert input_count == 1
    assert investigation_count == 0
    assert invocation_count == 0
