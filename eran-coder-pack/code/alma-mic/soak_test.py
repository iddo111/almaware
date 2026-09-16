"""alma-mic / soak_test.py — reliability proof: stress the recognition path and watch memory.

The old app leaked ~hundreds of MB/min during inference and crashed every ~2 days.
This hammers the REAL transcribe path many times and samples working-set memory; flat
memory + steady latency = the leak is gone. No mic/typing needed (safe unattended).
"""
import sys
import time
import ctypes
from ctypes import wintypes

import numpy as np

from config import Config
from stt import Transcriber

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
AUDIO_SECS = 3.0


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


_kernel32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
_psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def rss_mb() -> float:
    c = _PMC(); c.cb = ctypes.sizeof(c)
    if not _psapi.GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return -1.0
    return c.WorkingSetSize / 1e6


def main():
    cfg = Config.load()
    t = Transcriber(cfg)
    t.load(log=lambda m: print(m, flush=True))
    print(f"[soak] model: {t.desc}  rss={rss_mb():.0f}MB", flush=True)

    rng = np.random.default_rng(0)
    base = None
    peak = 0.0
    lat = []
    n = int(16000 * AUDIO_SECS)
    for i in range(1, ITERS + 1):
        audio = (rng.standard_normal(n) * 0.05).astype(np.float32)
        t0 = time.time()
        t.transcribe(audio)
        lat.append(time.time() - t0)
        peak = max(peak, rss_mb())
        if i == 5:
            base = rss_mb()  # baseline after warmup
        if i % 30 == 0:
            print(f"[soak] iter {i:4}/{ITERS}  rss={rss_mb():.0f}MB  "
                  f"lat={np.mean(lat[-30:])*1000:.0f}ms", flush=True)

    end = rss_mb()
    growth = end - (base or end)
    avg = np.mean(lat) * 1000
    print(f"\n[soak] {ITERS} inferences  avg_latency={avg:.0f}ms", flush=True)
    print(f"[soak] rss baseline(after warmup)={base:.0f}MB  end={end:.0f}MB  "
          f"peak={peak:.0f}MB  growth={growth:+.0f}MB", flush=True)
    ok = growth < 150 and avg < 2000
    print(f"\nSOAK {'PASS' if ok else 'FAIL'} — "
          f"{'flat memory, fast, no leak' if ok else 'see growth/latency above'}",
          flush=True)


if __name__ == "__main__":
    main()
