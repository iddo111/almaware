"""Print the per-ant, per-codebook-size table from reports/discrimination.json."""
from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path("reports")
ORDER = ("64", "128", "256", "control-human-only-64")


def row(name: str, ant: str, data: dict) -> str:
    q = data.get("quantisation_error_by_source", {})
    human = q.get("human_speech", {}).get("error_after")
    syll = q.get("syllable", {}).get("error_after")
    s = data["syllable_heldout"]
    sq = data.get("syllable_heldout_quantised_features", {})
    w = data["words_leave_one_base_out"]
    f = data["frame_agreement_heldout"]
    return (
        f"{name:>22} {ant:<6} {data['units']:>4} "
        f"{data.get('heldout_error_after', float('nan')):>7.4f} "
        f"{(human if human is not None else float('nan')):>7.4f} "
        f"{(syll if syll is not None else float('nan')):>7.4f} "
        f"{s['top1'] * 100:>6.1f} {s['top5'] * 100:>6.1f} "
        f"{sq.get('top1', float('nan')) * 100:>6.1f} "
        f"{w['top1'] * 100:>6.1f} {w['top5'] * 100:>6.1f} "
        f"{f['nmi_sqrt']:>6.3f} {f['units_used']:>5}/{data['units']}"
    )


def main() -> None:
    report = json.loads((REPORTS / "discrimination.json").read_text(encoding="utf-8"))
    header = (
        f"{'colony':>22} {'ant':<6} {'k':>4} {'QEall':>7} {'QEhum':>7} {'QEsyl':>7} "
        f"{'syl@1':>6} {'syl@5':>6} {'sylQ1':>6} {'wrd@1':>6} {'wrd@5':>6} "
        f"{'NMI':>6} {'used':>9}"
    )
    print(header)
    print("-" * len(header))
    colonies = report["colonies"]
    for name in list(ORDER) + [n for n in colonies if n not in ORDER]:
        if name not in colonies:
            continue
        for ant, data in colonies[name].items():
            print(row(name, ant, data))
        print()
    print("untrained codebooks (k-means round-zero init, same seeds):")
    for units, ants in report["untrained_codebook_control"].items():
        for ant, data in ants.items():
            print(row(f"untrained-{units}", ant, data))
        print()
    ref = report["reference_no_codebook"]
    print("no-codebook reference (raw 14-dim ant features):")
    print(f"  syllables heldout  top1={ref['syllable_heldout']['top1'] * 100:.1f}%  "
          f"top5={ref['syllable_heldout']['top5'] * 100:.1f}%  "
          f"chance={ref['syllable_heldout']['chance'] * 100:.1f}%")
    w = ref["words_leave_one_base_out"]
    print(f"  words LOBO         top1={w['top1'] * 100:.1f}%  top5={w['top5'] * 100:.1f}%  "
          f"chance={w['chance'] * 100:.1f}%")


if __name__ == "__main__":
    main()
