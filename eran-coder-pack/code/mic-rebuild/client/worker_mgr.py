"""KESHEV worker supervisor — K9 (PHASE2-DESIGN.md sections 3.2, 4.3).

Owns the ONE killable subprocess: spawn / warm / ping / kill / respawn.
Called only by the synchronous router thread (section 4.1), so at most one
decode is in flight, ever — every wait here is a simple blocking wait.

Laws implemented here (scars 10/13/44/57, criterion 2 local path):

  generation-id discard   every spawn bumps `gen`; the reader thread drops
                          ANY frame whose gen != the CURRENT generation and
                          journals STALE_GEN_DISCARD — a zombie's late reply
                          is structurally undeliverable (scar 10).
  stuck decode = kill     a local decode that misses its 10s deadline
                          (+0.5s grace) is TerminateProcess'd, never drained
                          (scar 13). Then: wait() confirms death, the free-
                          VRAM delta is asserted (criterion 2), WORKER_KILL
                          {vram_before, vram_after} is journaled, respawn.
  respawn backoff         immediate x2 -> 30s -> 2m -> 10m (consecutive
                          failures; reset by a successful decode).
  circuit breaker         3 failure-respawns / 10 min already in the window
                          -> the next failure is NOT respawned: BREAKER_TRIP,
                          state WORKER_DOWN, human `keshevctl engine reset`
                          only (section 4.3).
  kill triggers           decode deadline; 2 missed pongs (30s); pong
                          rss_mb > 2500; rolling-60s local decode p50 > 2s.
  graceful restart        config-swap ONLY: cmd=shutdown, clean exit, respawn
                          with NO backoff and NO breaker accounting — never
                          used for a stuck decode.

De-elevated spawn (scar 37/44 residual) is NOT implemented at K9 — the
spawn_fn seam is where CreateProcessWithTokenW lands when app.py exists;
recorded in the K9 RAMCHAT post, not silently dropped.

Injection seams (spawn_fn, vram_free_fn, monotonic, sleep) exist for the
replay rig and tests; defaults are the real thing.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from common.protocol import (
    DGX_DEADLINE_S,
    FrameError,
    LOCAL_DEADLINE_S,
    pack_frame,
    read_frame,
)

# ------------------------------------------------------------- constants
# section 4.3 — pinned as code under git, never config knobs (section 5).
KILL_GRACE_S = 0.5
PING_INTERVAL_S = 15
PONG_MISS_LIMIT = 2
RSS_KILL_MB = 2500
RESPAWN_BACKOFF_S = (0, 0, 30, 120, 600)
BREAKER_MAX_RESPAWNS = 3
BREAKER_WINDOW_S = 600
LATENCY_KILL_P50_MS = 2000
LATENCY_WINDOW_S = 60.0
LATENCY_MIN_N = 3

_REPO = Path(__file__).resolve().parent.parent


def default_spawn_fn(gen: int) -> subprocess.Popen:
    """The real spawn: `python -m client.keshev_worker` with pipes."""
    return subprocess.Popen(
        [sys.executable, "-u", "-m", "client.keshev_worker", "--gen", str(gen)],
        cwd=str(_REPO), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


class WorkerManager:
    """Supervisor for keshev_worker. All public methods are called from the
    single router thread; reader threads only feed queues + telemetry."""

    def __init__(self, telemetry, spawn_fn=default_spawn_fn, *, vram_free_fn,
                 local_deadline_s: float = LOCAL_DEADLINE_S,
                 dgx_deadline_s: float = DGX_DEADLINE_S,
                 kill_grace_s: float = KILL_GRACE_S,
                 warm_timeout_s: float = 90.0,
                 ping_timeout_s: float = 5.0,
                 probe_timeout_s: float = DGX_DEADLINE_S + 1.0,
                 vram_wait_s: float = 5.0,
                 monotonic=time.monotonic,
                 sleep=time.sleep,
                 backoff_s: tuple = RESPAWN_BACKOFF_S,
                 breaker_max: int = BREAKER_MAX_RESPAWNS,
                 breaker_window_s: float = BREAKER_WINDOW_S,
                 rss_kill_mb: int = RSS_KILL_MB,
                 latency_kill_p50_ms: int = LATENCY_KILL_P50_MS,
                 latency_window_s: float = LATENCY_WINDOW_S,
                 latency_min_n: int = LATENCY_MIN_N):
        self.telemetry = telemetry
        self.spawn_fn = spawn_fn
        self.vram_free_fn = vram_free_fn
        self.local_deadline_s = local_deadline_s
        self.dgx_deadline_s = dgx_deadline_s
        self.kill_grace_s = kill_grace_s
        self.warm_timeout_s = warm_timeout_s
        self.ping_timeout_s = ping_timeout_s
        self.probe_timeout_s = probe_timeout_s
        self.vram_wait_s = vram_wait_s
        self._mono = monotonic
        self._sleep = sleep
        self.backoff_s = backoff_s
        self.breaker_max = breaker_max
        self.breaker_window_s = breaker_window_s
        self.rss_kill_mb = rss_kill_mb
        self.latency_kill_p50_ms = latency_kill_p50_ms
        self.latency_window_s = latency_window_s
        self.latency_min_n = latency_min_n

        self._lock = threading.RLock()
        self.gen = 0
        self.state = "IDLE"  # IDLE|WARMING|READY|BUSY|WORKER_DOWN
        self.local_state = None  # READY | LOCAL_UNAVAILABLE (from ready frame)
        self.loaded_model = None
        self.worker_vram_mb = 0
        self.worker_rss_mb = -1
        self.proc = None
        self._reply_q: queue.Queue = queue.Queue()
        self._event_q: queue.Queue = queue.Queue()
        self._respawn_ts: deque = deque()
        self._consec_failures = 0
        self._pong_miss = 0
        self._local_lat: deque = deque()  # (mono_ts, decode_ms)
        self._stopping = False
        self._expected_dead: set = set()  # proc objects we killed on purpose

    # ---------------------------------------------------------------- spawn

    def start(self) -> None:
        """Spawn a new generation and block until its ready frame (or fail
        into the kill/respawn path)."""
        with self._lock:
            self.gen += 1
            gen = self.gen
            self._reply_q = queue.Queue()
            self._event_q = queue.Queue()
            self.state = "WARMING"
            self.local_state = None
            proc = self.spawn_fn(gen)
            self.proc = proc
            reply_q, event_q = self._reply_q, self._event_q
            t = threading.Thread(target=self._reader,
                                 args=(proc, reply_q, event_q),
                                 name=f"keshev-worker-reader-{gen}", daemon=True)
            t.start()
            deadline = time.monotonic() + self.warm_timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill("warm_timeout", proc)
                    return
                try:
                    evt = event_q.get(timeout=remaining)
                except queue.Empty:
                    continue
                kind = evt.get("event")
                if kind == "loading":
                    continue
                if kind == "vram_degrade":
                    self.telemetry.event("VRAM_DEGRADE", want=evt.get("want"),
                                         got=evt.get("got"),
                                         free_mb=evt.get("free_mb"))
                elif kind == "ready":
                    self.local_state = evt.get("local_state")
                    self.loaded_model = evt.get("model")
                    self.worker_vram_mb = int(evt.get("vram_mb") or 0)
                    if self.local_state == "LOCAL_UNAVAILABLE":
                        self.telemetry.event("LOCAL_UNAVAILABLE",
                                             free_mb=evt.get("free_mb"))
                    self.state = "READY"
                    self._pong_miss = 0
                    return
                elif kind == "fatal":
                    self.telemetry.event("STATE", level="ERROR",
                                         state="WORKER_FATAL",
                                         err=str(evt.get("err"))[:200])
                    self._expected_dead.add(id(proc))
                    self._wait_quiet(proc)
                    self._respawn(failure=True)
                    return
                # anything else pre-ready: journal and keep waiting
                else:
                    self.telemetry.event("STATE", state="WORKER_PRE_READY_FRAME",
                                         kind=str(kind)[:40])

    def _reader(self, proc, reply_q, event_q) -> None:
        """One thread per spawn: frames -> queues; gen law enforced HERE."""
        stream = proc.stdout
        try:
            while True:
                got = read_frame(stream)
                if got is None:
                    break
                header, _payload = got
                if header.get("gen") != self.gen:
                    self.telemetry.event("STATE", state="STALE_GEN_DISCARD",
                                         got_gen=header.get("gen"),
                                         cur_gen=self.gen)
                    continue
                if "id" in header and "event" not in header:
                    reply_q.put(header)
                else:
                    event_q.put(header)
        except (FrameError, OSError, ValueError) as exc:
            self.telemetry.event("STATE", level="ERROR", state="READER_ERROR",
                                 err=f"{type(exc).__name__}: {str(exc)[:120]}")
        finally:
            self._on_eof(proc)

    def _on_eof(self, proc) -> None:
        """Pipe closed. Expected deaths were handled by their killer;
        an UNEXPECTED death (crash/load-fail) respawns through the breaker."""
        if self._stopping or id(proc) in self._expected_dead:
            return
        with self._lock:
            if proc is not self.proc:
                return
            self._expected_dead.add(id(proc))
            self.telemetry.event("STATE", level="ERROR", state="WORKER_DIED",
                                 gen=self.gen)
            self._wait_quiet(proc)
            self._respawn(failure=True)

    @staticmethod
    def _wait_quiet(proc) -> None:
        try:
            proc.wait(timeout=15)
        except (TimeoutError, subprocess.TimeoutExpired, OSError):
            return

    # ---------------------------------------------------------------- decode

    def decode(self, rec_id: str, pcm: bytes, *, engine: str,
               lang_hint: str = "auto") -> dict:
        """Synchronous decode through the worker. Never raises on worker
        trouble — every failure is an {ok: False, err} dict for the router."""
        with self._lock:
            if self.state == "WORKER_DOWN":
                return {"ok": False, "err": "worker_down", "id": rec_id}
            if self.state != "READY":
                return {"ok": False, "err": "worker_unavailable", "id": rec_id}
            if engine == "local" and self.local_state == "LOCAL_UNAVAILABLE":
                return {"ok": False, "err": "local_unavailable", "id": rec_id}
            proc = self.proc
            reply_q = self._reply_q
            self.state = "BUSY"
            deadline_s = (self.local_deadline_s if engine == "local"
                          else self.dgx_deadline_s)
            header = {"gen": self.gen, "cmd": "decode", "id": rec_id,
                      "engine": engine, "lang_hint": lang_hint,
                      "deadline_ms": int(deadline_s * 1000)}
            try:
                proc.stdin.write(pack_frame(header, pcm))
                proc.stdin.flush()
            except (OSError, ValueError):
                self.state = "READY"
                self._kill("stdin_dead", proc)
                return {"ok": False, "err": "worker_unavailable", "id": rec_id}

        end = time.monotonic() + deadline_s + self.kill_grace_s
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                self._kill("decode_timeout", proc)
                return {"ok": False, "err": "timeout", "id": rec_id}
            try:
                reply = reply_q.get(timeout=remaining)
            except queue.Empty:
                continue
            if reply.get("id") != rec_id:
                self.telemetry.event("STATE", state="REPLY_ID_MISMATCH",
                                     want=str(rec_id)[:40],
                                     got=str(reply.get("id"))[:40])
                continue
            break

        with self._lock:
            if self.state == "BUSY":
                self.state = "READY"
            self._consec_failures = 0
        if engine == "local" and reply.get("ok"):
            self._latency_tick(reply.get("decode_ms"), proc)
        return reply

    def _latency_tick(self, decode_ms, proc) -> None:
        """section 4.3 latency watchdog: rolling-60s local p50 > 2s -> kill."""
        if not isinstance(decode_ms, (int, float)):
            return
        now = self._mono()
        self._local_lat.append((now, float(decode_ms)))
        while self._local_lat and now - self._local_lat[0][0] > self.latency_window_s:
            self._local_lat.popleft()
        if len(self._local_lat) < self.latency_min_n:
            return
        vals = sorted(v for _, v in self._local_lat)
        p50 = vals[len(vals) // 2]
        if p50 > self.latency_kill_p50_ms:
            self._local_lat.clear()
            self._kill("latency", proc)

    # ---------------------------------------------------------------- ping

    def ping(self) -> bool:
        """15s housekeeping pulse (router calls it). False = missed/killed."""
        with self._lock:
            if self.state != "READY":
                return False
            proc = self.proc
            event_q = self._event_q
            try:
                proc.stdin.write(pack_frame({"gen": self.gen, "cmd": "ping"}))
                proc.stdin.flush()
            except (OSError, ValueError):
                self._kill("stdin_dead", proc)
                return False
        end = time.monotonic() + self.ping_timeout_s
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                self._pong_miss += 1
                if self._pong_miss >= PONG_MISS_LIMIT:
                    self._pong_miss = 0
                    self._kill("pong_miss", proc)
                return False
            try:
                evt = event_q.get(timeout=remaining)
            except queue.Empty:
                continue
            if evt.get("event") != "pong":
                self.telemetry.event("STATE", state="UNEXPECTED_EVENT",
                                     kind=str(evt.get("event"))[:40])
                continue
            self._pong_miss = 0
            rss = evt.get("rss_mb")
            if isinstance(rss, int):
                self.worker_rss_mb = rss
                if rss > self.rss_kill_mb:
                    self._kill("rss", proc)
                    return False
            return True

    # ---------------------------------------------------------------- probe

    def probe(self) -> dict:
        """K12: GET /health via the worker (cmd=probe, section 3.2) — the
        worker owns ALL network egress, the elevated client never touches
        the LAN (section 7). NEVER raises and never kills: a wedged probe is
        an unhealthy answer for the router's FSM, not a lifecycle event —
        decode deadlines and pong misses own the kill triggers."""
        unhealthy = {"event": "probe_result", "state": "UNKNOWN",
                     "healthy": False}
        with self._lock:
            if self.state != "READY":
                return {**unhealthy, "reason": "worker_unavailable"}
            proc = self.proc
            event_q = self._event_q
            try:
                proc.stdin.write(pack_frame({"gen": self.gen, "cmd": "probe"}))
                proc.stdin.flush()
            except (OSError, ValueError):
                self._kill("stdin_dead", proc)
                return {**unhealthy, "reason": "stdin_dead"}
        end = time.monotonic() + self.probe_timeout_s
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return {**unhealthy, "reason": "probe_timeout"}
            try:
                evt = event_q.get(timeout=remaining)
            except queue.Empty:
                continue
            kind = evt.get("event")
            if kind == "probe_result":
                out = dict(evt)
                out.setdefault("healthy", False)
                out.setdefault("reason", str(out.get("err", "unknown"))[:40])
                return out
            if kind == "pong":                     # a stray ping answer
                rss = evt.get("rss_mb")
                if isinstance(rss, int):
                    self.worker_rss_mb = rss
                continue
            self.telemetry.event("STATE", state="UNEXPECTED_EVENT",
                                 kind=str(kind)[:40])

    # ---------------------------------------------------------------- kill

    def _kill(self, reason: str, proc) -> None:
        """TerminateProcess -> wait() -> free-VRAM delta assert -> journal ->
        respawn. The criterion-2 local choreography (scar 13)."""
        with self._lock:
            if proc is not self.proc or id(proc) in self._expected_dead:
                return  # already handled / superseded by a newer generation
            self._expected_dead.add(id(proc))
            vram_before = self._vram_read()
            try:
                proc.kill()
            except OSError as exc:
                self.telemetry.event("STATE", level="ERROR", state="KILL_ERROR",
                                     err=str(exc)[:120])
            self._wait_quiet(proc)

            expected_release = self.worker_vram_mb if self.loaded_model else 0
            floor = max(1, expected_release // 2)
            vram_after = vram_before
            vram_deadline = time.monotonic() + self.vram_wait_s
            while True:
                vram_after = self._vram_read()
                if expected_release <= 0 or (vram_after - vram_before) >= floor:
                    break
                if time.monotonic() >= vram_deadline:
                    self.telemetry.event("STATE", level="ERROR",
                                         state="VRAM_RELEASE_SUSPECT",
                                         vram_before=vram_before,
                                         vram_after=vram_after,
                                         expected_mb=expected_release)
                    break
                time.sleep(0.02)

            self.telemetry.event("WORKER_KILL", vram_before=vram_before,
                                 vram_after=vram_after, reason=reason,
                                 gen=self.gen)
            self._respawn(failure=True)

    def _vram_read(self) -> int:
        try:
            return int(self.vram_free_fn())
        except Exception as exc:  # noqa: BLE001 — probe trouble is loud, not fatal
            self.telemetry.event("STATE", level="ERROR", state="VRAM_PROBE_FAIL",
                                 err=f"{type(exc).__name__}: {str(exc)[:120]}")
            return -1

    # ---------------------------------------------------------------- respawn

    def _respawn(self, *, failure: bool) -> None:
        with self._lock:
            if self._stopping:
                return
            if failure:
                now = self._mono()
                while (self._respawn_ts
                       and now - self._respawn_ts[0] > self.breaker_window_s):
                    self._respawn_ts.popleft()
                if len(self._respawn_ts) >= self.breaker_max:
                    self.telemetry.event(
                        "BREAKER_TRIP",
                        respawns=len(self._respawn_ts),
                        window_s=int(self.breaker_window_s))
                    self.state = "WORKER_DOWN"
                    return
                backoff = self.backoff_s[
                    min(self._consec_failures, len(self.backoff_s) - 1)]
                self._sleep(backoff)
                self._respawn_ts.append(self._mono())
                self._consec_failures += 1
            self.telemetry.event("WORKER_RESPAWN", gen=self.gen + 1,
                                 cause="failure" if failure else "graceful")
            self.start()

    def reset_breaker(self) -> None:
        """Human override — `keshevctl engine reset` (section 4.3)."""
        with self._lock:
            self._respawn_ts.clear()
            self._consec_failures = 0
            if self.state == "WORKER_DOWN":
                self.state = "IDLE"

    # ---------------------------------------------------------------- graceful

    def restart_graceful(self) -> None:
        """Config-swap restart ONLY (section 4.3): shutdown -> clean exit ->
        respawn with no backoff, no breaker accounting, no WORKER_KILL."""
        with self._lock:
            proc = self.proc
            if proc is None:
                self.start()
                return
            self._expected_dead.add(id(proc))
            try:
                proc.stdin.write(pack_frame({"gen": self.gen, "cmd": "shutdown"}))
                proc.stdin.flush()
            except (OSError, ValueError):
                try:
                    proc.kill()
                except OSError:
                    self.telemetry.event("STATE", level="ERROR",
                                         state="KILL_ERROR", err="graceful")
            self._wait_quiet(proc)
            self._respawn(failure=False)

    # ---------------------------------------------------------------- stop

    def stop(self) -> None:
        """Tear down without respawn (client shutdown / tests)."""
        self._stopping = True
        with self._lock:
            proc = self.proc
            if proc is None:
                return
            self._expected_dead.add(id(proc))
            try:
                proc.kill()
            except OSError:
                return
            finally:
                self._wait_quiet(proc)
