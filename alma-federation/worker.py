"""Private Alma Federation worker with a deny-by-default execution policy.

Safety properties:

* no shell command strings and no ``shell=True``;
* three bounded, structured task kinds only;
* dry-run unless ``ALMA_EXECUTE=1`` is set explicitly;
* a strong enrollment token is mandatory;
* cleartext HTTP is accepted only for a loopback coordinator.
"""

from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from task_policy import PolicyError, planned_argv, validate_task

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MAX_RESPONSE_BYTES = 1_048_576
MAX_RESULT_CHARS = 65_536
WORKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True)
class Settings:
    coordinator: str
    token: str = field(repr=False)
    worker: str
    poll_seconds: float
    timeout_seconds: int
    dry_run: bool


def validate_token(token: str) -> str:
    token = (token or "").strip()
    if token.lower() == "alma" or len(token) < 24:
        raise ValueError("ALMA_TOKEN must be an explicit enrollment token of at least 24 characters")
    return token


def validate_coordinator_url(value: str) -> str:
    raw = (value or "").strip()
    try:
        parsed = urllib.parse.urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid ALMA_COORD: {exc}") from exc

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ALMA_COORD must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ALMA_COORD cannot contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("ALMA_COORD cannot contain a path")

    host = parsed.hostname.lower()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme == "http" and not is_loopback:
        raise ValueError("remote ALMA_COORD must use HTTPS; cleartext HTTP is loopback-only")
    return raw.rstrip("/")


def load_settings() -> Settings:
    token = validate_token(os.environ.get("ALMA_TOKEN", ""))
    coordinator = validate_coordinator_url(os.environ.get("ALMA_COORD", "http://127.0.0.1:8900"))
    worker = os.environ.get("ALMA_WORKER", socket.gethostname()).strip()
    if not WORKER_RE.fullmatch(worker):
        raise ValueError("ALMA_WORKER may contain only letters, digits, dot, underscore, and hyphen")
    poll = min(max(float(os.environ.get("ALMA_POLL", "3")), 0.5), 60.0)
    timeout = min(max(int(os.environ.get("ALMA_JOB_TIMEOUT", "60")), 1), 600)
    dry_run = os.environ.get("ALMA_EXECUTE", "0") != "1"
    return Settings(coordinator, token, worker, poll, timeout, dry_run)


def call(settings: Settings, path: str, obj: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(obj).encode("utf-8") if obj is not None else None
    req = urllib.request.Request(
        settings.coordinator + path,
        data=data,
        method="POST" if data is not None else "GET",
    )
    req.add_header("X-Alma-Token", settings.token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("coordinator response exceeded 1 MiB")
    decoded = json.loads(raw or b"{}")
    if not isinstance(decoded, dict):
        raise ValueError("coordinator response must be a JSON object")
    return decoded


def run_task(task: Any, *, dry_run: bool, timeout_seconds: int = 60) -> tuple[str, int]:
    normalized = validate_task(task)
    argv = planned_argv(normalized)
    if dry_run:
        return json.dumps(
            {"dry_run": True, "accepted": normalized, "argv": argv},
            ensure_ascii=False,
        ), 0

    kind = normalized["kind"]
    if kind == "system.info":
        result = {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count(),
        }
        return json.dumps(result, ensure_ascii=False), 0
    if kind == "diagnostic.echo":
        return normalized["message"], 0
    if kind == "python.version" and argv is not None:
        completed = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        return output[:MAX_RESULT_CHARS], completed.returncode
    raise PolicyError("task has no implementation")


def main() -> int:
    try:
        settings = load_settings()
    except (TypeError, ValueError) as exc:
        print(f"[worker] configuration refused: {exc}")
        return 2

    mode = "DRY-RUN (no tasks execute)" if settings.dry_run else "EXECUTION ENABLED"
    print(f"[worker] {mode}; coordinator={settings.coordinator}; worker={settings.worker}")
    meta = {
        "host": settings.worker,
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "dry_run": settings.dry_run,
        "policy": "structured-v1",
    }
    while True:
        try:
            call(settings, "/register", {"worker": settings.worker, "meta": meta})
            break
        except Exception as exc:
            print(f"[worker] registration failed: {exc}; retry in {settings.poll_seconds}s")
            time.sleep(settings.poll_seconds)

    worker_query = urllib.parse.urlencode({"worker": settings.worker})
    while True:
        try:
            job = call(settings, f"/pull?{worker_query}")
            job_id = job.get("job_id")
            if not job_id:
                time.sleep(settings.poll_seconds)
                continue
            try:
                output, return_code = run_task(
                    job.get("task"),
                    dry_run=settings.dry_run,
                    timeout_seconds=settings.timeout_seconds,
                )
            except (PolicyError, TypeError, ValueError) as exc:
                output, return_code = f"policy rejected task: {exc}", 126
            call(
                settings,
                "/result",
                {"job_id": str(job_id)[:128], "output": output[:MAX_RESULT_CHARS], "rc": return_code},
            )
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            print(f"[worker] coordinator error: {exc}; retry in {settings.poll_seconds}s")
            time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
