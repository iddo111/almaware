# -*- coding: utf-8 -*-
"""Is any of Iddo's real speech hiding in the LOUD "empty" segments?

KESHEV-EMPTY-20260903.md sampled 30 empties across the whole level range and
found laughter and breath in all 30. But there is a sharper question it did not
ask, and tonight handed me the reason to ask it: FOUR of the ten sentences Iddo
actually said do not appear ANYWHERE in tonight's decoded output. Not garbled -
absent.

So this sweeps the population where lost speech would hide if it is hiding
anywhere: every "empty" segment at peak_rms >= 4000 - the band where his
confirmed speech lives - through the new model, and looks for real Hebrew
sentences and for the four missing sentences specifically.

A NEGATIVE RESULT IS THE POINT. If nothing comes back, the empties are settled
and the remaining problem is upstream of the decoder, which is a different fix
and an honest thing to tell him.
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

# whole-utterance non-speech: the politeness hallucination and the noises the
# ivrit model emits for laughter/breath
NOISE = re.compile(r"^[\s.,!?'\"()־-]*(תודה( רבה)?|כתוביות|עברית|בהצלחה|\(צחוק\)|"
                   r"\(מחיאות כפיים\)|שקט|[חהאשספצ]{2,}|[א-ת])[\s.,!?'\"()־-]*$")

MISSING = ["קורס", "ורבע", "לכתוב מחדש", "פסייטראנס", "מיקרופון שעובד", "אפליקציית"]


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


def is_sentence(t: str) -> bool:
    """Three or more Hebrew words that are not the known non-speech outputs."""
    t = (t or "").strip()
    if not t or NOISE.match(t):
        return False
    return len(HEB.findall(t)) >= 3


def main() -> None:
    floor = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    recs = [json.loads(l) for l in
            (ROOT / "state/night.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    loud = [r for r in recs
            if r["decode"] == "empty" and (r["peak_rms"] or 0) >= floor]
    print(f"sweeping {len(loud)} empty segments at peak_rms >= {floor}", flush=True)

    rows, sentences, hits = [], [], []
    t0 = time.monotonic()
    for k, r in enumerate(loud):
        try:
            data = pcm(r["wav"])
        except Exception:
            continue
        t = ask(data, f"swp{k:05d}-{int(time.time()*1000)}")
        rows.append({"wav": r["wav"], "peak_rms": r["peak_rms"], "secs": r["secs"],
                     "new_text": t})
        if is_sentence(t):
            sentences.append(rows[-1])
        if any(m in t for m in MISSING):
            hits.append(rows[-1])
        if (k + 1) % 50 == 0:
            print(f"  {k+1}/{len(loud)}  {time.monotonic()-t0:.0f}s", flush=True)

    (ROOT / "state/empties_sweep.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows), encoding="utf-8")
    n = max(len(rows), 1)
    print(f"\n{len(sentences)} of {len(rows)} loud 'empty' segments came back as a real "
          f"Hebrew sentence ({len(sentences)/n*100:.1f}%)")
    for s in sentences[:40]:
        print(f"  rms={s['peak_rms']:>6} {s['secs']:>5}s  {s['new_text'][:90]}")
    print(f"\nsegments containing one of the four MISSING sentences: {len(hits)}")
    for h in hits:
        print(f"  {h['wav']}  {h['new_text'][:110]}")


if __name__ == "__main__":
    main()
