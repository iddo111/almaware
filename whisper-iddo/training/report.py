"""Collect run histories into the WER-per-epoch curve and the final tables.

Also measures the defect Iddo actually complained about, which no WER number
captures on its own: Whisper's subtitle-boilerplate reflex. The corpus that this
model was NOT trained on contained "תודה רבה." as the label on 194 clips and
"תודה." on 123 more -- hallucinations over silence. If fine-tuning made the
model emit those MORE often, WER could still improve while the product got
worse, so it is counted directly.
"""
from __future__ import annotations

import glob
import json
import os
import sys

STOCK = ["תודה רבה", "תודה על הצפייה", "תודה", "כתוביות",
         "thanks for watching", "thank you", "subtitles", "amara.org",
         "please subscribe", "bye."]


def hall_rate(path):
    """Fraction of hypotheses that are ONLY a stock phrase."""
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    n = 0
    for r in rows:
        h = r["hyp"].strip().lower().rstrip(".!? ")
        if h and any(h == s.lower().rstrip(".!? ") for s in STOCK):
            n += 1
    return n / max(1, len(rows)), len(rows)


def curve(run_dir):
    p = os.path.join(run_dir, "history.json")
    if not os.path.exists(p):
        return None
    hist = json.load(open(p, encoding="utf-8"))
    return hist


def main():
    runs = sys.argv[1:] or sorted(glob.glob(os.path.expanduser("~/whisper-iddo/runs/ft*")))
    for rd in runs:
        h = curve(rd)
        if not h:
            print(f"{rd}: no history yet")
            continue
        print(f"\n=== {rd}")
        print(f"{'step':>6} {'epoch':>6} {'enc':>8} {'tierA':>8} {'LID':>6} "
              f"{'fl_he':>8} {'fl_en':>8} {'elig':>5} {'peak':>6} {'min':>6}")
        for e in h:
            r = e["res"]
            print(f"{e['step']:>6} {e['epoch']:>6.2f} {e.get('encoder','-'):>8} "
                  f"{r['iddo_tierA']['wer']*100:>8.2f} "
                  f"{r['iddo_tierA']['lid_acc']*100:>6.1f} "
                  f"{r.get('fleurs_he',{}).get('wer',float('nan'))*100:>8.2f} "
                  f"{r.get('fleurs_en',{}).get('wer',float('nan'))*100:>8.2f} "
                  f"{str(e.get('eligible','-')):>5} "
                  f"{e.get('peak_gib',0):>6.1f} {e.get('minutes',0):>6.1f}")
            if e.get("guard"):
                print(f"       guard: {'; '.join(e['guard'])}")
        s = os.path.join(rd, "summary.json")
        if os.path.exists(s):
            sm = json.load(open(s, encoding="utf-8"))
            print(f"  best: {sm['best']}  peak {sm['peak_gib']:.1f} GiB  "
                  f"wall {sm['wall_minutes']:.1f} min")

    hd = os.path.expanduser("~/whisper-iddo/hyps")
    if os.path.isdir(hd):
        print("\n=== stock-phrase hallucination rate (hyp is ONLY a stock phrase)")
        for f in sorted(glob.glob(os.path.join(hd, "*.jsonl"))):
            r, n = hall_rate(f)
            if n:
                print(f"  {r*100:5.2f}%  ({n:5d})  {os.path.basename(f)}")


if __name__ == "__main__":
    main()
