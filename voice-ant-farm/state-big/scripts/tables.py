# -*- coding: utf-8 -*-
"""Render the markdown tables that go into RESULTS.md, from the JSON artefacts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
BIG = ROOT / "state-big"
BEFORE = {"ant-a": (660, 1064, "ok"), "ant-b": (392, 1948, "no"),
          "ant-c": (348, 1332, "no"), "ant-d": (660, 1064, "ok")}
ORDER = ["all-256", "multi-13.8h-256", "iddo-13.8h-256", "orig-253s-256",
         "random-frames-256"]


def f(v, d=0):
    return "-" if v is None else f"{v:.{d}f}"


def headline(rep: dict) -> str:
    out = ["| ant | before F1/F2 | before | after F1/F2 | after | unit | periodicity |",
           "|---|---|---|---|---|---|---|"]
    e = rep["all-256"]["ants"]
    for ant in ("ant-a", "ant-b", "ant-c", "ant-d"):
        h = e[ant]["headline"]
        b = BEFORE[ant]
        out.append(f"| {ant} | {b[0]} / {b[1]} | {'**/a/**' if b[2]=='ok' else 'not /a/'} "
                   f"| {f(h['f1'])} / {f(h['f2'])} | "
                   f"{'**/a/**' if h['is_a'] else 'not /a/ (' + (h['nearest_vowel'] or '?') + ')'} "
                   f"| {h['unit']} | {h['periodicity']:.2f} |")
    return "\n".join(out)


def per_colony(rep: dict) -> str:
    out = ["| colony | hours | speaker ids | ants whose headline exemplar is /a/ "
           "| /a/-capable units (of 256) | best /a/ candidate F1/F2 | held-out err |",
           "|---|---|---|---|---|---|---|"]
    names = [("BEFORE (253 s, 64 units)", "BEFORE (253 s, 64 units)")] + [(c, c) for c in ORDER]
    for key, label in names:
        if key not in rep:
            continue
        ants = rep[key]["ants"]
        n_a = sum(1 for r in ants.values() if r["headline"]["is_a"])
        units = "/".join(str(r["a_capable_units"]) for r in ants.values())
        voiced = "/".join(str(r["a_capable_units_periodic"]) for r in ants.values())
        best = []
        for r in ants.values():
            b = r.get("best_a_candidate")
            best.append(f"{b['f1']:.0f}/{b['f2']:.0f}" if b else "-")
        hrs = next((r["hours"] for r in ants.values() if r["hours"]), 0.0702)
        spk = next((r["speaker_id_count"] for r in ants.values() if r["speaker_id_count"]), 1)
        err = sum(r["heldout_error_after"] for r in ants.values()) / len(ants)
        tot = next(iter(ants.values()))["total_units"]
        out.append(f"| {label} | {hrs:.2f} | {spk} | **{n_a}/4** | {units} (of {tot}) "
                   f"| {', '.join(best)} | {err:.3f} |")
    return "\n".join(out)


def vowel_space(rep: dict) -> str:
    out = ["| colony | ant | regions hit by the 12 most periodic exemplars | count |",
           "|---|---|---|---|"]
    for key in ["BEFORE (253 s, 64 units)"] + ORDER:
        if key not in rep:
            continue
        for ant, r in rep[key]["ants"].items():
            cov = r["regions_covered_inside_box"]
            out.append(f"| {key} | {ant} | {', '.join(f'/{v}/' for v in cov) or '(none)'} "
                       f"| {len(cov)}/5 |")
    return "\n".join(out)


def whole_codebook(rep: dict) -> str:
    out = ["| colony | voiced units | /a/ | /e/ | /i/ | /o/ | /u/ | vowels covered |",
           "|---|---|---|---|---|---|---|---|"]
    for key in ["BEFORE (253 s, 64 units)"] + ORDER:
        if key not in rep:
            continue
        ants = rep[key]["ants"]
        n = sum(r["voiced_unit_count"] for r in ants.values()) / len(ants)
        c = {v: sum(r["vowel_box_counts"][v] for r in ants.values()) / len(ants)
             for v in "aeiou"}
        cov = sum(1 for v in "aeiou" if c[v] >= 1.0)
        out.append(f"| {key} | {n:.1f} | " + " | ".join(f"{c[v]:.1f}" for v in "aeiou")
                   + f" | {cov}/5 |")
    return "\n".join(out)


def knowledge() -> str:
    p = BIG / "syllable-knowledge-big.json"
    if not p.exists():
        return "_(not run)_"
    rep = json.loads(p.read_text(encoding="utf-8"))
    rows = {}
    for c in rep["codebooks"]:
        rows.setdefault(c["group"], []).append(c)
    out = ["| colony | k | cos@1 | cos@5 | edit@1 | edit@5 | best single ant cos@1 |",
           "|---|---|---|---|---|---|---|"]
    for g, cs in rows.items():
        cos1 = [c["test2_nearest_neighbour"]["cosine"]["top1"] for c in cs]
        cos5 = [c["test2_nearest_neighbour"]["cosine"]["top5"] for c in cs]
        ed1 = [c["test2_nearest_neighbour"]["edit"]["top1"] for c in cs]
        ed5 = [c["test2_nearest_neighbour"]["edit"]["top5"] for c in cs]
        out.append(f"| {g} | {cs[0]['units']} | {100*sum(cos1)/len(cos1):.1f} "
                   f"| {100*sum(cos5)/len(cos5):.1f} | {100*sum(ed1)/len(ed1):.1f} "
                   f"| {100*sum(ed5)/len(ed5):.1f} | {100*max(cos1):.1f} |")
    ref = rep["references"]
    out.append(f"| _ceiling: raw features, no codebook_ | - "
               f"| {100*ref['raw_features_no_codebook']['syllable_top1']:.1f} "
               f"| {100*ref['raw_features_no_codebook']['syllable_top5']:.1f} | - | - | - |")
    out.append(f"| _floor: duration only_ | - "
               f"| {100*ref['duration_only']['syllable_top1']:.1f} "
               f"| {100*ref['duration_only']['syllable_top5']:.1f} | - | - | - |")
    return "\n".join(out)


def paired() -> str:
    p = BIG / "paired-tests-big.json"
    if not p.exists():
        return "_(not run)_"
    rep = json.loads(p.read_text(encoding="utf-8"))
    out = ["| comparison | metric | left | right | delta | McNemar p | ants left wins |",
           "|---|---|---|---|---|---|---|"]
    for c in rep["comparisons"]:
        out.append(f"| {c['comparison']} | {c['metric']} "
                   f"| {100*c['pooled_left_accuracy']:.1f} "
                   f"| {100*c['pooled_right_accuracy']:.1f} "
                   f"| {c['pooled_delta_points']:+.1f} "
                   f"| {c['pooled_mcnemar']['p_value']:.4f} "
                   f"| {c['ants_where_left_wins']}/4 |")
    return "\n".join(out)


def corpus() -> str:
    p = BIG / "corpus-vowels.json"
    if not p.exists():
        return "_(not run)_"
    rep = json.loads(p.read_text(encoding="utf-8"))
    out = ["| pool | hours | F1 med | F2 med | /a/ rate of voiced frames | "
           "vowel boxes hit (a/e/i/o/u) |", "|---|---|---|---|---|---|"]
    for name, r in rep.items():
        b = r["vowel_box_hits"]
        out.append(f"| {name} | {r['pool_hours']:.2f} | {r['f1_median']:.0f} "
                   f"| {r['f2_median']:.0f} | {100*r['a_rate']:.2f}% | "
                   f"{b.get('a',0)}/{b.get('e',0)}/{b.get('i',0)}/{b.get('o',0)}/{b.get('u',0)} |")
    return "\n".join(out)


if __name__ == "__main__":
    rep = json.loads((BIG / "formants.json").read_text(encoding="utf-8"))
    for title, fn in (("HEADLINE", lambda: headline(rep)),
                      ("PER COLONY", lambda: per_colony(rep)),
                      ("VOWEL SPACE", lambda: vowel_space(rep)),
                      ("WHOLE CODEBOOK", lambda: whole_codebook(rep)),
                      ("CORPUS", corpus), ("KNOWLEDGE", knowledge), ("PAIRED", paired)):
        print(f"\n### {title}\n")
        print(fn())
