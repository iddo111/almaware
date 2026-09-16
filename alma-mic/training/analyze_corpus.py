"""alma-mic / training / analyze_corpus.py — is this corpus fit to train on?

Runs on the PC (stdlib only, no torch, nothing heavy). Answers one question before
a single GPU-hour is spent: how much of voice_corpus/ is REAL speech with a REAL
transcript, and how much is Whisper talking to itself?

WHY THIS MATTERS MORE THAN THE TRAINER
  Every label in voice_corpus/ was written by the same model we are about to
  train. Fine-tuning a model on its own output is self-distillation: it sharpens
  what the model already believes, including the things it believes wrongly. The
  known failure mode of Whisper is hallucinating stock phrases over silence or
  noise - "תודה", "כתוביות", "Thank you." - and those labels are poison. Train on
  them and the model learns to emit them MORE. That is degradation, and no amount
  of clever optimisation undoes a bad target.

  So we measure first, and we throw away aggressively.

    python training/analyze_corpus.py
    python training/analyze_corpus.py --json report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import wave

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(os.path.dirname(HERE), "voice_corpus")
MANIFEST = os.path.join(CORPUS, "corpus.jsonl")

# Phrases Whisper emits when it has nothing to transcribe. Trained on YouTube,
# it falls back to subtitle boilerplate. Any utterance that is ONLY one of these
# is assumed hallucinated unless the audio is long and loud.
HALLUCINATION = [
    "תודה", "תודה רבה", "תודה על הצפייה", "כתוביות", "תרגום", "עריכה",
    "בהצלחה", "להתראות", "שלום", "הכתוביות", "עמותת", "אבי", "המשך",
    "thank you", "thanks for watching", "thank you for watching",
    "subscribe", "bye", "you", "okay", "ok", "hello", "hi", "so",
    "please subscribe", "amara.org", "www.", "http",
]
HALLU_RE = re.compile(
    r"^[\s‏‎‫‬.,!?\-–—״\"']*(" +
    "|".join(re.escape(h) for h in HALLUCINATION) +
    r")[\s‏‎.,!?\-–—״\"']*$", re.IGNORECASE)

HEB = re.compile(r"[֐-׿]")
LAT = re.compile(r"[A-Za-z]")


def degenerate(t: str) -> str | None:
    """Detect Whisper's repetition collapse. Returns a reason, or None if clean.

    THIS IS THE MOST IMPORTANT FILTER IN THE FILE. Measured on the real corpus,
    the model does not fail on Iddo's voice by mishearing a word - it fails by
    falling into a loop and never getting out:

        "...מותה פאקאקאקאקאקאקאקאקאקאקאקאקא"
        "דודשן, דודשן, דודשן, דודשן, דודשן, דודשן, דודשן."
        "ל ל ל ל ל ל ל ל"

    Those are labels sitting in voice_corpus/ right now. Train on them and you are
    explicitly teaching the model that looping is the correct response to hard
    audio - it would get MORE likely, not less. That is the degradation Iddo asked
    me to make impossible, and no eval gate downstream can repair a target this bad.
    """
    s = (t or "").strip()
    if not s:
        return None
    toks = s.split()
    # a word repeated 4+ times in a row
    run = best = 1
    for i in range(1, len(toks)):
        run = run + 1 if toks[i] == toks[i - 1] else 1
        best = max(best, run)
    if best >= 4:
        return "repeated word x%d" % best
    # low vocabulary over a long utterance
    if len(toks) >= 8 and len(set(toks)) / len(toks) < 0.34:
        return "vocabulary collapse (%d unique of %d)" % (len(set(toks)), len(toks))
    # character-level loops inside one long token: פאקאקאקאקאקא
    # Periodicity test: if shifting the token by p characters makes it line up with
    # itself almost everywhere, it is a loop of period p. Catches קא-קא-קא and also
    # single-character runs, which a naive prefix test misses.
    for tok in toks:
        n = len(tok)
        if n < 8:
            continue
        for p in range(1, 5):
            if n // p < 4:
                break
            hits = sum(1 for i in range(n - p) if tok[i] == tok[i + p])
            if hits / max(n - p, 1) > 0.85:
                return "character loop (period %d) in one token" % p
    # the same short token dominating
    if len(toks) >= 6:
        top = collections.Counter(toks).most_common(1)[0][1]
        if top / len(toks) >= 0.6:
            return "one token is %d%% of the utterance" % int(100 * top / len(toks))
    return None


def dur(path: str) -> float:
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


def script_of(t: str) -> str:
    h, l = len(HEB.findall(t)), len(LAT.findall(t))
    if h and l:
        return "mixed"
    if h:
        return "he"
    if l:
        return "en"
    return "none"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    if not os.path.exists(MANIFEST):
        print("no corpus at %s" % MANIFEST)
        return 1

    rows = []
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    total = len(rows)
    texts = collections.Counter()
    langs = collections.Counter()
    scripts = collections.Counter()
    reasons = collections.Counter()
    kept, secs_all, secs_kept = [], 0.0, 0.0
    missing = 0

    for r in rows:
        raw = (r.get("text") or "")
        # strip the RTL control marks the recogniser prepends; they are not speech
        t = raw.replace("‫", "").replace("‏", "").replace("‬", "").strip()
        wav = os.path.join(CORPUS, r.get("wav") or "")
        d = dur(wav) if os.path.exists(wav) else 0.0
        if not os.path.exists(wav):
            missing += 1
        secs_all += d
        texts[t] += 1
        langs[r.get("lang") or "?"] += 1
        scripts[script_of(t)] += 1

        why = None
        if not t:
            why = "empty text"
        elif d <= 0.0:
            why = "wav missing or unreadable"
        elif HALLU_RE.match(t) and d < 2.5:
            why = "stock phrase over short audio (hallucination)"
        elif len(t) < 2:
            why = "text shorter than 2 chars"
        elif d < 0.35:
            why = "audio under 0.35 s"
        elif degenerate(t):
            why = "repetition collapse: " + degenerate(t)
        elif len(t) / max(d, 0.01) > 28:
            why = "impossible speech rate (>28 chars/s)"
        elif script_of(t) == "none":
            why = "no letters in transcript"
        if why:
            reasons[why] += 1
        else:
            kept.append((r, t, d))
            secs_kept += d

    # how repetitive is it? a corpus of 400 x "תודה" teaches nothing
    dup_mass = sum(c for t, c in texts.items() if c > 1)
    uniq_kept = len({t for _r, t, _d in kept})

    print("ALMA-MIC  CORPUS QUALITY")
    print("=" * 72)
    print("utterances on disk        : %d  (%.2f h of audio)" % (total, secs_all / 3600))
    print("wav files missing         : %d" % missing)
    print("unique transcripts        : %d of %d  (%.0f%% are repeats)"
          % (len(texts), total, 100.0 * dup_mass / max(total, 1)))
    print("language tag              : %s" % dict(langs.most_common(6)))
    print("script actually present   : %s" % dict(scripts.most_common(6)))
    print("-" * 72)
    print("REJECTED %d of %d" % (total - len(kept), total))
    for why, n in reasons.most_common():
        print("   %-46s %6d" % (why, n))
    print("-" * 72)
    print("USABLE                    : %d utterances, %.2f h, %d unique texts"
          % (len(kept), secs_kept / 3600, uniq_kept))
    print()
    print("most repeated surviving transcripts:")
    ktext = collections.Counter(t for _r, t, _d in kept)
    for t, n in ktext.most_common(12):
        print("   %5d x  %s" % (n, t[:60]))

    print()
    print("VERDICT")
    hours = secs_kept / 3600
    if hours < 1:
        print("  under 1 h of usable speech. Full fine-tuning of an 809M-parameter")
        print("  model on this will overfit hard. Keep collecting.")
    elif hours < 5:
        print("  %.1f h usable. Enough for a CAREFUL full fine-tune (low LR, few" % hours)
        print("  epochs, anti-forgetting regulariser, strict eval gate) - not enough")
        print("  to train freely. The gate is what makes this safe.")
    else:
        print("  %.1f h usable - a solid speaker-adaptation set." % hours)
    print()
    print("  NOTE: every label here was written by the model we are training.")
    print("  Self-training cannot teach it words it already gets wrong. Real gains")
    print("  need a stronger TEACHER to relabel (training/relabel_teacher.py) or")
    print("  your own corrections. See training/README.md.")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"total": total, "usable": len(kept),
                       "hours_all": secs_all / 3600, "hours_usable": secs_kept / 3600,
                       "unique_usable": uniq_kept, "rejected": dict(reasons),
                       "langs": dict(langs)}, f, ensure_ascii=False, indent=2)
        print("\nwrote %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
