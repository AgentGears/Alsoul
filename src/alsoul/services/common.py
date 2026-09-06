from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Callable, TypeVar
from uuid import UUID

from sqlalchemy import Connection, insert, select
from sqlalchemy.exc import IntegrityError

from alsoul.domain.errors import DomainError, fail
from alsoul.storage import schema

T = TypeVar("T")


def _json_default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot canonicalize {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_digest(value: Any) -> str:
    return sha256_text(canonical_json(value))


def load_operation_receipt(
    connection: Connection,
    *,
    scope: str,
    operation_id: UUID,
    expected_request_digest: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        select(schema.operation_receipt).where(
            schema.operation_receipt.c.operation_scope == scope,
            schema.operation_receipt.c.operation_id == operation_id,
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    if row["request_digest"] != expected_request_digest:
        fail(
            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST",
            f"operation {scope}/{operation_id} was already committed with a different request",
        )
    return dict(row["result_json"])


def save_operation_receipt(
    connection: Connection,
    *,
    scope: str,
    operation_id: UUID,
    req_digest: str,
    result_kind: str,
    result_ref: UUID,
    result_json: dict[str, Any],
    committed_at: datetime,
) -> None:
    connection.execute(
        insert(schema.operation_receipt).values(
            operation_scope=scope,
            operation_id=operation_id,
            request_digest=req_digest,
            result_kind=result_kind,
            result_ref=result_ref,
            result_json=result_json,
            committed_at=committed_at,
        )
    )


def require_row(connection: Connection, table, condition, code: str, message: str) -> dict[str, Any]:
    row = connection.execute(select(table).where(condition)).mappings().one_or_none()
    if row is None:
        fail(code, message)
    return dict(row)


def translate_integrity_error(exc: IntegrityError, code: str, message: str) -> DomainError:
    return DomainError(code, f"{message}: {exc.orig}")
