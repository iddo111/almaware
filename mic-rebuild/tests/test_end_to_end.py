"""KESHEV END-TO-END SMOKE PATH — the test that answers "is it a program yet".

Every other test file proves one module. test_app.py proves the ASSEMBLY is
wired. This file proves the assembled thing CARRIES SPEECH: synthetic PCM in
at the injection seam, real text out at the typer, in order, once.

    inject (PCM, 16k mono f32)
      -> segmenter   (energy gate -> auto-gain -> VAD -> 28s split)
      -> spool       (write-ahead file, THEN the queue record)
      -> router      (the section-4.1 loop: fresh/stale gate -> decode)
      -> stub worker (scripted replies — no subprocess, no model, no LAN)
      -> textguard   (the REAL K13 guard, resolved from the router)
      -> Typer       (the REAL K14 typer over a fake Win32 layer)
      -> text

The injection seam is `tools/keshevctl.py inject`, built exactly as
PHASE2-DESIGN.md section 9 gate 17 specifies it: "feeds PCM into the pipeline
AFTER the capture layer — no speakers, Sacred Audio". So:

  * NO microphone. The rig never calls open_capture_now(); its default
    device-enumeration seam RAISES if anything asks for a device list.
  * NO speaker. keshevctl has no audio-output import or call site at all
    (lint gate G6 covers the repo; this file asserts it for the new module).
  * NO subprocess, NO model, NO network. The decoder is a scripted stub.
  * alma-mic is never touched, never probed, never signalled.

The hard cases the design cares about, all here:

  burst      10 utterances inside 30s of audio -> all 10 typed, in order,
             zero duplicates, zero stale diversion of live speech
             (PHASE2-DESIGN K12 row, criterion 21).
  run-on     a 20-40s run-on splits at 28s with a 0.5s overlap and still
             types in order — the overlap is proven at the BYTE level:
             the tail of segment 1's stored PCM IS the head of segment 2's
             (design section 2 segmenter row).
  stale      a segment older than stale_sec (25s) is still decoded but
             lands in recovered.txt and NEVER in the live typer
             (scar 16, design section 4.1's ONE fresh/stale gate).

Fakes are REUSED from the files that own them (tests/test_focus.py's FakeApi,
tests/test_typer.py's FakeClip/FakeInput, tests/test_app.py's DeviceSpies /
StubWorker / make_cfg) so this file tests the pipeline, not a second copy of
the fixtures.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from client import router as router_mod  # noqa: E402
from client import textguard  # noqa: E402
from client.segmenter import (  # noqa: E402
    MAX_SEGMENT_S,
    SPLIT_OVERLAP_S,
)
from tests.test_app import (  # noqa: E402
    BRIO,
    XM4,
    DeviceSpies,
    StubWorker,
    default_focus_api,
    make_cfg,
)
from tests.test_typer import FakeClip, FakeInput  # noqa: E402

from tools import keshevctl  # noqa: E402

KESHEVCTL_SRC = (REPO / "tools" / "keshevctl.py").read_text(encoding="utf-8")

SR = keshevctl.SAMPLE_RATE          # 16000
FRAME = keshevctl.FRAME_SAMPLES     # 480 = 30ms, the K7 capture block


# ------------------------------------------------------------------- signal


def speech(seconds: float, *, amp: float = 0.3, phase: int = 0) -> np.ndarray:
    """`seconds` of synthetic "speech": a saw whose phase rolls every frame.

    Two properties this test leans on hard:
      * every 480-sample frame holds exactly +amp and -amp, so the segmenter's
        auto-gain computes the SAME gain for every segment cut out of it —
        which is what makes a byte-level overlap comparison legitimate;
      * no two frames are identical (the roll advances by 7 samples), so an
        overlap that matches did not match by accident.
    """
    n_frames = max(1, int(round(seconds * SR / FRAME)))
    base = np.linspace(-amp, amp, FRAME, dtype=np.float32)
    return np.concatenate(
        [np.roll(base, (phase + 7 * k) % FRAME) for k in range(n_frames)])


def hush(seconds: float) -> np.ndarray:
    """Digital silence — below any calibrated gate, closes an open segment."""
    return np.zeros(int(round(seconds * SR)), dtype=np.float32)


# --------------------------------------------------------------------- rig


class RigCase(unittest.TestCase):
    """A built injection rig over a temp state dir, torn down every test."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="keshev-e2e-")
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def rig(self, *, texts=None, replies=None, cfg=None, real_typer=True,
            **over) -> keshevctl.InjectRig:
        """The pipeline under test. `texts` scripts the stub decoder; every
        other seam defaults to the safe headless thing."""
        worker = over.pop("worker", None)
        if worker is None:
            worker = keshevctl.ScriptedDecoder(texts=texts, replies=replies)
        kwargs = dict(cfg=cfg or make_cfg(), state_dir=self.tmp / "state",
                      session_id="abcdef12", worker=worker)
        if real_typer:
            # the REAL client/typer.py over a fake Win32 layer: fake windows,
            # fake SendInput, fake clipboard — zero OS effect, full typer code
            self.clip = FakeClip()
            self.input = FakeInput()
            self.api = over.pop("api", None) or default_focus_api()
            kwargs.update(type_fn=None, focus_api=self.api,
                          input_api=self.input, clipboard=self.clip)
        kwargs.update(over)
        r = keshevctl.build_rig(**kwargs)
        self.addCleanup(r.close)
        self._rig = r
        return r

    # ------------------------------------------------------------ readers

    def typed(self) -> list[str]:
        """What actually reached the screen. With the real typer that is the
        clipboard the paste burst set (scar 31: paste-first, always)."""
        return list(self.clip.set_calls)

    def journal(self) -> list[dict]:
        path = self.tmp / "state" / "spool" / "journal.jsonl"
        if not path.is_file():
            return []
        return [json.loads(x) for x in
                path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def outcomes(self) -> list[str]:
        return [j["outcome"] for j in self.journal()]

    def ledger(self) -> list[dict]:
        path = self.tmp / "state" / "events.jsonl"
        if not path.is_file():
            return []
        return [json.loads(x) for x in
                path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def events(self) -> list[str]:
        return [e["evt"] for e in self.ledger()]

    def recovered(self) -> str:
        path = self.tmp / "state" / "recovered.txt"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    # ------------------------------------------------------------ asserts

    def assertNoDuplicates(self, rig, expected_n: int):
        """One utterance = one delivery. Checked from four independent
        places, because "typed twice" is the failure this repo exists for."""
        self.assertEqual(len(self.typed()), expected_n, self.typed())
        self.assertEqual(len(set(self.typed())), len(self.typed()),
                         f"the same text was typed twice: {self.typed()}")
        typed_ids = [j["id"] for j in self.journal() if j["outcome"] == "TYPED"]
        self.assertEqual(len(typed_ids), expected_n)
        self.assertEqual(len(set(typed_ids)), len(typed_ids),
                         f"an id was journaled TYPED twice: {typed_ids}")
        self.assertEqual(len(rig.app.router._typed), expected_n)
        self.assertNotIn("DUP_DISCARD", self.events())


# ------------------------------------------------------ the injection seam


class InjectionSeamTests(RigCase):
    """`keshevctl inject` is the seam the design named. It must reach the
    REAL assembly and touch no hardware doing it."""

    def test_the_rig_is_the_real_assembly_from_client_app(self):
        import client.app as app_mod
        from client.router import Router
        from client.segmenter import Segmenter
        from client.spool import Spool
        from client.typer import Typer

        r = self.rig(texts=["x"])
        self.assertIsInstance(r.app, app_mod.KeshevApp)
        self.assertIsInstance(r.app.router, Router)
        self.assertIsInstance(r.app.segmenter, Segmenter)
        self.assertIsInstance(r.app.spool, Spool)
        self.assertIsInstance(r.app.typer, Typer)

    def test_the_rig_runs_on_the_real_textguard_not_the_k12_placeholder(self):
        """If inject ran on router.default_guard the smoke path would be a
        lie: it would "prove" a pipeline that types hallucinations."""
        r = self.rig(texts=["x"])
        self.assertIs(r.app.router.guard_fn, textguard.guard)
        self.assertIsNot(r.app.router.guard_fn, router_mod.default_guard)

    def test_injection_enters_AFTER_the_capture_layer(self):
        """Design section 9: PCM goes in after capture. No stream is opened,
        no CapturePipeline exists, and the segmenter still receives audio."""
        r = self.rig(texts=["hello"])
        r.injector.feed_utterance(speech(1.5))
        self.assertIsNone(r.app.capture)
        self.assertIsNone(r.app.stream)
        self.assertEqual(r.app.state, "ASSEMBLED")
        self.assertEqual(r.app.segmenter.segments_enqueued, 1)

    def test_injection_never_enumerates_or_opens_an_audio_device(self):
        """The default device seam REFUSES, loudly. Anything that reached for
        a microphone during a headless inject run would raise here rather
        than quietly stealing Iddo's BRIO."""
        r = self.rig(texts=["hello"])
        r.injector.feed_utterance(speech(1.0))
        r.drain()
        self.assertEqual(self.typed(), ["hello"])
        with self.assertRaises(keshevctl.InjectionRefused):
            r.app.resolve_device()

    def test_keshevctl_has_no_audio_device_or_output_code_path(self):
        """Sacred Audio, structurally: the module cannot open a capture
        endpoint or an audio sink because it has no code that could.

        Two checks, because prose and code are different things: naming the
        layer this tool bypasses is GOOD documentation, importing it is the
        hazard. So the API-token check covers call sites only, and an AST
        pass covers imports.

        Every needle is assembled from pieces so THIS file does not itself
        contain the tokens lint gate G6 hunts for — the same discipline
        tools/lint.py uses in its own self-test."""
        call_tokens = ("Input" + "Stream", "Output" + "Stream",
                       "win" + "sound", "play" + "sound", "sd." + "play",
                       "query_devices", "check_input_settings")
        for needle in call_tokens:
            with self.subTest(token=needle):
                self.assertNotIn(needle, KESHEVCTL_SRC)

        audio_modules = {"sound" + "device", "pyaudio", "sd", "alsaaudio",
                         "win" + "sound", "simpleaudio", "pygame"}
        imported: list[str] = []
        for node in ast.walk(ast.parse(KESHEVCTL_SRC)):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            with self.subTest(imported=name):
                self.assertNotIn(name.split(".")[0], audio_modules)

    def test_keshevctl_never_touches_alma_mic(self):
        """Iddo's only working dictation app is not this program's business
        during an offline inject run."""
        for banned in ("mic-switch", "ALMA-MIC", "taskkill", "Stop-Process"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, KESHEVCTL_SRC)

    def test_the_decoder_seam_is_the_worker_duck_type_not_a_private_one(self):
        """The rig must accept ANY worker the router accepts. Driven here
        with tests/test_app.py's StubWorker, untouched — if inject only ever
        worked with its own decoder class, it would be testing itself."""
        worker = StubWorker([
            {"ok": True, "text": "foreign decoder", "lang": "en",
             "avg_logprob": -0.2}])
        r = self.rig(worker=worker)
        r.injector.feed_utterance(speech(1.0))
        r.drain()
        self.assertEqual(self.typed(), ["foreign decoder"])
        self.assertEqual([e for _, e in worker.calls], ["dgx"])

    def test_wav_injection_round_trips_through_the_whole_pipeline(self):
        wav = self.tmp / "utterance.wav"
        keshevctl.write_wav(wav, speech(1.5))
        r = self.rig(texts=["מהקובץ"])
        r.injector.feed_wav(wav)
        r.injector.feed_silence(0.8)
        r.drain()
        self.assertEqual(self.typed(), ["מהקובץ"])

    def test_a_wav_that_is_not_16k_mono_s16_is_refused_loudly(self):
        """The injector sits BELOW the resampler. Silently accepting 48k
        would shift every duration and every staleness decision."""
        wav = self.tmp / "wrong.wav"
        keshevctl.write_wav(wav, speech(0.5), rate=48000)
        r = self.rig(texts=["x"])
        with self.assertRaises(keshevctl.InjectionRefused) as ctx:
            r.injector.feed_wav(wav)
        self.assertIn("48000", str(ctx.exception))


# ------------------------------------------------------------- the smoke path


class SmokePathTests(RigCase):
    """The whole point: audio in, text out, in order, exactly once."""

    def test_synthetic_pcm_becomes_typed_text_in_order(self):
        r = self.rig(texts=["שלום עולם", "second utterance", "third one"])
        for _ in range(3):
            r.injector.feed_utterance(speech(1.2))
        self.assertEqual(r.app.spool.qsize(), 3)

        r.drain()

        self.assertEqual(self.typed(),
                         ["שלום עולם", "second utterance", "third one"])
        self.assertEqual(self.outcomes(), ["TYPED", "TYPED", "TYPED"])
        self.assertNoDuplicates(r, 3)

    def test_the_write_ahead_file_exists_before_anything_is_typed(self):
        """Structural move #2: the segment is on DISK before it is a queue
        record. A crash after this point loses nothing."""
        r = self.rig(texts=["on disk first"])
        r.injector.feed_utterance(speech(1.0))
        spool_dir = self.tmp / "state" / "spool"
        wavs = sorted(spool_dir.glob("*.wav"))
        self.assertEqual(len(wavs), 1)
        self.assertGreater(wavs[0].stat().st_size, 0)
        self.assertEqual(self.typed(), [])
        r.drain()
        self.assertEqual(self.typed(), ["on disk first"])

    def test_extra_router_steps_never_re_deliver_a_typed_utterance(self):
        """Idle ticks run the recovery drain. A typed segment's file is still
        on disk (1h retention) — it must not come back as recovered text."""
        r = self.rig(texts=["only once"])
        r.injector.feed_utterance(speech(1.0))
        r.drain()
        for _ in range(6):
            r.app.router.step()
        self.assertEqual(self.typed(), ["only once"])
        self.assertNotIn("only once", self.recovered())
        self.assertNoDuplicates(r, 1)

    def test_a_re_delivered_record_is_discarded_not_typed_twice(self):
        """The scar-53 defense, exercised end to end: the SAME segment handed
        to the router a second time must be journaled DUP_DISCARD and must
        never reach the screen. "Once" is asserted against a real attempt to
        deliver twice, not merely against a count that happened to be one."""
        r = self.rig(texts=["say it once"])
        r.injector.feed_utterance(speech(1.0))
        rec = r.app.spool.pop(timeout=0)
        r.app.spool.enqueue(rec)
        r.app.router.step()
        r.app.spool.enqueue(rec)               # the very same record again
        r.app.router.step()
        self.assertEqual(self.typed(), ["say it once"])
        self.assertEqual(self.outcomes(), ["TYPED", "DUP_DISCARD"])
        self.assertIn("DUP_DISCARD", self.events())

    def test_a_hallucination_is_dropped_by_the_guard_and_order_survives(self):
        r = self.rig(texts=["real one", "תודה רבה", "real two"])
        for _ in range(3):
            r.injector.feed_utterance(speech(1.0))
        r.drain()
        self.assertEqual(self.typed(), ["real one", "real two"])
        self.assertEqual(self.outcomes(), ["TYPED", "GUARD_DROP", "TYPED"])

    def test_the_pipeline_reports_honest_counts(self):
        r = self.rig(texts=["first line", "second line"])
        for _ in range(2):
            r.injector.feed_utterance(speech(1.0))
        r.drain()
        report = r.report()
        self.assertEqual(report["segments"], 2)
        self.assertEqual(report["typed"], 2)
        self.assertEqual(report["recovered"], 0)
        self.assertEqual(report["guard_drop"], 0)
        self.assertEqual(report["texts"], ["first line", "second line"])
        self.assertEqual(report["device_opens"], 0)
        self.assertGreater(report["audio_s"], 2.0)

    def test_ultra_short_decodes_never_reach_the_screen(self):
        """The real guard's ultra-short rule, seen from end to end: a
        one-character decode is a click or a cough, not a word."""
        r = self.rig(texts=["a", "genuine sentence"])
        for _ in range(2):
            r.injector.feed_utterance(speech(1.0))
        r.drain()
        self.assertEqual(self.typed(), ["genuine sentence"])
        self.assertEqual(self.outcomes(), ["GUARD_DROP", "TYPED"])


# -------------------------------------------------------------------- burst


class BurstTests(RigCase):
    """Criterion 21 / K12 row: an injected burst of 10 utterances in 30s —
    all 10 arrive, in order, zero dedup false-positives, zero stale diversion
    of LIVE speech."""

    def test_ten_utterances_in_thirty_seconds_arrive_in_order(self):
        texts = [f"utterance {i:02d}" for i in range(10)]
        r = self.rig(texts=texts)

        audio_s = 0.0
        for i in range(10):
            r.injector.feed_utterance(speech(2.0, phase=13 * i),
                                      tail_silence_ms=700)
            audio_s += 2.0 + 0.7
        self.assertLessEqual(audio_s, 30.0,
                             "the burst must fit inside 30s of audio")
        self.assertEqual(r.app.spool.qsize(), 10)

        r.drain()

        self.assertEqual(self.typed(), texts)
        self.assertEqual(self.outcomes(), ["TYPED"] * 10)
        self.assertNoDuplicates(r, 10)
        self.assertNotIn("STALE_DIVERT", self.events())
        self.assertEqual(self.recovered(), "",
                         "live speech was diverted to recovered.txt")

    def test_the_burst_ids_are_monotonic_and_wire_legal(self):
        from common import protocol

        r = self.rig(texts=[f"u{i}" for i in range(10)])
        for i in range(10):
            r.injector.feed_utterance(speech(0.8, phase=5 * i))
        ids = []
        while (rec := r.app.spool.pop(timeout=0)) is not None:
            ids.append(rec.id)
        self.assertEqual(len(ids), 10)
        self.assertEqual(ids, sorted(ids), "segment ids are out of order")
        for rid in ids:
            with self.subTest(rid=rid):
                self.assertTrue(protocol.valid_request_id(rid), rid)


# ------------------------------------------------------------------- run-on


class RunOnTests(RigCase):
    """Design section 2: "max 28s, split w/ 0.5s overlap". A 20-40s run-on
    must split, keep the boundary word twice, and still type in order."""

    def _run_on(self, seconds: float):
        r = self.rig(texts=["part one", "part two", "part three"])
        r.injector.feed_float32(speech(seconds))
        tail = r.injector.flush()
        return r, tail

    def test_a_forty_second_run_on_splits_at_28s(self):
        r, _ = self._run_on(40.0)
        recs = r.injector.records
        self.assertEqual(len(recs), 2, [x.duration_ms for x in recs])
        first_ms = recs[0].duration_ms
        # one 30ms frame of slack: the split fires on the frame that WOULD
        # cross 28s, so the closed segment is 28s minus at most one frame.
        self.assertLessEqual(first_ms, MAX_SEGMENT_S * 1000)
        self.assertGreater(first_ms, MAX_SEGMENT_S * 1000 - 31)

    def test_the_split_carries_a_half_second_overlap_byte_for_byte(self):
        """Not "an overlap was intended" — the stored audio proves it. The
        last 0.5s of segment 1's PCM must BE the first 0.5s of segment 2's."""
        r, _ = self._run_on(40.0)
        first, second = r.injector.records
        overlap_bytes = int(SPLIT_OVERLAP_S * SR) * 2      # s16le
        head = second.read_pcm()[:overlap_bytes]
        tail = first.read_pcm()[-overlap_bytes:]
        self.assertEqual(len(head), overlap_bytes)
        self.assertEqual(head, tail,
                         "the 0.5s split overlap is missing — a word on the "
                         "28s boundary is lost")

    def test_a_run_on_still_types_in_order(self):
        r, _ = self._run_on(40.0)
        r.drain()
        self.assertEqual(self.typed(), ["part one", "part two"])
        self.assertEqual(self.outcomes(), ["TYPED", "TYPED"])
        self.assertNoDuplicates(r, 2)

    def test_a_twenty_second_run_on_does_not_split(self):
        """The lower end of the design's 20-40s band: one segment, one type."""
        r, _ = self._run_on(20.0)
        self.assertEqual(len(r.injector.records), 1)
        r.drain()
        self.assertEqual(self.typed(), ["part one"])


# -------------------------------------------------------------------- stale


class StaleBacklogTests(RigCase):
    """Scar 16 / design section 4.1: the ONE fresh/stale gate. A segment
    older than stale_sec is still DECODED — Iddo never loses a word — but it
    lands in recovered.txt and never in whatever window has focus now."""

    def test_a_stale_segment_goes_to_recovered_and_never_to_the_typer(self):
        r = self.rig(texts=["minutes old"])
        r.injector.feed_utterance(speech(1.0))
        aged = r.injector.age_queued(30.0)      # > stale_sec (25)
        self.assertEqual(aged, 1)

        r.drain()

        self.assertEqual(self.typed(), [],
                         "stale text was typed into live focus (scar 16)")
        self.assertIn("minutes old", self.recovered())
        self.assertEqual(self.outcomes(), ["RECOVERED"])
        self.assertIn("STALE_DIVERT", self.events())

    def test_stale_diversion_uses_the_configured_threshold_not_a_guess(self):
        """24s is fresh, 26s is stale, with stale_sec=25 — the boundary the
        config actually carries."""
        for age, expect_typed in ((24.0, True), (26.0, False)):
            with self.subTest(age=age):
                self.setUp()
                r = self.rig(texts=["boundary"], cfg=make_cfg(stale_sec=25))
                r.injector.feed_utterance(speech(1.0))
                r.injector.age_queued(age)
                r.drain()
                if expect_typed:
                    self.assertEqual(self.typed(), ["boundary"])
                    self.assertEqual(self.recovered(), "")
                else:
                    self.assertEqual(self.typed(), [])
                    self.assertIn("boundary", self.recovered())

    def test_fresh_speech_still_types_while_stale_backlog_is_diverted(self):
        """The mixed case that matters after a laptop wakes up: old backlog
        must not push its way onto the screen ahead of live dictation."""
        r = self.rig(texts=["old backlog", "live speech"])
        r.injector.feed_utterance(speech(1.0))
        r.injector.age_queued(45.0)
        r.injector.feed_utterance(speech(1.0))     # fresh, enqueued after

        r.drain()

        self.assertEqual(self.typed(), ["live speech"])
        self.assertIn("old backlog", self.recovered())
        self.assertNotIn("live speech", self.recovered())
        self.assertEqual(self.outcomes(), ["RECOVERED", "TYPED"])


# ------------------------------------------------------- the program, running


class ThreadedProgramTests(RigCase):
    """The synchronous tests above drive router.step() by hand. This one
    starts the REAL threads — worker, focus watcher, capture pump, device
    supervisor, router — over a fake device, injects, and waits for text.
    This is the honest answer to "is it a program yet"."""

    def test_the_started_program_carries_injected_speech_to_the_typer(self):
        spies = DeviceSpies(devices=(BRIO, XM4))
        r = self.rig(texts=["threaded one", "threaded two"],
                     enumerate_fn=spies.enumerate_fn,
                     native_format_fn=spies.native_format_fn,
                     check_format_fn=spies.check_format_fn,
                     open_stream_fn=spies.open_stream_fn,
                     set_priority_fn=lambda: 1)
        before = threading.active_count()
        r.app.start()
        try:
            self.assertEqual(r.app.state, "CAPTURING")
            self.assertEqual(spies.opens, [(BRIO.index, 16000, 1)],
                             "the forbidden headset was opened")
            r.injector.feed_utterance(speech(1.0))
            r.injector.feed_utterance(speech(1.0))
            deadline = time.monotonic() + 15.0
            while len(self.typed()) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
        finally:
            r.app.shutdown()

        self.assertEqual(self.typed(), ["threaded one", "threaded two"])
        self.assertNoDuplicates(r, 2)
        # the counter reports opens that SUCCEEDED — here, exactly the one
        # fake stream; in every other test in this file, zero.
        self.assertEqual(r.report()["device_opens"], 1)
        deadline = time.monotonic() + 5.0
        while threading.active_count() > before and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(threading.active_count(), before,
                         [t.name for t in threading.enumerate()])


# ---------------------------------------------------------------------- CLI


class InjectCliTests(RigCase):
    """`python -m tools.keshevctl inject ...` — the operator-facing door.
    Prints one JSON report; never types onto the real screen by default."""

    def _run(self, argv) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = keshevctl.main(argv)
        out = buf.getvalue()
        try:
            return code, json.loads(out)
        except json.JSONDecodeError:
            return code, {"_raw": out}

    def test_inject_tone_reports_typed_text(self):
        code, rep = self._run([
            "inject", "--tone", "3", "--seconds", "1.0",
            "--state-dir", str(self.tmp / "state"), "--text", "canary alpha"])
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["segments"], 3)
        self.assertEqual(rep["typed"], 3)
        self.assertEqual(rep["texts"], ["canary alpha"] * 3)
        self.assertEqual(rep["device_opens"], 0)

    def test_inject_writes_the_transcript_where_it_says_it_did(self):
        out = self.tmp / "typed.txt"
        code, rep = self._run([
            "inject", "--tone", "2", "--seconds", "1.0",
            "--state-dir", str(self.tmp / "state"),
            "--transcript", str(out), "--text", "written down"])
        self.assertEqual(code, 0, rep)
        self.assertEqual(out.read_text(encoding="utf-8").splitlines(),
                         ["written down", "written down"])

    def test_inject_refuses_the_live_typer_without_the_explicit_gate(self):
        """--typer live drives real SendInput into whatever window has focus.
        It must be impossible to reach it by accident while Iddo is working."""
        code, rep = self._run([
            "inject", "--tone", "1", "--seconds", "0.5", "--typer", "live",
            "--state-dir", str(self.tmp / "state")])
        self.assertEqual(code, keshevctl.EXIT_REFUSED, rep)
        self.assertIn("KESHEV_INJECT_LIVE_TYPER", rep["error"])
        self.assertFalse((self.tmp / "state").exists(),
                         "a refused run still built state on disk")

    def test_inject_exits_nonzero_when_nothing_is_delivered(self):
        """A smoke run that delivers to NEITHER destination is a FAILED smoke
        run, and the exit code has to say so — a green log line is not a
        working microphone."""
        code, rep = self._run([
            "inject", "--tone", "2", "--seconds", "1.0",
            "--state-dir", str(self.tmp / "state"), "--text", "תודה רבה"])
        self.assertEqual(rep["typed"], 0)
        self.assertEqual(rep["recovered"], 0)
        self.assertEqual(rep["guard_drop"], 2)
        self.assertEqual(code, keshevctl.EXIT_NOTHING_DELIVERED)

    def test_a_recovered_only_run_is_not_called_a_failure(self):
        """--stale-age drills the scar-16 lane on purpose: nothing is typed
        and that is the CORRECT outcome. Design section 9 counts silent drops
        across BOTH destinations, so recovered text is delivered text."""
        code, rep = self._run([
            "inject", "--tone", "1", "--seconds", "1.0", "--stale-age", "40",
            "--state-dir", str(self.tmp / "state"), "--text", "backlog line"])
        self.assertEqual(rep["typed"], 0)
        self.assertEqual(rep["recovered"], 1)
        self.assertEqual(code, keshevctl.EXIT_OK)


class CliSubprocessTests(RigCase):
    """The in-process tests above capture stdout into a StringIO, which has no
    encoding and therefore cannot see an encoding bug. These run the CLI the
    way an operator does — a real process, a real pipe, a real console
    codec — because Hebrew IS the primary language of this microphone."""

    def _spawn(self, argv, encoding="cp1252"):
        import subprocess
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = encoding      # force the Windows console codec
        proc = subprocess.run([sys.executable, "-m", "tools.keshevctl"] + argv,
                              cwd=str(REPO), capture_output=True, env=env,
                              timeout=180)
        return proc

    def test_a_hebrew_report_survives_a_cp1252_console(self):
        proc = self._spawn([
            "inject", "--tone", "2", "--seconds", "1.0",
            "--state-dir", str(self.tmp / "state"), "--text", "שלום עולם"])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        report = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(report["typed"], 2)
        self.assertEqual(report["texts"], ["שלום עולם", "שלום עולם"])

    def test_the_transcript_file_is_utf8_regardless_of_the_console(self):
        out = self.tmp / "typed.txt"
        proc = self._spawn([
            "inject", "--tone", "1", "--seconds", "1.0",
            "--state-dir", str(self.tmp / "state"),
            "--transcript", str(out), "--text", "עברית בקובץ"])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(out.read_text(encoding="utf-8").strip(), "עברית בקובץ")


if __name__ == "__main__":
    unittest.main()
