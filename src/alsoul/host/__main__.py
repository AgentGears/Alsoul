from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from alsoul.adapters import AdapterError, AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError
from alsoul.host.application import FoundationHostApplication
from alsoul.host.config import HostConfigurationError, load_host_config, load_runtime_secrets
from alsoul.host.ingress_io import IngressEnvelopeError, parse_ingress_envelope
from alsoul.host.readiness import HostReadinessError, assess_host_readiness


class HostCommandError(ValueError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HostCommandError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="alsoul-host")
    parser.add_argument("--config", required=True, help="Path to host JSON configuration")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("ready", help="Validate database/schema readiness without provider I/O")

    ingest = commands.add_parser(
        "ingest",
        help="Admit one trusted first-party input envelope from standard input",
    )
    ingest.set_defaults(reads_ingress=True)

    interact = commands.add_parser(
        "interact",
        help="Admit one trusted first-party input envelope and run the bounded F4 interaction",
    )
    interact.add_argument("--after-process-loss", action="store_true")
    interact.set_defaults(reads_ingress=True)

    diagnose = commands.add_parser("diagnose", help="Derive content-free recovery state")
    _add_response_identity_arguments(diagnose, include_route=False)

    commands.add_parser(
        "probe-model-contract",
        help="Verify configured model wire contract using synthetic non-canonical context",
    )

    respond = commands.add_parser("respond", help="Resume one already-admitted F4 response")
    _add_response_identity_arguments(respond, include_route=True)
    respond.add_argument("--after-process-loss", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        config = load_host_config(Path(args.config))

        if args.command == "ready":
            readiness = assess_host_readiness(config)
            if not readiness.ready:
                _emit_error(
                    "HOST_NOT_READY",
                    "runtime host readiness checks failed",
                    details=_jsonable(readiness),
                )
                return 3
            _emit_success("ready", readiness)
            return 0

        envelope = None
        if getattr(args, "reads_ingress", False):
            envelope = parse_ingress_envelope(sys.stdin.read())

        secrets = load_runtime_secrets()
        with FoundationHostApplication(config=config, secrets=secrets) as app:
            if args.command == "ingest":
                assert envelope is not None
                result = app.ingress.admit(envelope)
            elif args.command == "interact":
                assert envelope is not None
                admitted = app.ingress.admit(envelope)
                interaction = app.runtime.interact(
                    relationship_id=admitted.relationship_id,
                    current_input_event_id=admitted.event_id,
                    surface_binding_id=admitted.surface_binding_id,
                    channel_binding_id=admitted.channel_binding_id,
                    after_process_loss=args.after_process_loss,
                )
                result = {
                    "ingress": _jsonable(admitted),
                    "interaction_purpose": interaction.interaction_purpose,
                    "memory": _jsonable(interaction.memory_admission),
                    "response": _jsonable(interaction.response),
                }
            elif args.command == "diagnose":
                result = app.runtime.diagnose(
                    relationship_id=args.relationship_id,
                    current_input_event_id=args.current_input_event_id,
                )
            elif args.command == "probe-model-contract":
                result = app.runtime.probe_model_contract()
            elif args.command == "respond":
                result = app.runtime.respond(
                    relationship_id=args.relationship_id,
                    current_input_event_id=args.current_input_event_id,
                    surface_binding_id=args.surface_binding_id,
                    channel_binding_id=args.channel_binding_id,
                    after_process_loss=args.after_process_loss,
                )
            else:  # pragma: no cover - argparse constrains this branch.
                raise HostCommandError(f"unsupported command: {args.command}")

        _emit_success(args.command, result)
        return 0
    except HostCommandError as exc:
        _emit_error("HOST_COMMAND_INVALID", str(exc))
        return 2
    except HostConfigurationError as exc:
        _emit_error("HOST_CONFIG_INVALID", str(exc))
        return 2
    except IngressEnvelopeError as exc:
        _emit_error("INGRESS_ENVELOPE_INVALID", str(exc))
        return 2
    except HostReadinessError as exc:
        _emit_error(
            "HOST_NOT_READY",
            "runtime host readiness checks failed",
            details=_jsonable(exc.readiness),
        )
        return 3
    except DomainError as exc:
        _emit_error(exc.code, exc.message)
        return 4
    except AdapterRejected as exc:
        _emit_error("ADAPTER_REJECTED", str(exc))
        return 5
    except AdapterOutcomeUnknown as exc:
        _emit_error("ADAPTER_OUTCOME_UNKNOWN", str(exc))
        return 6
    except AdapterError:
        _emit_error("ADAPTER_ERROR", "provider adapter failed")
        return 6
    except OSError:
        _emit_error("HOST_IO_ERROR", "runtime host I/O failed")
        return 7
    except Exception:
        _emit_error("HOST_INTERNAL_ERROR", "runtime host failed unexpectedly")
        return 70


def _add_response_identity_arguments(
    parser: argparse.ArgumentParser, *, include_route: bool
) -> None:
    parser.add_argument("--relationship-id", type=_uuid, required=True)
    parser.add_argument("--current-input-event-id", type=_uuid, required=True)
    if include_route:
        parser.add_argument("--surface-binding-id", type=_uuid, required=True)
        parser.add_argument("--channel-binding-id", type=_uuid, required=True)


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected UUID") from exc


def _emit_success(operation: str, result: Any) -> None:
    payload = {"ok": True, "operation": operation, "result": _jsonable(result)}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _emit_error(code: str, message: str, *, details: Any | None = None) -> None:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    print(
        json.dumps({"ok": False, "error": error}, sort_keys=True, separators=(",", ":")),
        file=sys.stderr,
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
