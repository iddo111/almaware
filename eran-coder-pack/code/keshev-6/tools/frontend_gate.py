# -*- coding: utf-8 -*-
"""Could speech_ratio have kept tonight's non-speech off the GPU entirely?

1,360 of tonight's 1,586 segments went to the decoder and came back as nothing.
They are not lost speech (KESHEV-EMPTY-20260903.md: 30/30 gave no Hebrew from
three independent decoders) - they are laughter, breath and room. But every one
of them cost a GPU decode, a round trip, and a slot in a queue that his real
words were waiting in.

This measures the ONLY thing that matters before such a gate could ship:
what it would have cost him. A gate that saves 85% of the work and eats one
sentence he said is a worse mic, not a better one.

Pure numpy, no GPU, no model.
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keshev6_server import speech_ratio  # noqa: E402

SEG = Path(r"D:/CLAUDE/keshev-next/segments")


def pcm(name: str):
    with wave.open(str(SEG / name)) as w:
        return np.frombuffer(w.readframes(w.getnframes()),
                             dtype=np.int16).astype(np.float32) / 32768.0


def main() -> None:
    recs = [json.loads(l) for l in
            (ROOT / "state/night.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for r in recs:
        try:
            out.append({"wav": r["wav"], "decode": r["decode"],
                        "peak_rms": r["peak_rms"], "secs": r["secs"],
                        "sr": round(speech_ratio(pcm(r["wav"])), 3)})
        except Exception:
            pass
    (ROOT / "state/frontend.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in out), encoding="utf-8")

    ok = [o for o in out if o["decode"] == "ok"]
    empty = [o for o in out if o["decode"] == "empty"]
    print(f"scored {len(out)} segments: {len(ok)} real speech, {len(empty)} empty\n")
    print(f"{'threshold':>10} {'GPU calls saved':>16} {'real speech LOST':>18}")
    for th in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50):
        saved = sum(1 for o in empty if o["sr"] < th)
        lost = sum(1 for o in ok if o["sr"] < th)
        print(f"{th:>10.2f} {saved:>7} / {len(empty)}  {saved/max(len(empty),1)*100:>4.0f}%"
              f" {lost:>8} / {len(ok)}  {lost/max(len(ok),1)*100:>4.0f}%")
    med = lambda xs: float(np.median([o["sr"] for o in xs])) if xs else 0.0
    print(f"\nmedian speech_ratio: real speech {med(ok):.3f}   empty {med(empty):.3f}")


if __name__ == "__main__":
    main()
