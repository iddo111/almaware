# -*- coding: utf-8 -*-
"""30-minute soak: replay tonight's spool at real-time pace against :8738 while
:8737 keeps serving the live mic.

The question this answers is not "is it fast" - that is the A/B - but "does it
still answer after half an hour, and does anything leak". Three things are
watched every minute:

    drops / timeouts / non-200   the failure Iddo actually feels
    latency drift                a decoder that slows down is a decoder dying
    GPU + RSS memory             flat, or it is a leak with a countdown on it

Pace is REAL TIME: segments are sent with the same gaps they were recorded with
(capped, so a coffee break does not eat the soak), because a burst test proves
nothing about an all-day mic.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import wave
from pathlib import Path

import requests

TOKEN = Path(r"D:/CLAUDE/mic-rebuild/state/stt-token").read_text(encoding="utf-8").strip()
URL = "http://127.0.0.1:8738/v1/transcribe"
HEALTH = "http://127.0.0.1:8738/health"


def gpu_free_mib() -> int:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return -1


def server_rss_mib() -> int:
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            cl = p.info.get("cmdline") or []
            if any("keshev6_server" in str(c) for c in cl):
                return int(p.memory_info().rss / (1024 * 1024))
    except Exception:
        pass
    return -1


def stamp(name: str) -> float:
    """seconds-of-day from a `YYYYmmdd-HHMMSS-mmm.wav` name."""
    h, m, s = int(name[9:11]), int(name[11:13]), int(name[13:15])
    return h * 3600 + m * 60 + s + int(name[16:19]) / 1000.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--dir", default=r"D:/CLAUDE/keshev-next/segments")
    ap.add_argument("--since", default="20260903-17")
    ap.add_argument("--max-gap", type=float, default=3.0)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "state/soak.json"))
    args = ap.parse_args()

    wavs = sorted(p for p in Path(args.dir).glob("20260903-*.wav") if p.name >= args.since)
    print(f"soak: {len(wavs)} segments available, running {args.minutes} min", flush=True)

    t_start = time.monotonic()
    deadline = t_start + args.minutes * 60
    lat: list[int] = []
    codes: dict[str, int] = {}
    errors = 0
    samples = []
    prev_stamp = None
    i = 0
    last_report = t_start

    while time.monotonic() < deadline:
        p = wavs[i % len(wavs)]
        i += 1
        try:
            with wave.open(str(p)) as w:
                data = w.readframes(w.getnframes())
        except Exception:
            continue
        # real-time pace
        st = stamp(p.name)
        if prev_stamp is not None:
            gap = min(max(st - prev_stamp, 0.0), args.max_gap)
            if gap > 0:
                time.sleep(gap)
        prev_stamp = st

        rid = f"soak{i:04d}-{int(time.time()*1000)}"
        t0 = time.monotonic()
        try:
            r = requests.post(URL, data=data, timeout=15, headers={
                "Authorization": f"Bearer {TOKEN}", "Content-Type": "audio/x-raw",
                "X-Request-Id": rid, "X-Audio-Duration-Ms": str(len(data) // 32),
                "X-Lang-Hint": "he"})
            code = str(r.status_code)
        except Exception as e:
            code = f"EXC:{type(e).__name__}"
            errors += 1
        ms = int((time.monotonic() - t0) * 1000)
        codes[code] = codes.get(code, 0) + 1
        if code == "200":
            lat.append(ms)

        if time.monotonic() - last_report >= 60:
            last_report = time.monotonic()
            w = sorted(lat[-200:])
            samples.append({
                "min": round((time.monotonic() - t_start) / 60, 1),
                "n": len(lat),
                "p50_ms": w[len(w) // 2] if w else 0,
                "p95_ms": w[int(len(w) * 0.95)] if w else 0,
                "gpu_free_mib": gpu_free_mib(), "rss_mib": server_rss_mib(),
                "codes": dict(codes), "errors": errors})
            print(json.dumps(samples[-1]), flush=True)

    allw = sorted(lat)
    result = {"minutes": args.minutes, "requests": sum(codes.values()),
              "codes": codes, "errors": errors,
              "p50_ms": allw[len(allw) // 2] if allw else 0,
              "p95_ms": allw[int(len(allw) * 0.95)] if allw else 0,
              "samples": samples}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("SOAK DONE", json.dumps({k: v for k, v in result.items() if k != "samples"}),
          flush=True)


if __name__ == "__main__":
    main()
