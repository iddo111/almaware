# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / reconcile.py -- THE GOLD LABELS. His corrections, mined.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

THE IDEA
--------
Every time the mic types a sentence and Iddo FIXES it before sending, he has
handed us a labelled pair for free: the audio, plus the right answer. A
correction is the only label in this system that is not the model's own
opinion -- it is Iddo telling the model it was WRONG.

WHERE THE TWO HALVES LIVE
-------------------------
  the ASR half  : keshev-next/trial.log -> (wav, asr_text, clock)   [collect.py]
  the truth half: the text he ACTUALLY SENT, in the Claude Code session
                  transcripts ~/.claude/projects/D--CLAUDE/*.jsonl, each
                  message carrying an ISO timestamp.

THE TRAP THIS FILE EXISTS TO AVOID (measured 2026-09-12, the first version
of this file walked straight into it)
-----------------------------------------------------------------------
KESHEV types MANY segments into ONE message before he presses send. So a
single 2-second wav very often corresponds to a FRAGMENT of the sent text,
not to all of it. Matching the fragment against the whole message produces
pairs like:

    ASR   : "דשבור לא עובד."
    "truth": "הלינק שנתתת לדשבורד לא עובד, מה?"

which is not a correction at all -- it is one clip paired with a sentence
containing words that clip never contained. Training on it teaches the model
to hallucinate the extra words. That is the same class of bad label that sank
the previous personal LoRA (0/13 names, CER 28.5% vs 18.0% for the baseline).

THE GUARD: a real correction preserves LENGTH. He fixes a word, he does not
triple the sentence. So a candidate is rejected unless

    min(len(asr), len(truth)) / max(len(asr), len(truth))  >=  LEN_RATIO

Fragment-of-a-longer-message fails this immediately. The rejects are COUNTED
and reported, never silently dropped -- the count is the honest measure of how
much of the backlog this method can actually label.

    identical (sim >= HI)                -> CONFIRMED. He accepted it verbatim.
                                            Real, but the model already agreed.
    close, same length (HI > sim >= LO)  -> CORRECTION. The gold.
    close, different length              -> FRAGMENT. Rejected, counted.
    far                                  -> a different sentence. Rejected.

When in doubt this drops the row. A wrong label is worse than a missing one.
"""
from __future__ import annotations
import argparse, datetime, difflib, glob, io, json, os, re, sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJ = os.path.expanduser(r"~\.claude\projects\D--CLAUDE")
SIM_HI, SIM_LO = 0.995, 0.55
LEN_RATIO = 0.80          # a correction preserves length; a fragment does not
WINDOW_S = 180            # he sends within about three minutes of dictating

# THE SECOND TRAP, measured 2026-09-12 by reading the survivors out loud.
# With the length guard in place 14 "corrections" remained, and inspection
# showed most were COINCIDENCE, not correction:
#     "תודה."  -> "דפה."      (x3)
#     "ששמי."  -> "שיחה."
#     "יאלו."  -> "הלו."
# Two short Hebrew words of equal length share letters by chance, and
# SequenceMatcher happily scores that 0.60-0.67. Below this many characters a
# similarity score is not evidence of anything. Only ~3 of the 14 survived a
# human read ("תודה רבה, דרקס." -> "תודה רבה, אדוני." is a real one).
# So: a correction must be long enough for the match to mean something.
MIN_CHARS = 12

SKIP_SHAPES = ("<command-message>", "<command-name>", "<local-command",
               "<system-reminder>", "Base directory for this skill",
               "# Workflow authoring", "Caveat: The messages below")


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def len_ratio(a, b):
    la, lb = len(norm(a)), len(norm(b))
    if not la or not lb:
        return 0.0
    return min(la, lb) / float(max(la, lb))


def load_sent(since=None):
    out = []
    for p in glob.glob(os.path.join(PROJ, "*.jsonl")):
        try:
            with io.open(p, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if '"type":"user"' not in ln and '"type": "user"' not in ln:
                        continue
                    try:
                        d = json.loads(ln)
                    except Exception:
                        continue
                    if d.get("type") != "user":
                        continue
                    c = (d.get("message") or {}).get("content")
                    if isinstance(c, str):
                        t = c
                    elif isinstance(c, list):
                        t = " ".join(x.get("text", "") for x in c
                                     if isinstance(x, dict) and x.get("type") == "text")
                    else:
                        continue
                    t = norm(t)
                    if not t or len(t) < 3 or len(t) > 600:
                        continue
                    if any(k in t for k in SKIP_SHAPES):
                        continue
                    ts = d.get("timestamp")
                    if not ts:
                        continue
                    try:
                        ep = datetime.datetime.fromisoformat(
                            ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        continue
                    if since and ep < since:
                        continue
                    out.append((ep, t))
        except OSError:
            continue
    out.sort()
    return out


def wav_epoch(name):
    m = re.match(r"(\d{8})-(\d{6})-(\d{3})\.wav$", name)
    if not m:
        return None
    try:
        dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        return dt.timestamp() + int(m.group(3)) / 1000.0
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=r"D:\CLAUDE\keshev-autotrain\data\asr_pairs.jsonl")
    ap.add_argument("--out", default=r"D:\CLAUDE\keshev-autotrain\data\gold_pairs.jsonl")
    ap.add_argument("--window", type=float, default=WINDOW_S)
    ap.add_argument("--len-ratio", type=float, default=LEN_RATIO)
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    a = ap.parse_args()

    rows = []
    with io.open(a.pairs, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    print("[reconcile] asr utterances: %d" % len(rows))

    eps = [wav_epoch(r["wav"]) for r in rows]
    lo = min([e for e in eps if e], default=None)
    sent = load_sent(since=(lo - 600) if lo else None)
    print("[reconcile] his sent messages in range: %d" % len(sent))

    n_corr = n_conf = n_far = n_frag = n_nots = n_short = 0
    out = []
    for r, ep in zip(rows, eps):
        if not ep:
            n_nots += 1
            continue
        best, bt = 0.0, None
        for (sep, st) in sent:
            if sep < ep - 5:
                continue
            if sep > ep + a.window:
                break
            s = sim(r["text"], st)
            if s > best:
                best, bt = s, st
        if bt is None or best < SIM_LO:
            n_far += 1
            continue
        if best >= SIM_HI:
            n_conf += 1
            out.append(dict(r, truth=r["text"], source="confirmed", sim=round(best, 4)))
            continue
        lr = len_ratio(r["text"], bt)
        if lr < a.len_ratio:
            n_frag += 1                 # one clip vs a multi-segment message
            continue
        if max(len(norm(r["text"])), len(norm(bt))) < a.min_chars:
            n_short += 1                # too short for a similarity score to mean anything
            continue
        n_corr += 1
        out.append(dict(r, truth=bt, source="correction",
                        sim=round(best, 4), len_ratio=round(lr, 3)))

    print("[reconcile] CORRECTIONS (gold)        : %d" % n_corr)
    print("[reconcile] confirmed (verbatim)      : %d" % n_conf)
    print("[reconcile] REJECTED, fragment-of-msg : %d   <- trap 1, counted" % n_frag)
    print("[reconcile] REJECTED, too short       : %d   <- trap 2, counted" % n_short)
    print("[reconcile] no match / different      : %d" % n_far)
    print("[reconcile] unusable timestamp        : %d" % n_nots)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("[reconcile] wrote %d -> %s" % (len(out), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
