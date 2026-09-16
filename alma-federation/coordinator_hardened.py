"""Loopback coordinator for the deny-by-default Alma Federation worker."""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from task_policy import PolicyError, validate_task

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOKEN = os.environ.get("ALMA_TOKEN", "").strip()
PORT = int(os.environ.get("ALMA_PORT", "8900"))
BIND = os.environ.get("ALMA_BIND", "127.0.0.1").strip()
STALE = min(max(float(os.environ.get("ALMA_STALE", "120")), 30.0), 86_400.0)
STATE = os.path.abspath(
    os.environ.get("ALMA_STATE", "").strip()
    or os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma_state.json")
)
MAX_BODY = 65_536
MAX_OUTPUT_CHARS = 65_536
WORKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_lock = threading.RLock()
_jobs: dict[str, dict[str, Any]] = {}
_pending: list[str] = []
_nodes: dict[str, dict[str, Any]] = {}
_next = [1]


def require_token(value: str) -> str:
    if value.lower() == "alma" or len(value) < 24:
        raise ValueError("ALMA_TOKEN must be an explicit enrollment token of at least 24 characters")
    return value


def require_loopback_bind(value: str) -> str:
    host = value.lower()
    if host == "localhost":
        return value
    try:
        if ipaddress.ip_address(host).is_loopback:
            return value
    except ValueError:
        pass
    raise ValueError("raw coordinator HTTP must bind to loopback; expose it only through an authenticated TLS proxy")


def _load() -> None:
    try:
        with open(STATE, encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError("state root is not an object")
        _jobs.update(data.get("jobs", {}))
        _nodes.update(data.get("nodes", {}))
        _next[0] = max(int(data.get("next", 1)), 1)
        for job_id in data.get("pending", []):
            job = _jobs.get(job_id, {})
            try:
                job["task"] = validate_task(job.get("task"))
                _pending.append(job_id)
            except PolicyError as exc:
                job.update(status="rejected-policy", output=f"legacy/invalid task: {exc}", rc=126)
        print(f"[coordinator] restored {len(_jobs)} jobs; {len(_pending)} remain policy-valid")
    except FileNotFoundError:
        return
    except Exception as exc:
        print(f"[coordinator] state load skipped: {exc}")


def _save() -> None:
    payload = {"jobs": _jobs, "pending": _pending, "nodes": _nodes, "next": _next[0]}
    temporary = STATE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
    os.replace(temporary, STATE)


def _jid() -> str:
    result = f"job{_next[0]:05d}"
    _next[0] += 1
    return result


def _prune_loop() -> None:
    while True:
        time.sleep(30)
        now = time.time()
        with _lock:
            for node in _nodes.values():
                if now - float(node.get("last_seen", 0)) > STALE:
                    node["online"] = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        return

    def _authorized(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Alma-Token", ""), TOKEN)

    def _send(self, obj: dict[str, Any], code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > MAX_BODY:
            raise ValueError("request body exceeds 64 KiB")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:
        if not self._authorized():
            self._send({"error": "auth"}, 401)
            return
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/pull":
            worker = (query.get("worker") or [""])[0]
            if not WORKER_RE.fullmatch(worker):
                self._send({"error": "invalid worker"}, 400)
                return
            with _lock:
                if worker in _nodes:
                    _nodes[worker].update(last_seen=time.time(), online=True)
                while _pending:
                    job_id = _pending.pop(0)
                    job = _jobs.get(job_id, {})
                    try:
                        task = validate_task(job.get("task"))
                    except PolicyError as exc:
                        job.update(status="rejected-policy", output=str(exc), rc=126)
                        continue
                    job.update(status="running", worker=worker)
                    _save()
                    self._send({"job_id": job_id, "task": task})
                    return
                _save()
            self._send({})
            return
        if parsed.path.startswith("/result/"):
            with _lock:
                job = _jobs.get(parsed.path.rsplit("/", 1)[1])
            self._send(job or {"error": "no such job"}, 200 if job else 404)
            return
        if parsed.path == "/nodes":
            with _lock:
                self._send({"nodes": _nodes})
            return
        if parsed.path == "/status":
            with _lock:
                online = [name for name, node in _nodes.items() if node.get("online")]
                self._send({"pending": len(_pending), "jobs": len(_jobs), "nodes": len(_nodes), "online": online})
            return
        self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send({"error": "auth"}, 401)
            return
        try:
            body = self._body()
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send({"error": f"bad request: {exc}"}, 400)
            return

        if self.path == "/register":
            worker = body.get("worker", "")
            if not isinstance(worker, str) or not WORKER_RE.fullmatch(worker):
                self._send({"error": "invalid worker"}, 400)
                return
            with _lock:
                previous = _nodes.get(worker, {})
                _nodes[worker] = {
                    "meta": body.get("meta", {}),
                    "last_seen": time.time(),
                    "online": True,
                    "jobs_done": previous.get("jobs_done", 0),
                }
                _save()
            self._send({"ok": True, "worker": worker})
            return

        if self.path == "/submit":
            if "cmd" in body:
                self._send({"error": "legacy command strings are forbidden; submit a structured task"}, 400)
                return
            try:
                task = validate_task(body.get("task"))
            except PolicyError as exc:
                self._send({"error": f"policy: {exc}"}, 400)
                return
            with _lock:
                job_id = _jid()
                _jobs[job_id] = {
                    "task": task,
                    "status": "pending",
                    "worker": None,
                    "output": None,
                    "rc": None,
                    "ts": time.time(),
                }
                _pending.append(job_id)
                _save()
            self._send({"job_id": job_id})
            return

        if self.path == "/result":
            job_id = str(body.get("job_id", ""))[:128]
            output = str(body.get("output", ""))[:MAX_OUTPUT_CHARS]
            try:
                return_code = int(body.get("rc", 1))
            except (TypeError, ValueError):
                self._send({"error": "invalid return code"}, 400)
                return
            with _lock:
                if job_id not in _jobs:
                    self._send({"error": "no such job"}, 404)
                    return
                _jobs[job_id].update(status="done", output=output, rc=return_code)
                worker = _jobs[job_id].get("worker")
                if worker in _nodes:
                    _nodes[worker]["jobs_done"] = int(_nodes[worker].get("jobs_done", 0)) + 1
                _save()
            self._send({"ok": True})
            return

        self._send({"error": "not found"}, 404)


def main() -> int:
    try:
        require_token(TOKEN)
        require_loopback_bind(BIND)
    except ValueError as exc:
        print(f"[coordinator] configuration refused: {exc}")
        return 2
    _load()
    threading.Thread(target=_prune_loop, daemon=True).start()
    print(f"[coordinator] structured-v1 on http://{BIND}:{PORT}; raw HTTP is loopback-only")
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
