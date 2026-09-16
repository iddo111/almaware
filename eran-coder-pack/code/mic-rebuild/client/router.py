"""KESHEV router — K12 (PHASE2-DESIGN.md sections 4.1/4.2/4.4, scars
16/53/54, criteria 6/13/20/21).

ONE synchronous thread. At most one decode in flight, ever. The ONLY caller
of the typer. Ordered typing (criterion 21) falls out for free; a late DGX
reply after local re-decode cannot be delivered because the socket that
would carry it is closed and the worker is synchronous — scar 53 closed by
construction. The dedup LRU here is defense-in-depth, not the mechanism.

Two classes:

  FailoverFSM   the section-4.2 table as CODE-under-git. States PRIMARY_DGX /
                FALLBACK_LOCAL / PINNED_LOCAL, orthogonal MAINT flag, derived
                DEAF. Structural invariant (criterion 20): the FSM and the
                router hold NO model handles and have NO load/unload call
                sites — a transition moves a routing pointer only; the warm
                fallback stays resident in the worker regardless of routing
                (scar 57). tests/test_router.py asserts this against the
                source (AST), not just against behavior.

  Router        the section-4.1 loop, verbatim shape: spool.pop -> the ONE
                fresh/stale gate (scar 16) -> decode with per-record
                dgx->local failover (SAME id, section 4.4) -> textguard seam
                (K13) -> typed-LRU dedup assert -> typer seam (K14) ->
                journal terminal outcome -> GC. Idle ticks do housekeeping:
                probe / worker ping / recovery drain / heartbeat / spool GC.

Row-5 "transitions" note (design divergence resolved in favor of criterion
20): flap units are RECORDED for every unplanned transition (DEMOTE and
PROMOTE — the design's literal "≥3 transitions within 10 min") PLUS every
broken recovery streak (the link came up and dropped again while we stayed
FALLBACK). The pin check EVALUATES on down-edges only (demote / broken
streak), so a clean recovery never pins by itself, but a demote-promote-
demote sequence pins exactly as row 5 reads. Pure state-transition counting
alone can never reach 3 under promote hysteresis — a 20-40s flapping link
would hold the state at FALLBACK forever and the pin would be unreachable,
which is exactly the thrash criterion 20 exists to surface. PIN_FLAKY and
PLANNED_DEMOTION are protective/planned and are dwell-exempt; DEMOTE and
PROMOTE honor the 60s minimum dwell.

Every transition is journaled through K3 telemetry (closed vocabulary).
stdlib only — no numpy, no network, no model imports (enforced by test).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from typing import Any, Callable, NamedTuple

from client.spool import RecoveredTranscript, Spool, SpoolRecord, is_stale
from client.textguard import guard as textguard_guard
from client.textguard import from_result as textguard_from_result

# ---------------------------------------------------------------- constants
# Section 4.2, pinned as code under git — drift requires a commit (section 5).

PRIMARY_DGX = "PRIMARY_DGX"
FALLBACK_LOCAL = "FALLBACK_LOCAL"
PINNED_LOCAL = "PINNED_LOCAL"

DEMOTE_CONSEC_FAILS = 3          # row 1
SLOW_P50_MS = 2500               # row 2: rolling-60s p50 over >= 5 decodes
SLOW_WINDOW_S = 60.0
SLOW_MIN_N = 5
SLOW_CONSEC_MS = 6000            # row 2: OR 2 consecutive > 6s
SLOW_CONSEC_N = 2
PROMOTE_CONSEC_PROBES = 5        # row 4: 5 consecutive healthy probes…
PROMOTE_P95_MS = 2500            # …with p95 < 2500…
PROMOTE_MIN_UPTIME_S = 120       # …never into a still-loading server
MIN_DWELL_S = 60.0               # minimum dwell in ANY state
FLAP_N = 3                       # row 5: >= 3 flap units / 10 min -> pin
FLAP_WINDOW_S = 600.0
PIN_RECOVER_S = 1800.0           # row 6: 30 min continuously healthy
MAINT_START_HM = (1, 55)         # row 7: nightly fleet reboot window
MAINT_END_HM = (2, 20)           # [01:55, 02:20) local wall clock
PROBE_INTERVAL_S = 10.0
MAINT_PROBE_INTERVAL_S = 30.0    # row 7: probes slow inside the window
DEAF_PROBE_INTERVAL_S = 60.0     # row 8: retry 60s
PING_INTERVAL_S = 15.0           # section 3.2 worker ping cadence
HEARTBEAT_INTERVAL_S = 60.0      # section 8
RECOVERY_DRAIN_INTERVAL_S = 5.0  # idle-tick recovery lane cadence
RECOVERY_DRAIN_BATCH = 3         # orphans per idle tick — stay responsive
SWEEP_INTERVAL_S = 60.0          # spool GC cadence
TYPED_LRU_SIZE = 512             # scar-53 defense-in-depth window


class Transition(NamedTuple):
    row: int
    src: str          # state name or "*"
    trigger: str
    dst: str
    event: str        # the telemetry event that journals it


# The section-4.2 table AS DATA. _apply() validates every state change
# against this table — an undeclared transition is a hard bug, not a
# new behavior. tests/test_router.py pins the rows against the design.
TRANSITIONS: tuple[Transition, ...] = (
    Transition(1, PRIMARY_DGX, "fail3", FALLBACK_LOCAL, "DEMOTE"),
    Transition(2, PRIMARY_DGX, "slow", FALLBACK_LOCAL, "DEMOTE"),
    Transition(3, PRIMARY_DGX, "probe_unhealthy", FALLBACK_LOCAL, "DEMOTE"),
    Transition(4, FALLBACK_LOCAL, "probes5_dwell", PRIMARY_DGX, "PROMOTE"),
    Transition(5, "*", "flap3", PINNED_LOCAL, "PIN_FLAKY"),
    Transition(6, PINNED_LOCAL, "healthy30m_or_unpin", PRIMARY_DGX, "PROMOTE"),
    Transition(7, "*", "maint_window", FALLBACK_LOCAL, "PLANNED_DEMOTION"),
    Transition(8, FALLBACK_LOCAL, "worker_dead_dgx_down", "DEAF", "DEAF"),
)


def in_maint_window(dt: datetime) -> bool:
    """[01:55, 02:20) local wall clock — the nightly fleet reboot (row 7)."""
    hm = (dt.hour, dt.minute)
    return MAINT_START_HM <= hm < MAINT_END_HM


# ---------------------------------------------------------------------- FSM


class FailoverFSM:
    """Section 4.2. Holds a routing POINTER only — no model, no socket, no
    worker handle. All inputs are pushed by the router thread; nothing here
    is called concurrently."""

    def __init__(self, telemetry, *,
                 monotonic: Callable[[], float] = time.monotonic,
                 wallclock: Callable[[], datetime] = datetime.now) -> None:
        self.telemetry = telemetry
        self._mono = monotonic
        self._wall = wallclock
        self.deaf = False
        self._consec_fail = 0
        self._consec_slow = 0
        self._lat: deque = deque()            # (mono_ts, decode_ms) dgx OKs
        self._probe_streak = 0
        self._flaps: deque = deque()          # mono ts of flap units
        self._pinned_healthy_since: float | None = None
        # Boot is not a transition: dwell starts satisfied so a genuinely
        # sick link demotes on its first bad probe, not 60s later.
        self._last_transition = self._mono() - MIN_DWELL_S
        # Row 7: the window check precedes ALL failure accounting — a client
        # launched inside the window starts FALLBACK_LOCAL(MAINT) cleanly.
        if in_maint_window(self._wall()):
            self.state = FALLBACK_LOCAL
            self.maint = True
            self.telemetry.event("PLANNED_DEMOTION", src=PRIMARY_DGX,
                                 dst=FALLBACK_LOCAL, cause="boot_in_window",
                                 row=7)
        else:
            self.state = PRIMARY_DGX
            self.maint = False

    # ------------------------------------------------------------- queries

    def engine(self) -> str | None:
        """The routing pointer: 'dgx' | 'local' | None (DEAF)."""
        if self.deaf:
            return None
        return "dgx" if self.state == PRIMARY_DGX else "local"

    def client_state(self) -> str:
        """Section 4.5 tray-honesty mapping."""
        if self.deaf:
            return "DEAF"
        if self.state == PINNED_LOCAL:
            return "FLAKY"
        if self.state == FALLBACK_LOCAL:
            return "DEGRADED"
        return "READY"

    def probe_interval(self) -> float:
        if self.deaf:
            return DEAF_PROBE_INTERVAL_S
        if self.maint:
            return MAINT_PROBE_INTERVAL_S
        return PROBE_INTERVAL_S

    # ------------------------------------------------------------- inputs

    def tick(self) -> None:
        """Wall-clock housekeeping: the MAINT window (row 7)."""
        inw = in_maint_window(self._wall())
        if inw and not self.maint:
            self.maint = True
            # planned: no failure counters, no flap increment, no dwell
            if self.state == PRIMARY_DGX:
                self._apply(row=7, dst=FALLBACK_LOCAL,
                            event="PLANNED_DEMOTION", cause="maint",
                            planned=True)
            else:
                self.telemetry.event("PLANNED_DEMOTION", src=self.state,
                                     dst=self.state, cause="maint_flag_only",
                                     row=7)
            self._reset_dgx_accounting()
        elif not inw and self.maint:
            self.maint = False
            self.telemetry.event("STATE", state="MAINT_EXIT")

    def on_decode_result(self, *, engine: str, ok: bool,
                         decode_ms: Any = None) -> None:
        """Rows 1-2 accounting. Only DGX results in PRIMARY count; local
        latency is the worker manager's watchdog, not a routing signal."""
        if engine != "dgx" or self.state != PRIMARY_DGX or self.maint:
            return
        if not ok:
            self._consec_fail += 1
            self._consec_slow = 0
            if self._consec_fail >= DEMOTE_CONSEC_FAILS:
                self._apply(row=1, dst=FALLBACK_LOCAL, event="DEMOTE",
                            cause="fail")
            return
        self._consec_fail = 0
        ms = float(decode_ms) if isinstance(decode_ms, (int, float)) else 0.0
        # 2 consecutive > 6s — alive but crawling (criterion 13)
        if ms > SLOW_CONSEC_MS:
            self._consec_slow += 1
            if self._consec_slow >= SLOW_CONSEC_N:
                self._apply(row=2, dst=FALLBACK_LOCAL, event="DEMOTE",
                            cause="slow")
                return
        else:
            self._consec_slow = 0
        # rolling-60s p50 over >= 5 decodes
        now = self._mono()
        self._lat.append((now, ms))
        while self._lat and now - self._lat[0][0] > SLOW_WINDOW_S:
            self._lat.popleft()
        if len(self._lat) >= SLOW_MIN_N:
            vals = sorted(v for _, v in self._lat)
            if vals[len(vals) // 2] > SLOW_P50_MS:
                self._apply(row=2, dst=FALLBACK_LOCAL, event="DEMOTE",
                            cause="slow")

    def on_probe(self, *, healthy: bool, p95_ms: float = 0,
                 uptime_s: float = 0) -> None:
        """Rows 3-6. `healthy` already carries scar-5 law (canary freshness,
        READY state) from dgx_engine.ProbeResult; the promote gate adds the
        p95 and uptime clauses of row 4."""
        if self.maint:
            return                             # planned window: no accounting
        promotable = (healthy and p95_ms < PROMOTE_P95_MS
                      and uptime_s > PROMOTE_MIN_UPTIME_S)
        if self.state == PRIMARY_DGX:
            if not healthy:
                self._apply(row=3, dst=FALLBACK_LOCAL, event="DEMOTE",
                            cause="probe")
        elif self.state == FALLBACK_LOCAL:
            if promotable:
                self._probe_streak += 1
                if self._probe_streak >= PROMOTE_CONSEC_PROBES:
                    self._apply(row=4, dst=PRIMARY_DGX, event="PROMOTE",
                                cause="recovered")
            else:
                if self._probe_streak > 0 and not healthy:
                    # the link came up and dropped again: a flap even though
                    # the STATE never moved (criterion 20 — see module doc)
                    self._flap_unit(evaluate=True)
                self._probe_streak = 0
        elif self.state == PINNED_LOCAL:
            now = self._mono()
            if promotable:
                if self._pinned_healthy_since is None:
                    self._pinned_healthy_since = now
                elif now - self._pinned_healthy_since >= PIN_RECOVER_S:
                    self.telemetry.event("UNPIN", cause="auto")
                    self._apply(row=6, dst=PRIMARY_DGX, event="PROMOTE",
                                cause="pin_recovered", planned=True)
            else:
                self._pinned_healthy_since = None

    def unpin(self) -> None:
        """Manual override — `keshevctl unpin` (row 6, always available)."""
        if self.state != PINNED_LOCAL:
            return
        self.telemetry.event("UNPIN", cause="manual")
        self._apply(row=6, dst=PRIMARY_DGX, event="PROMOTE", cause="unpin",
                    planned=True)

    def set_deaf(self, flag: bool) -> None:
        """Row 8, derived by the router (worker dead AND DGX unreachable).
        Edge-triggered journaling; the flag never moves self.state — DEAF is
        an overlay, and recovery resumes from whatever state remains."""
        if flag and not self.deaf:
            self.deaf = True
            self.telemetry.event("DEAF", src=self.state, row=8)
        elif not flag and self.deaf:
            self.deaf = False
            self.telemetry.event("STATE", state="DEAF_CLEAR")

    # ----------------------------------------------------------- internals

    def _reset_dgx_accounting(self) -> None:
        self._consec_fail = 0
        self._consec_slow = 0
        self._lat.clear()
        self._probe_streak = 0
        self._pinned_healthy_since = None

    def _apply(self, *, row: int, dst: str, event: str, cause: str,
               planned: bool = False) -> bool:
        """The ONE place state moves. Validates against TRANSITIONS, honors
        the 60s dwell (planned/protective moves exempt), journals, and runs
        flap accounting."""
        spec = next(t for t in TRANSITIONS if t.row == row)
        if spec.src != "*" and spec.src != self.state:
            raise AssertionError(
                f"row {row} fired from {self.state}, table says {spec.src}")
        if spec.dst != dst or spec.event != event:
            raise AssertionError(f"row {row} does not declare {event}->{dst}")
        now = self._mono()
        if not planned and now - self._last_transition < MIN_DWELL_S:
            return False                      # dwell: counters keep counting
        src = self.state
        self.state = dst
        self._last_transition = now
        self.telemetry.event(event, src=src, dst=dst, cause=cause, row=row)
        self._reset_dgx_accounting()
        if not planned:
            # a PROMOTE is recorded (it is a transition) but only a
            # down-edge triggers the pin evaluation — see module docstring
            self._flap_unit(evaluate=(event == "DEMOTE"))
        return True

    def _flap_unit(self, *, evaluate: bool) -> None:
        """Row 5: >= FLAP_N units inside FLAP_WINDOW_S pins to local."""
        if self.state == PINNED_LOCAL:
            return
        now = self._mono()
        self._flaps.append(now)
        while self._flaps and now - self._flaps[0] > FLAP_WINDOW_S:
            self._flaps.popleft()
        if evaluate and len(self._flaps) >= FLAP_N:
            src = self.state
            self.state = PINNED_LOCAL
            self._last_transition = now
            self.telemetry.event("PIN_FLAKY", src=src, dst=PINNED_LOCAL,
                                 flaps=len(self._flaps), row=5)
            self._reset_dgx_accounting()
            self._flaps.clear()


# ------------------------------------------------------------------- router


def default_guard(res: dict) -> str | None:
    """The K12 pass-through placeholder — SUPERSEDED by K13.

    It is NOT the Router's default any more: `textguard_guard` is (see
    Router.__init__). It stays defined because it is the negative reference
    client/app.py:196 compares against — the assembly refuses to boot on it,
    since passing text through untouched types every Whisper silence
    hallucination into whatever window has focus. Tests inject it to prove
    that refusal fires. Never make it a default again."""
    text = res.get("text")
    return text if isinstance(text, str) else None


def _default_type_fn(text: str) -> bool:  # pragma: no cover - wiring guard
    raise RuntimeError(
        "no typer wired: Router(type_fn=...) is mandatory until K14 lands")


class Router:
    """Section 4.1 — the ONE synchronous routing thread.

    Seams (all injected; defaults are the real thing where it exists):
      guard_fn   K13 textguard        (default: THE REAL GUARD, textguard.guard)
      type_fn    K14 typer            (REQUIRED — no default typer exists)
      probe_fn   worker.probe()       (the worker owns ALL network egress)

    scar 28: the router is textguard's ONLY importer client-side, and its
    default IS the guard — a Router nobody injects into still drops
    hallucinations, because "someone forgot to pass guard_fn" must never be
    the difference between a filtered mic and a typing one.
    """

    def __init__(self, spool: Spool, worker, telemetry, *,
                 recovered: RecoveredTranscript,
                 type_fn: Callable[[str], bool] = _default_type_fn,
                 guard_fn: Callable[[dict], str | None] = textguard_guard,
                 probe_fn: Callable[[], dict] | None = None,
                 on_typed: Callable[..., None] | None = None,
                 fsm: FailoverFSM | None = None,
                 stale_sec: float = 25.0,
                 monotonic: Callable[[], float] = time.monotonic,
                 now: Callable[[], float] = time.time,
                 wallclock: Callable[[], datetime] = datetime.now,
                 pop_timeout: float = 0.5,
                 # 2026-08-16: was never passed at all, so every decode went
                 # out with the wire default "auto". On short Hebrew segments
                 # the detector picks EN and the decoder writes Hebrew in
                 # LATIN letters — "סוכה" came back "suka", "חולרה" came back
                 # "cholera", "מה קורה" came back "Makore". Not a weak model:
                 # eran1 scores CER 0.000 on a clean fixture. A routing bug.
                 # The script-mismatch retry in common/langpolicy.py only
                 # catches the OTHER direction (Hebrew characters inside an EN
                 # decode), so it can never catch a pure transliteration.
                 lang_hint: str = "auto",
                 # Dual-decode only the SHORT, ambiguous clips: a long
                 # utterance is decided confidently and costs one decode.
                 # 2026-08-16 12:21 — TURNED OFF. Enabling this stopped decodes
                 # entirely: SEG kept arriving, the spool filled to 50 and
                 # SPILLED, and not one DECODE event was emitted. His mic went
                 # dead and the watchdog still printed "healthy — 52 segments in
                 # 10 min", because it counts SEGMENTS, not decodes. Off until
                 # the second decode call is understood; do not re-enable
                 # without a test that asserts a DECODE event follows a SEG.
                 dual_decode: bool = False,
                 dual_decode_max_ms: int = 4000,
                 rss_fn: Callable[[], int] = lambda: -1,
                 drop_frames_fn: Callable[[], int] = lambda: 0) -> None:
        self.spool = spool
        self.worker = worker
        self.telemetry = telemetry
        self.recovered = recovered
        self.type_fn = type_fn
        self.guard_fn = guard_fn
        self.lang_hint = lang_hint
        self.dual_decode = dual_decode
        self.dual_decode_max_ms = dual_decode_max_ms
        # Called with (rec, text, res) after an utterance was ACCEPTED into
        # his window — the corpus seam. None means no capture at all.
        self.on_typed = on_typed
        self.probe_fn = probe_fn or (lambda: self.worker.probe())
        self.stale_sec = float(stale_sec)
        self._mono = monotonic
        self._now = now
        self.fsm = fsm or FailoverFSM(telemetry, monotonic=monotonic,
                                      wallclock=wallclock)
        self.pop_timeout = float(pop_timeout)
        self._rss_fn = rss_fn
        self._drop_frames_fn = drop_frames_fn

        self._typed: OrderedDict[str, None] = OrderedDict()  # scar-53 LRU
        self._typed_lat: deque = deque()   # (mono, ms) for heartbeat p50/p95
        never = -10.0 ** 9                 # first idle tick fires everything
        self._last_probe = never
        self._last_ping = never
        self._last_hb = self._mono()       # heartbeat starts one period out
        self._last_drain = never
        self._last_sweep = never
        self._last_probe_healthy = True    # optimistic until proven otherwise
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------ the loop


    @staticmethod
    def _drop_reason(res: dict) -> str:
        """Which textguard rule fired -- a rule NAME only, never the text."""
        try:
            v = textguard_from_result(res)
            return f"{v.reason}:{v.detail}" if getattr(v, "detail", None) else str(v.reason)
        except Exception:
            return "unknown"

    def step(self) -> None:
        """One iteration of the section-4.1 loop — synchronous, testable."""
        rec = self.spool.pop(timeout=self.pop_timeout)
        self.fsm.tick()                    # window check precedes accounting
        if rec is None:
            self._housekeep()
            return
        now = self._now()
        if is_stale(rec, self.stale_sec, now):
            # stale is still decoded… but NEVER typed into live focus
            res = self._decode_failover(rec)
            self._divert(rec, res, age_s=now - rec.t_end, evt="STALE_DIVERT")
            return
        res = self._decode_failover(rec)
        if not res.get("ok"):
            self.spool.journal_outcome(rec.id, "SPILLED")
            self.telemetry.event("SPILLED", id=rec.id,
                                 err=str(res.get("err"))[:40])
            return                         # file stays -> recovery lane
        text = self.guard_fn(res)
        if text is None:
            # 2026-08-29 -- textguard.guard()'s docstring calls this out itself:
            # "KNOWN FIDELITY COST ... the Verdict's reason/detail are dropped on
            # the floor." So every drop looked identical in the log and there was
            # no way to tell a correctly-silenced hallucination from a mic that had
            # gone mute -- the same blindness that hid a deaf BRIO for twelve hours
            # this morning. The reason is a rule NAME, never transcript text, so
            # naming it keeps the no-transcripts-in-logs rule intact.
            self.spool.journal_outcome(rec.id, "GUARD_DROP")
            self.telemetry.event("GUARD_DROP", id=rec.id,
                                 why=self._drop_reason(res))
            self.spool.gc(rec.id)
            return
        if not text.strip():
            self.spool.journal_outcome(rec.id, "EMPTY")
            self.telemetry.event("EMPTY", id=rec.id)
            self.spool.gc(rec.id)
            return
        if rec.id in self._typed:          # scar 53 defense-in-depth
            self.telemetry.event("DUP_DISCARD", id=rec.id, stage="typed_lru")
            self.spool.journal_outcome(rec.id, "DUP_DISCARD")
            self.spool.gc(rec.id)
            return
        ok = bool(self.type_fn(text))
        self._typed_add(rec.id)
        if ok:
            self.spool.journal_outcome(rec.id, "TYPED")
            self.telemetry.event("TYPED", id=rec.id,
                                 eng=str(res.get("engine", "?")),
                                 ms=int(res.get("decode_ms") or 0),
                                 len=len(text))
            # Corpus capture (Iddo, 2026-08-15: "make the mic always train").
            # HERE and nowhere else, deliberately: this is the one line in the
            # program that knows an utterance was accepted into his window,
            # having passed every guard including presence and focus. That is
            # the gate the corpus rides on — room audio is never typed, so it
            # can never be trained on. It must also run BEFORE spool.gc()
            # below, which is about to delete the audio.
            if self.on_typed is not None:
                try:
                    self.on_typed(rec, text, res)
                except Exception as exc:   # capture must never cost a decode
                    self.telemetry.event("STATE", level="ERROR",
                                         state="CORPUS_ERROR",
                                         err=f"{type(exc).__name__}: "
                                             f"{str(exc)[:80]}")
        else:
            self.spool.journal_outcome(rec.id, "PARKED")
            self.telemetry.event("TYPE_FAIL_PARKED", id=rec.id, len=len(text))
        self.spool.gc(rec.id)              # refuses inside retention — fine

    # ------------------------------------------------------------- decode

    def _decode_failover(self, rec: SpoolRecord) -> dict:
        """Decode with the section-4.1 per-record failover: dgx fail ->
        LOCAL, SAME id (section 4.4 one-engine-in-flight is trivially true —
        this thread is the only decoder)."""
        eng = self.fsm.engine()
        if eng is None:                    # DEAF: spool keeps absorbing
            return {"ok": False, "err": "deaf", "id": rec.id}
        pcm = rec.read_pcm()
        res = self._decode_one(rec, pcm, eng)
        if not res.get("ok") and eng == "dgx":
            res = self._decode_one(rec, pcm, "local")
        return res

    @staticmethod
    def _latin_fraction(text: str) -> float:
        letters = [c for c in (text or "") if c.isalpha()]
        if not letters:
            return 0.0
        return sum(1 for c in letters if "a" <= c.lower() <= "z") / len(letters)

    def _decode_one(self, rec: SpoolRecord, pcm: bytes, eng: str) -> dict:
        res = self.worker.decode(rec.id, pcm, engine=eng,
                                 lang_hint=self.lang_hint)

        # 2026-08-16, both directions of the same scar, in one hour:
        #   lang_hint="auto" -> he speaks Hebrew, the detector says EN on a
        #       short clip, and the decoder TRANSLITERATES: "סוכה" came back
        #       "suka", "מה קורה" came back "Makore".
        #   lang_hint="he"   -> he says "check RTC" and it comes back in
        #       Hebrew letters. "עכשיו זה עברית יותר מדי" — his words.
        # Neither hint is right, because the language changes mid-session and
        # a hint is a standing order. So: DECODE TWICE on the ambiguous cases
        # only, and let the model's own confidence pick the winner. The clean
        # cases (long, decisive) still cost exactly one decode.
        if (self.dual_decode and res.get("ok")
                and len(pcm) // 32 <= self.dual_decode_max_ms):
            text = str(res.get("text") or "")
            latin = self._latin_fraction(text)
            if text.strip() and (latin > 0.6 or latin < 0.4):
                other = "en" if latin > 0.6 else "he"
                alt = self.worker.decode(rec.id, pcm, engine=eng, lang_hint=other)
                if alt.get("ok"):
                    a = alt.get("avg_logprob")
                    b = res.get("avg_logprob")
                    # avg_logprob is the decoder's own confidence: closer to 0
                    # is better. Only override on a clear win, so a coin-flip
                    # never rewrites what the first pass already got right.
                    if a is not None and b is not None and float(a) > float(b) + 0.05:
                        self.telemetry.event("LANG_FLIP", id=rec.id,
                                             to=other, was=round(float(b), 3),
                                             now=round(float(a), 3))
                        alt["id"] = rec.id
                        res = alt
        got = res.get("id")
        if got is not None and got != rec.id:
            # scar 53: a LATE reply surfacing under another record's decode.
            # Discard loudly; it can never reach the typer.
            self.telemetry.event("DUP_DISCARD", got=str(got)[:40],
                                 want=rec.id, stage="late_reply", eng=eng)
            res = {"ok": False, "err": "late_reply", "id": rec.id}
        self.fsm.on_decode_result(engine=eng, ok=bool(res.get("ok")),
                                  decode_ms=res.get("decode_ms"))
        self.telemetry.event("DECODE", id=rec.id, eng=eng,
                             ok=int(bool(res.get("ok"))),
                             ms=int(res.get("decode_ms") or 0))
        if res.get("ok"):
            self._lat_add(res.get("decode_ms"))
        return res

    def _divert(self, rec: SpoolRecord, res: dict, *, age_s: float,
                evt: str) -> None:
        """Second destination (scar 16): recovered.txt, never live focus."""
        if not res.get("ok"):
            self.spool.journal_outcome(rec.id, "SPILLED")
            self.telemetry.event("SPILLED", id=rec.id,
                                 err=str(res.get("err"))[:40])
            return
        text = self.guard_fn(res)
        if text is None or not text.strip():
            self.spool.journal_outcome(
                rec.id, "GUARD_DROP" if text is None else "EMPTY")
            self.spool.gc(rec.id)
            return
        self.recovered.append(rec.id, text, age_s)
        self.spool.journal_outcome(rec.id, "RECOVERED")
        self.telemetry.event(evt, id=rec.id, age_s=int(age_s), len=len(text))
        self.spool.gc(rec.id)

    # -------------------------------------------------------- housekeeping

    def _housekeep(self) -> None:
        now = self._mono()
        if now - self._last_probe >= self.fsm.probe_interval():
            self._last_probe = now
            self._do_probe()
        if now - self._last_ping >= PING_INTERVAL_S:
            self._last_ping = now
            self.worker.ping()
        if now - self._last_drain >= RECOVERY_DRAIN_INTERVAL_S:
            self._last_drain = now
            self._drain_recovery()
        if now - self._last_hb >= HEARTBEAT_INTERVAL_S:
            self._last_hb = now
            self._heartbeat()
        if now - self._last_sweep >= SWEEP_INTERVAL_S:
            self._last_sweep = now
            self.spool.sweep()

    def _do_probe(self) -> None:
        try:
            p = dict(self.probe_fn() or {})
        except Exception as exc:  # noqa: BLE001 — probe trouble is data
            self.telemetry.event("STATE", level="ERROR", state="PROBE_FAIL",
                                 err=f"{type(exc).__name__}: {str(exc)[:120]}")
            p = {"healthy": False}
        healthy = bool(p.get("healthy"))
        self._last_probe_healthy = healthy
        self.fsm.on_probe(healthy=healthy,
                          p95_ms=float(p.get("decode_p95_ms", 0) or 0),
                          uptime_s=float(p.get("uptime_s", 0) or 0))
        # row 8: DEAF = relying on local + local dead + DGX unreachable
        local_dead = (getattr(self.worker, "state", "") == "WORKER_DOWN"
                      or getattr(self.worker, "local_state", "")
                      == "LOCAL_UNAVAILABLE")
        self.fsm.set_deaf(self.fsm.state != PRIMARY_DGX and local_dead
                          and not healthy)

    def _drain_recovery(self) -> None:
        """Backlog orphans (crash survivors + spilled evictions) -> decode ->
        recovered.txt. Never the live typer (scar 16)."""
        if self.fsm.engine() is None:
            return
        for rec in self.spool.orphans()[:RECOVERY_DRAIN_BATCH]:
            res = self._decode_failover(rec)
            if not res.get("ok"):
                return                     # engine trouble — retry next tick
            text = self.guard_fn(res)
            if text is None or not text.strip():
                self.spool.journal_outcome(
                    rec.id, "GUARD_DROP" if text is None else "EMPTY")
                self.spool.gc(rec.id)
                continue
            age_s = max(0.0, self._now() - rec.t_end)
            self.recovered.append(rec.id, text, age_s)
            self.spool.journal_outcome(rec.id, "RECOVERED")
            self.telemetry.event("DIVERTED", id=rec.id, age_s=int(age_s),
                                 len=len(text))
            self.spool.gc(rec.id)

    def _heartbeat(self) -> None:
        vals = sorted(v for _, v in self._typed_lat)
        p50 = int(vals[len(vals) // 2]) if vals else 0
        p95 = int(vals[min(len(vals) - 1, int(len(vals) * 0.95))]) if vals else 0
        spool_files = list(self.spool.spool_dir.glob("*.wav"))
        spool_mb = round(sum(f.stat().st_size for f in spool_files)
                         / (1024 * 1024), 1)
        self.telemetry.heartbeat(
            q=self.spool.qsize(), spool_n=len(spool_files),
            spool_mb=spool_mb, eng=self.fsm.engine() or "none",
            state=self.fsm.client_state(), p50=p50, p95=p95,
            rss_mb=int(self._rss_fn()),
            worker_rss_mb=int(getattr(self.worker, "worker_rss_mb", -1)),
            worker_vram_mb=int(getattr(self.worker, "worker_vram_mb", -1)),
            drop_frames=int(self._drop_frames_fn()))

    # ---------------------------------------------------------- internals

    def _typed_add(self, seg_id: str) -> None:
        self._typed[seg_id] = None
        while len(self._typed) > TYPED_LRU_SIZE:
            self._typed.popitem(last=False)

    def _lat_add(self, decode_ms: Any) -> None:
        if not isinstance(decode_ms, (int, float)):
            return
        now = self._mono()
        self._typed_lat.append((now, float(decode_ms)))
        while self._typed_lat and now - self._typed_lat[0][0] > 300.0:
            self._typed_lat.popleft()

    # ------------------------------------------------------------- thread

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("router already running")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run,
                                        name="keshev-router", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.step()

    def stop(self, timeout: float = 10.0) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():        # never silent (scar 18)
            self.telemetry.event("STATE", level="ERROR",
                                 state="ROUTER_STOP_TIMEOUT")
        self._thread = None
