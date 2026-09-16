"""K9 TDD tests — client/worker_mgr.py (PHASE2-DESIGN.md sections 3.2, 4.3).

The worker subprocess supervisor, tested against a FAKE process (socketpair
pipes + scripted behavior threads) so every lifecycle law is provable fast
and deterministically. Real-subprocess proof lives in
test_worker_integration.py.

Laws under test (scars 10/13/44/57, criterion 2 local path):

  * generation-id discard — a reply tagged with an old generation is
    DISCARDED, never delivered (scar 10 promoted to the process boundary).
  * a STUCK decode never drains — deadline miss = kill (TerminateProcess),
    then wait() + free-VRAM delta assert, then respawn (scar 13).
  * respawn backoff immediate x2 -> 30s -> 2m -> 10m; circuit breaker
    3 respawns / 10 min -> WORKER_DOWN, human reset only (section 4.3).
  * kill triggers: decode deadline, 2 missed pongs, rss > 2500,
    1-min local decode p50 > 2s (section 4.3 kill triggers).
  * graceful shutdown (config swap ONLY) respawns with no backoff and no
    breaker accounting — it is not a kill.

Telemetry goes to a REAL Telemetry instance (tmpdir) — so the closed event
vocabulary of K3 (WORKER_KILL requires vram_before/vram_after, etc.) is
exercised, not mocked.
"""
from __future__ import annotations

import contextlib
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.telemetry import Telemetry  # noqa: E402
from common.protocol import pack_frame, read_frame  # noqa: E402
from client.worker_mgr import (  # noqa: E402
    BREAKER_MAX_RESPAWNS,
    BREAKER_WINDOW_S,
    PONG_MISS_LIMIT,
    RESPAWN_BACKOFF_S,
    RSS_KILL_MB,
    WorkerManager,
)


def write_frame(stream, header: dict, payload: bytes = b"") -> None:
    stream.write(pack_frame(header, payload))


# ------------------------------------------------------------ fake process

class ScriptedWorker:
    """Behavior of the fake worker process on the far side of the pipes."""

    def __init__(self, *, gen, vram_mb=7, model="small",
                 decode_mode="ok", decode_modes=None, decode_ms=5, pong_rss=100,
                 answer_pings=True, exit_after_ready=False,
                 pre_reply_gen=None, pre_reply_id=None, probe_reply=None):
        self.gen = gen
        self.vram_mb = vram_mb
        self.model = model
        self.decode_mode = decode_mode
        self.decode_modes = list(decode_modes) if decode_modes else None
        self.decode_ms = decode_ms
        self.pong_rss = pong_rss
        self.answer_pings = answer_pings
        self.exit_after_ready = exit_after_ready
        self.pre_reply_gen = pre_reply_gen
        self.pre_reply_id = pre_reply_id
        self.probe_reply = probe_reply       # None = never answer (timeout)

    def serve(self, rf, wf):
        def send(header):
            header["gen"] = header.get("gen", self.gen)
            write_frame(wf, header)
            wf.flush()

        send({"event": "loading"})
        send({"event": "ready", "local_state": "READY", "model": self.model,
              "vram_mb": self.vram_mb, "warm_ms": 1})
        if self.exit_after_ready:
            return
        while True:
            got = read_frame(rf)
            if got is None:
                return
            header, _ = got
            cmd = header.get("cmd")
            if cmd == "ping":
                if self.answer_pings:
                    send({"event": "pong", "rss_mb": self.pong_rss})
            elif cmd == "decode":
                mode = self.decode_mode
                if self.decode_modes:
                    mode = self.decode_modes.pop(0)
                if mode == "hang":
                    time.sleep(3600)
                if self.pre_reply_gen is not None:
                    send({"gen": self.pre_reply_gen, "id": header["id"],
                          "ok": True, "engine": "local", "text_len": 6,
                          "lang": "he", "decode_ms": 1})
                if self.pre_reply_id is not None:
                    send({"id": self.pre_reply_id, "ok": True, "engine": "local",
                          "text_len": 6, "lang": "he", "decode_ms": 1})
                send({"id": header["id"], "ok": True, "engine": header["engine"],
                      "text": "שלום", "lang": "he", "avg_logprob": -0.2,
                      "no_speech_prob": 0.01, "decode_ms": self.decode_ms})
            elif cmd == "probe":
                if self.probe_reply is not None:
                    send(dict(self.probe_reply))
            elif cmd == "shutdown":
                return


class FakeWorkerProc:
    """Popen-alike over a socketpair; behavior runs in a daemon thread."""

    def __init__(self, gen, behavior: ScriptedWorker, on_death=None):
        mgr_sock, wrk_sock = socket.socketpair()
        self.stdin = mgr_sock.makefile("wb")
        self.stdout = mgr_sock.makefile("rb")
        self.stderr = None
        self._mgr_sock = mgr_sock
        self._wrk_sock = wrk_sock
        self._rf = wrk_sock.makefile("rb")
        self._wf = wrk_sock.makefile("wb")
        self.pid = 40000 + gen
        self._exit = None
        self._on_death = on_death
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, args=(behavior,), daemon=True)
        self._thread.start()

    def _run(self, behavior):
        try:
            behavior.serve(self._rf, self._wf)
        except (OSError, ValueError):
            return  # killed under us
        finally:
            self._close_worker_side()
            with self._lock:
                if self._exit is None:
                    self._exit = 0
            if self._on_death:
                self._on_death()

    def _close_worker_side(self):
        # Shut down the RAW socket, never the makefile wrappers: closing a
        # buffered socket-file from a foreign thread deadlocks on Windows
        # against a reader parked in readinto() on the same socket.
        with contextlib.suppress(OSError):
            self._wrk_sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            self._wrk_sock.close()

    def poll(self):
        return self._exit

    def wait(self, timeout=None):
        deadline = time.monotonic() + (timeout if timeout is not None else 30)
        while self._exit is None:
            if time.monotonic() > deadline:
                raise TimeoutError("fake proc did not exit")
            time.sleep(0.01)
        return self._exit

    def kill(self):
        with self._lock:
            if self._exit is None:
                self._exit = 1
        self._close_worker_side()  # behavior thread dies on closed pipe
        if self._on_death:
            self._on_death()

    terminate = kill


# ------------------------------------------------------------ harness

class MgrHarness:
    """Manager + fake clock + fake VRAM + spawn plan (one behavior per spawn)."""

    def __init__(self, tmpdir, behaviors, *, vram_free=2400, vram_bump_on_death=10,
                 **mgr_kw):
        self.telemetry = Telemetry(tmpdir, session_id="k9test")
        self.tmpdir = Path(tmpdir)
        self.behaviors = list(behaviors)
        self.spawned: list[FakeWorkerProc] = []
        self.sleeps: list[float] = []
        self.now = [1000.0]
        self.vram = [vram_free]
        self.vram_bump = vram_bump_on_death

        def monotonic():
            return self.now[0]

        def fake_sleep(s):
            self.sleeps.append(s)
            self.now[0] += s

        def vram_free_fn():
            return self.vram[0]

        def spawn_fn(gen):
            beh = self.behaviors.pop(0)
            beh.gen = gen

            def on_death():
                self.vram[0] += self.vram_bump
            proc = FakeWorkerProc(gen, beh, on_death=on_death)
            self.spawned.append(proc)
            return proc

        kw = dict(local_deadline_s=0.25, kill_grace_s=0.05, dgx_deadline_s=0.25,
                  warm_timeout_s=5.0, ping_timeout_s=0.2, vram_wait_s=0.5,
                  monotonic=monotonic, sleep=fake_sleep)
        kw.update(mgr_kw)
        self.mgr = WorkerManager(self.telemetry, spawn_fn,
                                 vram_free_fn=vram_free_fn, **kw)

    def events(self):
        self.telemetry.close()
        path = self.tmpdir / "events.jsonl"
        return [json.loads(l) for l in
                path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def close(self):
        try:
            self.mgr.stop()
        finally:
            try:
                self.telemetry.close()
            except RuntimeError:
                return


def pcm(n=1600):
    return b"\x01\x00" * n


class TestHappyPath(unittest.TestCase):
    def test_start_ready_decode(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                self.assertEqual(h.mgr.state, "READY")
                self.assertEqual(h.mgr.gen, 1)
                res = h.mgr.decode("s-000001", pcm(), engine="local")
                self.assertTrue(res["ok"])
                self.assertEqual(res["text"], "שלום")
                self.assertEqual(h.mgr.state, "READY")
            finally:
                h.close()

    def test_decode_before_start_is_unavailable(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [])
            try:
                res = h.mgr.decode("s-000001", pcm(), engine="local")
                self.assertFalse(res["ok"])
                self.assertEqual(res["err"], "worker_unavailable")
            finally:
                h.close()


class TestGenerationLaw(unittest.TestCase):
    def test_stale_gen_reply_discarded_fresh_one_delivered(self):
        """The scar-10 law: a reply tagged with an OLD generation is discarded.
        The behavior sends a stale-gen reply for the SAME id first, then the
        real one — only the real one may be delivered."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, pre_reply_gen=999)])
            try:
                h.mgr.start()
                res = h.mgr.decode("s-000002", pcm(), engine="local")
                self.assertTrue(res["ok"])
                self.assertEqual(res["text"], "שלום")          # the FRESH reply
                self.assertNotIn("text_len", res)              # not the stale one
            finally:
                h.close()
            evts = h.events()
            stale = [e for e in evts if e["evt"] == "STATE"
                     and e.get("state") == "STALE_GEN_DISCARD"]
            self.assertEqual(len(stale), 1)

    def test_mismatched_id_reply_discarded(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, pre_reply_id="other-999999")])
            try:
                h.mgr.start()
                res = h.mgr.decode("s-000003", pcm(), engine="local")
                self.assertTrue(res["ok"])
                self.assertEqual(res.get("id"), "s-000003")
            finally:
                h.close()


class TestStuckDecodeKill(unittest.TestCase):
    def test_deadline_miss_kills_asserts_vram_and_respawns(self):
        """scar 13: a stuck decode never drains — kill, wait(), VRAM-delta
        assert, respawn. Criterion 2's local path in miniature."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, decode_mode="hang"),
                                ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                first = h.spawned[0]
                res = h.mgr.decode("s-000004", pcm(), engine="local")
                self.assertFalse(res["ok"])
                self.assertEqual(res["err"], "timeout")
                self.assertIsNotNone(first.poll())             # really dead
                self.assertEqual(len(h.spawned), 2)            # respawned
                self.assertEqual(h.mgr.gen, 2)
                self.assertEqual(h.mgr.state, "READY")
                res2 = h.mgr.decode("s-000005", pcm(), engine="local")
                self.assertTrue(res2["ok"])
            finally:
                h.close()
            evts = h.events()
            kills = [e for e in evts if e["evt"] == "WORKER_KILL"]
            self.assertEqual(len(kills), 1)
            k = kills[0]
            self.assertEqual(k["reason"], "decode_timeout")
            self.assertGreaterEqual(k["vram_after"] - k["vram_before"], 3)
            self.assertTrue(any(e["evt"] == "WORKER_RESPAWN" for e in evts))

    def test_vram_not_released_is_loud(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, decode_mode="hang"),
                                ScriptedWorker(gen=0)],
                           vram_bump_on_death=0, vram_wait_s=0.1)
            try:
                h.mgr.start()
                h.mgr.decode("s-000006", pcm(), engine="local")
                self.assertEqual(h.mgr.state, "READY")         # still respawned
            finally:
                h.close()
            evts = h.events()
            suspects = [e for e in evts if e["evt"] == "STATE"
                        and e.get("state") == "VRAM_RELEASE_SUSPECT"]
            self.assertEqual(len(suspects), 1)


class TestBreakerAndBackoff(unittest.TestCase):
    def _hangers(self, n):
        return [ScriptedWorker(gen=0, decode_mode="hang") for _ in range(n)]

    def test_backoff_schedule_then_breaker(self):
        """immediate x2 -> 30s, then the breaker: 3 respawns already inside
        the 10-min window means the NEXT failure trips WORKER_DOWN."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, self._hangers(4))
            try:
                h.mgr.start()
                for i in range(4):
                    res = h.mgr.decode(f"s-{i:06d}", pcm(), engine="local")
                    self.assertFalse(res["ok"])
                self.assertEqual(h.sleeps, [0, 0, 30])
                self.assertEqual(h.mgr.state, "WORKER_DOWN")
                self.assertEqual(len(h.spawned), 4)            # 1 initial + 3 respawns
                res = h.mgr.decode("s-999999", pcm(), engine="local")
                self.assertEqual(res["err"], "worker_down")
            finally:
                h.close()
            evts = h.events()
            self.assertEqual(len([e for e in evts if e["evt"] == "BREAKER_TRIP"]), 1)

    def test_backoff_reaches_2m_and_10m_when_window_expires(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, self._hangers(7))
            try:
                h.mgr.start()
                for i in range(6):
                    h.mgr.decode(f"t-{i:06d}", pcm(), engine="local")
                    h.now[0] += 700.0                          # empty the window
                self.assertEqual(h.sleeps, [0, 0, 30, 120, 600, 600])
                self.assertEqual(h.mgr.state, "READY")         # never tripped
            finally:
                h.close()

    def test_reset_breaker_allows_restart(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, self._hangers(4) + [ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                for i in range(4):
                    h.mgr.decode(f"u-{i:06d}", pcm(), engine="local")
                self.assertEqual(h.mgr.state, "WORKER_DOWN")
                h.mgr.reset_breaker()
                h.mgr.start()
                self.assertEqual(h.mgr.state, "READY")
                res = h.mgr.decode("u-999999", pcm(), engine="local")
                self.assertTrue(res["ok"])
            finally:
                h.close()

    def test_success_resets_consecutive_backoff(self):
        with TemporaryDirectory() as td:
            behaviors = [ScriptedWorker(gen=0, decode_mode="hang"),
                         ScriptedWorker(gen=0, decode_modes=["ok", "hang"]),
                         ScriptedWorker(gen=0)]
            h = MgrHarness(td, behaviors)
            try:
                h.mgr.start()
                h.mgr.decode("v-000001", pcm(), engine="local")      # kill #1
                self.assertTrue(h.mgr.decode("v-000002", pcm(), engine="local")["ok"])
                h.now[0] += 700.0                                    # window empties
                h.mgr.decode("v-000003", pcm(), engine="local")      # kill #2
                # consecutive-failure index was reset by the success:
                self.assertEqual(h.sleeps, [0, 0])
            finally:
                h.close()

    def test_crash_loop_hits_breaker(self):
        """A worker that dies right after ready (load-fail class) is respawned
        with backoff until the breaker holds it down."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, exit_after_ready=True)
                                for _ in range(5)])
            try:
                h.mgr.start()
                deadline = time.monotonic() + 10
                while h.mgr.state != "WORKER_DOWN" and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(h.mgr.state, "WORKER_DOWN")
                self.assertEqual(len(h.spawned), 4)            # 1 + 3 respawns
            finally:
                h.close()
            evts = h.events()
            self.assertEqual(len([e for e in evts if e["evt"] == "BREAKER_TRIP"]), 1)


class TestPingKills(unittest.TestCase):
    def test_two_missed_pongs_kill(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, answer_pings=False),
                                ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                self.assertFalse(h.mgr.ping())                 # miss 1 — no kill
                self.assertEqual(h.mgr.gen, 1)
                self.assertFalse(h.mgr.ping())                 # miss 2 — kill
                self.assertEqual(h.mgr.gen, 2)
                self.assertEqual(h.mgr.state, "READY")
            finally:
                h.close()
            evts = h.events()
            kills = [e for e in evts if e["evt"] == "WORKER_KILL"]
            self.assertEqual(kills[0]["reason"], "pong_miss")

    def test_pong_resets_miss_counter(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                for _ in range(4):
                    self.assertTrue(h.mgr.ping())
                self.assertEqual(h.mgr.gen, 1)                 # never killed
            finally:
                h.close()

    def test_rss_over_cap_kills(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, pong_rss=3000),
                                ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                h.mgr.ping()
                self.assertEqual(h.mgr.gen, 2)
            finally:
                h.close()
            evts = h.events()
            kills = [e for e in evts if e["evt"] == "WORKER_KILL"]
            self.assertEqual(kills[0]["reason"], "rss")


class TestLatencyWatchdog(unittest.TestCase):
    def test_slow_local_p50_kills(self):
        """section 4.3: 1-min local decode p50 > 2s -> kill."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, decode_ms=2500),
                                ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                for i in range(3):
                    res = h.mgr.decode(f"w-{i:06d}", pcm(), engine="local")
                    self.assertTrue(res["ok"])                 # replies delivered
                self.assertEqual(h.mgr.gen, 2)                 # then killed
            finally:
                h.close()
            evts = h.events()
            kills = [e for e in evts if e["evt"] == "WORKER_KILL"]
            self.assertEqual(kills[0]["reason"], "latency")

    def test_fast_decodes_do_not_kill(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, decode_ms=100)])
            try:
                h.mgr.start()
                for i in range(5):
                    h.mgr.decode(f"x-{i:06d}", pcm(), engine="local")
                self.assertEqual(h.mgr.gen, 1)
            finally:
                h.close()


class TestPinnedSupervisionConstants(unittest.TestCase):
    """Section 4.3 numbers are code under git, never config knobs."""

    def test_constants(self):
        self.assertEqual(RESPAWN_BACKOFF_S, (0, 0, 30, 120, 600))
        self.assertEqual(BREAKER_MAX_RESPAWNS, 3)
        self.assertEqual(BREAKER_WINDOW_S, 600)
        self.assertEqual(PONG_MISS_LIMIT, 2)
        self.assertEqual(RSS_KILL_MB, 2500)


class TestProbe(unittest.TestCase):
    """K12 addition: the router probes DGX health THROUGH the worker (the
    worker owns ALL network egress — section 7). probe() never raises; every
    failure mode is an unhealthy dict the FSM can consume."""

    def test_probe_returns_scripted_result(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, probe_reply={
                "event": "probe_result", "state": "READY", "healthy": True,
                "decode_p50_ms": 400, "decode_p95_ms": 1200,
                "canary_age_s": 42, "uptime_s": 3600})])
            try:
                h.mgr.start()
                p = h.mgr.probe()
                self.assertTrue(p["healthy"])
                self.assertEqual(p["state"], "READY")
                self.assertEqual(p["decode_p95_ms"], 1200)
                self.assertEqual(p["uptime_s"], 3600)
            finally:
                h.close()

    def test_probe_before_start_is_unhealthy(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [])
            try:
                p = h.mgr.probe()
                self.assertFalse(p["healthy"])
                self.assertEqual(p["reason"], "worker_unavailable")
            finally:
                h.close()

    def test_probe_timeout_is_unhealthy_not_a_kill(self):
        """A worker that never answers the probe: unhealthy result after the
        probe timeout — the DECODE deadline machinery must not fire."""
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0, probe_reply=None)],
                           probe_timeout_s=0.2)
            try:
                h.mgr.start()
                p = h.mgr.probe()
                self.assertFalse(p["healthy"])
                self.assertEqual(p["reason"], "probe_timeout")
                self.assertEqual(h.mgr.state, "READY")     # alive, not killed
                self.assertTrue(h.mgr.decode("p-000001", pcm(),
                                             engine="local")["ok"])
            finally:
                h.close()
            evts = h.events()
            self.assertEqual([e for e in evts if e["evt"] == "WORKER_KILL"], [])


class TestGracefulRestart(unittest.TestCase):
    def test_config_swap_restart_no_backoff_no_kill(self):
        with TemporaryDirectory() as td:
            h = MgrHarness(td, [ScriptedWorker(gen=0), ScriptedWorker(gen=0)])
            try:
                h.mgr.start()
                h.mgr.restart_graceful()
                self.assertEqual(h.mgr.gen, 2)
                self.assertEqual(h.mgr.state, "READY")
                self.assertEqual(h.sleeps, [])                 # no backoff
                self.assertTrue(h.mgr.decode("y-000001", pcm(), engine="local")["ok"])
            finally:
                h.close()
            evts = h.events()
            self.assertEqual([e for e in evts if e["evt"] == "WORKER_KILL"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
