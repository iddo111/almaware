"""The watchdog cadence law — scar 5, and the bug that killed keshev-stt on eran1.

WHAT HAPPENED (2026-08-12, observed on eran1, journal verbatim):
    21:57:12  evt=READY version=3802036-k10-live
    21:58:42  keshev-stt.service: Watchdog timeout (limit 1min 30s)!
    21:58:42  Killing process 58561 (python) with signal SIGABRT
    ... five times, then: "Start request repeated too quickly."

The server was healthy. The canary worked. The petting code was correct and wired.
The service could still never survive, because two individually-sensible numbers
lived in two different files:

    common/protocol.py      CANARY_INTERVAL_S = 300   # pet every 5 min
    server/keshev-stt.service  WatchdogSec=90         # die after 90 s

300 > 90, so the FIRST pet was always ~3.3x too late. Structurally impossible.

THE LAW THIS FILE PINS:
    The pet cadence must be at most WatchdogSec/2, which is the systemd convention
    and leaves one whole missed pet of margin before the kill.

AND THE SEPARATION THAT MAKES IT AFFORDABLE (scar 5 preserved):
    We do NOT fix this by running a real GPU decode every 30 s — eran1 is Qwen's
    machine and KESHEV is the quiet tenant (Nice=10, design section 6). Instead the
    PET is decoupled from the DECODE: a cheap heartbeat pets often, but ONLY while
    the last real canary decode is still fresh. A wedged model stops refreshing the
    canary, the heartbeat stops petting, and systemd restarts us — exactly the
    behaviour section 6 specifies, at 1/10th the GPU cost.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNIT = REPO / "server" / "keshev-stt.service"


def _watchdog_sec() -> int:
    """The WatchdogSec actually declared in the shipped unit file."""
    for line in UNIT.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("WatchdogSec"):
            return int(re.split(r"[=\s]+", s)[1])
    raise AssertionError("no WatchdogSec in server/keshev-stt.service")


class WatchdogCadence(unittest.TestCase):
    def test_unit_still_declares_a_watchdog(self):
        """Disabling the watchdog is NOT an acceptable fix for a cadence bug.

        It removes the only mechanism that restarts a wedged model (scar 5).
        If someone comments this out again, this test fails and says why.
        """
        self.assertGreater(
            _watchdog_sec(), 0,
            "WatchdogSec was removed/zeroed. That deletes the wedged-model guard "
            "instead of fixing the cadence. Fix PET_INTERVAL_S, not the watchdog.")

    def test_pet_cadence_is_at_most_half_the_watchdog(self):
        """THE BUG. This is the assertion that was never written."""
        from common import protocol
        wd = _watchdog_sec()
        self.assertLessEqual(
            protocol.PET_INTERVAL_S, wd / 2,
            f"pet cadence {protocol.PET_INTERVAL_S}s > WatchdogSec/2 ({wd/2}s): "
            f"systemd will SIGABRT the server before it ever pets. This is exactly "
            f"what killed it on eran1 on 2026-08-12.")

    def test_pet_cadence_is_not_absurdly_fast(self):
        """A 1 s pet would pass the law above and hammer the box for nothing."""
        from common import protocol
        self.assertGreaterEqual(protocol.PET_INTERVAL_S, 5)

    def test_canary_decode_stays_expensive_and_rare(self):
        """The real GPU decode must NOT be dragged down to the pet cadence.

        eran1 is Qwen's machine. Decoding every 30 s to satisfy a watchdog would
        make KESHEV a bad tenant. The whole point of the split is that the cheap
        thing is frequent and the expensive thing is not.
        """
        from common import protocol
        self.assertGreater(protocol.CANARY_INTERVAL_S, protocol.PET_INTERVAL_S * 4)

    def test_staleness_limit_covers_at_least_one_missed_canary(self):
        """Freshness window must tolerate one late canary but not a dead one."""
        from common import protocol
        self.assertGreater(protocol.CANARY_STALE_S, protocol.CANARY_INTERVAL_S)
        self.assertLessEqual(protocol.CANARY_STALE_S, protocol.CANARY_INTERVAL_S * 3)


class PetGating(unittest.TestCase):
    """The pet must be earned by real output, never given for merely being alive."""

    def _srv(self):
        from server import stt_server
        return stt_server

    def test_should_pet_is_false_before_any_canary(self):
        stt = self._srv()
        self.assertFalse(
            stt.should_pet(canary_age_s=float(10 ** 9)),
            "a server that has never produced real output must not be petted")

    def test_should_pet_is_true_while_canary_is_fresh(self):
        from common import protocol
        stt = self._srv()
        self.assertTrue(stt.should_pet(canary_age_s=protocol.CANARY_INTERVAL_S * 0.5))

    def test_should_pet_goes_false_once_canary_is_stale(self):
        """A wedged model stops refreshing the canary -> we stop petting -> systemd
        restarts us. This is the entire safety property, in one assertion."""
        from common import protocol
        stt = self._srv()
        self.assertFalse(stt.should_pet(canary_age_s=protocol.CANARY_STALE_S + 1))


if __name__ == "__main__":
    unittest.main()
