#!/usr/bin/env python3
"""
glm_router.py -- stdlib-only OpenAI-compatible load balancer for the GLM-5.2 fleet.

Each Colibri replica is started with --max-queue 1 and --kv-slots 1, i.e. it serves
exactly ONE request at a time (plus one queued).  The entire value of this router is
therefore admission control + fan-out: concurrent clients land on DIFFERENT nodes
instead of serialising behind one.

Endpoints
    POST /v1/chat/completions   proxied (streaming and non-streaming)
    POST /v1/completions        proxied (bonus, same path)
    GET  /v1/models             served from the first healthy backend (cached 60s)
    GET  /health                router + per-backend live status

Scheduling
    Least-connections.  Ties broken round-robin by last-pick sequence.  If every
    healthy backend is busy the request WAITS in the router (not in the backend's
    1-deep queue) until a slot frees or ROUTER_ADMIT_TIMEOUT elapses.

Health gating
    A background thread probes every backend's /health every ROUTER_HEALTH_INTERVAL
    seconds, WITH the bearer key.  This matters: colibri b085b48 returns a bare
    {"status":"ok"} to unauthenticated probes and only reveals hwinfo/tiers when
    authenticated.  An unauthenticated poller would see no "gpus" field at all.

    A backend is healthy only when ALL of:
        HTTP 200, status == "ok", hwinfo.gpus >= 1, tiers.vram_gb > 0
    The vram_gb > 0 test is deliberate.  Both staging nodes came up once reporting
    "gpus": 1 while the CUDA expert tier was empty (0 experts / 0.00 GB) because the
    weights rsync had left the page cache full and cudaMemGetInfo saw no free pages.
    Such a node answers, slowly, entirely on CPU.  gpus>=1 alone does NOT prove GPU
    acceleration; vram_gb does.

Security
    Bearer key required on EVERY inbound request, including /health, and forwarded
    verbatim to the backends.  Binds 127.0.0.1 by default and refuses to bind a
    wildcard address.  No CORS headers are ever emitted.

Environment
    COLI_API_KEY            shared fleet bearer key (or ROUTER_KEY_FILE)
    ROUTER_KEY_FILE         path to a file containing the key
    ROUTER_HOST             default 127.0.0.1   (0.0.0.0 / :: are refused)
    ROUTER_PORT             default 8801
    GLM_BACKENDS            "name=host:port,name=host:port,..."
    ROUTER_DEPRIORITIZE     comma-separated backend names to pick last when
                            equally loaded, default "eran4" (it also serves
                            gpt-oss on :8000). Set to "" to disable.  Measured
                            2026-08-06 this is also the SLOWEST node by ~2x
                            (~2.0 s/tok vs ~1.0 s/tok), because its expert tier
                            is only ~12 GB and the rest streams from disk, so
                            picking it last is doubly correct.
    ROUTER_HEALTH_INTERVAL  seconds between health polls, default 30
    ROUTER_HEALTH_TIMEOUT   seconds per health probe, default 10
    ROUTER_REQUEST_TIMEOUT  seconds per inference call, default 1800.  Measured
                            2026-08-06 after the big-core OMP pinning fix:
                            ~1.0 s/tok on eran1/2/3, ~2.0 s/tok on eran4 (was
                            ~1.7 and ~2.6 respectively).  1800 s therefore covers
                            roughly a 1800-token reply on a fast node and ~900 on
                            eran4; raise it for longer generations.
    ROUTER_ADMIT_TIMEOUT    seconds to wait for a free backend, default 900
    ROUTER_REQUIRE_VRAM     "1" (default) to require tiers.vram_gb > 0
    ROUTER_LOG              log file path, default ./logs/glm_router.log

Python 3.13, standard library only.
"""

from __future__ import annotations

import argparse
import hmac
import http.client
import json
import logging
import os
import socket
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_BACKENDS = (
    "eran1=<tailnet-ip>:8800,"
    "eran2=<tailnet-ip>:8800,"
    "eran3=<tailnet-ip>:8800,"
    "eran4=<tailnet-ip>:8800"
)

WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", "*", ""}
RETRYABLE_STATUS = {429, 502, 503, 504}
PROXY_PATHS = {"/v1/chat/completions", "/v1/completions"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] {name}={raw!r} is not an integer, using {default}", file=sys.stderr)
        return default


HEALTH_INTERVAL = _env_int("ROUTER_HEALTH_INTERVAL", 30)
HEALTH_TIMEOUT = _env_int("ROUTER_HEALTH_TIMEOUT", 10)
REQUEST_TIMEOUT = _env_int("ROUTER_REQUEST_TIMEOUT", 1800)
ADMIT_TIMEOUT = _env_int("ROUTER_ADMIT_TIMEOUT", 900)
REQUIRE_VRAM = os.environ.get("ROUTER_REQUIRE_VRAM", "1") not in ("0", "false", "no")
MAX_ATTEMPTS = _env_int("ROUTER_MAX_ATTEMPTS", 3)
MODELS_CACHE_TTL = 60.0

log = logging.getLogger("glm-router")


def setup_logging() -> str:
    path = os.environ.get("ROUTER_LOG") or os.path.join(HERE, "logs", "glm_router.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    log.setLevel(logging.INFO)
    log.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return path


def load_key() -> str:
    key = os.environ.get("COLI_API_KEY", "").strip()
    if not key:
        key_file = os.environ.get("ROUTER_KEY_FILE", "").strip()
        if key_file:
            try:
                with open(key_file, "r", encoding="utf-8") as fh:
                    key = fh.read().strip()
            except OSError as exc:
                sys.exit(f"FATAL: cannot read ROUTER_KEY_FILE {key_file}: {exc}")
    if not key:
        sys.exit(
            "FATAL: no bearer key. Set COLI_API_KEY or ROUTER_KEY_FILE.\n"
            "       The router refuses to run unauthenticated."
        )
    return key


# --------------------------------------------------------------------------- #
# backend model
# --------------------------------------------------------------------------- #


class Backend:
    __slots__ = (
        "name", "host", "port", "inflight", "seq", "healthy", "reason",
        "gpus", "vram_gb", "ram_gb", "active", "queued", "last_check",
        "dispatched", "completed", "failed", "tokens", "busy_seconds",
        "priority",
    )

    def __init__(self, name: str, host: str, port: int,
                 priority: int = 0) -> None:
        self.name = name
        self.host = host
        self.port = port
        # Tiebreak only: a higher number is picked last when several backends
        # are equally loaded. eran4 also serves gpt-oss on :8000 and runs with
        # ~1 GB of memory free, so GLM work landing there degrades the one
        # model that is actually fast. It is still used when it is the least
        # loaded option — deprioritised, never excluded.
        self.priority = priority
        self.inflight = 0
        self.seq = 0
        self.healthy = False          # nothing is trusted until the first probe
        self.reason = "not probed yet"
        self.gpus = None
        self.vram_gb = None
        self.ram_gb = None
        self.active = None
        self.queued = None
        self.last_check = 0.0
        self.dispatched = 0
        self.completed = 0
        self.failed = 0
        self.tokens = 0
        self.busy_seconds = 0.0

    @property
    def addr(self) -> str:
        return f"{self.host}:{self.port}"

    def snapshot(self) -> dict:
        age = None if not self.last_check else round(time.time() - self.last_check, 1)
        return {
            "name": self.name,
            "url": f"http://{self.addr}",
            "healthy": self.healthy,
            "reason": self.reason,
            "inflight": self.inflight,
            "priority": self.priority,
            "gpus": self.gpus,
            "vram_gb": self.vram_gb,
            "ram_gb": self.ram_gb,
            "backend_active": self.active,
            "backend_queued": self.queued,
            "last_check_age_s": age,
            "dispatched": self.dispatched,
            "completed": self.completed,
            "failed": self.failed,
            "completion_tokens": self.tokens,
            "avg_elapsed_s": (
                round(self.busy_seconds / self.completed, 2) if self.completed else None
            ),
        }


def parse_backends(spec: str) -> list[Backend]:
    # Names listed in ROUTER_DEPRIORITIZE are used last among equally loaded
    # backends. Defaults to eran4, which also hosts gpt-oss on :8000.
    deprioritised = {
        n.strip() for n in
        os.environ.get("ROUTER_DEPRIORITIZE", "eran4").split(",") if n.strip()
    }
    out: list[Backend] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, _, addr = item.partition("=")
        if not addr:
            addr, name = name, name.replace(":", "_")
        host, _, port = addr.rpartition(":")
        if not host:
            sys.exit(f"FATAL: bad backend spec {item!r}, expected name=host:port")
        nm = name.strip()
        out.append(Backend(nm, host.strip(), int(port),
                           priority=1 if nm in deprioritised else 0))
    if not out:
        sys.exit("FATAL: GLM_BACKENDS is empty")
    return out


# --------------------------------------------------------------------------- #
# router core
# --------------------------------------------------------------------------- #


class Router:
    def __init__(self, backends: list[Backend], key: str) -> None:
        self.backends = backends
        self.key = key
        self.cond = threading.Condition()
        self._seq = 0
        self._models_cache: tuple[float, bytes] | None = None
        self._models_lock = threading.Lock()
        self.stop = threading.Event()

    # -- least connections ------------------------------------------------- #

    def acquire(self, deadline: float, exclude: set[str]) -> tuple[Backend | None, str]:
        """Reserve a slot on the least-loaded healthy backend.

        Returns (backend, mode).  mode is "free" when the backend was idle,
        "queued" when we gave up waiting and handed it to a busy backend, or
        (None, reason) when nothing is available.
        """
        waited_for_health = False
        with self.cond:
            while True:
                pool = [b for b in self.backends if b.healthy and b.name not in exclude]
                if pool:
                    best = min(pool, key=lambda b: (b.inflight, b.priority, b.seq))
                    if best.inflight == 0:
                        self._seq += 1
                        best.seq = self._seq
                        best.inflight += 1
                        best.dispatched += 1
                        return best, "free"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if pool:
                        best = min(pool, key=lambda b: (b.inflight, b.priority, b.seq))
                        self._seq += 1
                        best.seq = self._seq
                        best.inflight += 1
                        best.dispatched += 1
                        return best, "queued"
                    return None, (
                        "no healthy backend recovered within admit timeout"
                        if waited_for_health else "all backends unhealthy"
                    )
                if not pool:
                    waited_for_health = True
                self.cond.wait(min(remaining, 1.0))

    def release(self, backend: Backend) -> None:
        with self.cond:
            backend.inflight = max(0, backend.inflight - 1)
            self.cond.notify_all()

    def mark_down(self, backend: Backend, reason: str) -> None:
        with self.cond:
            was = backend.healthy
            backend.healthy = False
            backend.reason = reason
            self.cond.notify_all()
        if was:
            log.warning("HEALTH  %-6s DOWN  (%s) -- %s", backend.name, backend.addr, reason)

    # -- health polling ----------------------------------------------------- #

    def probe(self, backend: Backend) -> None:
        ok, reason, info = False, "", {}
        conn = None
        try:
            conn = http.client.HTTPConnection(backend.host, backend.port, timeout=HEALTH_TIMEOUT)
            conn.request("GET", "/health", headers={"Authorization": f"Bearer {self.key}"})
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                reason = f"HTTP {resp.status}"
            else:
                try:
                    info = json.loads(raw.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    info = {}
                    reason = "unparseable /health body"
                if not reason:
                    hw = info.get("hwinfo") or {}
                    tiers = info.get("tiers") or {}
                    gpus = hw.get("gpus")
                    vram = tiers.get("vram_gb")
                    if info.get("status") != "ok":
                        reason = f"status={info.get('status')!r}"
                    elif "gpus" not in hw:
                        # unauthenticated colibri b085b48 answers a bare {"status":"ok"}
                        reason = "no hwinfo.gpus in /health (bad key or old build?)"
                    elif not gpus or gpus < 1:
                        reason = f"gpus={gpus} -- backend built without CUDA"
                    elif REQUIRE_VRAM and not (isinstance(vram, (int, float)) and vram > 0):
                        reason = f"vram_gb={vram} -- CUDA expert tier empty, CPU-only"
                    else:
                        ok, reason = True, "ok"
        except Exception as exc:  # noqa: BLE001 -- any transport failure means "down"
            reason = f"{type(exc).__name__}: {exc}"
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

        hw = info.get("hwinfo") or {}
        tiers = info.get("tiers") or {}
        sched = info.get("scheduler") or {}
        with self.cond:
            was = backend.healthy
            prev_reason = backend.reason
            backend.healthy = ok
            backend.reason = reason
            backend.last_check = time.time()
            backend.gpus = hw.get("gpus")
            backend.vram_gb = tiers.get("vram_gb")
            backend.ram_gb = tiers.get("ram_gb")
            backend.active = sched.get("active")
            backend.queued = sched.get("queued")
            self.cond.notify_all()
        if ok and not was:
            log.warning(
                "HEALTH  %-6s UP    (%s) gpus=%s vram_gb=%s ram_gb=%s%s",
                backend.name, backend.addr, backend.gpus, backend.vram_gb, backend.ram_gb,
                "" if prev_reason == "not probed yet" else "  [re-added]",
            )
        elif was and not ok:
            log.warning("HEALTH  %-6s DOWN  (%s) -- %s", backend.name, backend.addr, reason)
        else:
            log.debug("HEALTH  %-6s %s -- %s", backend.name, "ok" if ok else "down", reason)

    def health_loop(self) -> None:
        log.info(
            "HEALTH  poller started: every %ss, timeout %ss, require gpus>=1%s",
            HEALTH_INTERVAL, HEALTH_TIMEOUT,
            " and tiers.vram_gb>0" if REQUIRE_VRAM else "",
        )
        while not self.stop.is_set():
            threads = [
                threading.Thread(target=self.probe, args=(b,), daemon=True,
                                 name=f"probe-{b.name}")
                for b in self.backends
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(HEALTH_TIMEOUT + 5)
            self.stop.wait(HEALTH_INTERVAL)

    # -- models ------------------------------------------------------------- #

    def models(self) -> bytes | None:
        with self._models_lock:
            if self._models_cache and time.monotonic() - self._models_cache[0] < MODELS_CACHE_TTL:
                return self._models_cache[1]
        for backend in [b for b in self.backends if b.healthy] or self.backends:
            conn = None
            try:
                conn = http.client.HTTPConnection(backend.host, backend.port, timeout=HEALTH_TIMEOUT)
                conn.request("GET", "/v1/models",
                             headers={"Authorization": f"Bearer {self.key}"})
                resp = conn.getresponse()
                raw = resp.read()
                if resp.status == 200:
                    with self._models_lock:
                        self._models_cache = (time.monotonic(), raw)
                    return raw
            except Exception as exc:  # noqa: BLE001
                log.debug("models probe %s failed: %s", backend.name, exc)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
        return None

    def snapshot(self) -> dict:
        with self.cond:
            backends = [b.snapshot() for b in self.backends]
            healthy = sum(1 for b in self.backends if b.healthy)
            inflight = sum(b.inflight for b in self.backends)
        return {
            "status": "ok" if healthy else "unavailable",
            "degraded": healthy < len(backends),
            "healthy_backends": healthy,
            "total_backends": len(backends),
            "inflight": inflight,
            "capacity": healthy,          # 1 concurrent request per replica
            "health_interval_s": HEALTH_INTERVAL,
            "request_timeout_s": REQUEST_TIMEOUT,
            "admit_timeout_s": ADMIT_TIMEOUT,
            "backends": backends,
        }


ROUTER: Router = None  # type: ignore[assignment]
API_KEY: str = ""


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    server_version = "glm-router/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = REQUEST_TIMEOUT + 120

    # -- plumbing ----------------------------------------------------------- #

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.debug("http %s - %s", self.address_string(), fmt % args)

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send_raw(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _error(self, code: int, message: str, etype: str = "router_error") -> None:
        self._send_json(code, {"error": {"message": message, "type": etype, "code": code}})

    def _authorised(self) -> bool:
        header = self.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), API_KEY):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("WWW-Authenticate", 'Bearer realm="glm-router"')
            body = json.dumps({"error": {"message": "invalid or missing bearer key",
                                         "type": "unauthorized", "code": 401}}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            log.info("AUTH    401 from %s %s %s", self.client_address[0], self.command, self.path)
            return False
        return True

    # -- routes -------------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if not self._authorised():
            return
        if path == "/health":
            snap = ROUTER.snapshot()
            self._send_json(200 if snap["healthy_backends"] else 503, snap)
        elif path == "/v1/models":
            raw = ROUTER.models()
            if raw is None:
                self._error(503, "no backend could serve /v1/models", "no_healthy_backend")
            else:
                self._send_raw(200, "application/json", raw)
        else:
            self._error(404, f"unknown path {path}", "not_found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if not self._authorised():
            return
        if path not in PROXY_PATHS:
            self._error(404, f"unknown path {path}", "not_found")
            return
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            self._error(411, "chunked request bodies are not supported; send Content-Length")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(400, "bad Content-Length")
            return
        body = self.rfile.read(length) if length > 0 else b""
        self._proxy(path, body)

    # -- proxy --------------------------------------------------------------- #

    def _proxy(self, path: str, body: bytes) -> None:
        req_id = uuid.uuid4().hex[:8]
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        stream = bool(payload.get("stream"))
        model = payload.get("model", "?")
        n_msg = len(payload.get("messages") or []) if isinstance(payload.get("messages"), list) else 0
        max_tok = payload.get("max_tokens") or payload.get("max_completion_tokens")

        log.info(
            "RECV    [%s] %s model=%s messages=%s stream=%s max_tokens=%s bytes=%d from=%s",
            req_id, path, model, n_msg, stream, max_tok, len(body), self.client_address[0],
        )

        deadline = time.monotonic() + ADMIT_TIMEOUT
        tried: set[str] = set()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            queued_at = time.monotonic()
            backend, mode = ROUTER.acquire(deadline, tried)
            if backend is None:
                log.error("REJECT  [%s] 503 -- %s (tried=%s)", req_id, mode, sorted(tried) or "none")
                self._error(503, f"no healthy GLM backend available: {mode}", "no_healthy_backend")
                return
            wait_s = time.monotonic() - queued_at
            with ROUTER.cond:
                loads = ", ".join(f"{b.name}={b.inflight}" for b in ROUTER.backends)
            log.info(
                "DISPATCH[%s] -> %-6s (%s) attempt=%d mode=%s router_wait=%.2fs loads[%s]",
                req_id, backend.name, backend.addr, attempt, mode, wait_s, loads,
            )

            started = time.monotonic()
            conn = None
            try:
                conn = http.client.HTTPConnection(backend.host, backend.port,
                                                  timeout=REQUEST_TIMEOUT)
                headers = {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Authorization": f"Bearer {API_KEY}",
                    "Accept": "text/event-stream" if stream else "application/json",
                    "X-Router-Request-Id": req_id,
                }
                conn.request("POST", path, body=body, headers=headers)
                resp = conn.getresponse()
            except Exception as exc:  # noqa: BLE001 -- transport failure before any reply
                elapsed = time.monotonic() - started
                with ROUTER.cond:
                    backend.failed += 1
                ROUTER.release(backend)
                ROUTER.mark_down(backend, f"dispatch failed: {type(exc).__name__}: {exc}")
                tried.add(backend.name)
                log.error(
                    "FAIL    [%s] <- %-6s transport error after %.2fs: %s: %s (attempt %d/%d)",
                    req_id, backend.name, elapsed, type(exc).__name__, exc, attempt, MAX_ATTEMPTS,
                )
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                continue

            if resp.status in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                raw = resp.read()
                elapsed = time.monotonic() - started
                with ROUTER.cond:
                    backend.failed += 1
                ROUTER.release(backend)
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                tried.add(backend.name)
                log.warning(
                    "RETRY   [%s] <- %-6s HTTP %d after %.2fs: %s",
                    req_id, backend.name, resp.status, elapsed,
                    raw[:200].decode("utf-8", "replace"),
                )
                continue

            if stream:
                self._relay_stream(req_id, backend, conn, resp, started)
            else:
                self._relay_json(req_id, backend, conn, resp, started)
            return

        log.error("REJECT  [%s] 502 -- all attempts exhausted (tried=%s)", req_id, sorted(tried))
        self._error(502, f"all GLM backends failed: {sorted(tried)}", "backend_failure")

    def _relay_json(self, req_id, backend, conn, resp, started) -> None:
        try:
            raw = resp.read()
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            with ROUTER.cond:
                backend.failed += 1
            ROUTER.release(backend)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            ROUTER.mark_down(backend, f"read failed: {type(exc).__name__}: {exc}")
            log.error("FAIL    [%s] <- %-6s read error after %.2fs: %s",
                      req_id, backend.name, elapsed, exc)
            self._error(502, f"backend {backend.name} dropped the response: {exc}",
                        "backend_failure")
            return

        elapsed = time.monotonic() - started
        ctype = resp.getheader("Content-Type", "application/json")
        status = resp.status
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

        prompt_t = completion_t = total_t = None
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
            usage = data.get("usage") or {}
            prompt_t = usage.get("prompt_tokens")
            completion_t = usage.get("completion_tokens")
            total_t = usage.get("total_tokens")
        except (json.JSONDecodeError, AttributeError):
            pass

        with ROUTER.cond:
            if status == 200:
                backend.completed += 1
                backend.busy_seconds += elapsed
                if isinstance(completion_t, int):
                    backend.tokens += completion_t
            else:
                backend.failed += 1
        ROUTER.release(backend)

        tps = (completion_t / elapsed) if (isinstance(completion_t, int) and elapsed > 0) else None
        log.info(
            "DONE    [%s] <- %-6s (%s) status=%d elapsed=%.2fs prompt=%s completion=%s "
            "total=%s tok/s=%s bytes=%d",
            req_id, backend.name, backend.addr, status, elapsed, prompt_t, completion_t,
            total_t, f"{tps:.2f}" if tps else "n/a", len(raw),
        )
        self._send_raw(status, ctype, raw)

    def _relay_stream(self, req_id, backend, conn, resp, started) -> None:
        status = resp.status
        ctype = resp.getheader("Content-Type", "text/event-stream")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        chunks = 0
        nbytes = 0
        completion_t = None
        first_token_at = None
        client_gone = False
        try:
            while True:
                line = resp.readline()
                if not line:
                    break
                nbytes += len(line)
                if line.startswith(b"data:"):
                    chunks += 1
                    if first_token_at is None:
                        first_token_at = time.monotonic() - started
                    if b'"usage"' in line:
                        try:
                            obj = json.loads(line[5:].strip().decode("utf-8", "replace"))
                            usage = obj.get("usage") or {}
                            if isinstance(usage.get("completion_tokens"), int):
                                completion_t = usage["completion_tokens"]
                        except json.JSONDecodeError:
                            pass
                if not client_gone:
                    try:
                        self.wfile.write(line)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_gone = True
                        log.warning("STREAM  [%s] client disconnected, draining %s",
                                    req_id, backend.name)
        except Exception as exc:  # noqa: BLE001
            log.error("STREAM  [%s] <- %-6s error: %s: %s", req_id, backend.name,
                      type(exc).__name__, exc)
        finally:
            elapsed = time.monotonic() - started
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            if completion_t is None:
                completion_t = max(chunks - 1, 0)   # [DONE] sentinel is not a token
            with ROUTER.cond:
                if status == 200:
                    backend.completed += 1
                    backend.busy_seconds += elapsed
                    backend.tokens += completion_t
                else:
                    backend.failed += 1
            ROUTER.release(backend)
            tps = completion_t / elapsed if elapsed > 0 else 0.0
            log.info(
                "DONE    [%s] <- %-6s (%s) status=%d stream elapsed=%.2fs ttft=%s "
                "completion~%s tok/s=%.2f bytes=%d",
                req_id, backend.name, backend.addr, status, elapsed,
                f"{first_token_at:.2f}s" if first_token_at else "n/a",
                completion_t, tps, nbytes,
            )


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False        # do not silently steal a port already in use
    request_queue_size = 64


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    global ROUTER, API_KEY  # noqa: PLW0603

    ap = argparse.ArgumentParser(description="GLM-5.2 fleet router (stdlib only)")
    ap.add_argument("--probe", action="store_true",
                    help="probe every backend once, print JSON, exit")
    args = ap.parse_args()

    log_path = setup_logging()
    API_KEY = load_key()
    backends = parse_backends(os.environ.get("GLM_BACKENDS", DEFAULT_BACKENDS))
    ROUTER = Router(backends, API_KEY)

    if args.probe:
        threads = [threading.Thread(target=ROUTER.probe, args=(b,)) for b in backends]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        print(json.dumps(ROUTER.snapshot(), indent=2))
        return 0

    host = os.environ.get("ROUTER_HOST", "127.0.0.1").strip()
    port = _env_int("ROUTER_PORT", 8801)
    if host in WILDCARD_HOSTS:
        sys.exit(
            f"FATAL: refusing to bind wildcard address {host!r}. "
            "Use 127.0.0.1 or an explicit Tailscale IP."
        )

    log.info("=" * 78)
    log.info("glm-router starting  python=%s", sys.version.split()[0])
    log.info("bind    http://%s:%d   (log: %s)", host, port, log_path)
    log.info("backends: %s", ", ".join(f"{b.name}@{b.addr}" for b in backends))
    log.info("timeouts: request=%ss admit=%ss health=%ss/%ss  max_attempts=%d",
             REQUEST_TIMEOUT, ADMIT_TIMEOUT, HEALTH_INTERVAL, HEALTH_TIMEOUT, MAX_ATTEMPTS)

    # first probe synchronously so /health is meaningful the moment we listen
    first = [threading.Thread(target=ROUTER.probe, args=(b,), daemon=True) for b in backends]
    for t in first:
        t.start()
    for t in first:
        t.join(HEALTH_TIMEOUT + 5)

    poller = threading.Thread(target=ROUTER.health_loop, daemon=True, name="health")
    poller.start()

    try:
        httpd = Server((host, port), Handler)
    except OSError as exc:
        log.error("cannot bind %s:%d -- %s", host, port, exc)
        return 1
    httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    ready = sum(1 for b in backends if b.healthy)
    log.info("READY   listening on %s:%d with %d/%d healthy backends",
             host, port, ready, len(backends))
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log.info("SIGINT -- shutting down")
    finally:
        ROUTER.stop.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
