#!/usr/bin/env python3
"""KESHEV control CLI — `inject`, the offline end-to-end path.

PHASE2-DESIGN.md section 9 (gate 17) names this tool and defines it in one
sentence: replay utterances "through the FULL client path via `keshevctl
inject` (feeds PCM into the pipeline AFTER the capture layer — no speakers,
Sacred Audio)". That sentence is the whole specification, and this module is
its literal implementation:

    PCM (16k mono s16/float32)
      -> segmenter   gate -> auto-gain -> VAD -> 28s split w/ 0.5s overlap
      -> spool       write-ahead file FIRST, queue record second
      -> router      the section-4.1 loop, fresh/stale gate, failover
      -> decoder     scripted stub by default (no subprocess, no model, no LAN)
      -> textguard   the REAL K13 guard, resolved from the router by app.py
      -> typer       a record-only sink by default; the real typer on request
      -> report      ONE JSON object on stdout, honest counts

WHAT THIS MODULE STRUCTURALLY CANNOT DO
  * open a microphone — the injection point is BELOW capture, and every
    device seam defaults to a function that RAISES InjectionRefused. There is
    no device enumeration, no capture-endpoint code path, nothing to open.
  * make a sound — there is no audio-sink import or call site anywhere here
    (Sacred Audio, scar 22; lint gate G6 enforces it repo-wide).
  * disturb the mic Iddo is dictating into — nothing here starts, stops,
    signals or inspects another dictation app.
  * type into a live window by accident — `--typer live` is refused unless
    KESHEV_INJECT_LIVE_TYPER=1 is set AND the coexistence probe in
    client/app.py says no rival dictation client is running.

WHAT IS HONESTLY STUBBED (do not read more into a green inject run)
  * the DECODER. `inject` proves the plumbing carries text end to end; it
    proves nothing about transcription quality. Real decode numbers come from
    gate 17 against eran1.
  * the VAD verdict, unless `--vad real` is passed. The default permissive
    VAD keeps a smoke run deterministic; VAD behavior is K8's business
    (tests/test_segmenter.py).
  * `--typer sink` records deliveries instead of pressing keys, so it does
    not exercise client/typer.py. Pass a real focus/input/clipboard layer
    (or `--typer live`) when the typer is what you are testing.

SCOPE: only `inject` is built. The design's other keshevctl subcommands
(status, config set, calibrate, drill, enroll-owner, gate18, unpin, engine,
update, rollback) are NOT implemented and are not stubbed — an argparse
error is a truer answer than a command that pretends.

RECORDED DIVERGENCE from PHASE2-DESIGN section 2: the module map places this
file at `client\\keshevctl.py`. It lives at `tools\\keshevctl.py` instead —
it is an operator tool, not part of the client's runtime import graph, and
client/ is where the no-torch and import-discipline gates apply. Noted here
rather than silently, so the map and the tree can be reconciled by a ruling
instead of by archaeology.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------- constants

SAMPLE_RATE = 16000            # the pipeline's ONE rate below the resampler
FRAME_SAMPLES = 480            # 30ms — client/app.py BLOCK_MS at 16k
SAMPLE_WIDTH = 2               # s16le
CHANNELS = 1
HANGOVER_MS = 700              # > segmenter CLOSE_SILENCE_MS (600): closes it
POP_TIMEOUT_S = 0.05           # the rig's router is driven, not waited on
DEFAULT_STALE_TEXT = "keshev inject"
LIVE_TYPER_ENV = "KESHEV_INJECT_LIVE_TYPER"

EXIT_OK = 0
EXIT_REFUSED = 5               # a safety gate said no — nothing was run
EXIT_NOTHING_DELIVERED = 6     # segments went in, NEITHER destination got text

# The journal's closed vocabulary (client/spool.py), lower-cased into the
# report so the counts and the ledger can never drift apart.
REPORTED_OUTCOMES = ("TYPED", "RECOVERED", "GUARD_DROP", "EMPTY",
                     "DUP_DISCARD", "PARKED", "SPILLED")


class InjectionRefused(RuntimeError):
    """An injection run reached for something it is not allowed to have — a
    device, a sound card, a live typer, an unsupported audio format. Loud and
    fatal: a silent degrade is how the old mic went deaf for 38 days."""


# ------------------------------------------------------------------- audio


def read_wav(path: str | Path) -> np.ndarray:
    """A WAV as float32 in [-1, 1). REFUSES anything that is not 16k mono
    s16le: the injector sits BELOW the resampler, so accepting 48k here would
    silently stretch every duration and every staleness decision."""
    path = Path(path)
    with wave.open(str(path), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if (rate, channels, width) != (SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH):
        raise InjectionRefused(
            f"{path.name}: {rate} Hz / {channels} ch / {width * 8}-bit — "
            f"inject feeds the pipeline BELOW the resampler and needs "
            f"{SAMPLE_RATE} Hz / {CHANNELS} ch / 16-bit PCM. Convert it "
            f"first; this tool will not resample and call it the same audio.")
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def write_wav(path: str | Path, samples: np.ndarray,
              rate: int = SAMPLE_RATE) -> Path:
    """float32 -> s16le mono WAV. Used to build injection corpora."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
           * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(int(rate))
        w.writeframes(pcm)
    return path


def tone_utterance(seconds: float, *, amp: float = 0.3,
                   phase: int = 0) -> np.ndarray:
    """Synthetic "speech" loud enough to open a segment: a saw whose phase
    rolls every frame, so no two frames are identical while every frame holds
    the same peak (constant auto-gain across segments)."""
    n_frames = max(1, int(round(seconds * SAMPLE_RATE / FRAME_SAMPLES)))
    base = np.linspace(-amp, amp, FRAME_SAMPLES, dtype=np.float32)
    return np.concatenate(
        [np.roll(base, (phase + 7 * k) % FRAME_SAMPLES) for k in range(n_frames)])


# ----------------------------------------------------------------- decoder


def _guess_lang(text: str) -> str:
    """he/en from the script itself — the whitelist common/langpolicy.py
    locks. A stub that answered `lang=None` would be testing a wire shape
    that cannot occur."""
    return "he" if any("֐" <= ch <= "׿" for ch in text) else "en"


class ScriptedDecoder:
    """The default inject decoder: answers from a script.

    Same duck type as client/worker_mgr.WorkerManager — start/stop/decode/
    ping/probe — so the router cannot tell it apart, and no subprocess, no
    model and no network exist in an inject run.

    `texts` cycles (one text + ten segments = the same line ten times, which
    is what a canary run wants). `replies` overrides with whole result dicts
    for failover/latency scripting.
    """

    def __init__(self, texts: Sequence[str] | None = None,
                 replies: Sequence[dict] | None = None, *,
                 healthy: bool = True, decode_ms: int = 120) -> None:
        self.texts = list(texts) if texts else [DEFAULT_STALE_TEXT]
        self.replies = list(replies) if replies else []
        self.decode_ms = int(decode_ms)
        self.calls: list[tuple[str, str]] = []
        self.started = 0
        self.stopped = 0
        self.state = "READY"
        self.local_state = "READY"
        self.worker_rss_mb = 0
        self.worker_vram_mb = 0
        self._healthy = bool(healthy)

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def ping(self) -> bool:
        return True

    def probe(self) -> dict:
        return {"healthy": self._healthy, "decode_p95_ms": 400,
                "uptime_s": 9999}

    def decode(self, rec_id: str, pcm: bytes, *, engine: str,
               lang_hint: str = "auto") -> dict:
        n = len(self.calls)
        self.calls.append((rec_id, engine))
        if self.replies:
            out = dict(self.replies[n % len(self.replies)])
        else:
            text = self.texts[n % len(self.texts)]
            out = {"ok": True, "text": text, "lang": _guess_lang(text),
                   "avg_logprob": -0.2, "no_speech_prob": 0.02,
                   "compression_ratio": 1.4}
        out["id"] = rec_id
        out.setdefault("engine", engine)
        out.setdefault("decode_ms", self.decode_ms)
        return out


# -------------------------------------------------------------- typer sinks


class TranscriptSink:
    """Records every delivery that succeeded, optionally to a file. This is
    what `--typer sink` hands the router: no window, no key, no clipboard."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.lines: list[str] = []
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def record(self, text: str) -> None:
        self.lines.append(text)
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")


def accept_delivery(text: str) -> bool:
    """The default inject type_fn: delivery succeeds, nothing is pressed."""
    return True


# ------------------------------------------------------------ device refusal


def refuse_device(*_args: Any, **_kwargs: Any):
    """Every device seam of an inject rig. Injection enters the pipeline
    ABOVE the segmenter and BELOW capture, so a call that lands here means
    something tried to reach a real microphone during an offline run — which
    is exactly the moment to be loud, never permissive."""
    raise InjectionRefused(
        "keshev inject never enumerates or opens an audio device: PCM is fed "
        "in AFTER the capture layer (PHASE2-DESIGN section 9). Something "
        "asked the device layer for hardware — refusing.")


def permissive_vad(_frame_bytes: bytes) -> bool:
    """The default inject VAD: every frame is speech. Keeps a smoke run
    deterministic; pass --vad real for the production webrtcvad."""
    return True


# ---------------------------------------------------------------- injector


class Injector:
    """THE SEAM: PCM in, after the capture layer.

    Everything upstream of the segmenter (device, PortAudio stream, block
    queue, FIR resample) is bypassed on purpose — that layer owns hardware,
    and this tool owns not touching it. Everything downstream is the real
    thing: the app's own Segmenter instance, its Spool, its Router.
    """

    def __init__(self, app) -> None:
        self.app = app
        self.records: list[Any] = []     # every SpoolRecord produced
        self.samples_fed = 0

    @property
    def audio_seconds(self) -> float:
        return self.samples_fed / SAMPLE_RATE

    # ----------------------------------------------------------- feeding

    def feed_float32(self, samples: Iterable[float]) -> list:
        """Slice into 30ms frames — the exact shape the capture pipeline
        hands the segmenter — and feed them one by one."""
        arr = np.asarray(samples, dtype=np.float32).reshape(-1)
        out: list = []
        for start in range(0, len(arr), FRAME_SAMPLES):
            out.extend(self.app.segmenter.feed(arr[start:start + FRAME_SAMPLES]))
        self.samples_fed += len(arr)
        self.records.extend(out)
        return out

    def feed_pcm_s16(self, pcm: bytes) -> list:
        return self.feed_float32(
            np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0)

    def feed_wav(self, path: str | Path) -> list:
        return self.feed_float32(read_wav(path))

    def feed_silence(self, seconds: float) -> list:
        return self.feed_float32(
            np.zeros(int(round(seconds * SAMPLE_RATE)), dtype=np.float32))

    def feed_utterance(self, samples: Iterable[float], *,
                       tail_silence_ms: int = HANGOVER_MS) -> list:
        """Speech + enough trailing silence to close the segment — one
        utterance, the way the hangover closes a real one."""
        out = self.feed_float32(samples)
        out += self.feed_silence(tail_silence_ms / 1000.0)
        return out

    def flush(self):
        """Close whatever segment is still open (device lost / end of run)."""
        rec = self.app.segmenter.flush()
        if rec is not None:
            self.records.append(rec)
        return rec

    # ---------------------------------------------------------- backlog

    def age_queued(self, seconds: float) -> int:
        """Make every QUEUED record `seconds` older, in place, preserving
        order. `t_end` is the staleness anchor client/spool.py:is_stale reads,
        so this is exactly the state a backlog reaches after the router was
        blocked (worker down, machine asleep) — reproduced without waiting
        half a minute per test. Returns how many records were aged."""
        spool = self.app.spool
        held = []
        while (rec := spool.pop(timeout=0)) is not None:
            rec.t_start -= float(seconds)
            rec.t_end -= float(seconds)
            held.append(rec)
        for rec in held:
            spool.enqueue(rec)
        return len(held)


# --------------------------------------------------------------------- rig


class InjectRig:
    """A built KESHEV client plus the injection seam and the delivery log."""

    def __init__(self, app, sink: TranscriptSink, counters: dict) -> None:
        self.app = app
        self.sink = sink
        self.counters = counters
        self.injector = Injector(app)
        self._closed = False

    # ------------------------------------------------------------ driving

    def drain(self, extra_idle_steps: int = 0) -> int:
        """Run the REAL router loop until the queue is empty.

        `Router.step()` is the section-4.1 loop body verbatim; `Router._run`
        only wraps it in `while`. Driving it here keeps a smoke run
        deterministic — no sleeps, no races, no flaky timing.
        """
        steps = 0
        budget = self.app.spool.qsize() * 4 + 8
        while self.app.spool.qsize() > 0 and steps < budget:
            self.app.router.step()
            steps += 1
        for _ in range(extra_idle_steps):
            self.app.router.step()
            steps += 1
        return steps

    # ------------------------------------------------------------ reading

    def journal(self) -> list[dict]:
        path = self.app.spool.journal_path
        if not path.is_file():
            return []
        return [json.loads(x) for x in
                path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def report(self) -> dict:
        counts = dict.fromkeys((o.lower() for o in REPORTED_OUTCOMES), 0)
        for entry in self.journal():
            key = str(entry.get("outcome", "")).lower()
            if key in counts:
                counts[key] += 1
        report = {
            "segments": self.app.segmenter.segments_enqueued,
            "gated_frames": self.app.segmenter.gated_frames,
            "vad_dropped": self.app.segmenter.segments_vad_dropped,
            "audio_s": round(self.injector.audio_seconds, 2),
            "texts": list(self.sink.lines),
            "device_opens": int(self.counters.get("device_opens", 0)),
            "state_dir": str(self.app.state_dir),
        }
        report.update(counts)
        return report

    # ------------------------------------------------------------ closing

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.app.shutdown()


def build_rig(*, cfg: dict | None = None,
              config_path: str | Path | None = None,
              state_dir: str | Path,
              session_id: str = "abcdef12",
              worker=None,
              texts: Sequence[str] | None = None,
              type_fn: Callable[[str], bool] | None = accept_delivery,
              transcript: str | Path | None = None,
              vad: Callable[[bytes], bool] | None = permissive_vad,
              enumerate_fn=refuse_device,
              native_format_fn=refuse_device,
              check_format_fn=refuse_device,
              open_stream_fn=refuse_device,
              **app_kwargs) -> InjectRig:
    """Assemble the REAL client (client/app.py:build_app) for injection.

    Only the hardware-facing seams are replaced. The router, the segmenter,
    the spool, the textguard resolution and the typer are production code —
    if any of them is broken, an inject run finds out.

    `type_fn=accept_delivery` (the default) records deliveries without
    pressing a key. Pass `type_fn=None` together with focus_api/input_api/
    clipboard to run the REAL typer over a fake Win32 layer.
    """
    from client.app import build_app                 # the real assembly
    from client.configstore import ConfigStore

    if cfg is None:
        path = Path(config_path) if config_path else REPO / "config" / "client.json"
        cfg = ConfigStore(path).load()

    counters = {"device_opens": 0}

    def counting_open_stream(device, rate, channels, pipeline):
        # counted AFTER the open returns: a refused attempt is not an open,
        # and a report that said otherwise would be the kind of almost-true
        # number this repo exists to stop shipping.
        handle = open_stream_fn(device, rate, channels, pipeline)
        counters["device_opens"] += 1
        return handle

    app = build_app(
        cfg,
        state_dir=Path(state_dir),
        session_id=session_id,
        worker=worker if worker is not None else ScriptedDecoder(texts=texts),
        type_fn=type_fn,
        vad=vad,
        enumerate_fn=enumerate_fn,
        native_format_fn=native_format_fn,
        check_format_fn=check_format_fn,
        open_stream_fn=counting_open_stream,
        **app_kwargs)

    # The router owns the ONLY typer call site (design 4.1). Wrapping its
    # type_fn — whatever it is: the sink, the real Typer, a fake — is the one
    # place where "what actually reached the screen" can be recorded without
    # a second delivery path existing.
    sink = TranscriptSink(transcript)
    inner = app.router.type_fn

    def recording_type_fn(text: str) -> bool:
        ok = bool(inner(text))
        if ok:
            sink.record(text)
        return ok

    app.router.type_fn = recording_type_fn
    app.router.pop_timeout = POP_TIMEOUT_S
    return InjectRig(app, sink, counters)


# --------------------------------------------------------------------- CLI


def _resolve_live_typer() -> None:
    """`--typer live` presses real keys into whatever window has focus. Two
    gates, both required, before that gun is loaded."""
    if os.environ.get(LIVE_TYPER_ENV) != "1":
        raise InjectionRefused(
            f"--typer live drives real SendInput into the foreground window. "
            f"Set {LIVE_TYPER_ENV}=1 to say you meant it, and only while no "
            f"one is using the keyboard.")
    from client.app import almamic_alive, default_list_procs, default_list_tasks
    alive, why = almamic_alive(list_procs_fn=default_list_procs,
                               list_tasks_fn=default_list_tasks)
    if alive:
        raise InjectionRefused(
            f"--typer live refused: another dictation client is running "
            f"({why}). Two of them typing into one window is the failure "
            f"this rebuild exists to end.")


def _collect_audio(args) -> list[np.ndarray]:
    """The utterances to inject, in order."""
    out: list[np.ndarray] = []
    for path in args.wav or ():
        out.append(read_wav(path))
    for i in range(int(args.tone or 0)):
        out.append(tone_utterance(float(args.seconds), phase=13 * i))
    if not out:
        raise InjectionRefused(
            "nothing to inject: pass --wav <16k mono s16 file> (repeatable) "
            "or --tone N for synthetic utterances.")
    return out


def cmd_inject(args) -> tuple[int, dict]:
    typer_mode = args.typer
    if typer_mode == "live":
        _resolve_live_typer()
    audio = _collect_audio(args)

    vad = None if args.vad == "real" else permissive_vad
    rig = build_rig(
        config_path=args.config,
        state_dir=args.state_dir,
        worker=ScriptedDecoder(texts=args.text),
        type_fn=None if typer_mode == "live" else accept_delivery,
        transcript=args.transcript,
        vad=vad)
    try:
        for samples in audio:
            rig.injector.feed_utterance(samples)
        rig.injector.flush()
        if args.stale_age:
            rig.injector.age_queued(float(args.stale_age))
        rig.drain(extra_idle_steps=2)
        report = rig.report()
    finally:
        rig.close()

    # Design section 9 counts silent drops across BOTH destinations. A
    # --stale-age drill types nothing on purpose and is a PASS; a run where
    # neither the screen nor recovered.txt received a word is the failure.
    if report["segments"] and not (report["typed"] + report["recovered"]):
        return EXIT_NOTHING_DELIVERED, report
    return EXIT_OK, report


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="keshevctl",
        description="KESHEV control CLI (only `inject` is implemented).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    inj = sub.add_parser(
        "inject",
        help="feed PCM into the pipeline AFTER the capture layer "
             "(no microphone, no sound, no subprocess)")
    inj.add_argument("--wav", action="append", metavar="PATH",
                     help="16k mono s16 WAV to inject; repeatable")
    inj.add_argument("--tone", type=int, default=0, metavar="N",
                     help="inject N synthetic utterances instead of files")
    inj.add_argument("--seconds", type=float, default=2.0,
                     help="length of each synthetic utterance (default 2.0)")
    inj.add_argument("--text", action="append", metavar="TEXT",
                     help="what the stub decoder returns; cycles; repeatable")
    inj.add_argument("--state-dir", default=str(REPO / "state"),
                     help="state directory to use (spool, journal, ledger)")
    inj.add_argument("--config", default=None,
                     help="client.json to load (default: config/client.json)")
    inj.add_argument("--transcript", default=None, metavar="PATH",
                     help="write every delivered line here, one per line")
    inj.add_argument("--typer", choices=("sink", "live"), default="sink",
                     help="sink = record deliveries (default); live = REAL "
                          f"SendInput, gated on {LIVE_TYPER_ENV}=1")
    inj.add_argument("--vad", choices=("permissive", "real"),
                     default="permissive",
                     help="permissive (default, deterministic) or the "
                          "production webrtcvad")
    inj.add_argument("--stale-age", type=float, default=0.0, metavar="S",
                     help="age every queued segment by S seconds before "
                          "routing — drills the scar-16 recovered.txt lane")
    inj.set_defaults(func=cmd_inject)
    return ap


def _write_utf8(stream, line: str) -> None:
    """Bytes to the stream's raw buffer when it has one, text otherwise."""
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        print(line, file=stream, flush=True)
        return
    stream.flush()
    buffer.write(line.encode("utf-8") + b"\n")
    buffer.flush()


def emit(payload: dict) -> None:
    """One JSON object on stdout, ALWAYS UTF-8.

    A Windows console pipe is cp1252 here, and `print()` would raise
    UnicodeEncodeError on the first Hebrew transcript — the tool would die
    exactly when it had something worth saying (found by RUNNING it, not by
    reading it: an in-process StringIO capture has no codec and cannot see
    this bug at all). Writing encoded bytes straight to the raw buffer
    sidesteps the console codec; the text fallback in _write_utf8 is for a
    stdout that has no buffer (a test capture, a redirect object).
    """
    _write_utf8(sys.stdout, json.dumps(payload, ensure_ascii=False,
                                       sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, report = args.func(args)
    except InjectionRefused as exc:
        _write_utf8(sys.stderr, f"keshevctl: refused: {exc}")
        emit({"error": str(exc), "refused": True})
        return EXIT_REFUSED
    emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
