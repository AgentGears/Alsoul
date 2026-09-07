from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from alsoul.admin.service import AdministrationError, FoundationAdministrator
from alsoul.domain.errors import DomainError


class AdminCommandError(ValueError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AdminCommandError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="alsoul-admin")
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "initialize-store",
        help="Create a new database and migrate it to the packaged schema head",
    )
    initialize.add_argument("--database", required=True)

    migrate = commands.add_parser(
        "migrate-store",
        help="Upgrade an existing database to the packaged schema head",
    )
    migrate.add_argument("--database", required=True)

    status = commands.add_parser(
        "status",
        help="Derive content-free administration status for one database",
    )
    status.add_argument("--database", required=True)

    bootstrap = commands.add_parser(
        "bootstrap-foundation",
        help="Create the one-time F4 Person/Counterpart/Relationship identity graph",
    )
    bootstrap.add_argument("--database", required=True)
    bootstrap.add_argument("--identity-namespace", required=True)
    bootstrap.add_argument("--external-subject", required=True)
    bootstrap.add_argument("--surface-namespace", default="alsoul.first_party")
    bootstrap.add_argument("--surface-ref", default="primary-text-surface")
    bootstrap.add_argument("--channel-namespace", default="alsoul.first_party")
    bootstrap.add_argument("--channel-ref", default="primary-text-channel")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        admin = FoundationAdministrator()
        if args.command == "initialize-store":
            result = admin.initialize_store(args.database)
        elif args.command == "migrate-store":
            result = admin.migrate_store(args.database)
        elif args.command == "status":
            result = admin.status(args.database)
        elif args.command == "bootstrap-foundation":
            result = admin.bootstrap_foundation(
                args.database,
                identity_namespace=args.identity_namespace,
                external_subject=args.external_subject,
                surface_namespace=args.surface_namespace,
                surface_ref=args.surface_ref,
                channel_namespace=args.channel_namespace,
                channel_ref=args.channel_ref,
            )
        else:  # pragma: no cover - argparse constrains this branch.
            raise AdminCommandError(f"unsupported command: {args.command}")
        _emit_success(args.command, result)
        return 0
    except AdminCommandError as exc:
        _emit_error("ADMIN_COMMAND_INVALID", str(exc))
        return 2
    except AdministrationError as exc:
        _emit_error(exc.code, exc.message)
        return 3
    except DomainError as exc:
        _emit_error(exc.code, exc.message)
        return 4
    except OSError:
        _emit_error("ADMIN_IO_ERROR", "administration I/O failed")
        return 5
    except Exception:
        _emit_error("ADMIN_INTERNAL_ERROR", "administration command failed unexpectedly")
        return 70


def _emit_success(operation: str, result: Any) -> None:
    payload = {"ok": True, "operation": operation, "result": _jsonable(result)}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _emit_error(code: str, message: str) -> None:
    print(
        json.dumps(
            {"ok": False, "error": {"code": code, "message": message}},
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
