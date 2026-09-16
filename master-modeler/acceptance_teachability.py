#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

THE ACCEPTANCE TEST for MODEH (teachability.py).
================================================
Iddo's standing law: the builder does not grade himself. So this file does not
ask whether the organ ran; it asks whether the organ, run backwards over the
corpora ERAN has ACTUALLY been fed, reaches the verdicts the human record
already reached the hard way -- by Iddo's ear, by a provenance inquiry, by a
month of wasted training.

The expected verdicts live in corpora.json under 'expect'. teachability.py
NEVER reads that field. This file does.

    python acceptance_teachability.py                 # everything
    python acceptance_teachability.py --tuned         # only the tuned set
    python acceptance_teachability.py --heldout       # only the frozen set

TUNED vs HELD-OUT -- declared, not hidden:
  Two thresholds were changed AFTER seeing results on the first six corpora:
  n_eff_starved 1.5 -> 3.0, and the drift-floor control was added when t07
  disagreed. Those six are therefore the TUNED set and prove nothing on their
  own. The three corpora marked `held_out_validation` in corpora.json were run
  ONLY after the thresholds were frozen. Those are the honest evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import teachability as T                                          # noqa: E402

# The human record's words -> the verdict family the organ must land in.
# A corpus the record calls unusable may come back REJECT or STARVED: both mean
# 'do not train on this as it stands'. What must never happen is a corpus the
# record calls poison coming back ACCEPT, or the reverse.
FAMILY = {
    "REJECT": {"REJECT", "STARVED"},
    "STARVED": {"REJECT", "STARVED"},
    "ACCEPT": {"ACCEPT", "ACCEPT-UNVERIFIED", "WEAK"},
    "ACCEPT-ISH": {"ACCEPT", "ACCEPT-UNVERIFIED", "WEAK"},
}


def expected_family(expect: str):
    head = re.split(r"[ \-—]", expect.strip(), 1)[0].upper()
    if expect.upper().startswith("ACCEPT-ISH"):
        head = "ACCEPT-ISH"
    return head, FAMILY.get(head)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuned", action="store_true")
    ap.add_argument("--heldout", action="store_true")
    ap.add_argument("--scratch", default="")
    a = ap.parse_args()

    T._below_normal()
    reg = T.load_registry(a.scratch)
    ear = T.Ear()

    rows, passed, failed, skipped = [], 0, 0, 0
    for spec in reg["corpora"]:
        held = bool(spec.get("held_out_validation"))
        if a.tuned and held:
            continue
        if a.heldout and not held:
            continue
        exp = spec.get("expect", "")
        head, fam = expected_family(exp)
        v = T.judge(spec, reg, ear, verbose=False)
        got = v["verdict"]
        if v["n_clips"] == 0:
            state, skipped = "SKIP (no clips)", skipped + 1
        elif fam is None:
            state, skipped = "SKIP (no expectation)", skipped + 1
        elif got in fam:
            state, passed = "PASS", passed + 1
        else:
            state, failed = "FAIL", failed + 1
        rows.append((spec["id"], "held-out" if held else "tuned",
                     head, got, state, v))

    print("=" * 96)
    print("MODEH ACCEPTANCE -- the organ run backwards over what ERAN was fed")
    print("=" * 96)
    print(f"{'corpus':<17}{'set':<10}{'record says':<13}{'MODEH says':<20}"
          f"{'':<6}{'drift floor':<12}{'n_eff'}")
    for cid, kind, head, got, state, v in rows:
        d = v.get("drift")
        df = f"{d['floor'] * 100:.1f}%" if d else "-"
        print(f"{cid:<17}{kind:<10}{head:<13}{got:<20}{state:<6}{df:<12}"
              f"{v.get('n_eff_median')}")
    print("-" * 96)
    print(f"PASS {passed}   FAIL {failed}   SKIP {skipped}")
    hp = sum(1 for r in rows if r[1] == "held-out" and r[4] == "PASS")
    hn = sum(1 for r in rows if r[1] == "held-out" and r[4] in ("PASS", "FAIL"))
    if hn:
        print(f"held-out (thresholds frozen first): {hp}/{hn}")
    print("\nTHE TIME-ONLY CONTROL -- early vs late clips of the SAME unit.")
    print("A perfect corpus scores 50%: nothing but the syllable is in the audio.")
    for cid, kind, head, got, state, v in rows:
        d = v.get("drift")
        if not d:
            continue
        f = d["floor"]
        band = ("chance -- no 'when' channel at all" if f < 0.57 else
                "a sitting's own drift (mic, warmth, posture)" if f < 0.80 else
                "the clip's manufacture is readable straight off the audio")
        print(f"   {cid:<17}{f * 100:5.1f}%   {band}")
    out = HERE / "runs" / "acceptance.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        [{"corpus": c, "set": k, "record": h, "modeh": g, "state": s}
         for c, k, h, g, s, _ in rows], ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nwritten: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
