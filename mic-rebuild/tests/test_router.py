"""K12 TDD tests — client/router.py (PHASE2-DESIGN.md sections 4.1/4.2,
scars 16/53/54, criteria 6/13/20/21).

The router is the KISS masterstroke under test: ONE synchronous thread, at
most one decode in flight, the ONLY caller of the typer. The failover FSM
(section 4.2) is table-driven — every one of the 8 design rows is exercised
here by name, and the module-level TRANSITIONS table is pinned against the
design so drift requires changing both.

What is proven in this file, all against MOCK engines + fake clocks (no
device, no network, no model, no real server — wave-4 guardrails):

  * rows 1-3: demotion on 3 consecutive failures / latency (rolling-60s
    p50 > 2500ms over >= 5 decodes, OR 2 consecutive > 6s) / unhealthy probe
  * row 4:    promotion hysteresis — 5 consecutive promotable probes AND
              60s dwell; never into a still-loading server (uptime gate)
  * row 5:    flap accounting -> PINNED_LOCAL + PIN_FLAKY
  * row 6:    pin recovery — 30 min continuous health, or manual unpin
  * row 7:    MAINT window 01:55-02:20 (code constant) — PLANNED_DEMOTION,
              no failure counters, no flap increment, boot-inside-window
  * row 8:    DEAF derivation — worker dead AND DGX unreachable
  * scar 53:  request-id dedup — a late DGX reply after failover is
              DUP_DISCARDed, never double-typed (criterion-6 torture: 20
              forced switches with injected late replies)
  * criterion 20: flap torture — link flaps for 15 simulated minutes cause
              exactly ONE demotion, PIN_FLAKY, ZERO model loads (asserted
              structurally: the router has no load call sites at all)
  * criterion 21: burst of 10 utterances types in order on BOTH engines
  * criterion 6 (pause/resume half, mock level): 50 rapid start/stop cycles
              -> zero double-types, thread count returns to baseline.
              (The exactly-one-model-resident VRAM half needs the REAL
              worker + GPU — proven at K9 kill-level; full integration
              deferred to the K17 soak. Not claimed here.)

Every transition is journaled through the REAL K3 Telemetry (closed
vocabulary enforced), not a stub.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import threading
import time
import unittest
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.router import (  # noqa: E402
    DEMOTE_CONSEC_FAILS,
    FALLBACK_LOCAL,
    FLAP_N,
    FLAP_WINDOW_S,
    FailoverFSM,
    MAINT_END_HM,
    MAINT_PROBE_INTERVAL_S,
    MAINT_START_HM,
    MIN_DWELL_S,
    PIN_RECOVER_S,
    PINNED_LOCAL,
    PRIMARY_DGX,
    PROBE_INTERVAL_S,
    PROMOTE_CONSEC_PROBES,
    PROMOTE_MIN_UPTIME_S,
    PROMOTE_P95_MS,
    Router,
    SLOW_CONSEC_MS,
    SLOW_CONSEC_N,
    SLOW_MIN_N,
    SLOW_P50_MS,
    TRANSITIONS,
    in_maint_window,
)
from client.spool import RecoveredTranscript, Spool  # noqa: E402
from client.telemetry import Telemetry  # noqa: E402

PCM = b"\x01\x00" * 320  # 20ms of s16le samples


# ------------------------------------------------------------------ fakes


class Clock:
    """One fake timeline: monotonic, epoch and wall clock move together."""

    def __init__(self, start: float = 10_000.0,
                 wall: datetime | None = None) -> None:
        self.t = float(start)
        self._start = float(start)
        self._wall0 = wall or datetime(2026, 8, 12, 12, 0, 0)

    def mono(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t

    def wall(self) -> datetime:
        return self._wall0 + timedelta(seconds=self.t - self._start)

    def advance(self, s: float) -> None:
        self.t += float(s)


class Recorder(Telemetry):
    """The REAL K3 telemetry (vocabulary law enforced) + in-memory tap."""

    def __init__(self, tmp: str) -> None:
        super().__init__(tmp, session_id="k12test0")
        self.tap: list[tuple[str, dict]] = []

    def event(self, evt: str, level: str = "INFO", **fields) -> None:
        super().event(evt, level, **fields)
        self.tap.append((evt, dict(fields)))

    def of(self, evt: str) -> list[dict]:
        return [f for e, f in self.tap if e == evt]

    def close_quiet(self) -> None:
        try:
            self.close()
        except RuntimeError:
            return


class FakeWorker:
    """Mock of WorkerManager for the router: synchronous decode with a
    scriptable link and late-reply injection.

    Late replies model scar 53: a DGX answer that arrives AFTER the router
    abandoned the request. ``late_mode``:
      * "same_id"     the late reply surfaces on the very next decode call
                      (the local failover for the SAME id)
      * "next_record" it surfaces one call later — on a DIFFERENT record's
                      decode (the id-mismatch case the router must discard)
    """

    def __init__(self) -> None:
        self.state = "READY"
        self.local_state = "READY"
        self.worker_rss_mb = 100
        self.worker_vram_mb = 1000
        self.link_up = True
        self.inject_late = False
        self.late_mode = "same_id"
        self.late: deque = deque()          # [skip_calls, reply]
        self.decode_calls: list[tuple[str, str]] = []
        self.pings = 0
        self.probes = 0
        self.dgx_ms = 500
        self.local_ms = 800
        self.local_ok = True
        self.uptime_s = 9999

    def decode(self, rec_id: str, pcm: bytes, *, engine: str,
               lang_hint: str = "auto") -> dict:
        self.decode_calls.append((rec_id, engine))
        if self.late:
            if self.late[0][0] <= 0:
                return self.late.popleft()[1]
            self.late[0][0] -= 1
        if engine == "dgx":
            if not self.link_up:
                if self.inject_late:
                    skip = 0 if self.late_mode == "same_id" else 1
                    self.late.append([skip, {
                        "ok": True, "id": rec_id, "engine": "dgx",
                        "text": f"late {rec_id}", "lang": "he",
                        "avg_logprob": -0.3, "no_speech_prob": 0.02,
                        "decode_ms": 6100}])
                return {"ok": False, "err": "timeout", "id": rec_id,
                        "engine": "dgx", "decode_ms": 6000}
            return {"ok": True, "id": rec_id, "engine": "dgx",
                    "text": f"dgx {rec_id}", "lang": "he",
                    "avg_logprob": -0.3, "no_speech_prob": 0.02,
                    "decode_ms": self.dgx_ms}
        if engine == "local":
            if not self.local_ok or self.local_state == "LOCAL_UNAVAILABLE":
                return {"ok": False, "err": "local_unavailable", "id": rec_id}
            return {"ok": True, "id": rec_id, "engine": "local",
                    "text": f"local {rec_id}", "lang": "he",
                    "avg_logprob": -0.3, "no_speech_prob": 0.02,
                    "decode_ms": self.local_ms}
        return {"ok": False, "err": "unknown_engine", "id": rec_id}

    def ping(self) -> bool:
        self.pings += 1
        return True

    def probe(self) -> dict:
        self.probes += 1
        if self.link_up:
            return {"event": "probe_result", "state": "READY", "healthy": True,
                    "decode_p50_ms": 400, "decode_p95_ms": 1200,
                    "canary_age_s": 10, "uptime_s": self.uptime_s}
        return {"event": "probe_result", "state": "UNKNOWN",
                "healthy": False, "reason": "conn"}


# ------------------------------------------------------------------ helpers


def fail_n(fsm: FailoverFSM, n: int) -> None:
    for _ in range(n):
        fsm.on_decode_result(engine="dgx", ok=False, decode_ms=6000)


def healthy_probes(fsm: FailoverFSM, clock: Clock, n: int,
                   gap_s: float = PROBE_INTERVAL_S, **kw) -> None:
    p = dict(healthy=True, p95_ms=1200, uptime_s=9999)
    p.update(kw)
    for _ in range(n):
        clock.advance(gap_s)
        fsm.on_probe(**p)


def demote_by_failures(fsm: FailoverFSM, clock: Clock) -> None:
    clock.advance(MIN_DWELL_S + 1)
    fail_n(fsm, DEMOTE_CONSEC_FAILS)


def promote_by_probes(fsm: FailoverFSM, clock: Clock) -> None:
    clock.advance(MIN_DWELL_S + 1)
    healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES)


class FsmCase(unittest.TestCase):
    """FSM under a fake clock; teardown closes telemetry BEFORE the tmpdir
    goes away (Windows: an open log fd blocks directory deletion)."""

    def make(self, *, wall: datetime | None = None
             ) -> tuple[FailoverFSM, Recorder, Clock]:
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        clock = Clock(wall=wall)
        tel = Recorder(td.name)
        self.addCleanup(tel.close_quiet)     # LIFO: closes before cleanup
        fsm = FailoverFSM(tel, monotonic=clock.mono, wallclock=clock.wall)
        return fsm, tel, clock


class Rig:
    """Router + real Spool + real Telemetry + FakeWorker on a fake clock."""

    def __init__(self, td: str, **router_kw) -> None:
        self.td = Path(td)
        self.clock = router_kw.pop("clock", None) or Clock()
        self.worker = router_kw.pop("worker", None) or FakeWorker()
        self.tel = Recorder(td)
        self.spool = Spool(self.td / "spool", now_fn=self.clock.now)
        self.recovered_path = self.td / "recovered.txt"
        self.recovered = RecoveredTranscript(self.recovered_path)
        self.typed: list[str] = []
        self.fsm = FailoverFSM(self.tel, monotonic=self.clock.mono,
                               wallclock=self.clock.wall)

        def type_fn(text: str) -> bool:
            self.typed.append(text)
            return True

        kw = dict(recovered=self.recovered, fsm=self.fsm, type_fn=type_fn,
                  stale_sec=25.0, monotonic=self.clock.mono,
                  now=self.clock.now, wallclock=self.clock.wall,
                  pop_timeout=0.01)
        kw.update(router_kw)
        self.router = Router(self.spool, self.worker, self.tel, **kw)
        self._seq = 0

    def feed(self, *, age_s: float = 0.0, dur_ms: int = 1000) -> str:
        self._seq += 1
        rid = f"c6c6c6c6-{self._seq:06d}"
        t_end = self.clock.now() - age_s
        rec = self.spool.write_ahead(PCM, seg_id=rid, t_start=t_end - 1.0,
                                     t_end=t_end, duration_ms=dur_ms,
                                     rms_raw=0.01, gain=1.0)
        self.spool.enqueue(rec)
        return rid

    def orphan(self, *, age_s: float = 0.0) -> str:
        """Write-ahead WITHOUT enqueue — a crash survivor for recovery."""
        self._seq += 1
        rid = f"c6c6c6c6-{self._seq:06d}"
        t_end = self.clock.now() - age_s
        self.spool.write_ahead(PCM, seg_id=rid, t_start=t_end - 1.0,
                               t_end=t_end, duration_ms=1000,
                               rms_raw=0.01, gain=1.0)
        return rid

    def idle(self, sim_s: float, tick_s: float = 5.0) -> None:
        """Idle housekeeping steps across `sim_s` fake seconds."""
        elapsed = 0.0
        while elapsed < sim_s:
            self.clock.advance(tick_s)
            elapsed += tick_s
            self.router.step()

    def journal(self) -> list[dict]:
        p = self.spool.journal_path
        if not p.is_file():
            return []
        return [json.loads(x) for x in
                p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def outcomes(self, outcome: str) -> list[str]:
        return [e["id"] for e in self.journal() if e["outcome"] == outcome]

    def recovered_ids(self) -> list[str]:
        if not self.recovered_path.is_file():
            return []
        return re.findall(r"\[(\S+) \+",
                          self.recovered_path.read_text(encoding="utf-8"))


class RigCase(unittest.TestCase):
    def make_rig(self, **kw) -> Rig:
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        rig = Rig(td.name, **kw)
        self.addCleanup(rig.tel.close_quiet)  # LIFO: before td.cleanup
        return rig


# ================================================================== the table


class TestTransitionTable(unittest.TestCase):
    """The section-4.2 table is DATA in the module, pinned verbatim here —
    changing a row requires changing the design first."""

    def test_table_pins_design_rows(self):
        want = {
            1: (PRIMARY_DGX, FALLBACK_LOCAL, "DEMOTE"),
            2: (PRIMARY_DGX, FALLBACK_LOCAL, "DEMOTE"),
            3: (PRIMARY_DGX, FALLBACK_LOCAL, "DEMOTE"),
            4: (FALLBACK_LOCAL, PRIMARY_DGX, "PROMOTE"),
            5: ("*", PINNED_LOCAL, "PIN_FLAKY"),
            6: (PINNED_LOCAL, PRIMARY_DGX, "PROMOTE"),
            7: ("*", FALLBACK_LOCAL, "PLANNED_DEMOTION"),
            8: (FALLBACK_LOCAL, "DEAF", "DEAF"),
        }
        rows = {t.row: (t.src, t.dst, t.event) for t in TRANSITIONS}
        self.assertEqual(rows, want)

    def test_constants_pin_design(self):
        self.assertEqual(DEMOTE_CONSEC_FAILS, 3)
        self.assertEqual(SLOW_P50_MS, 2500)
        self.assertEqual(SLOW_MIN_N, 5)
        self.assertEqual(SLOW_CONSEC_MS, 6000)
        self.assertEqual(SLOW_CONSEC_N, 2)
        self.assertEqual(PROMOTE_CONSEC_PROBES, 5)
        self.assertEqual(PROMOTE_P95_MS, 2500)
        self.assertEqual(PROMOTE_MIN_UPTIME_S, 120)
        self.assertEqual(MIN_DWELL_S, 60.0)
        self.assertEqual(FLAP_N, 3)
        self.assertEqual(FLAP_WINDOW_S, 600.0)
        self.assertEqual(PIN_RECOVER_S, 1800.0)
        self.assertEqual(MAINT_START_HM, (1, 55))
        self.assertEqual(MAINT_END_HM, (2, 20))
        self.assertEqual(PROBE_INTERVAL_S, 10.0)
        self.assertEqual(MAINT_PROBE_INTERVAL_S, 30.0)


# ================================================================== rows 1-3


class TestDemotion(FsmCase):
    def test_row1_three_consecutive_failures_demote(self):
        fsm, tel, clock = self.make()
        fail_n(fsm, 2)
        self.assertEqual(fsm.state, PRIMARY_DGX)   # 2 is not 3
        fail_n(fsm, 1)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        demotes = tel.of("DEMOTE")
        self.assertEqual(len(demotes), 1)
        self.assertEqual(demotes[0]["cause"], "fail")
        self.assertEqual(demotes[0]["src"], PRIMARY_DGX)
        self.assertEqual(demotes[0]["dst"], FALLBACK_LOCAL)

    def test_success_resets_failure_count(self):
        fsm, tel, clock = self.make()
        fail_n(fsm, 2)
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=500)
        fail_n(fsm, 2)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        self.assertEqual(tel.of("DEMOTE"), [])

    def test_local_results_never_demote(self):
        fsm, tel, clock = self.make()
        for _ in range(10):
            fsm.on_decode_result(engine="local", ok=False, decode_ms=100)
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row2_p50_latency_demotes(self):
        fsm, tel, clock = self.make()
        for _ in range(SLOW_MIN_N):
            clock.advance(5)
            fsm.on_decode_result(engine="dgx", ok=True, decode_ms=3000)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertEqual(tel.of("DEMOTE")[0]["cause"], "slow")

    def test_row2_p50_needs_five_decodes(self):
        fsm, tel, clock = self.make()
        for _ in range(SLOW_MIN_N - 1):
            clock.advance(5)
            fsm.on_decode_result(engine="dgx", ok=True, decode_ms=3000)
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row2_samples_expire_outside_60s_window(self):
        fsm, tel, clock = self.make()
        for _ in range(SLOW_MIN_N):
            clock.advance(16)     # 5th sample: first is 64s old -> expired
            fsm.on_decode_result(engine="dgx", ok=True, decode_ms=3000)
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row2_two_consecutive_over_6s_demote(self):
        fsm, tel, clock = self.make()
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=6100)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        clock.advance(1)
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=6200)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertEqual(tel.of("DEMOTE")[0]["cause"], "slow")

    def test_row2_fast_decode_resets_consecutive_slow(self):
        fsm, tel, clock = self.make()
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=6100)
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=500)
        fsm.on_decode_result(engine="dgx", ok=True, decode_ms=6100)
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row3_unhealthy_probe_demotes(self):
        fsm, tel, clock = self.make()
        fsm.on_probe(healthy=False)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertEqual(tel.of("DEMOTE")[0]["cause"], "probe")


# ================================================================== row 4


class TestPromotionHysteresis(FsmCase):
    def test_row4_four_probes_insufficient_fifth_promotes(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        clock.advance(MIN_DWELL_S + 1)
        healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES - 1)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        healthy_probes(fsm, clock, 1)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        self.assertEqual(len(tel.of("PROMOTE")), 1)

    def test_row4_dwell_blocks_early_promote(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        # 5 healthy probes only 50s after the demotion: dwell not met
        healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES, gap_s=10)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        healthy_probes(fsm, clock, 1, gap_s=15)   # now past the 60s dwell
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row4_broken_streak_resets(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        clock.advance(MIN_DWELL_S + 1)
        healthy_probes(fsm, clock, 3)
        fsm.on_probe(healthy=False)               # streak broken
        healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES - 1)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        healthy_probes(fsm, clock, 1)
        self.assertEqual(fsm.state, PRIMARY_DGX)

    def test_row4_never_promote_into_loading_server(self):
        """uptime_s <= 120 means the server just rebooted — not promotable."""
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        clock.advance(MIN_DWELL_S + 1)
        healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES + 2, uptime_s=30)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)

    def test_row4_slow_p95_not_promotable(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        clock.advance(MIN_DWELL_S + 1)
        healthy_probes(fsm, clock, PROMOTE_CONSEC_PROBES + 2, p95_ms=2600)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)


# ================================================================== rows 5-6


class TestFlapPin(FsmCase):
    def test_row5_three_transitions_in_window_pin(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)            # transition 1
        promote_by_probes(fsm, clock)             # transition 2
        demote_by_failures(fsm, clock)            # transition 3 -> pin
        self.assertEqual(fsm.state, PINNED_LOCAL)
        self.assertEqual(len(tel.of("PIN_FLAKY")), 1)

    def test_row5_spread_transitions_do_not_pin(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        clock.advance(FLAP_WINDOW_S + 5)
        promote_by_probes(fsm, clock)
        clock.advance(FLAP_WINDOW_S + 5)
        demote_by_failures(fsm, clock)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertEqual(tel.of("PIN_FLAKY"), [])

    def test_row5_clean_recovery_never_pins(self):
        """demote -> clean promote is 2 transitions: never a pin by itself."""
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        promote_by_probes(fsm, clock)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        self.assertEqual(tel.of("PIN_FLAKY"), [])

    def test_row5_broken_recovery_streaks_count_as_flaps(self):
        """A link that comes up and drops again while we are FALLBACK is a
        flap even though the STATE never changed — that is what criterion 20
        needs: the hysteresis holds the state still, the pin still happens."""
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)            # flap 1
        healthy_probes(fsm, clock, 2)
        fsm.on_probe(healthy=False)               # flap 2 (broken streak)
        healthy_probes(fsm, clock, 2)
        fsm.on_probe(healthy=False)               # flap 3 -> pin
        self.assertEqual(fsm.state, PINNED_LOCAL)
        self.assertEqual(len(tel.of("PIN_FLAKY")), 1)

    def _pin(self, fsm, clock):
        demote_by_failures(fsm, clock)
        healthy_probes(fsm, clock, 2)
        fsm.on_probe(healthy=False)
        healthy_probes(fsm, clock, 2)
        fsm.on_probe(healthy=False)
        assert fsm.state == PINNED_LOCAL

    def test_row6_pinned_ignores_short_recovery(self):
        fsm, tel, clock = self.make()
        self._pin(fsm, clock)
        healthy_probes(fsm, clock, 60)            # 10 minutes healthy
        self.assertEqual(fsm.state, PINNED_LOCAL)

    def test_row6_pinned_recovers_after_30_min_continuous(self):
        fsm, tel, clock = self.make()
        self._pin(fsm, clock)
        healthy_probes(fsm, clock, int(PIN_RECOVER_S / 10) + 2)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        unpins = tel.of("UNPIN")
        self.assertEqual(len(unpins), 1)
        self.assertEqual(unpins[0]["cause"], "auto")

    def test_row6_unhealthy_probe_resets_recovery_clock(self):
        fsm, tel, clock = self.make()
        self._pin(fsm, clock)
        healthy_probes(fsm, clock, 150)           # 25 min
        fsm.on_probe(healthy=False)
        healthy_probes(fsm, clock, 150)           # 25 more
        self.assertEqual(fsm.state, PINNED_LOCAL)

    def test_row6_manual_unpin(self):
        fsm, tel, clock = self.make()
        self._pin(fsm, clock)
        fsm.unpin()
        self.assertEqual(fsm.state, PRIMARY_DGX)
        self.assertEqual(tel.of("UNPIN")[0]["cause"], "manual")


# ================================================================== row 7


class TestMaintWindow(FsmCase):
    def test_window_edges(self):
        def dt(h, m):
            return datetime(2026, 8, 13, h, m, 0)
        self.assertFalse(in_maint_window(dt(1, 54)))
        self.assertTrue(in_maint_window(dt(1, 55)))
        self.assertTrue(in_maint_window(dt(2, 0)))
        self.assertTrue(in_maint_window(dt(2, 19)))
        self.assertFalse(in_maint_window(dt(2, 20)))
        self.assertFalse(in_maint_window(dt(12, 0)))

    def test_row7_planned_demotion_on_entry(self):
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 1, 50, 0))
        self.assertEqual(fsm.state, PRIMARY_DGX)
        clock.advance(6 * 60)                     # 01:56
        fsm.tick()
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertTrue(fsm.maint)
        self.assertEqual(fsm.engine(), "local")
        self.assertEqual(len(tel.of("PLANNED_DEMOTION")), 1)
        self.assertEqual(tel.of("DEMOTE"), [])    # planned, not a failure

    def test_row7_no_failure_accounting_inside_maint(self):
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 1, 50, 0))
        clock.advance(6 * 60)
        fsm.tick()
        fail_n(fsm, 10)
        for _ in range(5):
            fsm.on_probe(healthy=False)
        self.assertEqual(tel.of("DEMOTE"), [])
        self.assertEqual(tel.of("PIN_FLAKY"), [])

    def test_row7_no_flap_increment(self):
        """A planned demotion + the post-window promote must not count
        toward the flap pin: the nightly 02:00 pair is not flapping."""
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 1, 50, 0))
        clock.advance(6 * 60)                     # inside window
        fsm.tick()
        clock.advance(30 * 60)                    # 02:26 — window over
        fsm.tick()
        self.assertFalse(fsm.maint)
        promote_by_probes(fsm, clock)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        # one more unplanned demote right after: only 2 flap units in the
        # window -> NO pin
        demote_by_failures(fsm, clock)
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertEqual(tel.of("PIN_FLAKY"), [])

    def test_row7_boot_inside_window_starts_fallback_maint(self):
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 2, 0, 0))
        self.assertEqual(fsm.state, FALLBACK_LOCAL)
        self.assertTrue(fsm.maint)
        self.assertEqual(tel.of("DEMOTE"), [])
        self.assertEqual(len(tel.of("PLANNED_DEMOTION")), 1)

    def test_row7_probe_interval_slows_inside_maint(self):
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 1, 50, 0))
        self.assertEqual(fsm.probe_interval(), PROBE_INTERVAL_S)
        clock.advance(6 * 60)
        fsm.tick()
        self.assertEqual(fsm.probe_interval(), MAINT_PROBE_INTERVAL_S)

    def test_row7_exit_then_promotes_normally(self):
        fsm, tel, clock = self.make(wall=datetime(2026, 8, 13, 1, 56, 0))
        self.assertTrue(fsm.maint)
        clock.advance(26 * 60)                    # 02:22
        fsm.tick()
        self.assertFalse(fsm.maint)
        promote_by_probes(fsm, clock)
        self.assertEqual(fsm.state, PRIMARY_DGX)
        self.assertEqual(len(tel.of("PROMOTE")), 1)


# ================================================================== row 8


class TestDeaf(FsmCase, RigCase):
    def test_set_deaf_emits_once_and_engine_is_none(self):
        fsm, tel, clock = self.make()
        demote_by_failures(fsm, clock)
        fsm.set_deaf(True)
        fsm.set_deaf(True)
        self.assertIsNone(fsm.engine())
        self.assertEqual(len(tel.of("DEAF")), 1)
        fsm.set_deaf(False)
        self.assertEqual(fsm.engine(), "local")

    def test_router_derives_deaf_and_spills(self):
        rig = self.make_rig()
        rig.worker.link_up = False
        for _ in range(3):                         # 3 fails -> demote
            rig.feed()
            rig.router.step()
        self.assertEqual(rig.fsm.state, FALLBACK_LOCAL)
        # now the worker dies too
        rig.worker.state = "WORKER_DOWN"
        rig.worker.local_ok = False
        rig.idle(21, tick_s=7)                     # probes see DGX down
        self.assertTrue(rig.fsm.deaf)
        self.assertEqual(len(rig.tel.of("DEAF")), 1)
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed[3:], [])        # nothing typed while deaf
        self.assertIn(rid, rig.outcomes("SPILLED"))
        self.assertIn(rid, [r.id for r in rig.spool.orphans()])
        # link returns + worker revives -> deaf clears (row-8 retry is 60s)
        rig.worker.link_up = True
        rig.worker.state = "READY"
        rig.worker.local_ok = True
        rig.idle(130, tick_s=10)
        self.assertFalse(rig.fsm.deaf)


# ================================================================== delivery


class TestRouterDelivery(RigCase):
    def test_fresh_segment_typed_and_journaled(self):
        rig = self.make_rig()
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [f"dgx {rid}"])
        self.assertEqual(rig.outcomes("TYPED"), [rid])
        self.assertEqual(len(rig.tel.of("TYPED")), 1)
        self.assertTrue(rig.tel.of("DECODE"))

    def test_stale_segment_diverted_never_typed(self):
        rig = self.make_rig()
        rid = rig.feed(age_s=30.0)                 # > 25s stale gate
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.outcomes("RECOVERED"), [rid])
        self.assertEqual(rig.recovered_ids(), [rid])
        self.assertEqual(len(rig.tel.of("STALE_DIVERT")), 1)

    def test_failover_same_id_dgx_then_local(self):
        rig = self.make_rig()
        rig.worker.link_up = False
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.worker.decode_calls,
                         [(rid, "dgx"), (rid, "local")])
        self.assertEqual(rig.typed, [f"local {rid}"])
        self.assertEqual(rig.outcomes("TYPED"), [rid])

    def test_both_engines_fail_spills_file_stays(self):
        rig = self.make_rig()
        rig.worker.link_up = False
        rig.worker.local_ok = False
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertIn(rid, rig.outcomes("SPILLED"))
        self.assertTrue((rig.spool.spool_dir / f"{rid}.wav").is_file())
        self.assertIn(rid, [r.id for r in rig.spool.orphans()])

    def test_guard_drop(self):
        rig = self.make_rig(guard_fn=lambda res: None)
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.outcomes("GUARD_DROP"), [rid])
        self.assertEqual(len(rig.tel.of("GUARD_DROP")), 1)

    def test_empty_after_guard(self):
        rig = self.make_rig(guard_fn=lambda res: "   ")
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.outcomes("EMPTY"), [rid])

    def test_type_fail_parked(self):
        rig = self.make_rig()
        rig.router.type_fn = lambda text: False
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.outcomes("PARKED"), [rid])
        self.assertEqual(len(rig.tel.of("TYPE_FAIL_PARKED")), 1)

    def test_duplicate_id_typed_exactly_once(self):
        """scar 53 defense-in-depth: a re-delivered id can never type twice."""
        rig = self.make_rig()
        rid = rig.feed()
        rig.router.step()
        # re-deliver the SAME id (crash-recovery re-enqueue class)
        rec = rig.spool.write_ahead(PCM, seg_id=rid,
                                    t_start=rig.clock.now() - 1,
                                    t_end=rig.clock.now(),
                                    duration_ms=1000, rms_raw=0.01, gain=1.0)
        rig.spool.enqueue(rec)
        rig.router.step()
        self.assertEqual(rig.typed, [f"dgx {rid}"])          # once
        self.assertEqual(rig.outcomes("DUP_DISCARD"), [rid])
        self.assertEqual(len(rig.tel.of("DUP_DISCARD")), 1)

    def test_recovery_drain_to_recovered_txt(self):
        rig = self.make_rig()
        rid = rig.orphan(age_s=120.0)
        rig.idle(30, tick_s=6)
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.outcomes("RECOVERED"), [rid])
        self.assertEqual(rig.recovered_ids(), [rid])
        self.assertTrue(rig.tel.of("DIVERTED"))

    def test_heartbeat_and_ping_cadence(self):
        rig = self.make_rig()
        rig.idle(130, tick_s=5)
        self.assertGreaterEqual(len(rig.tel.of("HEARTBEAT")), 2)
        hb = rig.tel.of("HEARTBEAT")[0]
        for f in ("q", "spool_n", "spool_mb", "eng", "state", "p50",
                  "p95", "rss_mb", "worker_rss_mb", "worker_vram_mb",
                  "drop_frames"):
            self.assertIn(f, hb)
        self.assertGreaterEqual(rig.worker.pings, 7)


# ================================================================== criterion 6


class TestCriterion6FailoverTorture(RigCase):
    """20 forced switches (10 demote + 10 promote) mid-stream, late DGX
    replies injected after failover — both the same-id and the wrong-id
    delivery patterns. Zero double-types, zero lost utterances counting both
    destinations, every late wrong-id reply DUP_DISCARD-logged."""

    def test_twenty_forced_switches_zero_double_types(self):
        rig = self.make_rig()
        fed: list[str] = []
        for cycle in range(10):
            rig.worker.link_up = False
            rig.worker.inject_late = True
            rig.worker.late_mode = ("same_id" if cycle % 2 == 0
                                    else "next_record")
            for _ in range(3):                     # 3 fails -> demote
                fed.append(rig.feed())
                rig.router.step()
            self.assertEqual(rig.fsm.state, FALLBACK_LOCAL,
                             f"cycle {cycle}: demote missing")
            rig.worker.link_up = True
            rig.worker.inject_late = False
            fed.append(rig.feed())                 # rides the local engine
            rig.router.step()
            # recovery: healthy probes until promotion (dwell + streak)
            rig.idle(140, tick_s=10)
            self.assertEqual(rig.fsm.state, PRIMARY_DGX,
                             f"cycle {cycle}: promote missing")
            rig.clock.advance(500)                 # spread the transitions
            rig.router.step()                      # (no flap-pin)

        rig.idle(40, tick_s=5)                     # final recovery drain

        typed_ids = [t.split()[-1] for t in rig.typed]
        recovered_ids = rig.recovered_ids()
        # zero double-types: no id typed twice, none typed AND recovered
        self.assertEqual(len(typed_ids), len(set(typed_ids)))
        self.assertEqual(set(typed_ids) & set(recovered_ids), set())
        # zero lost: every utterance landed in exactly one destination
        self.assertEqual(set(fed), set(typed_ids) | set(recovered_ids))
        # 20 switches, journaled
        self.assertEqual(len(rig.tel.of("DEMOTE")), 10)
        self.assertEqual(len(rig.tel.of("PROMOTE")), 10)
        self.assertEqual(rig.tel.of("PIN_FLAKY"), [])
        # late wrong-id replies were discarded and logged (5 next_record
        # cycles x 2 surfaced-late replies each)
        dups = rig.tel.of("DUP_DISCARD")
        self.assertGreaterEqual(len(dups), 10)
        for d in dups:
            self.assertNotEqual(d.get("got"), d.get("want"))


class TestCriterion6PauseResume(RigCase):
    """50 rapid start/stop cycles of the router THREAD (mock engines):
    zero double-types, thread count returns to baseline — no zombies.
    The exactly-one-model-resident VRAM assert requires the real worker and
    is owned by the K17 soak (worker-level kill/VRAM proven at K9)."""

    def test_fifty_start_stop_cycles(self):
        rig = self.make_rig()
        baseline = threading.active_count()
        for i in range(50):
            rig.feed()
            rig.router.start()
            deadline = time.monotonic() + 5.0
            while len(rig.typed) < i + 1 and time.monotonic() < deadline:
                time.sleep(0.002)
            rig.router.stop()
            self.assertEqual(len(rig.typed), i + 1,
                             f"cycle {i}: utterance not typed")
        self.assertEqual(threading.active_count(), baseline)
        typed_ids = [t.split()[-1] for t in rig.typed]
        self.assertEqual(len(typed_ids), len(set(typed_ids)))
        self.assertEqual(len(typed_ids), 50)


# ================================================================== criterion 20


class TestCriterion20FlapTorture(RigCase):
    """Link flaps (25s down / 35s up) for 15 simulated minutes: exactly ONE
    demotion, PIN_FLAKY raised, zero promotions, zero model loads — the warm
    fallback stays resident by DESIGN (the router cannot load anything, see
    TestStructuralNoModelHandles), and the flapping costs routing only."""

    def test_flap_torture_one_demotion_pin_no_loads(self):
        rig = self.make_rig()
        fed: list[str] = []
        t = 0.0
        while t < 900.0:
            rig.clock.advance(5.0)
            t += 5.0
            rig.worker.link_up = (t % 60.0) < 35.0
            if int(t) % 120 == 0:                  # speech under the flap
                fed.append(rig.feed())
            rig.router.step()
        self.assertEqual(len(rig.tel.of("DEMOTE")), 1)
        self.assertEqual(len(rig.tel.of("PIN_FLAKY")), 1)
        self.assertEqual(rig.tel.of("PROMOTE"), [])
        self.assertEqual(rig.fsm.state, PINNED_LOCAL)
        # every utterance delivered (typed via the warm local fallback)
        typed_ids = [x.split()[-1] for x in rig.typed]
        self.assertEqual(set(fed), set(typed_ids))
        self.assertEqual(len(typed_ids), len(set(typed_ids)))


class TestStructuralNoModelHandles(unittest.TestCase):
    """Criterion 20's zero-loads clause, asserted the design's way: the
    router has NO load call sites and holds NO model handles — a transition
    moves a routing pointer only. Checked against the SOURCE (AST)."""

    SRC = (REPO / "client" / "router.py").read_text(encoding="utf-8")

    def test_no_model_imports(self):
        tree = ast.parse(self.SRC)
        banned = {"ctranslate2", "faster_whisper", "torch", "onnxruntime",
                  "client.keshev_worker", "keshev_worker",
                  "client.dgx_engine", "dgx_engine"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name, banned, a.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module or "", banned, node.module)

    def test_no_load_or_unload_call_sites(self):
        """No CALL in the router may load or unload anything model-shaped —
        scanned over the AST so comments cannot hide one."""
        tree = ast.parse(self.SRC)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            self.assertNotIn("load", name.lower(),
                             f"load-shaped call site: {name}")
            self.assertNotIn("model", name.lower(),
                             f"model-shaped call site: {name}")

    def test_worker_surface_is_routing_only(self):
        """The router may touch worker.{decode,ping,probe,state,local_state,
        worker_rss_mb,worker_vram_mb} — nothing else. No spawn, no kill,
        no model handle."""
        allowed = {"decode", "ping", "probe", "state", "local_state",
                   "worker_rss_mb", "worker_vram_mb"}
        tree = ast.parse(self.SRC)
        touched = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "worker"):
                touched.add(node.attr)
        self.assertTrue(touched, "router never touches its worker?")
        self.assertLessEqual(touched, allowed, touched - allowed)


# ================================================================== criterion 21


class TestCriterion21OrderedBurst(RigCase):
    """Burst of 10 utterances in 30s: all arrive, in order, zero dedup
    false-positives, zero stale diversion of live speech — on BOTH engines.
    (Run-on splits are consecutive spool records — same ordering property;
    the 28s+overlap split mechanics themselves are K8's, proven there.)"""

    def _burst(self, rig: Rig) -> list[str]:
        fed = []
        for _ in range(10):
            rig.clock.advance(3.0)                 # 10 segments across 30s
            fed.append(rig.feed())
            rig.router.step()
        return fed

    def test_burst_in_order_on_dgx(self):
        rig = self.make_rig()
        fed = self._burst(rig)
        self.assertEqual(rig.typed, [f"dgx {r}" for r in fed])
        self.assertEqual(rig.tel.of("DUP_DISCARD"), [])
        self.assertEqual(rig.tel.of("STALE_DIVERT"), [])

    def test_burst_in_order_on_local(self):
        rig = self.make_rig()
        rig.worker.link_up = False                 # demotes on the fly
        fed = self._burst(rig)
        self.assertEqual([t.split()[-1] for t in rig.typed], fed)
        self.assertTrue(all(t.startswith("local ") for t in rig.typed))
        self.assertEqual(rig.tel.of("DUP_DISCARD"), [])
        self.assertEqual(rig.tel.of("STALE_DIVERT"), [])
        self.assertEqual(len(rig.tel.of("DEMOTE")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
