# -*- coding: utf-8 -*-
"""A/B one WAV (or a whole set) against :8737 (live) and :8738 (KESHEV-6).

Read-only against the live server: an ordinary client request, one at a time,
with a configurable pause, so the mic is never starved. Never restarts anything.
"""
from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path

import requests

TOKEN = Path(r"D:/CLAUDE/mic-rebuild/state/stt-token").read_text(encoding="utf-8").strip()
OLD = "http://127.0.0.1:8737/v1/transcribe"
NEW = "http://127.0.0.1:8738/v1/transcribe"


def pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


def ask(url: str, data: bytes, rid: str, hint: str = "he",
        extra: dict | None = None, timeout: float = 30.0) -> dict:
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "audio/x-raw",
         "X-Request-Id": rid, "X-Audio-Duration-Ms": str(len(data) // 32),
         "X-Lang-Hint": hint}
    h.update(extra or {})
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
    ap.add_argument("wavs", nargs="*")
    ap.add_argument("--list", help="file with one wav path per line (argv-safe)")
    ap.add_argument("--out")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="pause between requests - the live server serves the MIC first")
    ap.add_argument("--only", choices=["old", "new", "both"], default="both")
    ap.add_argument("--join", action="store_true")
    args = ap.parse_args()

    wavs = list(args.wavs)
    if args.list:
        wavs += [ln.strip() for ln in
                 Path(args.list).read_text(encoding="utf-8").splitlines() if ln.strip()]

    rows = []
    for i, w in enumerate(wavs):
        p = Path(w)
        try:
            data = pcm(p)
        except Exception as e:
            print("SKIP", p.name, type(e).__name__)
            continue
        rid = f"{i:08x}-{int(time.time() * 1000)}"
        row = {"wav": p.name, "secs": round(len(data) / 32000, 2)}
        if args.only in ("old", "both"):
            row["old"] = ask(OLD, data, rid)
            time.sleep(args.sleep)
        if args.only in ("new", "both"):
            extra = {"X-Join": "1", "X-Client-Id": "ab"} if args.join else None
            row["new"] = ask(NEW, data, rid, extra=extra)
            time.sleep(args.sleep)
        rows.append(row)
        if not args.out:
            o = (row.get("old") or {}).get("text", "")
            n = (row.get("new") or {}).get("text", "")
            print(f"{p.name}  {row['secs']}s")
            print(f"   OLD: {o!r}")
            print(f"   NEW: {n!r}")
    if args.out:
        Path(args.out).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        print("wrote", args.out, len(rows), "rows")


if __name__ == "__main__":
    main()
