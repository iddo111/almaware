"""K9 TDD tests — client/keshev_worker.py (PHASE2-DESIGN.md sections 3.2, 4.3, 7).

The killable subprocess, tested IN-PROCESS here (WorkerMain against BytesIO
pipes + the fake engine module). Real-subprocess behavior (real pipes, real
TerminateProcess) lives in test_worker_integration.py.

Laws under test:

  scar 11   "ready" is emitted only AFTER a real dummy inference validates
            the engine (warm() before the ready frame, warm() before any
            decode).
  scar 14   WARMING begins with a free-VRAM probe; short headroom steps
            down the pinned ladder with a VRAM_DEGRADE event; below the
            bottom rung the worker loads NOTHING and reports
            READY(LOCAL_UNAVAILABLE) — graceful, never an OOM attempt.
  scar 47   No torch import, and NO CPU code path: the string "cpu" does
            not exist as a constant anywhere in the module (structural).
  section 3.2  Every reply frame carries the worker's spawn generation.

The engine is injected by dotted-module spec (`fake:tests.fake_worker_engine`)
— the same spec mechanism the replay rig uses; behavior triggers ride in the
PCM payload so the worker itself has zero test-only branches.
"""
from __future__ import annotations

import ast
import io
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from common.protocol import pack_frame, read_frame  # noqa: E402
from client.keshev_worker import (  # noqa: E402
    LADDER,
    VRAM_MARGIN_MB,
    VRAM_NEED_MB,
    VramProbeError,
    WorkerMain,
    choose_model,
    parse_free_vram_mb,
)

FAKE = "fake:tests.fake_worker_engine"


def write_frame(stream, header: dict, payload: bytes = b"") -> None:
    stream.write(pack_frame(header, payload))


def run_worker(cmds: list[tuple[dict, bytes]], *, gen: int = 1,
               free_mb: int = 8000, model: str | None = None,
               ladder=None, need_mb=None, server_url: str | None = None):
    """Drive WorkerMain over BytesIO pipes; return (exit_code, frames, worker)."""
    stdin = io.BytesIO()
    for header, payload in cmds:
        header.setdefault("gen", gen)
        write_frame(stdin, header, payload)
    stdin.seek(0)
    stdout = io.BytesIO()
    worker = WorkerMain(
        gen=gen,
        model=model or LADDER[0],
        engine_spec=FAKE,
        free_vram_mb_fn=lambda: free_mb,
        stdin=stdin,
        stdout=stdout,
        server_url=server_url,
        ladder=ladder,
        need_mb=need_mb,
    )
    rc = worker.run()
    stdout.seek(0)
    frames = []
    while (fr := read_frame(stdout)) is not None:
        frames.append(fr[0])
    return rc, frames, worker


class TestVramLadder(unittest.TestCase):
    """scar 14 — every rung, boundary-exact, zero OOM attempts."""

    def test_ladder_and_needs_are_pinned(self):
        self.assertGreaterEqual(len(LADDER), 2)
        self.assertEqual(VRAM_MARGIN_MB, 512)
        for name in LADDER:
            self.assertIn(name, VRAM_NEED_MB)
            self.assertGreater(VRAM_NEED_MB[name], 0)
        # ladder is strictly shrinking — a degrade never grows the model
        needs = [VRAM_NEED_MB[n] for n in LADDER]
        self.assertEqual(needs, sorted(needs, reverse=True))

    def test_enough_headroom_keeps_configured(self):
        top = LADDER[0]
        chosen, evt = choose_model(top, VRAM_NEED_MB[top] + VRAM_MARGIN_MB)
        self.assertEqual(chosen, top)
        self.assertIsNone(evt)

    def test_one_mb_short_degrades_one_rung(self):
        top, second = LADDER[0], LADDER[1]
        free = VRAM_NEED_MB[top] + VRAM_MARGIN_MB - 1
        self.assertGreaterEqual(free, VRAM_NEED_MB[second] + VRAM_MARGIN_MB)
        chosen, evt = choose_model(top, free)
        self.assertEqual(chosen, second)
        self.assertEqual((evt["want"], evt["got"], evt["free_mb"]),
                         (top, second, free))

    def test_fits_only_bottom_rung(self):
        bottom = LADDER[-1]
        free = VRAM_NEED_MB[bottom] + VRAM_MARGIN_MB
        chosen, evt = choose_model(LADDER[0], free)
        self.assertEqual(chosen, bottom)
        self.assertEqual(evt["want"], LADDER[0])

    def test_below_bottom_rung_is_local_unavailable(self):
        chosen, evt = choose_model(LADDER[0], VRAM_NEED_MB[LADDER[-1]] + VRAM_MARGIN_MB - 1)
        self.assertIsNone(chosen)
        self.assertIsNone(evt)

    def test_configured_mid_ladder_never_upgrades(self):
        if len(LADDER) < 2:
            self.skipTest("ladder too short")
        chosen, _ = choose_model(LADDER[1], 10 ** 6)
        self.assertEqual(chosen, LADDER[1])

    def test_unknown_configured_model_refused(self):
        with self.assertRaises(ValueError):
            choose_model("no-such-model", 10 ** 6)


class TestVramProbeParse(unittest.TestCase):
    def test_single_gpu(self):
        self.assertEqual(parse_free_vram_mb("2466\n"), 2466)

    def test_multi_gpu_takes_device_zero(self):
        self.assertEqual(parse_free_vram_mb("2466\n1024\n"), 2466)

    def test_garbage_is_loud(self):
        for bad in ("", "no devices found", "NaN\n"):
            with self.assertRaises(VramProbeError):
                parse_free_vram_mb(bad)


class TestStartupSequence(unittest.TestCase):
    def test_loading_then_ready_and_warm_before_ready(self):
        rc, frames, worker = run_worker([({"cmd": "shutdown"}, b"")])
        self.assertEqual(rc, 0)
        self.assertEqual(frames[0]["event"], "loading")
        ready = frames[1]
        self.assertEqual(ready["event"], "ready")
        self.assertEqual(ready["local_state"], "READY")
        self.assertEqual(ready["model"], LADDER[0])
        self.assertEqual(ready["vram_mb"], 7)          # fake engine's figure
        # scar 11: the engine was actually warmed (real dummy inference slot)
        self.assertTrue(worker.engine.warm_called)
        # and the worker recorded that warm preceded the ready write
        self.assertTrue(worker.warm_before_ready)

    def test_every_frame_carries_spawn_gen(self):
        rc, frames, _ = run_worker([({"cmd": "ping"}, b""), ({"cmd": "shutdown"}, b"")], gen=42)
        self.assertTrue(frames)
        for fr in frames:
            self.assertEqual(fr["gen"], 42)

    def test_degrade_emits_vram_degrade_frame(self):
        top, second = LADDER[0], LADDER[1]
        free = VRAM_NEED_MB[top] + VRAM_MARGIN_MB - 1
        rc, frames, _ = run_worker([({"cmd": "shutdown"}, b"")], free_mb=free)
        events = [f["event"] for f in frames]
        self.assertIn("vram_degrade", events)
        deg = frames[events.index("vram_degrade")]
        self.assertEqual((deg["want"], deg["got"]), (top, second))
        ready = frames[events.index("ready")]
        self.assertEqual(ready["model"], second)

    def test_no_headroom_is_ready_local_unavailable(self):
        rc, frames, worker = run_worker(
            [({"cmd": "decode", "id": "a-000001", "engine": "local"}, b"pcm"),
             ({"cmd": "shutdown"}, b"")],
            free_mb=1,
        )
        self.assertEqual(rc, 0)
        ready = [f for f in frames if f.get("event") == "ready"][0]
        self.assertEqual(ready["local_state"], "LOCAL_UNAVAILABLE")
        self.assertIsNone(worker.engine)               # loaded NOTHING
        reply = [f for f in frames if f.get("id") == "a-000001"][0]
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["err"], "local_unavailable")

    def test_engine_warm_failure_is_fatal_not_silent(self):
        rc, frames, _ = run_worker(
            [], model="warmfail",
            ladder=("warmfail",), need_mb={"warmfail": 1},
        )
        self.assertEqual(rc, 13)
        self.assertEqual(frames[-1]["event"], "fatal")

    def test_vram_probe_failure_is_fatal(self):
        stdout = io.BytesIO()
        def boom():
            raise VramProbeError("nvidia-smi absent")
        worker = WorkerMain(gen=1, model=LADDER[0], engine_spec=FAKE,
                            free_vram_mb_fn=boom, stdin=io.BytesIO(), stdout=stdout)
        self.assertEqual(worker.run(), 13)


class TestCommands(unittest.TestCase):
    def test_local_decode_happy_path(self):
        rc, frames, _ = run_worker(
            [({"cmd": "decode", "id": "s-000001", "engine": "local",
               "lang_hint": "auto"}, b"\x00\x01" * 800),
             ({"cmd": "shutdown"}, b"")])
        reply = [f for f in frames if f.get("id") == "s-000001"][0]
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["engine"], "local")
        self.assertEqual(reply["text"], "שלום עולם")
        self.assertEqual(reply["lang"], "he")
        self.assertIn("decode_ms", reply)
        self.assertIn("avg_logprob", reply)
        self.assertIn("no_speech_prob", reply)

    def test_engine_exception_is_error_reply_not_crash(self):
        rc, frames, _ = run_worker(
            [({"cmd": "decode", "id": "s-000002", "engine": "local"}, b"BOOM"),
             ({"cmd": "ping"}, b""),
             ({"cmd": "shutdown"}, b"")])
        self.assertEqual(rc, 0)
        reply = [f for f in frames if f.get("id") == "s-000002"][0]
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["err"], "engine_error")
        # worker survived: the ping after the failure was answered
        self.assertTrue(any(f.get("event") == "pong" for f in frames))

    def test_ping_pong_carries_rss(self):
        rc, frames, _ = run_worker([({"cmd": "ping"}, b""), ({"cmd": "shutdown"}, b"")])
        pong = [f for f in frames if f.get("event") == "pong"][0]
        self.assertIsInstance(pong["rss_mb"], int)
        # a live python process is never 0MB — a -1 here means the psapi
        # probe regressed (the 64-bit HANDLE truncation found at K9)
        self.assertGreater(pong["rss_mb"], 0)

    def test_dgx_unconfigured_is_clean_error(self):
        rc, frames, _ = run_worker(
            [({"cmd": "decode", "id": "s-000003", "engine": "dgx"}, b"pcm"),
             ({"cmd": "probe"}, b""),
             ({"cmd": "shutdown"}, b"")])
        reply = [f for f in frames if f.get("id") == "s-000003"][0]
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["err"], "dgx_unconfigured")
        probe = [f for f in frames if f.get("event") == "probe_result"][0]
        self.assertEqual(probe["state"], "UNKNOWN")

    def test_unknown_cmd_is_error_frame_not_crash(self):
        rc, frames, _ = run_worker(
            [({"cmd": "frobnicate"}, b""), ({"cmd": "shutdown"}, b"")])
        self.assertEqual(rc, 0)
        self.assertTrue(any(f.get("event") == "error"
                            and f.get("err") == "unknown_cmd" for f in frames))

    def test_eof_without_shutdown_exits_zero(self):
        """Parent death closes the pipe — the orphan leaves quietly."""
        rc, frames, _ = run_worker([])
        self.assertEqual(rc, 0)


class TestStructuralNoCpuNoTorch(unittest.TestCase):
    """scar 47 — CPU decode is UNREPRESENTED; torch does not exist here.
    (The lint G5 gate also covers torch; this pins the module even if the
    gate's scope ever changes.)"""

    def setUp(self):
        src = (REPO / "client" / "keshev_worker.py").read_text(encoding="utf-8")
        self.tree = ast.parse(src)

    def test_no_torch_import(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertFalse(a.name.split(".")[0] == "torch", a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(node.module.split(".")[0] == "torch", node.module)

    def test_no_cpu_string_constant(self):
        cpus = [n for n in ast.walk(self.tree)
                if isinstance(n, ast.Constant) and n.value == "cpu"]
        self.assertEqual(cpus, [], "a 'cpu' literal is a CPU code path (scar 47)")

    def test_cuda_literal_exists_cpu_does_not(self):
        literals = {n.value for n in ast.walk(self.tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn("cuda", literals)
        self.assertNotIn("cpu", literals)


if __name__ == "__main__":
    unittest.main(verbosity=2)
