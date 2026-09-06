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
    ids = bootstrapper.bootstrap(
        identity_namespace="host-process",
        external_subject=str(uuid4()),
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
    current = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="host-current",
            content_text="Would the current software run on my machine?",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    engine.dispose()
    return ids, current


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


def _run_host(config_path: Path, *args: str, env: dict[str, str] | None = None):
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
        timeout=30,
    )


def test_host_process_exposes_readiness_diagnostics_probe_and_full_response(tmp_path, now):
    db_path = tmp_path / "alsoul.db"
    ids, current = _prepare_database(db_path, now)

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

        diagnose = _run_host(
            config_path,
            "diagnose",
            "--relationship-id",
            str(ids.relationship_id),
            "--current-input-event-id",
            str(current.event_id),
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

        respond = _run_host(
            config_path,
            "respond",
            "--relationship-id",
            str(ids.relationship_id),
            "--current-input-event-id",
            str(current.event_id),
            "--surface-binding-id",
            str(ids.surface_binding_id),
            "--channel-binding-id",
            str(ids.channel_binding_id),
            env=env,
        )
        assert respond.returncode == 0, respond.stderr
        response_payload = json.loads(respond.stdout)["result"]
        assert response_payload["presented_event_id"]
        assert secret not in respond.stdout
        assert secret not in respond.stderr
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
        counts = {
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

    assert counts == {"world_results": 1, "generated": 1, "presented": 1}
    assert "You told me" in presented["content_text"]
    assert "I checked" in presented["content_text"]
    assert "My take" in presented["content_text"]
