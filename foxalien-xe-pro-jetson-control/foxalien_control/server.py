from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from .config import load_config
from .examples import public_examples
from .machine import MachineError, MachineService


MAX_BODY = 2 * 1024 * 1024
STATIC_ROOT = Path(__file__).resolve().parent / "static"


class ConsoleHandler(BaseHTTPRequestHandler):
    service: MachineService

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[http] " + (format % args) + "\n")

    def _json_body(self) -> Dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise MachineError("POST requests require application/json")
        origin = self.headers.get("Origin")
        host = self.headers.get("Host")
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            raise MachineError("Cross-origin control requests are blocked")
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            raise MachineError("Request body exceeds 2 MiB")
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MachineError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise MachineError("JSON body must be an object")
        return data

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, relative: str) -> None:
        filename = "index.html" if relative in {"", "/"} else relative.lstrip("/")
        target = (STATIC_ROOT / filename).resolve()
        if STATIC_ROOT not in target.parents and target != STATIC_ROOT:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(HTTPStatus.OK, {"ok": True, **self.service.snapshot()})
        elif path == "/api/config":
            self._send_json(HTTPStatus.OK, {"ok": True, "config": self.service.config.public_dict()})
        elif path == "/api/examples":
            self._send_json(HTTPStatus.OK, {"ok": True, "examples": public_examples()})
        elif path == "/health":
            snapshot = self.service.snapshot()
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "mode": "simulation" if self.service.config.simulation else "hardware",
                    "connected": snapshot["connected"],
                    "machine_state": snapshot["machine"]["state"],
                },
            )
        elif path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Unknown endpoint"})
        else:
            self._send_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._json_body()
            payload = self._dispatch(path, body)
            self._send_json(HTTPStatus.OK, {"ok": True, **payload})
        except MachineError as exc:
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
        except (TypeError, ValueError, KeyError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"Internal error: {type(exc).__name__}"},
            )

    def _dispatch(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if path == "/api/connect":
            self.service.connect()
        elif path == "/api/disconnect":
            self.service.disconnect()
        elif path == "/api/realtime":
            self.service.realtime(str(body["action"]))
        elif path == "/api/jog":
            self.service.jog(
                str(body["axis"]),
                float(body["distance_mm"]),
                float(body["feed_mm_min"]) if "feed_mm_min" in body else None,
            )
        elif path == "/api/home":
            if body.get("confirm") is not True:
                raise MachineError("Homing requires explicit confirmation")
            self.service.home()
        elif path == "/api/unlock":
            self.service.unlock()
        elif path == "/api/work-zero":
            if body.get("confirm") is not True:
                raise MachineError("Setting work zero requires explicit confirmation")
            self.service.set_work_zero()
        elif path == "/api/job/validate":
            result = self.service.validate(str(body.get("source", "")))
            return {"validation": result.as_dict()}
        elif path == "/api/job/start":
            result = self.service.start_job(
                str(body.get("name", "untitled.nc")),
                str(body.get("source", "")),
                dict(body.get("approvals", {})),
            )
            return {"validation": result.as_dict()}
        elif path == "/api/job/pause":
            self.service.pause_job()
        elif path == "/api/job/resume":
            self.service.resume_job()
        elif path == "/api/job/abort":
            self.service.abort_job()
        else:
            raise KeyError("Unknown endpoint")
        return self.service.snapshot()


def make_server(
    config_path: Path,
    host_override: Optional[str] = None,
    port_override: Optional[int] = None,
) -> Tuple[ThreadingHTTPServer, MachineService]:
    config = load_config(config_path)
    if host_override is not None or port_override is not None:
        config = replace(
            config,
            bind_host=host_override if host_override is not None else config.bind_host,
            bind_port=port_override if port_override is not None else config.bind_port,
        )
    service = MachineService(config)
    handler = type("ConfiguredConsoleHandler", (ConsoleHandler,), {"service": service})
    server = ThreadingHTTPServer((config.bind_host, config.bind_port), handler)
    return server, service


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxAlien XE-PRO Jetson control console")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/machine.json"),
        help="Path to machine JSON configuration",
    )
    parser.add_argument("--host", help="Override the configured bind host")
    parser.add_argument("--port", type=int, help="Override the configured bind port")
    args = parser.parse_args()
    try:
        server, service = make_server(args.config, args.host, args.port)
    except (OSError, ValueError) as exc:
        print(f"STARTUP BLOCKED: {exc}", file=sys.stderr)
        return 2

    host, port = server.server_address[:2]
    print(f"FoxAlien console listening at http://{host}:{port}")
    print("SIMULATION" if service.config.simulation else "HARDWARE MODE")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if service.transport.connected:
            service.transport.disconnect()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
