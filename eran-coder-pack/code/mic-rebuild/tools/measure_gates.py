"""KESHEV hard-gate harness — Gate 17, loaded-fleet latency.

PHASE2-DESIGN.md section 9, Gate 17, implemented verbatim:

  1. REAL Qwen load on eran1:8080 (the 480B RPC head) for the WHOLE window,
     with the load PROVEN: llama-server slots-busy + eran1 loadavg sampled
     every 10s and written into the report. "An idle-fleet number is
     auto-marked INVALID" — so `verdict()` refuses to say PASS when the
     samples show an idle machine. The gate cannot be won by unloading it.
  2. Replay through the FULL client path via the `keshevctl inject` seam —
     PCM enters BELOW capture. No microphone, no speakers (Sacred Audio),
     no second pipeline: `instrument()` hangs the stopwatch on the REAL
     Router.type_fn and the REAL Spool.pop of the assembled client.
  3. t0 = segment close (SpoolRecord.t_end, stamped by the segmenter at the
     instant the hangover closed the segment). t1 = the instant the typer
     call RETURNS. Both client-side, one clock, no clock-sync problem.
     Deliberately NOT decode_ms: the server's own number cannot see the
     spool queue, the textguard, or the typer round-trip, and shipping it
     as "dictation latency" would be the almost-true number this repo
     exists to stop shipping.
  4. PASS = p95 <= 3000ms AND p50 <= 1500ms. Report to
     state/reports/gate17-<date>.json.

Everything network-facing takes an injectable seam so the arithmetic and the
verdict are unit-tested offline (tests/test_measure_gates.py) — the live run
is the only part that needs the fleet.

No torch. No audio device. stdlib + numpy only.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

# ------------------------------------------------------------- the two bars
PASS_P50_MS = 1500.0
PASS_P95_MS = 3000.0

# Below this mean slots-busy across the window the fleet was not meaningfully
# loaded and the measurement answers a question nobody asked (design sec 9).
BUSY_FLOOR_PCT = 50.0

QWEN_URL = "http://<lan-ip>:8080"
LOAD_CONCURRENCY = 3
LOAD_N_PREDICT = 1500
SAMPLE_EVERY_S = 10.0

REPORTS_DIR = REPO / "state" / "reports"


# --------------------------------------------------------------- arithmetic

def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile on the sorted samples.

    Nearest-rank on purpose: it returns a number that was actually MEASURED,
    never an interpolated value that no utterance ever experienced. An empty
    sample raises — a gate that reports 0.0 for "no data" is a gate that
    passes on nothing.
    """
    if not values:
        raise ValueError("percentile of an empty sample: there is no number "
                         "to report, and 0.0 would be a lie")
    ordered = sorted(float(v) for v in values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def verdict(*, n: int, p50_ms: float, p95_ms: float,
            load_proof: dict) -> str:
    """PASS / FAIL / INVALID — INVALID outranks both.

    INVALID is not a soft FAIL: it means the run did not measure the thing
    the gate is about (an unloaded fleet, or no utterances at all), so
    neither PASS nor FAIL may be claimed from it.
    """
    if int(n) <= 0:
        return "INVALID"
    if not load_proof or int(load_proof.get("n_samples", 0)) <= 0:
        return "INVALID"
    if float(load_proof.get("slots_busy_pct", 0.0)) < BUSY_FLOOR_PCT:
        return "INVALID"
    if float(p95_ms) <= PASS_P95_MS and float(p50_ms) <= PASS_P50_MS:
        return "PASS"
    return "FAIL"


def build_report(latencies_ms: Sequence[float], load_proof: dict,
                 **meta: Any) -> dict:
    """The section-9 report object: {n, p50_ms, p95_ms, load_proof, verdict}
    plus whatever provenance the caller adds."""
    n = len(latencies_ms)
    p50 = percentile(latencies_ms, 50) if n else 0.0
    p95 = percentile(latencies_ms, 95) if n else 0.0
    report = dict(meta)
    report.update({
        "gate": 17,
        "n": n,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "load_proof": load_proof,
        "verdict": verdict(n=n, p50_ms=p50, p95_ms=p95, load_proof=load_proof),
        "pass_bars": {"p50_ms": PASS_P50_MS, "p95_ms": PASS_P95_MS},
    })
    return report


# ---------------------------------------------------------------- stopwatch

class LatencyLedger:
    """t0 = segment close, t1 = typer return. One in flight at a time —
    the router's decode loop is single-threaded by construction (design
    sec 4.1), so the popped record and the next typed text are the same
    utterance and no correlation id is needed."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._current: Any = None
        self.latencies_ms: list[float] = []
        self.engines: list[str] = []
        self.popped = 0
        self.typed = 0
        self.parked = 0

    def on_pop(self, rec: Any, engine: str = "?") -> Any:
        """Called with whatever Spool.pop returned — including None on an
        idle tick, which must NOT become a phantom record."""
        if rec is not None:
            self.popped += 1
            self._current = (rec, engine)
        return rec

    def on_typed(self, ok: bool = True) -> None:
        if self._current is None:
            return
        rec, engine = self._current
        self._current = None
        if not ok:
            self.parked += 1          # never delivered -> not a latency
            return
        self.typed += 1
        self.latencies_ms.append((self._clock() - float(rec.t_end)) * 1000.0)
        self.engines.append(engine)


def instrument(rig: Any, ledger: LatencyLedger | None = None) -> LatencyLedger:
    """Hang the stopwatch on the assembled client's OWN seams.

    Not a copy of the pipeline, not a shadow timer around the decoder: the
    router's single type_fn call site and the spool's single pop call site.
    If the program changes shape, this measurement changes with it.
    """
    ledger = ledger if ledger is not None else LatencyLedger()
    spool = rig.app.spool
    router = rig.app.router
    inner_pop = spool.pop
    inner_type = router.type_fn

    def pop(timeout: float = 0.5):
        rec = inner_pop(timeout)
        engine = "?"
        if rec is not None:
            engine = str(router.fsm.engine())
        return ledger.on_pop(rec, engine)

    def type_fn(text: str) -> bool:
        ok = bool(inner_type(text))
        ledger.on_typed(ok)
        return ok

    spool.pop = pop
    router.type_fn = type_fn
    return ledger


# ------------------------------------------------------------- load + proof

def parse_slots(rows: Sequence[dict]) -> tuple[int, int, int]:
    """(busy, total, tokens_decoded) from a llama-server /slots payload.

    `is_processing` says a slot is CLAIMED. `next_token[].n_decoded` says
    tokens are actually coming out of it — a number a wedged server cannot
    keep increasing. The proof carries both.
    """
    busy = 0
    decoded = 0
    for row in rows:
        if row.get("is_processing"):
            busy += 1
        for nt in row.get("next_token") or ():
            decoded += int(nt.get("n_decoded") or 0)
    return busy, len(rows), decoded


def default_slots_fn(base_url: str = QWEN_URL) -> tuple[int, int, int]:
    """Live (busy, total, tokens_decoded). Raises on trouble — a load prover
    that swallows its own failure would prove nothing."""
    with urllib.request.urlopen(f"{base_url}/slots", timeout=10) as fh:
        return parse_slots(json.loads(fh.read().decode("utf-8")))


def default_loadavg_fn(host: str = "eran1") -> float:
    """eran1's 1-minute loadavg over ssh."""
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=8", host,
                          "cat /proc/loadavg"],
                         capture_output=True, text=True, timeout=25)
    if out.returncode != 0:
        raise RuntimeError(f"ssh {host} loadavg failed: {out.stderr.strip()[:200]}")
    return float(out.stdout.split()[0])


class LoadProber:
    """Samples slots-busy + eran1 loadavg every SAMPLE_EVERY_S for the whole
    window. The samples ARE the proof — they go into the report verbatim."""

    def __init__(self, *, slots_fn=default_slots_fn,
                 loadavg_fn=default_loadavg_fn,
                 every_s: float = SAMPLE_EVERY_S):
        self._slots_fn = slots_fn
        self._loadavg_fn = loadavg_fn
        self._every = every_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples: list[dict] = []
        self.errors: list[str] = []

    def sample_once(self) -> dict:
        row: dict = {"t": datetime.now().astimezone().isoformat(timespec="seconds")}
        try:
            busy, total, decoded = self._slots_fn()
            row["slots_busy"] = busy
            row["slots_total"] = total
            row["tokens_decoded"] = decoded
            row["busy_pct"] = round(100.0 * busy / total, 1) if total else 0.0
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            row["slots_err"] = f"{type(exc).__name__}: {exc}"[:120]
            self.errors.append(row["slots_err"])
        try:
            row["load1"] = self._loadavg_fn()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            row["load_err"] = f"{type(exc).__name__}: {exc}"[:120]
            self.errors.append(row["load_err"])
        return row

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append(self.sample_once())
            self._stop.wait(self._every)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="gate17-prober",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=40)


def summarize_load(samples: Sequence[dict]) -> dict:
    """Mean busy-pct and mean loadavg across the window, with the raw
    samples kept so the number can be argued with."""
    busy = [float(s["busy_pct"]) for s in samples if "busy_pct" in s]
    loads = [float(s["load1"]) for s in samples if "load1" in s]
    toks = [int(s["tokens_decoded"]) for s in samples if "tokens_decoded" in s]
    return {
        "slots_busy_pct": round(statistics.fmean(busy), 1) if busy else 0.0,
        "eran1_load": round(statistics.fmean(loads), 2) if loads else 0.0,
        "n_samples": len(samples),
        "min_busy_pct": round(min(busy), 1) if busy else 0.0,
        "max_load": round(max(loads), 2) if loads else 0.0,
        # Proof the head was GENERATING, not merely holding slots open.
        "tokens_decoded_seen": sum(1 for t in toks if t > 0),
        "max_tokens_decoded": max(toks) if toks else 0,
        "note": ("eran1 loadavg stays low under Qwen load by design: the 480B "
                 "runs over the llama.cpp RPC fabric and is GPU/interconnect "
                 "bound, not CPU-run-queue bound. nvidia-smi on GB10 reports "
                 "utilization/memory as N/A, so slots-busy + rising n_decoded "
                 "are the load proof that actually carries weight here."),
        "samples": list(samples),
    }


class QwenLoad:
    """LOAD_CONCURRENCY threads holding long generations on the 480B head
    for the whole window. Bounded on purpose: threads are counted, n_predict
    is fixed, and stop() is called in a finally — starving the fleet to win
    a latency gate would be the same dishonesty as unloading it."""

    PROMPTS = (
        "Explain, in detail, how a write-ahead log survives a crash.",
        "Describe the architecture of a streaming audio pipeline.",
        "Write a long technical note about failover state machines.",
    )

    def __init__(self, base_url: str = QWEN_URL, *,
                 concurrency: int = LOAD_CONCURRENCY,
                 n_predict: int = LOAD_N_PREDICT):
        self._url = f"{base_url}/completion"
        self._concurrency = concurrency
        self._n_predict = n_predict
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.started = 0
        self.completed = 0
        self.failures: list[str] = []
        self._lock = threading.Lock()

    def _one(self, idx: int) -> None:
        while not self._stop.is_set():
            body = json.dumps({
                "prompt": self.PROMPTS[idx % len(self.PROMPTS)],
                "n_predict": self._n_predict,
                "temperature": 0.8,
                "cache_prompt": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                self._url, data=body,
                headers={"Content-Type": "application/json"})
            with self._lock:
                self.started += 1
            try:
                with urllib.request.urlopen(req, timeout=900) as fh:
                    fh.read()
                with self._lock:
                    self.completed += 1
            except (urllib.error.URLError, OSError, ValueError) as exc:
                with self._lock:
                    self.failures.append(f"{type(exc).__name__}: {exc}"[:120])
                self._stop.wait(2.0)

    def start(self) -> None:
        for i in range(self._concurrency):
            t = threading.Thread(target=self._one, args=(i,),
                                 name=f"gate17-load-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        # The in-flight generations finish on the server's own schedule; we
        # stop issuing new ones and stop waiting on the old ones. Daemon
        # threads cannot outlive the process.
        for t in self._threads:
            t.join(timeout=1.0)

    def stats(self) -> dict:
        return {"concurrency": self._concurrency,
                "n_predict": self._n_predict,
                "requests_started": self.started,
                "requests_completed": self.completed,
                "failures": self.failures[:5]}


def wait_until_busy(prober: LoadProber, *, floor_pct: float = BUSY_FLOOR_PCT,
                    timeout_s: float = 180.0) -> dict:
    """Block until the head is actually chewing, so utterance #1 is measured
    on a loaded fleet like utterance #200."""
    deadline = time.monotonic() + timeout_s
    row: dict = {}
    while time.monotonic() < deadline:
        row = prober.sample_once()
        if float(row.get("busy_pct", 0.0)) >= floor_pct:
            return row
        time.sleep(3.0)
    return row


# --------------------------------------------------------------- baseline

def decode_baseline(pcms: Sequence[bytes], engine: Any) -> list[int]:
    """Server-side decode_ms for each clip, straight down the DGX HTTP path.

    Taken BEFORE the load starts. On its own it is exactly the idle-fleet
    number the design calls INVALID for the gate — its only job is to be
    compared against the loaded run, so "the fleet was busy" stops being an
    assertion and becomes a difference a reader can check.
    """
    out: list[int] = []
    for i, pcm in enumerate(pcms):
        # 8 hex + 6+ digits — common.protocol.REQUEST_ID_RE, or the server
        # answers bad_request for every clip and the baseline is empty.
        res = engine.transcribe(pcm, request_id=f"ba5e11ec-{100000 + i:06d}",
                                duration_ms=int(len(pcm) / 32),
                                lang_hint="auto")
        out.append(int(res.decode_ms))
    return out


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


# ------------------------------------------------------------- worker spawn

def spawn_fn_local_unavailable(cfg: dict, *, repo: Path | str = REPO,
                               python: str | None = None,
                               popen: Callable[..., Any] | None = None
                               ) -> Callable[[int], Any]:
    """The production spawn, pinned to the worker's LOCAL_UNAVAILABLE rung.

    This PC has neither faster_whisper nor ctranslate2 installed. The local
    engine therefore cannot warm, and a ModuleNotFoundError inside warm is
    a FATAL frame — which kills the worker and, with it, the DGX path that
    does not need the missing package at all. Gate 17 measures B's PRIMARY
    (DGX) path, so the harness asks the worker for the rung it would have
    chosen anyway if it had probed the VRAM it needs: load NOTHING, stay
    ready, serve DGX (scar 14).

    This is a stated scope limit, not a workaround: the report records
    local_engine=UNAVAILABLE, and a demotion to local during the window
    shows up as decode failures, not as a quietly better number.
    """
    launcher = popen if popen is not None else subprocess.Popen
    exe = python or sys.executable

    def spawn_fn(gen: int):
        from client.keshev_worker import LADDER
        argv = [exe, "-u", "-m", "client.keshev_worker",
                "--gen", str(gen), "--model", LADDER[0],
                "--free-vram-mb", "0",
                "--server-url", str(cfg["server_url"]),
                "--token-file", str(cfg["auth_token_file"])]
        return launcher(argv, cwd=str(repo), stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    return spawn_fn


# ------------------------------------------------------------------ corpus

def corpus_clips(directory: Path, *, lo_s: float = 2.0,
                 hi_s: float = 5.0) -> list[Path]:
    """Every 16k mono s16 WAV in the replay corpus whose duration is inside
    the design's 2-5s utterance band. Anything else is skipped, loudly, by
    simply not being counted — the report says the real n."""
    out: list[Path] = []
    for path in sorted(directory.rglob("*.wav")):
        try:
            with wave.open(str(path), "rb") as w:
                if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
                    continue
                seconds = w.getnframes() / float(w.getframerate())
        except (wave.Error, OSError) as exc:
            print(f"  skip {path.name}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            continue
        if lo_s <= seconds <= hi_s:
            out.append(path)
    return out


# -------------------------------------------------------------------- gate

def run_gate17(args) -> int:
    import keshevctl
    from client.app import build_spawn_fn
    from client.configstore import ConfigStore
    from client.keshev_worker import read_free_vram_mb
    from client.worker_mgr import WorkerManager

    corpus_dir = Path(args.corpus)
    clips = corpus_clips(corpus_dir)
    if not clips:
        print(f"gate17: no 2-5s 16k mono clips under {corpus_dir}",
              file=sys.stderr)
        return 2
    if args.limit:
        clips = clips[:args.limit]
    print(f"gate17: corpus {corpus_dir} -> {len(clips)} clips in the 2-5s band")

    cfg = ConfigStore(REPO / "config" / "client.json").load()

    baseline: dict = {"n": 0, "note": "not taken (--baseline 0)"}
    if args.baseline:
        from client.dgx_engine import DgxEngine
        token = (REPO / str(cfg["auth_token_file"])).read_text(
            encoding="utf-8").strip()
        eng = DgxEngine(str(cfg["server_url"]), token, timeout=30)
        picks = clips[:args.baseline]
        print(f"gate17: idle baseline over {len(picks)} clips (before load)…")
        ms = decode_baseline([read_pcm(p) for p in picks], eng)
        baseline = {
            "n": len(ms),
            "server_decode_p50_ms": percentile(ms, 50),
            "server_decode_p95_ms": percentile(ms, 95),
            "note": ("idle-fleet server-side decode_ms, taken BEFORE the load. "
                     "INVALID as a gate result by design sec 9 — here only to "
                     "show the load reached the STT path."),
        }
        print(f"gate17: idle baseline {baseline}")

    prober = LoadProber()
    load = QwenLoad(args.qwen_url)
    rig = None
    worker = None
    t_begin = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        print("gate17: starting Qwen load…")
        load.start()
        first = wait_until_busy(prober)
        print(f"gate17: head busy: {first}")
        prober.start()

        from client.telemetry import Telemetry
        state_dir = Path(args.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        tel = Telemetry(state_dir, "17171717")
        spawn = (spawn_fn_local_unavailable(cfg) if args.local == "unavailable"
                 else build_spawn_fn(cfg))
        worker = WorkerManager(tel, spawn, vram_free_fn=read_free_vram_mb)
        print(f"gate17: spawning the real worker (local={args.local})…")
        worker.start()
        print(f"gate17: worker state={worker.state} local={worker.local_state} "
              f"model={worker.loaded_model}")

        rig = keshevctl.build_rig(cfg=cfg, state_dir=state_dir,
                                  session_id="17171717", telemetry=tel,
                                  worker=worker,
                                  transcript=str(state_dir / "gate17-transcript.txt"))
        ledger = instrument(rig)

        for i, clip in enumerate(clips, 1):
            rig.injector.feed_utterance(keshevctl.read_wav(clip))
            rig.drain(extra_idle_steps=1)
            if i % 20 == 0 or i == len(clips):
                done = len(ledger.latencies_ms)
                p50 = percentile(ledger.latencies_ms, 50) if done else 0.0
                print(f"  {i}/{len(clips)} typed={done} p50={p50:.0f}ms")
    finally:
        load.stop()
        prober.stop()
        if rig is not None:
            rig.close()
        elif worker is not None:
            worker.stop()

    proof = summarize_load(prober.samples)
    report = build_report(
        ledger.latencies_ms, proof,
        host=args.host,
        began_at=t_begin,
        ended_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        corpus={"dir": str(corpus_dir), "clips_available": len(clips),
                "band_s": [2.0, 5.0]},
        counts={"popped": ledger.popped, "typed": ledger.typed,
                "parked": ledger.parked},
        engines={e: ledger.engines.count(e) for e in set(ledger.engines)},
        qwen_load=load.stats(),
        prober_errors=prober.errors[:5],
        local_engine=("UNAVAILABLE (faster_whisper/ctranslate2 not installed "
                      "on this PC) — DGX primary path only"
                      if args.local == "unavailable" else "production spawn"),
        stopwatch=("t0 = SpoolRecord.t_end (segment close); t1 = return of "
                   "the router's single type_fn call site. The Typer's own "
                   "client-side cost is ~0.6ms p50 / ~1.0ms p95 (measured "
                   "over the fake Win32 layer, n=40); the OS SendInput/paste "
                   "dispatch into a real window is NOT in these numbers — "
                   "it is what tests/test_selftest_uipi.py covers."),
        worker_state={"state": worker.state,
                      "local_state": worker.local_state,
                      "model": worker.loaded_model},
        idle_baseline=baseline,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out = REPORTS_DIR / f"gate17-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "load_proof"},
                     ensure_ascii=False, indent=2))
    print(f"gate17: n={report['n']} p50={report['p50_ms']}ms "
          f"p95={report['p95_ms']}ms busy={proof['slots_busy_pct']}% "
          f"load={proof['eran1_load']} -> {report['verdict']}")
    print(f"gate17: report -> {out}")
    return 0 if report["verdict"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="measure_gates",
                                 description="KESHEV hard-gate harness")
    ap.add_argument("--gate", type=int, required=True, choices=(17,))
    ap.add_argument("--host", default="eran1")
    ap.add_argument("--qwen-url", default=QWEN_URL)
    ap.add_argument("--corpus", default=str(REPO / "tools" / "replay" / "wavs"))
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the clip count (0 = the whole corpus)")
    ap.add_argument("--state-dir", default=str(REPO / "state" / "gate17"))
    ap.add_argument("--baseline", type=int, default=40, metavar="N",
                    help="clips to decode idle BEFORE the load, as a "
                         "comparison point (0 = skip)")
    ap.add_argument("--local", choices=("auto", "unavailable"), default="auto",
                    help="'unavailable' pins the worker to its no-local rung "
                         "(this PC has no faster_whisper/ctranslate2); the "
                         "choice is recorded in the report")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run_gate17(args)


if __name__ == "__main__":
    sys.exit(main())
