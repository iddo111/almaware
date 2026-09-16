# -*- coding: utf-8 -*-
"""Pair tonight's dumped segment WAVs with the OLD system's verdict in trial.log.

A wav is written for EVERY segment that reaches the decoder (main.py line ~339),
BEFORE the decode; the matching log line is printed right after. The decode
worker is strictly FIFO and single-threaded, so wavs and log lines are in the
same order. `bytes=` is carried in both -> a two-pointer alignment with resync.
"""
import json, os, re, sys, wave
from pathlib import Path

SEG = Path(r"D:/CLAUDE/keshev-next/segments")
LOG = Path(r"D:/CLAUDE/keshev-next/trial.log")
OUT = Path(r"D:/CLAUDE/keshev-6/state/night.jsonl")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "20260903-17"

wavs = sorted(p for p in SEG.glob("20260903-*.wav") if p.name >= SINCE)
wavinfo = []
for p in wavs:
    try:
        with wave.open(str(p)) as w:
            n = w.getnframes() * 2
            wavinfo.append((p.name, n, round(w.getnframes() / w.getframerate(), 3)))
    except Exception:
        pass

RE_SEG = re.compile(r"^\[segment\] bytes=(\d+) secs=[\d.]+ peak_rms=(\d+) gate=([\d.]+)/(PASS|BLOCK)(?: lp=(-?[\d.]+))? decode=(ok|empty|fail|-)(?: route=(\S+) text=(.*))?$")
RE_CONF = re.compile(r"^\[confidence\] dropped \((\d+) bytes, lp=(-?[\d.]+)\)$")

events = []
with LOG.open(encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.rstrip("\n").rstrip("\r")
        m = RE_SEG.match(line)
        if m:
            events.append({"bytes": int(m.group(1)), "peak_rms": int(m.group(2)),
                           "gate": float(m.group(3)), "gate_v": m.group(4),
                           "lp": float(m.group(5)) if m.group(5) else None,
                           "decode": m.group(6), "route": m.group(7),
                           "text": m.group(8) or ""})
            continue
        m = RE_CONF.match(line)
        if m:
            events.append({"bytes": int(m.group(1)), "peak_rms": None, "gate": None,
                           "gate_v": "PASS", "lp": float(m.group(2)),
                           "decode": "lowconf", "route": None, "text": ""})

# align from the END (tonight is the tail of both lists)
i, j = len(wavinfo) - 1, len(events) - 1
pairs = []
misses = 0
while i >= 0 and j >= 0:
    if wavinfo[i][1] == events[j]["bytes"]:
        pairs.append((wavinfo[i], events[j])); i -= 1; j -= 1
    else:
        # resync: look ahead up to 5 in the log for the wav's byte count
        found = -1
        for k in range(1, 6):
            if j - k >= 0 and events[j - k]["bytes"] == wavinfo[i][1]:
                found = j - k; break
        if found >= 0:
            pairs.append((wavinfo[i], events[found])); i -= 1; j = found - 1
        else:
            misses += 1; i -= 1
pairs.reverse()

with OUT.open("w", encoding="utf-8") as f:
    for (name, nb, secs), ev in pairs:
        rec = {"wav": name, "bytes": nb, "secs": secs}
        rec.update(ev)
        # un-escape the ascii()-quoted text from the log
        t = rec.get("text") or ""
        if t.startswith("'"):
            try:
                rec["old_text"] = eval(t if t.count("'") >= 2 else t + "'")
            except Exception:
                rec["old_text"] = t
        else:
            rec["old_text"] = ""
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

from collections import Counter
c = Counter(ev["decode"] for _, ev in pairs)
print("wavs", len(wavinfo), "log_events", len(events), "paired", len(pairs), "unpaired_wavs", misses)
print("old verdicts:", dict(c))
print("->", OUT)
