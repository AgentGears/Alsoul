from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from alsoul.domain.commands import AdmitPersonMemoryClaimCommand, AppendCounterpartInputCommand
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.services.foundation import RAM_PREDICATE
from alsoul.storage import create_schema, create_sqlite_engine, schema


class _ProviderState:
    authorization: str | None = None
    model_requests: int = 0
    world_requests: int = 0


class _ProviderHandler(BaseHTTPRequestHandler):
    state: _ProviderState

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/world":
            self.send_error(404)
            return
        self.state.world_requests += 1
        payload = b'{"minimum_memory_gb":24}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("ETag", '"host-process-1"')
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/model":
            self.send_error(404)
            return
        self.state.model_requests += 1
        self.state.authorization = self.headers.get("Authorization")
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        context = request["provider_context"]
        claim = context["personal_context"][0]
        world = context["world_context"][0]
        response = {
            "segments": [
                {
                    "epistemic_kind": "REMEMBERED_COUNTERPART_STATEMENT",
                    "text": f"You told me your machine has {claim['value']} GB RAM.",
                    "source_ref": claim["claim_id"],
                },
                {
                    "epistemic_kind": "CURRENT_CHECKED_WORLD",
                    "text": f"I checked the current requirement; it is {world['value']} GB.",
                    "source_ref": world["world_result_id"],
                },
                {
                    "epistemic_kind": "COMPANION_INTERPRETATION",
                    "text": "My take is that this machine does not meet that requirement.",
                    "source_ref": None,
                },
            ]
        }
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args) -> None:  # noqa: A002, ANN001
        return


def _generate_localhost_certificate(tmp_path: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is required for the process-level HTTPS acceptance test")
    cert = tmp_path / "localhost.crt"
    key = tmp_path / "localhost.key"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


@contextmanager
def _provider_server(tmp_path: Path) -> Iterator[tuple[str, Path, _ProviderState]]:
    cert, key = _generate_localhost_certificate(tmp_path)
    state = _ProviderState()
    handler = type("ProviderHandler", (_ProviderHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certfile=cert, keyfile=key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://localhost:{server.server_port}", cert, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _prepare_database(db_path: Path, now):
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    services = FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())
    bootstrapper = FoundationBootstrapper(engine, clock=FixedClock(now), ids=UUIDGenerator())
    external_subject = str(uuid4())
    ids = bootstrapper.bootstrap(
        identity_namespace="host-process",
        external_subject=external_subject,
    )
    memory = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="host-memory",
            content_text="My machine has 16 GB RAM.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    services.admit_person_memory_claim(
        AdmitPersonMemoryClaimCommand(
            operation_id=uuid4(),
            holder_companion_person_id=ids.companion_person_id,
            subject_counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            predicate=RAM_PREDICATE,
            value=16,
            source_event_id=memory.event_id,
        )
    )
    engine.dispose()
    return ids, external_subject


def _ingress_envelope(now, *, external_subject: str) -> str:
    return json.dumps(
        {
            "identity_namespace": "host-process",
            "external_subject": external_subject,
            "surface_namespace": "alsoul.first_party",
            "surface_ref": "primary-text-surface",
            "channel_namespace": "alsoul.first_party",
            "channel_ref": "primary-text-channel",
            "transport_event_id": "transport-event-1",
            "content_text": "Would the current software run on my machine?",
            "occurred_at": now.isoformat(),
            "conversation_id": "thread-b",
        }
    )


def _write_config(path: Path, *, db_path: Path, base_url: str) -> None:
    payload = {
        "host_config_version": 1,
        "database": {"path": str(db_path)},
        "world": {
            "locator": f"{base_url}/world",
            "timeout_seconds": 5,
        },
        "model": {
            "endpoint": f"{base_url}/model",
            "provider_binding_ref": "process-provider",
            "model_ref": "process-model-v1",
            "timeout_seconds": 5,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_host(
    config_path: Path,
    *args: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
):
    command = [
        sys.executable,
        "-m",
        "alsoul.host",
        "--config",
        str(config_path),
        *args,
    ]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        input=input_text,
        timeout=30,
    )


def test_host_process_ingests_then_resumes_full_interaction_across_processes(tmp_path, now):
    db_path = tmp_path / "alsoul.db"
    ids, external_subject = _prepare_database(db_path, now)
    envelope = _ingress_envelope(now, external_subject=external_subject)

    with _provider_server(tmp_path) as (base_url, cert, state):
        config_path = tmp_path / "host.json"
        _write_config(config_path, db_path=db_path, base_url=base_url)

        ready = _run_host(config_path, "ready")
        assert ready.returncode == 0, ready.stderr
        ready_payload = json.loads(ready.stdout)
        assert ready_payload["ok"] is True
        assert ready_payload["result"]["schema_compatible"] is True
        assert state.world_requests == 0
        assert state.model_requests == 0

        ingest = _run_host(config_path, "ingest", input_text=envelope)
        assert ingest.returncode == 0, ingest.stderr
        ingress_result = json.loads(ingest.stdout)["result"]
        current_event_id = ingress_result["event_id"]
        assert ingress_result["relationship_id"] == str(ids.relationship_id)
        assert ingress_result["idempotent_replay"] is False
        assert "Would the current software" not in ingest.stdout

        replay = _run_host(config_path, "ingest", input_text=envelope)
        assert replay.returncode == 0, replay.stderr
        replay_result = json.loads(replay.stdout)["result"]
        assert replay_result["event_id"] == current_event_id
        assert replay_result["idempotent_replay"] is True

        diagnose = _run_host(
            config_path,
            "diagnose",
            "--relationship-id",
            str(ids.relationship_id),
            "--current-input-event-id",
            current_event_id,
        )
        assert diagnose.returncode == 0, diagnose.stderr
        diagnostic = json.loads(diagnose.stdout)["result"]
        assert diagnostic["recovery_stage"] == "INPUT_ADMITTED"
        assert diagnostic["next_action"] == "START_INVESTIGATION"
        assert "Would the current software" not in diagnose.stdout
        assert "My machine has" not in diagnose.stdout

        secret = "process-only-secret"
        env = os.environ.copy()
        env["ALSOUL_MODEL_AUTHORIZATION_TOKEN"] = secret
        env["SSL_CERT_FILE"] = str(cert)
        probe = _run_host(config_path, "probe-model-contract", env=env)
        assert probe.returncode == 0, probe.stderr
        probe_payload = json.loads(probe.stdout)["result"]
        assert probe_payload["provider_binding_ref"] == "process-provider"
        assert probe_payload["epistemic_kinds"] == [
            "REMEMBERED_COUNTERPART_STATEMENT",
            "CURRENT_CHECKED_WORLD",
            "COMPANION_INTERPRETATION",
        ]
        assert state.authorization == f"Bearer {secret}"
        assert secret not in probe.stdout
        assert secret not in probe.stderr

        interact = _run_host(
            config_path,
            "interact",
            env=env,
            input_text=envelope,
        )
        assert interact.returncode == 0, interact.stderr
        interaction_payload = json.loads(interact.stdout)["result"]
        assert interaction_payload["ingress"]["event_id"] == current_event_id
        assert interaction_payload["ingress"]["idempotent_replay"] is True
        response_payload = interaction_payload["response"]
        assert response_payload["presented_event_id"]
        assert secret not in interact.stdout
        assert secret not in interact.stderr
        assert "Would the current software" not in interact.stdout
        assert state.world_requests == 1
        assert state.model_requests == 2

        second_interact = _run_host(
            config_path,
            "interact",
            env=env,
            input_text=envelope,
        )
        assert second_interact.returncode == 0, second_interact.stderr
        second_payload = json.loads(second_interact.stdout)["result"]
        assert (
            second_payload["response"]["presented_event_id"]
            == response_payload["presented_event_id"]
        )
        assert state.world_requests == 1
        assert state.model_requests == 2

    engine = create_sqlite_engine(db_path)
    with engine.connect() as conn:
        presented = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id
                == UUID(response_payload["presented_event_id"])
            )
        ).mappings().one()
        current = conn.execute(
            select(schema.interaction_event).where(
                schema.interaction_event.c.event_id == UUID(current_event_id)
            )
        ).mappings().one()
        counts = {
            "current_inputs": conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(schema.interaction_event.c.event_kind == "COUNTERPART_INPUT")
            ).scalar_one(),
            "world_results": conn.execute(
                select(func.count()).select_from(schema.world_result)
            ).scalar_one(),
            "generated": conn.execute(
                select(func.count()).select_from(schema.generated_output)
            ).scalar_one(),
            "presented": conn.execute(
                select(func.count())
                .select_from(schema.interaction_event)
                .where(schema.interaction_event.c.event_kind == "COMPANION_PRESENTED_OUTPUT")
            ).scalar_one(),
        }
    engine.dispose()

    assert current["relationship_id"] == ids.relationship_id
    assert current["surface_binding_id"] == ids.surface_binding_id
    assert current["channel_binding_id"] == ids.channel_binding_id
    assert counts == {
        "current_inputs": 2,
        "world_results": 1,
        "generated": 1,
        "presented": 1,
    }
    assert "You told me" in presented["content_text"]
    assert "I checked" in presented["content_text"]
    assert "My take" in presented["content_text"]
