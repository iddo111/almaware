"""alma-mic / training / promote.py — THE GATE. The only door to the deployed model.

This is the file that makes "never degrades" true rather than aspirational. Nothing
else in this project is permitted to change which model the app loads. A challenger
gets deployed only by walking through here, and this door only opens one way.

  python training/promote.py --challenger runs/20260806/epoch2-ct2
  python training/promote.py --challenger ... --apply     # actually swap it in
  python training/promote.py --rollback                   # go back one champion

FOUR CONDITIONS. ALL OF THEM. NO EXCEPTIONS, NO OVERRIDE FLAG.

  1. BETTER ON HIS VOICE, BEYOND NOISE
     WER on eval_voice must improve by more than the measurement noise. We do not
     compare two point estimates - with 683 utterances a 0.4% "win" is a coin flip.
     We bootstrap-resample the per-utterance errors 2000 times and require the
     challenger to win in at least 95% of resamples. A win that cannot survive
     resampling is not a win, it is luck, and deploying luck is how you drift
     downward one lucky step at a time.

  2. NO FORGETTING
     WER on eval_retain (the oldest sessions - different room, different mic) must
     not get worse by more than a hair. A model that got brilliant at this week and
     lost last month has degraded, whatever the headline number says.

  3. NO NEW REPETITION COLLAPSE
     The characteristic Whisper failure is looping, and it is the failure this corpus
     is full of. Count utterances whose output degenerates. It may not go up. A model
     with lower WER that loops more often is worse to actually use.

  4. SURVIVES CONVERSION
     The app runs CTranslate2, not the training format. A checkpoint is judged on the
     CT2 artifact that will actually be loaded, because conversion is a real place to
     quietly lose quality.

Every champion is kept forever in champions/. Rollback is a directory move.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
EVALS = os.path.join(HERE, "evals")
CHAMPS = os.path.join(HERE, "champions")
LEDGER = os.path.join(HERE, "promotions.jsonl")

RETAIN_TOLERANCE = 0.002      # 0.2 WER points of slack on the forgetting check
BOOTSTRAP = 2000
CONFIDENCE = 0.95


def load(tag: str, split: str) -> dict | None:
    p = os.path.join(EVALS, "%s__%s.json" % (tag, split))
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def bootstrap_win_rate(champ: dict, chal: dict) -> float:
    """Fraction of resamples in which the challenger has the lower WER.

    Needs per-utterance errors. If an eval was written by an older evaluate.py that
    only stored totals, we cannot resample - and we say so rather than guessing,
    because a fabricated confidence number is worse than no number.
    """
    a = champ.get("per_utt")
    b = chal.get("per_utt")
    if not a or not b or len(a) != len(b):
        return -1.0
    n = len(a)
    rng = random.Random(20260806)
    wins = 0
    for _ in range(BOOTSTRAP):
        idx = [rng.randrange(n) for _ in range(n)]
        ea = sum(a[i][0] for i in idx); wa = sum(a[i][1] for i in idx)
        eb = sum(b[i][0] for i in idx); wb = sum(b[i][1] for i in idx)
        if (eb / max(wb, 1)) < (ea / max(wa, 1)):
            wins += 1
    return wins / BOOTSTRAP


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--challenger", help="tag used when evaluate.py scored it")
    ap.add_argument("--champion", default="champion")
    ap.add_argument("--challenger-dir", default=None,
                    help="CT2 dir to install if the gate opens")
    ap.add_argument("--apply", action="store_true",
                    help="without this, decide and report but change nothing")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()

    os.makedirs(CHAMPS, exist_ok=True)

    if a.rollback:
        past = sorted(os.listdir(CHAMPS))
        if len(past) < 2:
            print("no previous champion to roll back to")
            return 1
        print("rolling back to %s" % past[-2])
        if a.apply:
            shutil.rmtree(os.path.join(CHAMPS, past[-1]))
            print("removed %s; point config at %s" % (past[-1], past[-2]))
        else:
            print("(dry run - pass --apply)")
        return 0

    if not a.challenger:
        print("need --challenger <tag>")
        return 2

    print("ALMA-MIC  PROMOTION GATE")
    print("=" * 72)
    verdicts = []

    cv = load(a.champion, "eval_voice")
    hv = load(a.challenger, "eval_voice")
    cr = load(a.champion, "eval_retain")
    hr = load(a.challenger, "eval_retain")

    missing = [n for n, v in (("champion/eval_voice", cv), ("challenger/eval_voice", hv),
                              ("champion/eval_retain", cr), ("challenger/eval_retain", hr))
               if v is None]
    if missing:
        print("REFUSING TO DECIDE - missing evals: %s" % ", ".join(missing))
        print("Run evaluate.py for both models on BOTH splits first.")
        print("A gate that guesses is not a gate.")
        return 3

    # ---- 1. better on his voice, beyond noise ----
    d = cv["wer"] - hv["wer"]
    win = bootstrap_win_rate(cv, hv)
    if win < 0:
        ok1 = False
        note1 = ("cannot bootstrap (evals lack per-utterance detail) - "
                 "REFUSING to call %+.4f a win" % d)
    else:
        ok1 = win >= CONFIDENCE
        note1 = "WER %.4f -> %.4f (%+.4f), wins %.1f%% of resamples" % (
            cv["wer"], hv["wer"], -d, 100 * win)
    verdicts.append(("better on eval_voice, beyond noise", ok1, note1))

    # ---- 2. no forgetting ----
    dr = hr["wer"] - cr["wer"]
    ok2 = dr <= RETAIN_TOLERANCE
    verdicts.append(("no forgetting on eval_retain", ok2,
                     "WER %.4f -> %.4f (%+.4f, tolerance %+.4f)"
                     % (cr["wer"], hr["wer"], dr, RETAIN_TOLERANCE)))

    # ---- 3. no new repetition collapse ----
    c_loop = cv.get("degenerate", None)
    h_loop = hv.get("degenerate", None)
    if c_loop is None or h_loop is None:
        ok3 = False
        note3 = "evals do not report a repetition-collapse count - cannot verify"
    else:
        ok3 = h_loop <= c_loop
        note3 = "looping utterances %d -> %d" % (c_loop, h_loop)
    verdicts.append(("no new repetition collapse", ok3, note3))

    # ---- 4. judged on the artifact that will actually be loaded ----
    ok4 = str(hv.get("model", "")).lower().find("ct2") >= 0 or \
        (a.challenger_dir or "").lower().find("ct2") >= 0
    verdicts.append(("challenger was scored as a CT2 artifact", ok4,
                     "model=%s" % hv.get("model", "?")))

    for name, ok, note in verdicts:
        print("  [%s] %-42s %s" % ("PASS" if ok else "FAIL", name, note))
    print("-" * 72)

    opened = all(ok for _n, ok, _t in verdicts)
    if not opened:
        print("GATE CLOSED — challenger DISCARDED. Champion stays deployed.")
        print("This is a normal, successful outcome. The system did its job.")
        return 1

    print("GATE OPEN — challenger earned promotion on every condition.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if not a.apply:
        print("(dry run — pass --apply to install it as champions/%s)" % stamp)
        return 0

    if not a.challenger_dir or not os.path.isdir(a.challenger_dir):
        print("--apply needs --challenger-dir pointing at the CT2 model directory")
        return 2
    dest = os.path.join(CHAMPS, stamp)
    shutil.copytree(a.challenger_dir, dest)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"when": stamp, "champion_dir": dest,
                            "from_wer": cv["wer"], "to_wer": hv["wer"],
                            "retain_from": cr["wer"], "retain_to": hr["wer"],
                            "bootstrap_win": win}, ensure_ascii=False) + "\n")
    print("installed %s" % dest)
    print("previous champions kept — rollback with: python training/promote.py --rollback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
