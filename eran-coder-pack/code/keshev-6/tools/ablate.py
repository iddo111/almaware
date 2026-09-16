# -*- coding: utf-8 -*-
"""Which part of KESHEV-6 actually earns the win: the MODEL, the PROMPT, or the REPAIR?

Three decodes of the same audio through one loaded model, so the comparison
costs one model on the card instead of three:

    C  model only              (ivrit-ai turbo, no initial_prompt, no repair)
    B  model + prompt          (the lexicon sentence as decoder context)
    A  model + prompt + repair (what :8738 serves)

Without this the report could credit a 3-line dictionary for a 1.6 GB model's
work, or the reverse. Run with the server STOPPED - the card has 8 GB and the
live :8737 is holding half of it.
"""
from __future__ import annotations

import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lexicon  # noqa: E402
from keshev6_server import IvritEngine  # noqa: E402


def pcm(path: str) -> np.ndarray:
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()),
                             dtype=np.int16).astype(np.float32) / 32768.0


def main() -> None:
    listfile = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "state/okset.txt")
    out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "state/ablate.jsonl")
    wavs = [ln.strip() for ln in
            Path(listfile).read_text(encoding="utf-8").splitlines() if ln.strip()]
    eng = IvritEngine(os.environ.get("K6_MODEL", "ivrit-ai/whisper-large-v3-turbo-ct2"))
    rows = []
    t0 = time.monotonic()
    for i, w in enumerate(wavs):
        a = pcm(w)
        c = eng.decode(a, language="he", initial_prompt=None)
        b = eng.decode(a, language="he", initial_prompt=lexicon.PROMPT_HE)
        a_txt, changes = lexicon.repair(b["text"])
        rows.append({"wav": Path(w).name,
                     "C_model": c["text"], "B_prompt": b["text"], "A_full": a_txt,
                     "repairs": [list(x) for x in changes],
                     "lp_C": round(c["avg_logprob"], 4), "lp_B": round(b["avg_logprob"], 4)})
        if (i + 1) % 25 == 0:
            print(f"{i+1}/{len(wavs)}  {time.monotonic()-t0:.0f}s", flush=True)
    Path(out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                         encoding="utf-8")
    print("wrote", out, len(rows))


if __name__ == "__main__":
    main()
