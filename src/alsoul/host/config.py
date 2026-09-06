from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from alsoul.services import (
    FoundationRuntimeConfig,
    ModelRuntimeConfig,
    PresentationRuntimeConfig,
    RuntimeSecrets,
    WorldRuntimeConfig,
)

HOST_CONFIG_VERSION = 2
MODEL_AUTHORIZATION_ENV = "ALSOUL_MODEL_AUTHORIZATION_TOKEN"


class HostConfigurationError(ValueError):
    """Raised when process-facing runtime configuration is invalid."""


@dataclass(frozen=True, slots=True)
class FoundationHostConfig:
    """Process configuration that never owns companion identity or authority."""

    host_config_version: int
    database_path: Path
    runtime: FoundationRuntimeConfig


def load_host_config(path: str | Path) -> FoundationHostConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HostConfigurationError("host configuration file could not be read") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HostConfigurationError("host configuration must be valid JSON") from exc

    root = _require_object(payload, "root")
    _reject_unknown(
        root,
        {"host_config_version", "database", "world", "model", "presentation"},
        "root",
    )

    version = root.get("host_config_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise HostConfigurationError("host_config_version must be an integer")
    if version != HOST_CONFIG_VERSION:
        raise HostConfigurationError(
            f"unsupported host_config_version {version}; expected {HOST_CONFIG_VERSION}"
        )

    database = _require_object(root.get("database"), "database")
    _reject_unknown(database, {"path"}, "database")
    database_path = _resolve_path(
        _require_nonempty_string(database.get("path"), "database.path"),
        base=config_path.parent,
    )

    world = _require_object(root.get("world"), "world")
    _reject_unknown(world, {"locator", "timeout_seconds"}, "world")
    try:
        world_config = WorldRuntimeConfig(
            locator=_require_nonempty_string(world.get("locator"), "world.locator"),
            timeout_seconds=_positive_number(
                world.get("timeout_seconds", 10.0), "world.timeout_seconds"
            ),
        )
    except ValueError as exc:
        raise HostConfigurationError(str(exc)) from exc

    model = _require_object(root.get("model"), "model")
    _reject_unknown(
        model,
        {"endpoint", "provider_binding_ref", "model_ref", "timeout_seconds"},
        "model",
    )
    try:
        model_config = ModelRuntimeConfig(
            endpoint=_require_nonempty_string(model.get("endpoint"), "model.endpoint"),
            provider_binding_ref=_require_nonempty_string(
                model.get("provider_binding_ref"), "model.provider_binding_ref"
            ),
            model_ref=_require_nonempty_string(model.get("model_ref"), "model.model_ref"),
            timeout_seconds=_positive_number(
                model.get("timeout_seconds", 30.0), "model.timeout_seconds"
            ),
        )
    except ValueError as exc:
        raise HostConfigurationError(str(exc)) from exc

    presentation = _require_object(root.get("presentation"), "presentation")
    _reject_unknown(presentation, {"endpoint", "timeout_seconds"}, "presentation")
    try:
        presentation_config = PresentationRuntimeConfig(
            endpoint=_require_nonempty_string(
                presentation.get("endpoint"), "presentation.endpoint"
            ),
            timeout_seconds=_positive_number(
                presentation.get("timeout_seconds", 10.0),
                "presentation.timeout_seconds",
            ),
        )
    except ValueError as exc:
        raise HostConfigurationError(str(exc)) from exc

    return FoundationHostConfig(
        host_config_version=version,
        database_path=database_path,
        runtime=FoundationRuntimeConfig(
            world=world_config,
            model=model_config,
            presentation=presentation_config,
        ),
    )


def load_runtime_secrets(environ: Mapping[str, str] | None = None) -> RuntimeSecrets:
    source = environ if environ is not None else os.environ
    token = source.get(MODEL_AUTHORIZATION_ENV)
    if token is not None and not token.strip():
        token = None
    return RuntimeSecrets(model_authorization_token=token)


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HostConfigurationError(f"{field} must be a JSON object")
    return value


def _reject_unknown(payload: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise HostConfigurationError(f"{field} contains unsupported field(s): {joined}")


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HostConfigurationError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HostConfigurationError(f"{field} must be a positive number")
    number = float(value)
    if number <= 0:
        raise HostConfigurationError(f"{field} must be a positive number")
    return number


def _resolve_path(value: str, *, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


__all__ = [
    "FoundationHostConfig",
    "HOST_CONFIG_VERSION",
    "HostConfigurationError",
    "MODEL_AUTHORIZATION_ENV",
    "load_host_config",
    "load_runtime_secrets",
]
