from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from alsoul.domain.errors import DomainError
from alsoul.host.config import HostConfigurationError, load_host_config, load_runtime_secrets
from alsoul.host.readiness import HostReadinessError
from alsoul.surface.application import LocalFirstPartySurfaceApplication, LocalSurfaceIdentity
from alsoul.surface.server import LocalSurfaceServer


class SurfaceCommandError(ValueError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SurfaceCommandError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="alsoul-surface")
    parser.add_argument("--config", required=True, help="Path to existing host JSON configuration")
    parser.add_argument("--state", required=True, help="Path to local surface operational state")
    parser.add_argument("--identity-namespace", required=True)
    parser.add_argument("--external-subject", required=True)
    parser.add_argument("--surface-namespace", default="alsoul.first_party")
    parser.add_argument("--surface-ref", default="primary-text-surface")
    parser.add_argument("--channel-namespace", default="alsoul.first_party")
    parser.add_argument("--channel-ref", default="primary-text-channel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    app: LocalFirstPartySurfaceApplication | None = None
    surface: LocalSurfaceServer | None = None
    try:
        args = build_parser().parse_args(argv)
        config = load_host_config(Path(args.config))
        identity = LocalSurfaceIdentity(
            identity_namespace=args.identity_namespace,
            external_subject=args.external_subject,
            surface_namespace=args.surface_namespace,
            surface_ref=args.surface_ref,
            channel_namespace=args.channel_namespace,
            channel_ref=args.channel_ref,
        )
        app = LocalFirstPartySurfaceApplication(
            config=config,
            identity=identity,
            surface_state_path=Path(args.state),
            secrets=load_runtime_secrets(),
        )
        surface = LocalSurfaceServer(
            application=app,
            host=args.host,
            port=args.port,
        )
        _emit_startup(surface.url)
        try:
            surface.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0
    except SurfaceCommandError as exc:
        _emit_error("SURFACE_COMMAND_INVALID", str(exc))
        return 2
    except HostConfigurationError as exc:
        _emit_error("HOST_CONFIG_INVALID", str(exc))
        return 2
    except HostReadinessError as exc:
        _emit_error("HOST_NOT_READY", "runtime host readiness checks failed")
        return 3
    except DomainError as exc:
        _emit_error(exc.code, exc.message)
        return 4
    except ValueError as exc:
        _emit_error("SURFACE_CONFIG_INVALID", str(exc))
        return 2
    except OSError:
        _emit_error("SURFACE_IO_ERROR", "local surface I/O failed")
        return 7
    except Exception:
        _emit_error("SURFACE_INTERNAL_ERROR", "local surface failed unexpectedly")
        return 70
    finally:
        if surface is not None:
            surface.close()
        if app is not None:
            app.close()


def _emit_startup(url: str) -> None:
    print(
        json.dumps(
            {"ok": True, "operation": "serve", "url": url},
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _emit_error(code: str, message: str) -> None:
    print(
        json.dumps(
            {"ok": False, "error": {"code": code, "message": message}},
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
