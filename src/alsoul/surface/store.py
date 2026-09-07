from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from alsoul.adapters import AdapterRejected, JsonHttpResponse


@dataclass(frozen=True, slots=True)
class LocalSurfaceInputReservation:
    occurred_at: datetime
    existing: bool


@dataclass(frozen=True, slots=True)
class LocalSurfacePresentation:
    presentation_key: str
    companion_output_id: UUID
    surface_binding_id: UUID
    channel_binding_id: UUID
    content_text: str
    content_digest: str
    receipt_ref: str
    accepted_at: datetime


class LocalSurfaceStore:
    """Durable operational state for one local first-party surface.

    This store is not canonical companion state. It preserves transport replay
    identity and first-party sink acceptance so local process restart cannot mutate
    the semantic request or duplicate logical presentation acceptance.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.parent.is_dir():
            raise OSError("local surface state parent directory does not exist")
        existed = self.path.exists()
        self._initialize()
        if not existed:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def reserve_input(
        self,
        *,
        transport_event_id: str,
        identity_namespace: str,
        external_subject: str,
        surface_namespace: str,
        surface_ref: str,
        channel_namespace: str,
        channel_ref: str,
        content_text: str,
        conversation_id: str | None,
        occurred_at: datetime,
    ) -> LocalSurfaceInputReservation:
        values = (
            transport_event_id,
            identity_namespace,
            external_subject,
            surface_namespace,
            surface_ref,
            channel_namespace,
            channel_ref,
            content_text,
            conversation_id,
        )
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM inbound_transport_event WHERE transport_event_id = ?",
                (transport_event_id,),
            ).fetchone()
            if existing is not None:
                existing_values = (
                    str(existing["transport_event_id"]),
                    str(existing["identity_namespace"]),
                    str(existing["external_subject"]),
                    str(existing["surface_namespace"]),
                    str(existing["surface_ref"]),
                    str(existing["channel_namespace"]),
                    str(existing["channel_ref"]),
                    str(existing["content_text"]),
                    existing["conversation_id"],
                )
                if existing_values != values:
                    raise ValueError(
                        "transport_event_id was replayed with different local input semantics"
                    )
                return LocalSurfaceInputReservation(
                    occurred_at=datetime.fromisoformat(str(existing["occurred_at"])),
                    existing=True,
                )

            conn.execute(
                """
                INSERT INTO inbound_transport_event (
                    transport_event_id,
                    identity_namespace,
                    external_subject,
                    surface_namespace,
                    surface_ref,
                    channel_namespace,
                    channel_ref,
                    content_text,
                    conversation_id,
                    occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, occurred_at.isoformat()),
            )
            conn.commit()
        return LocalSurfaceInputReservation(occurred_at=occurred_at, existing=False)

    def accept_transport_request(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        del timeout_seconds, headers
        required = {
            "schema_version",
            "presentation_key",
            "companion_output_id",
            "surface_binding_id",
            "channel_binding_id",
            "content_text",
            "content_digest",
        }
        if set(body) != required or body.get("schema_version") != 1:
            raise AdapterRejected("local surface received an invalid presentation request")

        try:
            presentation = self.accept(
                presentation_key=_nonempty(body["presentation_key"], "presentation_key"),
                companion_output_id=UUID(_nonempty(body["companion_output_id"], "companion_output_id")),
                surface_binding_id=UUID(_nonempty(body["surface_binding_id"], "surface_binding_id")),
                channel_binding_id=UUID(_nonempty(body["channel_binding_id"], "channel_binding_id")),
                content_text=_string(body["content_text"], "content_text"),
                content_digest=_nonempty(body["content_digest"], "content_digest"),
            )
        except (TypeError, ValueError) as exc:
            raise AdapterRejected("local surface received an invalid presentation request") from exc

        payload = {
            "schema_version": 1,
            "status": "ACCEPTED",
            "presentation_key": presentation.presentation_key,
            "receipt_ref": presentation.receipt_ref,
            "content_digest": presentation.content_digest,
        }
        return JsonHttpResponse(
            status_code=200,
            resolved_endpoint=endpoint,
            content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            headers={"content-type": "application/json"},
        )

    def accept(
        self,
        *,
        presentation_key: str,
        companion_output_id: UUID,
        surface_binding_id: UUID,
        channel_binding_id: UUID,
        content_text: str,
        content_digest: str,
    ) -> LocalSurfacePresentation:
        receipt_ref = f"local-surface:{presentation_key}"
        accepted_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM presentation_acceptance WHERE presentation_key = ?",
                (presentation_key,),
            ).fetchone()
            if existing is not None:
                current = _row_to_presentation(existing)
                if (
                    current.companion_output_id != companion_output_id
                    or current.surface_binding_id != surface_binding_id
                    or current.channel_binding_id != channel_binding_id
                    or current.content_digest != content_digest
                    or current.content_text != content_text
                ):
                    raise AdapterRejected(
                        "local surface presentation key was replayed with different semantic content"
                    )
                return current

            conn.execute(
                """
                INSERT INTO presentation_acceptance (
                    presentation_key,
                    companion_output_id,
                    surface_binding_id,
                    channel_binding_id,
                    content_text,
                    content_digest,
                    receipt_ref,
                    accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    presentation_key,
                    str(companion_output_id),
                    str(surface_binding_id),
                    str(channel_binding_id),
                    content_text,
                    content_digest,
                    receipt_ref,
                    accepted_at.isoformat(),
                ),
            )
            conn.commit()
        return LocalSurfacePresentation(
            presentation_key=presentation_key,
            companion_output_id=companion_output_id,
            surface_binding_id=surface_binding_id,
            channel_binding_id=channel_binding_id,
            content_text=content_text,
            content_digest=content_digest,
            receipt_ref=receipt_ref,
            accepted_at=accepted_at,
        )

    def get_by_companion_output_id(
        self, companion_output_id: UUID
    ) -> LocalSurfacePresentation | None:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM presentation_acceptance WHERE companion_output_id = ?",
                (str(companion_output_id),),
            ).fetchone()
        return _row_to_presentation(row) if row is not None else None

    def count(self) -> int:
        with sqlite3.connect(self.path) as conn:
            return int(
                conn.execute("SELECT COUNT(*) FROM presentation_acceptance").fetchone()[0]
            )

    def _initialize(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inbound_transport_event (
                    transport_event_id TEXT PRIMARY KEY,
                    identity_namespace TEXT NOT NULL,
                    external_subject TEXT NOT NULL,
                    surface_namespace TEXT NOT NULL,
                    surface_ref TEXT NOT NULL,
                    channel_namespace TEXT NOT NULL,
                    channel_ref TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    conversation_id TEXT,
                    occurred_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS presentation_acceptance (
                    presentation_key TEXT PRIMARY KEY,
                    companion_output_id TEXT NOT NULL UNIQUE,
                    surface_binding_id TEXT NOT NULL,
                    channel_binding_id TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    content_digest TEXT NOT NULL,
                    receipt_ref TEXT NOT NULL,
                    accepted_at TEXT NOT NULL
                )
                """
            )
            conn.commit()


class LocalSurfacePresentationTransport:
    """In-process transport that preserves the existing JSON presentation contract."""

    def __init__(self, store: LocalSurfaceStore) -> None:
        self.store = store

    def post_json(
        self,
        endpoint: str,
        *,
        body: dict[str, Any],
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> JsonHttpResponse:
        return self.store.accept_transport_request(
            endpoint,
            body=body,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )


def _row_to_presentation(row: sqlite3.Row) -> LocalSurfacePresentation:
    return LocalSurfacePresentation(
        presentation_key=str(row["presentation_key"]),
        companion_output_id=UUID(str(row["companion_output_id"])),
        surface_binding_id=UUID(str(row["surface_binding_id"])),
        channel_binding_id=UUID(str(row["channel_binding_id"])),
        content_text=str(row["content_text"]),
        content_digest=str(row["content_digest"]),
        receipt_ref=str(row["receipt_ref"]),
        accepted_at=datetime.fromisoformat(str(row["accepted_at"])),
    )


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


__all__ = [
    "LocalSurfaceInputReservation",
    "LocalSurfacePresentation",
    "LocalSurfacePresentationTransport",
    "LocalSurfaceStore",
]
