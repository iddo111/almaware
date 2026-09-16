# -*- coding: utf-8 -*-
"""Does joining a sub-second fragment to the segment before it recover real words?

262 of tonight's 1,360 empty segments were under one second, and the segmenter
cuts on a 900 ms unvoiced run - a run that lives INSIDE Iddo's far-field
sentences. The hypothesis: some fragments are half a word, and the model would
read them if it had the other half.

METHOD - and why it does not go through the X-Join header.
The server's JoinBuffer only joins when the two requests arrive within 500 ms of
each other, which is true of the LIVE mic and false of a test harness, because
the first request's own decode takes ~400-1300 ms. Testing through the header
would measure the harness's latency, not the hypothesis. So the audio is
concatenated here and sent as ONE ordinary request - byte for byte what
JoinBuffer.offer() would hand the decoder live. (test_contract_parity.py covers
the buffer's timing rule separately.)

A joined decode that only returns what the PREVIOUS segment already said on its
own is not a recovery - it is the previous sentence twice, which is exactly the
failure that keeps this feature switched off by default. That case is counted
separately and never as a win.
"""
from __future__ import annotations

import json
import re
import sys
import time
import wave
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SEG = Path(r"D:/CLAUDE/keshev-next/segments")
TOKEN = Path(r"D:/CLAUDE/mic-rebuild/state/stt-token").read_text(encoding="utf-8").strip()
URL = "http://127.0.0.1:8738/v1/transcribe"
HEB = re.compile(r"[\u0590-\u05FF]{2,}")
STOP = {"תודה", "תודה רבה", "כתוביות", "עברית", "בהצלחה", "המשך בפעם הבאה"}


def pcm(name: str) -> bytes:
    with wave.open(str(SEG / name)) as w:
        return w.readframes(w.getnframes())


def ask(data: bytes, rid: str) -> str:
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "audio/x-raw",
         "X-Request-Id": rid, "X-Audio-Duration-Ms": str(len(data) // 32),
         "X-Lang-Hint": "he"}
    try:
        r = requests.post(URL, data=data, headers=h, timeout=30)
        return r.json().get("text", "") if r.status_code == 200 else f"<{r.status_code}>"
    except Exception as e:
        return f"<{type(e).__name__}>"


def real_words(t: str) -> set:
    """Hebrew words that are not the politeness hallucination."""
    t = (t or "").strip()
    if t.strip(" .!?,") in STOP:
        return set()
    return set(HEB.findall(t))


def main() -> None:
    recs = [json.loads(l) for l in
            (ROOT / "state/night.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    idx = {r["wav"]: i for i, r in enumerate(recs)}
    shorts = [r for r in recs if r["decode"] == "empty" and r["secs"] < 0.8]
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    shorts = shorts[:limit]
    print(f"testing {len(shorts)} sub-0.8s empty fragments against their predecessor",
          flush=True)

    recovered = echo_only = nothing = 0
    rows = []
    for k, r in enumerate(shorts):
        i = idx[r["wav"]]
        if i == 0:
            continue
        prev = recs[i - 1]
        try:
            frag, before = pcm(r["wav"]), pcm(prev["wav"])
        except Exception:
            continue
        # keep at most the JoinBuffer's 6 s window of the previous segment
        before = before[-6 * 16000 * 2:]
        ms = int(time.time() * 1000)
        solo = ask(frag, f"solo{k:05d}-{ms}")
        prev_solo = ask(before, f"psol{k:05d}-{ms}")
        joined = ask(before + frag, f"join{k:05d}-{ms}")

        new = real_words(joined) - real_words(prev_solo) - real_words(solo)
        if new:
            recovered += 1
            tag = "RECOVERED"
        elif real_words(joined) - real_words(solo):
            echo_only += 1
            tag = "echo-of-previous"
        else:
            nothing += 1
            tag = "nothing"
        rows.append({"wav": r["wav"], "secs": r["secs"], "solo": solo,
                     "prev_solo": prev_solo, "joined": joined,
                     "new_words": sorted(new), "verdict": tag})
        if (k + 1) % 20 == 0:
            print(f"  {k+1}/{len(shorts)}", flush=True)

    (ROOT / "state/join_test.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows), encoding="utf-8")
    n = max(len(rows), 1)
    print(f"\nof {len(rows)} fragments: RECOVERED new real words {recovered} "
          f"({recovered/n*100:.0f}%) | only echoed the previous segment {echo_only} "
          f"| nothing {nothing}")
    for x in rows:
        if x["verdict"] == "RECOVERED":
            print(f"  {x['wav'][9:15]} ({x['secs']}s)  solo={x['solo']!r}")
            print(f"           joined={x['joined']!r}")
            print(f"           new={x['new_words']}")


if __name__ == "__main__":
    main()
