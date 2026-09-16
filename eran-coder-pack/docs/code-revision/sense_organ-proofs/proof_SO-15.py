# -*- coding: utf-8 -*-
"""PROOF SO-15 -- stale-config in the workspace LAW header: D:\\CLAUDE\\CLAUDE.md calls
eran2 "THE SENSES ... the auditory cortex and the vocal tract" and the systemd unit says
the same, while the living ERAN never connects to that organ (0 callers, 0.49 s of CPU in
4 days) and the throat track's real ear and mouth are ear3 + mouth2. A law header that
names a dormant tool as the child's live senses is how the next session gets it wrong.

    python proof_SO-15.py D:\\CLAUDE\\CLAUDE.md.bak-rev-20260906   -> FAIL
    python proof_SO-15.py D:\\CLAUDE\\CLAUDE.md                    -> PASS

Reads a file. Changes nothing, signals nothing.
"""
import io
import os
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\CLAUDE\CLAUDE.md"
print("PROOF SO-15 against %s" % PATH)
txt = io.open(PATH, encoding="utf-8").read()

i = txt.find("eran2 = THE SENSES")
block = txt[i:i + 2600] if i >= 0 else ""
checks = [
    ("the eran2 role paragraph exists at all", i >= 0, "found at char %d" % i),
    ("it carries an EMET-AUDIT note dated 2026-09-06",
     "EMET-AUDIT 2026-09-06" in block, "note present=%s" % ("EMET-AUDIT 2026-09-06" in block)),
    ("the note says the organ has no callers",
     "ZERO callers" in block or "0 references" in block,
     "caller evidence present=%s" % ("ZERO callers" in block)),
    ("the note gives the measurement, not an opinion",
     "546ms" in block or "0.49 s" in block, "CPU measurement present=%s" % ("546ms" in block)),
    ("the note names what the live ear and mouth actually are",
     "ear3" in block and "mouth2" in block,
     "ear3/mouth2 named=%s" % ("ear3" in block and "mouth2" in block)),
    ("it points at the decision Iddo has to make",
     "NEEDS-IDDO-sense_organ.md" in block, "pointer present=%s"
     % ("NEEDS-IDDO-sense_organ.md" in block)),
]
ok = all(c[1] for c in checks)
for label, good, detail in checks:
    print("  [%s] %s -- %s" % ("PASS" if good else "FAIL", label, detail))
print("PROOF %s" % ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
