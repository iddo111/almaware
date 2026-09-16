"""K9 integration tests — REAL keshev_worker subprocess under worker_mgr.

Real python child processes, real OS pipes, real TerminateProcess. The
engine is the fake module (`fake:tests.fake_worker_engine`) — the GPU is
shared 8GB and the live crutch mic holds ~2.6GB of it (wave guardrail), so
no CUDA is touched here. The REAL model-load + kill + nvidia-smi VRAM-delta
measurement is performed once, out-of-band, by tools/measure_k9_model.py
and recorded in state/reports (see the K9 RAMCHAT post).

Proven here:

  * the frame protocol survives real pipes end to end (loading -> ready ->
    decode reply, UTF-8 Hebrew intact);
  * "ready" arrives only after warm (scar 11 ordering, real process);
  * a stuck decode is REALLY killed (TerminateProcess), wait()ed, VRAM-delta
    asserted (stub reader), respawned with a bumped generation, and the next
    decode works (criterion 2's local choreography);
  * a worker spawned with --gen N stamps N on every frame it emits;
  * shutdown cmd -> clean exit 0.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.telemetry import Telemetry  # noqa: E402
from client.worker_mgr import WorkerManager  # noqa: E402
from common.protocol import pack_frame, read_frame  # noqa: E402


def write_frame(stream, header: dict, payload: bytes = b"") -> None:
    stream.write(pack_frame(header, payload))

FAKE = "fake:tests.fake_worker_engine"
MODEL = "base"  # any ladder rung; the fake engine ignores size


def worker_cmd(gen: int) -> list[str]:
    return [sys.executable, "-u", "-m", "client.keshev_worker",
            "--gen", str(gen), "--engine", FAKE, "--model", MODEL,
            "--free-vram-mb", "8000"]


def spawn_real(gen: int) -> subprocess.Popen:
    return subprocess.Popen(
        worker_cmd(gen), cwd=str(REPO), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class TestBareWorkerProcess(unittest.TestCase):
    """Direct Popen, no manager — the wire law on real pipes."""

    def test_startup_sequence_decode_and_clean_shutdown(self):
        proc = spawn_real(7)
        try:
            frames = []
            for _ in range(2):
                fr = read_frame(proc.stdout)
                self.assertIsNotNone(fr, "worker closed pipe before ready")
                frames.append(fr[0])
            self.assertEqual([f["event"] for f in frames], ["loading", "ready"])
            self.assertEqual(frames[1]["local_state"], "READY")
            for f in frames:
                self.assertEqual(f["gen"], 7)          # spawn gen stamped

            write_frame(proc.stdin, {"gen": 7, "cmd": "decode",
                                     "id": "r-000001", "engine": "local",
                                     "lang_hint": "auto"}, b"\x01\x00" * 800)
            proc.stdin.flush()
            header, _ = read_frame(proc.stdout)
            self.assertEqual(header["id"], "r-000001")
            self.assertTrue(header["ok"])
            self.assertEqual(header["text"], "שלום עולם")   # UTF-8 survived
            self.assertEqual(header["gen"], 7)

            write_frame(proc.stdin, {"gen": 7, "cmd": "shutdown"})
            proc.stdin.flush()
            self.assertEqual(proc.wait(timeout=15), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


class TestManagedRealWorker(unittest.TestCase):
    def _harness(self, td, vram_seq):
        telemetry = Telemetry(td, session_id="k9int")
        vram_iter = iter(vram_seq)
        last = [vram_seq[0]]

        def vram_free_fn():
            try:
                last[0] = next(vram_iter)
            except StopIteration:
                last[0] = vram_seq[-1]
            return last[0]

        mgr = WorkerManager(
            telemetry, spawn_real, vram_free_fn=vram_free_fn,
            local_deadline_s=1.0, kill_grace_s=0.2, warm_timeout_s=30.0,
            ping_timeout_s=5.0, vram_wait_s=1.0)
        return telemetry, mgr

    def test_decode_roundtrip_through_manager(self):
        with TemporaryDirectory() as td:
            telemetry, mgr = self._harness(td, [2400])
            try:
                mgr.start()
                self.assertEqual(mgr.state, "READY")
                res = mgr.decode("m-000001", b"\x01\x00" * 1600, engine="local")
                self.assertTrue(res["ok"])
                self.assertEqual(res["text"], "שלום עולם")
                self.assertTrue(mgr.ping())
            finally:
                mgr.stop()
                telemetry.close()

    def test_probe_through_real_worker_dgx_unconfigured(self):
        """K12 wiring proof on real pipes: cmd=probe -> probe_result. This
        worker has no --server-url, so the honest answer is unhealthy with
        the dgx_unconfigured reason — never a raise, never a kill."""
        with TemporaryDirectory() as td:
            telemetry, mgr = self._harness(td, [2400])
            try:
                mgr.start()
                p = mgr.probe()
                self.assertFalse(p["healthy"])
                self.assertEqual(p["state"], "UNKNOWN")
                self.assertIn("dgx_unconfigured", p["reason"])
                self.assertEqual(mgr.state, "READY")   # probe is not a kill
            finally:
                mgr.stop()
                telemetry.close()

    def test_stuck_decode_real_kill_real_respawn(self):
        """Criterion 2 (local choreography): 1s-deadline decode of a HANG
        payload -> the REAL child is terminated, wait()ed, VRAM delta
        asserted, a NEW child spawned with gen 2, and decoding resumes."""
        with TemporaryDirectory() as td:
            telemetry, mgr = self._harness(td, [1000, 1010])
            first_pid = None
            try:
                mgr.start()
                first_pid = mgr.proc.pid
                res = mgr.decode("m-000002", b"HANG" + b"\x00" * 100, engine="local")
                self.assertFalse(res["ok"])
                self.assertEqual(res["err"], "timeout")
                self.assertEqual(mgr.gen, 2)
                self.assertEqual(mgr.state, "READY")
                self.assertNotEqual(mgr.proc.pid, first_pid)
                res2 = mgr.decode("m-000003", b"\x01\x00" * 800, engine="local")
                self.assertTrue(res2["ok"])
            finally:
                mgr.stop()
                telemetry.close()
            evts = [json.loads(l) for l in
                    (Path(td) / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            kills = [e for e in evts if e["evt"] == "WORKER_KILL"]
            self.assertEqual(len(kills), 1)
            self.assertEqual(kills[0]["reason"], "decode_timeout")
            self.assertEqual(kills[0]["vram_before"], 1000)
            self.assertEqual(kills[0]["vram_after"], 1010)
            self.assertTrue(any(e["evt"] == "WORKER_RESPAWN" for e in evts))

    def test_graceful_restart_real_process(self):
        with TemporaryDirectory() as td:
            telemetry, mgr = self._harness(td, [2400])
            try:
                mgr.start()
                pid1 = mgr.proc.pid
                mgr.restart_graceful()
                self.assertEqual(mgr.state, "READY")
                self.assertNotEqual(mgr.proc.pid, pid1)
                res = mgr.decode("m-000004", b"\x01\x00" * 800, engine="local")
                self.assertTrue(res["ok"])
            finally:
                mgr.stop()
                telemetry.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
