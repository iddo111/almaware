"""K16 / Gate 17 — the loaded-fleet latency harness (PHASE2-DESIGN.md sec 9).

The gate itself is a LIVE measurement against eran1 under real Qwen load, and
a live measurement cannot be unit-tested. What CAN be pinned — and what this
file pins, before tools/measure_gates.py exists — is everything that decides
whether the live numbers mean anything:

  the arithmetic   p50/p95 by nearest rank, defined once, no interpolation
                   surprises hiding a bad tail.
  the verdict      PASS is p95 <= 3000ms AND p50 <= 1500ms. Nothing else.
  the INVALID rule the design's own sentence: "An idle-fleet number is
                   auto-marked INVALID". A harness that could report PASS on
                   an idle machine is a harness that measures nothing, so the
                   idle case is a test, not a comment.
  the stopwatch    t0 = segment close (SpoolRecord.t_end), t1 = the instant
                   the typer call RETURNS. Not decode_ms — decode_ms is the
                   server's own number and it cannot see the queue, the
                   guard, or the typer. The ledger is proven against a fake
                   clock so the two stamps are unambiguous.
  the wiring       the ledger must hang off the PRODUCTION seams of the real
                   assembled client (Router.type_fn, Spool.pop), never a
                   parallel copy of the pipeline. A latency measured beside
                   the program is not the program's latency.

No fleet, no network, no device, no audio: every test here runs offline.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import measure_gates  # noqa: E402


LOADED = {"slots_busy_pct": 100.0, "eran1_load": 6.4, "n_samples": 18}
IDLE = {"slots_busy_pct": 0.0, "eran1_load": 0.14, "n_samples": 18}


# ---------------------------------------------------------------- arithmetic

class Percentiles(unittest.TestCase):
    def test_nearest_rank_on_a_known_ladder(self):
        vals = [float(i) for i in range(1, 101)]
        self.assertEqual(measure_gates.percentile(vals, 50), 50.0)
        self.assertEqual(measure_gates.percentile(vals, 95), 95.0)
        self.assertEqual(measure_gates.percentile(vals, 100), 100.0)

    def test_unsorted_input_is_sorted_first(self):
        self.assertEqual(measure_gates.percentile([30.0, 10.0, 20.0], 50), 20.0)

    def test_single_sample(self):
        self.assertEqual(measure_gates.percentile([7.0], 95), 7.0)

    def test_empty_refuses_rather_than_inventing_zero(self):
        with self.assertRaises(ValueError):
            measure_gates.percentile([], 50)


# ------------------------------------------------------------------ verdict

class Verdict(unittest.TestCase):
    def test_pass_needs_both_bars(self):
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=900.0, p95_ms=2400.0,
                                  load_proof=LOADED), "PASS")

    def test_p95_over_bar_fails(self):
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=900.0, p95_ms=3000.1,
                                  load_proof=LOADED), "FAIL")

    def test_p50_over_bar_fails_even_with_a_good_tail(self):
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=1500.1, p95_ms=1600.0,
                                  load_proof=LOADED), "FAIL")

    def test_the_bars_are_inclusive(self):
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=1500.0, p95_ms=3000.0,
                                  load_proof=LOADED), "PASS")

    def test_idle_fleet_is_INVALID_even_when_the_latency_is_excellent(self):
        # PHASE2-DESIGN sec 9: "An idle-fleet number is auto-marked INVALID."
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=300.0, p95_ms=500.0,
                                  load_proof=IDLE), "INVALID")

    def test_missing_load_proof_is_INVALID(self):
        self.assertEqual(
            measure_gates.verdict(n=200, p50_ms=300.0, p95_ms=500.0,
                                  load_proof={"slots_busy_pct": 100.0,
                                              "eran1_load": 6.4,
                                              "n_samples": 0}), "INVALID")

    def test_zero_utterances_is_INVALID_not_PASS(self):
        self.assertEqual(
            measure_gates.verdict(n=0, p50_ms=0.0, p95_ms=0.0,
                                  load_proof=LOADED), "INVALID")


# ------------------------------------------------------------------- report

class ReportShape(unittest.TestCase):
    def test_report_carries_exactly_the_keys_the_design_names(self):
        rep = measure_gates.build_report([1000.0, 2000.0, 3000.0], LOADED)
        for key in ("n", "p50_ms", "p95_ms", "load_proof", "verdict"):
            self.assertIn(key, rep)
        self.assertEqual(rep["n"], 3)
        self.assertIn("slots_busy_pct", rep["load_proof"])
        self.assertIn("eran1_load", rep["load_proof"])

    def test_report_is_json_serialisable(self):
        rep = measure_gates.build_report([1000.0, 2000.0], LOADED)
        json.loads(json.dumps(rep, ensure_ascii=False))

    def test_report_of_nothing_says_INVALID_and_reports_n_zero(self):
        rep = measure_gates.build_report([], LOADED)
        self.assertEqual(rep["n"], 0)
        self.assertEqual(rep["verdict"], "INVALID")


# ---------------------------------------------------------------- stopwatch

class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeRec:
    def __init__(self, rec_id: str, t_end: float):
        self.id = rec_id
        self.t_end = t_end


class Ledger(unittest.TestCase):
    def test_latency_is_segment_close_to_typer_return(self):
        clock = FakeClock(1000.0)
        led = measure_gates.LatencyLedger(clock=clock)
        led.on_pop(FakeRec("seg-1", t_end=1000.0))
        clock.t = 1001.25                       # typer returns 1.25s later
        led.on_typed()
        self.assertEqual(led.latencies_ms, [1250.0])

    def test_a_record_that_never_types_contributes_no_number(self):
        clock = FakeClock(1000.0)
        led = measure_gates.LatencyLedger(clock=clock)
        led.on_pop(FakeRec("seg-1", t_end=1000.0))   # guard-dropped, say
        led.on_pop(FakeRec("seg-2", t_end=1002.0))
        clock.t = 1003.0
        led.on_typed()
        self.assertEqual(led.latencies_ms, [1000.0])
        self.assertEqual(led.popped, 2)
        self.assertEqual(led.typed, 1)

    def test_an_idle_pop_does_not_break_the_pairing(self):
        # Router.step() pops None on every idle tick; the ledger must not
        # attribute the next typed text to a phantom record.
        clock = FakeClock(1000.0)
        led = measure_gates.LatencyLedger(clock=clock)
        led.on_pop(None)
        led.on_pop(FakeRec("seg-1", t_end=1000.0))
        clock.t = 1000.4
        led.on_typed()
        self.assertEqual(len(led.latencies_ms), 1)
        self.assertAlmostEqual(led.latencies_ms[0], 400.0, places=6)


# ------------------------------------------------------------------- wiring

class Wiring(unittest.TestCase):
    """The ledger must ride the real client's own seams."""

    def test_instrument_replaces_the_production_router_typer_and_spool_pop(self):
        import keshevctl

        with tempfile.TemporaryDirectory() as td:
            rig = keshevctl.build_rig(state_dir=td, texts=["שלום עולם"])
            try:
                before_type = rig.app.router.type_fn
                before_pop = rig.app.spool.pop
                led = measure_gates.instrument(rig)
                self.assertIsNot(rig.app.router.type_fn, before_type)
                self.assertIsNot(rig.app.spool.pop, before_pop)
                self.assertIsInstance(led, measure_gates.LatencyLedger)
            finally:
                rig.close()

    def test_end_to_end_run_yields_one_latency_per_typed_utterance(self):
        import keshevctl

        with tempfile.TemporaryDirectory() as td:
            rig = keshevctl.build_rig(state_dir=td, texts=["שלום עולם"])
            try:
                led = measure_gates.instrument(rig)
                for i in range(3):
                    rig.injector.feed_utterance(
                        keshevctl.tone_utterance(2.0, phase=7 * i))
                    rig.drain(extra_idle_steps=1)
                self.assertEqual(len(led.latencies_ms), 3)
                for ms in led.latencies_ms:
                    self.assertGreater(ms, 0.0)
                    self.assertLess(ms, 60_000.0)
            finally:
                rig.close()


class SlotsParsing(unittest.TestCase):
    """`is_processing` alone proves a slot is claimed, not that tokens are
    coming out of it. llama-server's per-slot n_decoded is the number that
    cannot be faked by a wedged server, so the proof carries it."""

    ROWS = [
        {"id": 0, "is_processing": True,
         "next_token": [{"n_decoded": 58, "n_remain": 342}]},
        {"id": 1, "is_processing": False,
         "next_token": [{"n_decoded": 0, "n_remain": 0}]},
    ]

    def test_busy_total_and_decoded_are_read_from_the_slots_payload(self):
        self.assertEqual(measure_gates.parse_slots(self.ROWS), (1, 2, 58))

    def test_an_idle_server_reports_zero_busy(self):
        rows = [dict(r, is_processing=False) for r in self.ROWS]
        busy, total, _ = measure_gates.parse_slots(rows)
        self.assertEqual((busy, total), (0, 2))

    def test_a_slot_shape_without_next_token_does_not_crash_the_prober(self):
        busy, total, decoded = measure_gates.parse_slots(
            [{"id": 0, "is_processing": True}])
        self.assertEqual((busy, total, decoded), (1, 1, 0))


class IdleBaseline(unittest.TestCase):
    """The gate is only meaningful if the load actually reached the STT path.
    An idle baseline taken BEFORE the load turns "the fleet was busy" from an
    assertion into a difference anyone can check."""

    class FakeEngine:
        def __init__(self):
            self.calls = 0

        def transcribe(self, pcm, *, request_id, duration_ms, lang_hint="auto"):
            self.calls += 1
            return type("R", (), {"decode_ms": 100 * self.calls})()

    def test_baseline_collects_one_decode_ms_per_clip(self):
        eng = self.FakeEngine()
        pcms = [b"\x00\x00" * 16000] * 3
        out = measure_gates.decode_baseline(pcms, eng)
        self.assertEqual(out, [100, 200, 300])

    def test_baseline_request_ids_are_protocol_legal(self):
        """A malformed id makes the DGX answer bad_request for every clip and
        the baseline would silently be a list of nothing."""
        from common import protocol

        seen = []

        class IdSpy(IdleBaseline.FakeEngine):
            def transcribe(self, pcm, *, request_id, duration_ms,
                           lang_hint="auto"):
                seen.append(request_id)
                return super().transcribe(pcm, request_id=request_id,
                                          duration_ms=duration_ms)

        measure_gates.decode_baseline([b"\x00\x00" * 16000] * 3, IdSpy())
        self.assertEqual(len(seen), 3)
        self.assertEqual(len(set(seen)), 3, "ids must be unique per clip")
        for rid in seen:
            self.assertTrue(protocol.valid_request_id(rid), rid)


class LocalUnavailableSpawn(unittest.TestCase):
    """This PC has neither faster_whisper nor ctranslate2 installed, so the
    worker's local rung is genuinely unloadable — and a ModuleNotFoundError
    during warm is FATAL, which takes the DGX path down with it. Gate 17's
    subject is the DGX primary path, so the harness must be able to reach
    the worker's own LOCAL_UNAVAILABLE rung (scar 14: "load NOTHING — DGX
    still works through us") instead of dying in local warm.

    The flag must be visible in argv, because the report has to say that the
    fallback was not armed during the measurement.
    """

    def test_spawn_fn_forces_the_local_unavailable_rung(self):
        seen = {}

        def fake_popen(argv, **kwargs):
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return object()

        cfg = {"server_url": "http://<lan-ip>:8737/",
               "auth_token_file": "state\\stt-token"}
        spawn = measure_gates.spawn_fn_local_unavailable(cfg, popen=fake_popen)
        spawn(7)
        argv = seen["argv"]
        self.assertIn("--free-vram-mb", argv)
        self.assertEqual(argv[argv.index("--free-vram-mb") + 1], "0")
        # …and the DGX wiring must survive: without these the worker answers
        # dgx_unconfigured forever and the gate would measure nothing at all.
        self.assertIn("--server-url", argv)
        self.assertEqual(argv[argv.index("--server-url") + 1],
                         "http://<lan-ip>:8737/")
        self.assertIn("--token-file", argv)
        self.assertIn("--gen", argv)
        self.assertEqual(argv[argv.index("--gen") + 1], "7")


if __name__ == "__main__":
    unittest.main()
