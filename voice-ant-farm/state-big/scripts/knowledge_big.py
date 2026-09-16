# -*- coding: utf-8 -*-
"""Re-run the existing syllable-discrimination harness on the big-corpus ants.

Nothing new is invented here: Corpus, score_codebook and the probes come from
run_knowledge_tests / sequence_probes exactly as they ran for the 44.7 % result.
The only change is which codebooks get fed in.

Reference arms carried through the identical code path:
  * state/            the BEFORE ants, 64 units, 253 s
  * state-syllables/  the previous best, trained on the VITS syllable curriculum
  * state-big/        every colony trained here
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
sys.path.insert(0, str(ROOT))

import run_knowledge_tests as rkt  # noqa: E402
from acoustic_units import load_checkpoint  # noqa: E402

ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")


def jobs() -> list[dict]:
    out = []
    for label, root in (("BEFORE-253s-64", ROOT / "state"),
                        ("prev-syllable-curriculum", ROOT / "state-syllables"),
                        ("big", ROOT / "state-big")):
        if not root.exists():
            continue
        groups = ([root] if (root / "ant-a").exists()
                  else sorted(p for p in root.iterdir() if p.is_dir()
                              and (p / "ant-a").exists()))
        for g in groups:
            for ant in ANTS:
                cur = g / ant / "current.json"
                if not cur.exists():
                    continue
                ck = load_checkpoint(cur)
                name = label if g == root else f"{label}/{g.name}"
                out.append({
                    "group": name, "kind": label, "ant": ant, "seed": ck["seed"],
                    "units": ck["units"],
                    "hours": (ck.get("corpus_provenance") or {}).get("hours"),
                    "speakers": (ck.get("corpus_provenance") or {}).get("speaker_id_count"),
                    "centers": np.asarray(ck["centers"], dtype=np.float32),
                    "checkpoint_sha256": ck["checkpoint_sha256"],
                })
    return out


def main() -> None:
    corpus = rkt.Corpus()
    report = {
        "question": "does 40 h of real speech raise syllable discrimination above "
                    "the 44.7 % top-1 ceiling reached on the synthetic curriculum",
        "harness": "run_knowledge_tests.score_codebook, unmodified",
        "chance_syllable": 1 / len(corpus.classes),
        "heldout_items": len(corpus.held),
        "classes": corpus.classes,
        "leak_check": corpus.leak_check,
        "references": rkt.references(corpus),
        "codebooks": [],
    }
    print(json.dumps(report["references"], indent=2), flush=True)
    for job in jobs():
        t0 = time.time()
        s = rkt.score_codebook(corpus, job["centers"], job["seed"])
        s.update({k: job[k] for k in ("group", "kind", "ant", "seed", "hours",
                                      "speakers", "checkpoint_sha256")})
        s["seconds"] = round(time.time() - t0, 1)
        report["codebooks"].append(s)
        print(f"{job['group']:<34} {job['ant']} k={s['units']:<4} "
              f"cos@1={s['test2_nearest_neighbour']['cosine']['top1']:.3f} "
              f"edit@1={s['test2_nearest_neighbour']['edit']['top1']:.3f} "
              f"cos@5={s['test2_nearest_neighbour']['cosine']['top5']:.3f} "
              f"({s['seconds']}s)", flush=True)
    out = ROOT / "state-big" / "syllable-knowledge-big.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
