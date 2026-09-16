# -*- coding: utf-8 -*-
"""KESHEV AUTOTRAIN / collect.py -- turn what is already on disk into (audio, text) pairs.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

THE BACKLOG PROBLEM, AND THE ALIGNMENT THAT SOLVES IT
-----------------------------------------------------
keshev-next dumps every segment it processes to `segments/<YYYYmmdd-HHMMSS-mmm>.wav`
and prints ONE `[segment]` line per segment to trial.log. The line carries
`bytes=N` (the pcm length) and the text; it does NOT carry the wav filename.

A naive zip of the two ordered lists matches 218/4000 -- because segments that are
rejected EARLY (too-quiet, vad SKIP) print a line but never reach the dump. So the
wav pointer must advance only on lines that actually dumped one.

Measured rule (app/main.py): the dump happens at the top of process_full_segment,
AFTER the rms floor and vad endpoint checks have already returned. Those early
returns print lines containing " SKIP". Every other [segment] line dumped a wav.

We therefore walk trial.log in order, advance the wav cursor only on non-SKIP
lines, and REQUIRE size == bytes + 44 (the wav header) as a checksum. A mismatch
resynchronises rather than emitting a wrong pair: a wrong label is worse than no
label, because training on it teaches the error (that is what sank the last LoRA).

WHAT COUNTS AS A USABLE PAIR
----------------------------
Only `decode=ok` lines with real text. Those are the utterances that passed the
energy gate, VAD, the hallucination guard, the confidence floor and the language
route -- i.e. what the system actually believed and typed.

Their label is the ASR's own output, so this is WEAK (self-labelled, "circular")
data and it is tagged `source="asr"`. Circular labels are exactly what sank the
previous LoRA. They are collected for CONTEXT and for the full fine-tune's
language-model side, never presented as gold. The gold comes from reconcile.py.
"""
from __future__ import annotations
import argparse, json, os, re, sys, io, unicodedata

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

KESHEV = r"D:\CLAUDE\keshev-next"
SEGDIR = os.path.join(KESHEV, "segments")
TRIAL  = os.path.join(KESHEV, "trial.log")
OUT    = r"D:\CLAUDE\keshev-autotrain\data"

WAV_HEADER = 44
# a [segment] line, with or without the logstamp HH:MM:SS prefix
LINE = re.compile(r"^(?:(\d\d:\d\d:\d\d) )?\[segment\] bytes=(\d+) ")
TEXT = re.compile(r" text='(.*)'\s*$")


def _unesc(s: str) -> str:
    """trial.log writes text with ascii() -- backslash-u escapes. Bring it back."""
    try:
        return s.encode("ascii", "backslashreplace").decode("unicode_escape")
    except Exception:
        return s


def parse_trial(path):
    """Yield (idx, ts, nbytes, dumped, ok, text) in file order."""
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for i, ln in enumerate(fh):
            m = LINE.match(ln)
            if not m:
                continue
            ts, nb = m.group(1), int(m.group(2))
            # early returns (rms floor / vad) print " SKIP" and never dumped a wav
            dumped = " SKIP" not in ln
            ok = "decode=ok" in ln
            txt = ""
            if ok:
                t = TEXT.search(ln.rstrip("\n"))
                if t:
                    txt = _unesc(t.group(1)).strip()
            yield i, ts, nb, dumped, ok, txt


def align(verbose=False, limit=None):
    """Walk both ordered lists; advance the wav cursor only on dumping lines."""
    # os.scandir carries the size in the directory entry itself -- one syscall
    # per file instead of a listdir plus 48,851 separate stat() calls, which on
    # this directory is the difference between seconds and minutes.
    ents = []
    with os.scandir(SEGDIR) as it:
        for e in it:
            if e.name.endswith(".wav"):
                try: ents.append((e.name, e.stat().st_size))
                except OSError: pass
    ents.sort()
    wavs = [n for n, _ in ents]
    sizes = dict(ents)

    lines = list(parse_trial(TRIAL))
    n_dump = sum(1 for _ in lines if _[3])

    pairs, hit, miss, resync = [], 0, 0, 0
    ci = 0                                   # cursor into wavs
    for (_i, ts, nb, dumped, ok, txt) in lines:
        if not dumped:
            continue
        want = nb + WAV_HEADER
        # look ahead a little: a dropped/overwritten wav must not desync the rest
        found = -1
        for j in range(ci, min(ci + 24, len(wavs))):
            if sizes.get(wavs[j]) == want:
                found = j
                break
        if found < 0:
            miss += 1
            continue
        if found != ci:
            resync += 1
        hit += 1
        ci = found + 1
        if ok and txt:
            pairs.append({"wav": wavs[found], "text": txt, "ts": ts,
                          "bytes": nb, "source": "asr"})
        if limit and len(pairs) >= limit:
            break

    return {"wavs": len(wavs), "seg_lines": len(lines), "dumping_lines": n_dump,
            "aligned": hit, "unmatched": miss, "resyncs": resync,
            "pairs": pairs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["audit", "build"])
    ap.add_argument("--out", default=os.path.join(OUT, "asr_pairs.jsonl"))
    a = ap.parse_args()

    r = align()
    rate = (100.0 * r["aligned"] / r["dumping_lines"]) if r["dumping_lines"] else 0.0
    print(f"[collect] wav files on disk      : {r['wavs']}")
    print(f"[collect] [segment] lines        : {r['seg_lines']}")
    print(f"[collect]   of those, dumped a wav: {r['dumping_lines']}")
    print(f"[collect] ALIGNED (size-verified) : {r['aligned']}  ({rate:.1f}%)")
    print(f"[collect]   unmatched (skipped)   : {r['unmatched']}")
    print(f"[collect]   resyncs               : {r['resyncs']}")
    print(f"[collect] USABLE ASR PAIRS        : {len(r['pairs'])}   (weak/self-labelled)")

    if a.cmd == "build":
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with io.open(a.out, "w", encoding="utf-8") as fh:
            for p in r["pairs"]:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"[collect] wrote {len(r['pairs'])} -> {a.out}")


if __name__ == "__main__":
    main()
