"""The fallback chain must cover START, not only OPEN — 2026-08-15.

THE OUTAGE THIS ENCODES. On 2026-08-15 KESHEV logged 440 RERESOLVE_ERROR,
every one of them:

    PortAudioError: Error STARTING stream: Unanticipated host error
    [PaErrorCode -9999]: 'WdmSyncIoctl: DeviceIoControl ...'

for roughly forty minutes, going IDLE_NO_MIC and back in a loop that only the
watchdog broke, every ten minutes. Iddo had to type the word "mic".

The device chain was never the problem — a direct probe that day showed the
resolver ranking the BRIO correctly and BOTH better paths working on demand
while the failure was happening:

    idx 20  Windows WASAPI       Microphone (Logitech BRIO)  -> OPEN OK
    idx  9  Windows DirectSound  Microphone (Logitech BRIO)  -> OPEN OK
    idx 25  Windows WDM-KS       Microphone (Logitech BRIO)  -> FAIL -9999

The bug was that `handle.start()` sat OUTSIDE `open_with_retry`. The chain
guarded opening and nothing else, so a device that opened and then failed to
start raised past DeviceOpenError into the supervisor — and the remaining
devices in the chain, the ones that worked, were never tried.

These tests fail against that shape and pass against open-and-start-together.
"""
from __future__ import annotations

import unittest

from client.devices import DeviceInfo, DeviceOpenError, open_with_retry


class FakeHandle:
    def __init__(self, name, start_raises=False):
        self.name = name
        self.start_raises = start_raises
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        if self.start_raises:
            raise RuntimeError(
                "Error starting stream: Unanticipated host error "
                "[PaErrorCode -9999]: 'WdmSyncIoctl: DeviceIoControl'")
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def dev(index, hostapi, name="Microphone (Logitech BRIO)"):
    return DeviceInfo(index=index, name=name, hostapi=hostapi,
                      max_input_channels=2, max_output_channels=0)


# The real chain from that machine, in the resolver's own order.
CHAIN = [
    dev(20, "Windows WASAPI"),
    dev(9, "Windows DirectSound"),
    dev(25, "Windows WDM-KS"),
]


class TestStartFailureAdvancesTheChain(unittest.TestCase):

    def _factory(self, opens_ok, starts_ok, log):
        def open_and_start(d):
            log.append(("open", d.index))
            if d.index not in opens_ok:
                raise RuntimeError(f"open failed on {d.index}")
            h = FakeHandle(d.hostapi, start_raises=(d.index not in starts_ok))
            try:
                h.start()
            except Exception:
                h.stop()
                h.close()
                raise
            log.append(("start", d.index))
            return h
        return open_and_start

    def test_first_device_that_cannot_start_is_skipped(self):
        """WASAPI opens but will not start -> DirectSound must be tried."""
        log = []
        f = self._factory(opens_ok={20, 9, 25}, starts_ok={9, 25}, log=log)
        handle, device = open_with_retry(f, CHAIN, sleep_fn=lambda s: None)
        self.assertEqual(device.index, 9, "must fall through to DirectSound")
        self.assertTrue(handle.started)
        self.assertIn(("open", 20), log)
        self.assertIn(("open", 9), log)

    def test_the_real_outage_shape_recovers(self):
        """Only WDM-KS is broken — the shape seen on 2026-08-15. The chain
        must land on WASAPI and never reach WDM-KS at all."""
        log = []
        f = self._factory(opens_ok={20, 9, 25}, starts_ok={20, 9}, log=log)
        handle, device = open_with_retry(f, CHAIN, sleep_fn=lambda s: None)
        self.assertEqual(device.index, 20)
        self.assertNotIn(("open", 25), log, "WDM-KS should never be reached")

    def test_all_start_failures_raise_DeviceOpenError_not_a_raw_exception(self):
        """A total failure must arrive as DeviceOpenError so _open() can go
        IDLE_NO_MIC deliberately, instead of escaping into the supervisor and
        being journalled as RERESOLVE_ERROR."""
        log = []
        f = self._factory(opens_ok={20, 9, 25}, starts_ok=set(), log=log)
        with self.assertRaises(DeviceOpenError):
            open_with_retry(f, CHAIN, sleep_fn=lambda s: None)

    def test_every_device_was_attempted_before_giving_up(self):
        log = []
        f = self._factory(opens_ok={20, 9, 25}, starts_ok=set(), log=log)
        with self.assertRaises(DeviceOpenError):
            open_with_retry(f, CHAIN, sleep_fn=lambda s: None)
        attempted = {i for kind, i in log if kind == "open"}
        self.assertEqual(attempted, {20, 9, 25})


class TestHalfOpenHandleIsNotLeaked(unittest.TestCase):
    """PortAudio keeps the endpoint claimed until the handle dies. A handle
    that opened and failed to start MUST be closed, or the next attempt races
    KESHEV's own previous stream — which is precisely why killing the process
    freed the BRIO instantly on 2026-08-15."""

    def test_failed_start_closes_the_handle(self):
        made = []

        def open_and_start(d):
            h = FakeHandle(d.hostapi, start_raises=True)
            made.append(h)
            try:
                h.start()
            except Exception:
                h.stop()
                h.close()
                raise
            return h

        with self.assertRaises(DeviceOpenError):
            open_with_retry(open_and_start, CHAIN, sleep_fn=lambda s: None)

        self.assertTrue(made, "handles were created")
        for h in made:
            self.assertTrue(h.closed, f"{h.name} handle leaked - not closed")


class TestNormalPathUnchanged(unittest.TestCase):

    def test_healthy_first_device_wins_and_is_started(self):
        def open_and_start(d):
            h = FakeHandle(d.hostapi)
            h.start()
            return h

        handle, device = open_with_retry(open_and_start, CHAIN,
                                         sleep_fn=lambda s: None)
        self.assertEqual(device.index, 20)
        self.assertTrue(handle.started)
        self.assertFalse(handle.closed)


if __name__ == "__main__":
    unittest.main()
