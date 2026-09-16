# -*- coding: utf-8 -*-
"""One pass over the corpus: 14-dim frames to disk, plus a frame->file index.

The corpus lives on a spinning disk: single-threaded it reads 29 files/s, with
16 reader threads it reads 169 files/s. The work is I/O-latency bound, not
bandwidth bound, so the files are read through a thread pool. numpy's FFT
releases the GIL, so featurising overlaps the reads. Order is preserved by
`map`, which the frame->file index depends on.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fastfeat import features_batch, read_pcm16  # noqa: E402

OUT = Path(r"D:\CLAUDE\voice-ant-farm\state-big\corpus")
THREADS = 16
BATCH = 2048


def one(path: str):
    try:
        s, rate = read_pcm16(path)
        if rate != 16000:
            raise ValueError(f"sample rate {rate}")
        return features_batch(s), None
    except Exception as exc:                       # noqa: BLE001
        return np.zeros((0, 14), dtype=np.float32), f"{path}: {exc}"


def run(split: str) -> None:
    items = [i for i in json.loads((OUT / "items.json").read_text(encoding="utf-8"))
             if i["split"] == split]
    blocks, counts, kept = [], np.zeros(len(items), dtype=np.int64), 0
    t0 = time.time()
    with ThreadPoolExecutor(THREADS) as pool:
        for s0 in range(0, len(items), BATCH):
            batch = items[s0:s0 + BATCH]
            for k, (f, err) in enumerate(pool.map(one, [b["path"] for b in batch])):
                if err:
                    print(f"  skip {err}", flush=True)
                counts[s0 + k] = len(f)
                if len(f):
                    blocks.append(f)
                    kept += 1
            done = int(counts[:s0 + len(batch)].sum())
            print(f"  {split} {s0+len(batch)}/{len(items)} files  {done:,} frames  "
                  f"{time.time()-t0:.0f}s", flush=True)
    x = np.concatenate(blocks) if blocks else np.zeros((0, 14), np.float32)
    np.save(OUT / f"{split}_x.npy", x)
    np.save(OUT / f"{split}_counts.npy", counts)
    print(f"{split}: {kept}/{len(items)} files, {len(x):,} frames "
          f"({len(x)/100/3600:.3f} h of framed audio), {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    for split in sys.argv[1:] or ["train", "heldout"]:
        run(split)
