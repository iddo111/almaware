# -*- coding: utf-8 -*-
"""Queen selection over the big colonies. Selects, never merges.

No codebook is combined, averaged, or copied between ants. The Queen writes down
which ant she picked and why; every ant's checkpoint stays exactly as its own
seed produced it.

She ranks on held-out **syllable discrimination**, not quantisation error. A
prior controlled experiment established that quantisation error does not rank
ants on this task, so it is recorded here for provenance and explicitly not used
as the selection key.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
BIG = ROOT / "state-big"
ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")


def main() -> None:
    know = json.loads((BIG / "syllable-knowledge-big.json").read_text(encoding="utf-8"))
    formants = json.loads((BIG / "formants.json").read_text(encoding="utf-8"))
    scores = {}
    for c in know["codebooks"]:
        if not c["group"].startswith("big/"):
            continue
        scores[(c["group"].split("/", 1)[1], c["ant"])] = c

    out = {
        "format_version": 1,
        "architecture": "independent-waveform-acoustic-colony",
        "merge_policy": "none -- the Queen selects one ant, she never merges codebooks",
        "selection_key": "held-out syllable discrimination, cosine top-1",
        "selection_key_rejected": "held-out quantisation error -- a prior controlled "
                                  "experiment showed it does not rank ants on this task",
        "colonies": [],
    }
    for colony in sorted({k[0] for k in scores}):
        rows = []
        for ant in ANTS:
            s = scores.get((colony, ant))
            if not s:
                continue
            f = formants[colony]["ants"][ant]
            best = f.get("best_a_candidate")
            rows.append({
                "ant": ant, "seed": s["seed"],
                "checkpoint_sha256": s["checkpoint_sha256"],
                "syllable_top1_cosine": s["test2_nearest_neighbour"]["cosine"]["top1"],
                "syllable_top1_edit": s["test2_nearest_neighbour"]["edit"]["top1"],
                "heldout_quantisation_error": f["heldout_error_after"],
                "headline_exemplar_is_a": f["headline"]["is_a"],
                "has_voiced_a_unit": bool(best and best["is_a"]),
                "vowel_boxes_covered": len(f["regions_covered_inside_box"]),
            })
        chosen = max(rows, key=lambda r: (r["syllable_top1_cosine"], -r["ant"].count("")))
        out["colonies"].append({
            "colony": colony,
            "selected_ant": chosen["ant"],
            "selected_checkpoint_sha256": chosen["checkpoint_sha256"],
            "ants": rows,
        })
        print(f"{colony:<20} queen selects {chosen['ant']} "
              f"(cos@1={100*chosen['syllable_top1_cosine']:.1f}, "
              f"has /a/ unit={chosen['has_voiced_a_unit']}, "
              f"vowel boxes={chosen['vowel_boxes_covered']}/5)")
    (BIG / "queen").mkdir(parents=True, exist_ok=True)
    (BIG / "queen" / "current.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {BIG/'queen'/'current.json'}")


if __name__ == "__main__":
    main()
