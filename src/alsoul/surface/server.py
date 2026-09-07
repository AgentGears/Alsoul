from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from alsoul.adapters import AdapterError, AdapterOutcomeUnknown, AdapterRejected
from alsoul.domain.errors import DomainError
from alsoul.surface.application import LocalFirstPartySurfaceApplication

_MAX_REQUEST_BYTES = 65_536


class LocalSurfaceServer:
    """Loopback-only first-party web surface for one local Alsoul relationship."""

    def __init__(
        self,
        *,
        application: LocalFirstPartySurfaceApplication,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("local surface binds only to 127.0.0.1")
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.application = application
        self.session_token = secrets.token_urlsafe(32)
        handler = _handler_factory(self)
        self.httpd = HTTPServer((host, port), handler)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.httpd.server_address[:2]
        return str(host), int(port)

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}/"

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.25)

    def close(self) -> None:
        self.httpd.server_close()


def _handler_factory(server: LocalSurfaceServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AlsoulLocalSurface/0.0.1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send_html(_page(server.session_token))
                return
            if self.path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "surface": "local-first-party",
                        "ready": server.application.readiness.ready,
                    },
                )
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/interact":
                self._send_json(
                    HTTPStatus.NOT_FOUND, {"ok": False, "error": "NOT_FOUND"}
                )
                return
            if not secrets.compare_digest(
                self.headers.get("X-Alsoul-Surface-Token", ""), server.session_token
            ):
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"ok": False, "error": "SURFACE_SESSION_INVALID"},
                )
                return
            try:
                payload = self._read_json_body()
                content_text = payload.get("content_text")
                if not isinstance(content_text, str) or not content_text.strip():
                    raise ValueError("content_text must be a non-empty string")
                transport_event_id = payload.get("transport_event_id")
                if transport_event_id is not None and not isinstance(
                    transport_event_id, str
                ):
                    raise ValueError("transport_event_id must be a string")
                result = server.application.interact(
                    content_text,
                    transport_event_id=transport_event_id,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "result": {
                            "content_text": result.content_text,
                            "transport_event_id": result.transport_event_id,
                            "idempotent_input_replay": result.idempotent_input_replay,
                        },
                    },
                )
            except ValueError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "SURFACE_REQUEST_INVALID", "message": str(exc)},
                )
            except DomainError as exc:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {"ok": False, "error": exc.code, "message": exc.message},
                )
            except AdapterRejected as exc:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": "ADAPTER_REJECTED", "message": str(exc)},
                )
            except AdapterOutcomeUnknown as exc:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "ok": False,
                        "error": "ADAPTER_OUTCOME_UNKNOWN",
                        "message": str(exc),
                    },
                )
            except AdapterError:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": "ADAPTER_ERROR"},
                )
            except OSError:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": "SURFACE_IO_ERROR"},
                )
            except Exception:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": "SURFACE_INTERNAL_ERROR"},
                )

        def _read_json_body(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                raise ValueError("Content-Type must be application/json")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError as exc:
                raise ValueError("Content-Length is required") from exc
            if length <= 0 or length > _MAX_REQUEST_BYTES:
                raise ValueError("request body size is invalid")
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            if set(payload) - {"content_text", "transport_event_id"}:
                raise ValueError("request contains unsupported fields")
            return payload

        def _send_html(self, content: str) -> None:
            data = content.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._security_headers(content_type="text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            data = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self._security_headers(content_type="application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _security_headers(self, *, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            )

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return Handler


def _page(token: str) -> str:
    token_json = json.dumps(token)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Alsoul</title>
<style>
:root {{ font-family: ui-sans-serif, system-ui, sans-serif; color-scheme: light dark; }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: Canvas; color: CanvasText; }}
main {{ width: min(760px, calc(100vw - 32px)); height: min(820px, calc(100vh - 32px)); display: grid; grid-template-rows: auto 1fr auto; gap: 16px; }}
h1 {{ font-size: 1.15rem; margin: 0; }}
#messages {{ overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px; }}
.message {{ max-width: 86%; padding: 10px 12px; border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 14px; white-space: pre-wrap; line-height: 1.45; }}
.user {{ align-self: end; }}
.alsoul {{ align-self: start; }}
form {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; }}
textarea {{ min-height: 48px; max-height: 160px; resize: vertical; padding: 10px; font: inherit; }}
button {{ padding: 0 18px; font: inherit; }}
#status {{ font-size: .85rem; opacity: .72; }}
</style>
</head>
<body>
<main>
<header><h1>Alsoul</h1><div id=\"status\">Local first-party surface</div></header>
<section id=\"messages\" aria-live=\"polite\"></section>
<form id=\"composer\">
<textarea id=\"input\" aria-label=\"Message\" placeholder=\"Message Alsoul\" required></textarea>
<button type=\"submit\">Send</button>
</form>
</main>
<script>
const token = {token_json};
const form = document.getElementById('composer');
const input = document.getElementById('input');
const messages = document.getElementById('messages');
const status = document.getElementById('status');
function add(kind, text) {{
  const el = document.createElement('div');
  el.className = 'message ' + kind;
  el.textContent = text;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}}
form.addEventListener('submit', async (event) => {{
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const transportEventId = crypto.randomUUID();
  add('user', text);
  input.value = '';
  input.disabled = true;
  status.textContent = 'Working…';
  try {{
    const response = await fetch('/api/interact', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', 'X-Alsoul-Surface-Token': token}},
      body: JSON.stringify({{content_text: text, transport_event_id: transportEventId}})
    }});
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || payload.error || 'Interaction failed');
    add('alsoul', payload.result.content_text);
    status.textContent = 'Local first-party surface';
  }} catch (error) {{
    status.textContent = String(error.message || error);
  }} finally {{
    input.disabled = false;
    input.focus();
  }}
}});
</script>
</body>
</html>"""


__all__ = ["LocalSurfaceServer"]
