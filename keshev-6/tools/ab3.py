# -*- coding: utf-8 -*-
"""Three-way A/B: eran1's OLD :8737, the PC's KESHEV-6 :8738, eran1's NEW :8739.

Same audio, same request shape, one request at a time with a pause, because the
PC's :8738 is serving Iddo's LIVE microphone while this runs and a benchmark
that starves his mic is not a benchmark, it is an outage.

Written 2026-09-05 for the move of the good decoder onto the DGX. It is ab.py
with a third column; the two-way ab.py is left untouched so the 09-04 numbers
stay reproducible exactly as they were produced.
"""
from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path

import requests

TOKEN = Path(r"D:/CLAUDE/mic-rebuild/state/stt-token").read_text(encoding="utf-8").strip()

SIDES = {
    "old":  "http://<lan-ip>:8737/v1/transcribe",   # eran1, the old model
    "pc":   "http://127.0.0.1:8738/v1/transcribe",       # the PC, KESHEV-6
    "dgx":  "http://<lan-ip>:8739/v1/transcribe",   # eran1, KESHEV-6 (new)
}


def pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


def ask(url: str, data: bytes, rid: str, hint: str = "he", timeout: float = 30.0) -> dict:
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "audio/x-raw",
         "X-Request-Id": rid, "X-Audio-Duration-Ms": str(len(data) // 32),
         "X-Lang-Hint": hint}
    t0 = time.monotonic()
    try:
        r = requests.post(url, data=data, headers=h, timeout=timeout)
    except Exception as e:
        return {"http": 0, "err": type(e).__name__, "text": "",
                "wall_ms": int((time.monotonic() - t0) * 1000)}
    out = {"http": r.status_code, "wall_ms": int((time.monotonic() - t0) * 1000)}
    try:
        out.update(r.json())
    except ValueError:
        out["err"] = "not_json"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="file with one wav path per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--sides", default="old,pc,dgx")
    args = ap.parse_args()

    sides = [s for s in args.sides.split(",") if s]
    wavs = [ln.strip() for ln in
            Path(args.list).read_text(encoding="utf-8").splitlines() if ln.strip()]

    rows, t_start = [], time.monotonic()
    for i, w in enumerate(wavs):
        p = Path(w)
        try:
            data = pcm(p)
        except Exception as e:
            print("SKIP", p.name, type(e).__name__, flush=True)
            continue
        rid = f"{i:08x}-{int(time.time() * 1000)}"
        row = {"wav": p.name, "secs": round(len(data) / 32000, 2)}
        for s in sides:
            row[s] = ask(SIDES[s], data, rid)
            time.sleep(args.sleep)
        rows.append(row)
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(wavs)}  {time.monotonic()-t_start:.0f}s", flush=True)

    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("wrote", args.out, len(rows), "rows")


if __name__ == "__main__":
    main()
