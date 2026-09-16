"""parent.py — Iddo's channel. Taps pay out through eligibility traces.

Inbox: feedback/inbox/taps-*.jsonl, one JSON per line: {ts, tap: up|down|fire}.
  up   : plasticity bonus x10 on recently-active prototypes, under the OXT lift
  down : valence scar on recently-active prototypes — their attraction drops
  fire : the big bonus

Silence is neutral — NO inference from absence. Iddo is at sea; the child
waits without sulking. Processed files are renamed *.paid (the darwish-midi
pattern) so a tap is paid exactly once.

Embodies: the parent's approval IS the reward (ALMA-LIVING-NEURON engine 5);
oxytocin — the child learns most in the parent's presence.
"""
import json
import os

import genome


def check_inbox(brain, chem, inbox_dir=None, log=None):
    """Pay every unpaid tap file. Returns number of taps paid."""
    inbox = inbox_dir or genome.FEEDBACK_INBOX
    if not os.path.isdir(inbox):
        return 0
    taps_paid = 0
    for fname in sorted(os.listdir(inbox)):
        if not (fname.startswith("taps-") and fname.endswith(".jsonl")):
            continue
        path = os.path.join(inbox, fname)
        done = path + ".paid"
        if os.path.exists(done):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tap = json.loads(line)
                except ValueError:
                    continue
                kind = tap.get("tap")
                if kind not in ("up", "down", "fire"):
                    continue
                chem.parent_touch()                     # oxytocin rises FIRST
                paid = brain.pay_trace(kind, chem)
                chem.valence({"up": 1.0, "fire": 2.0, "down": -1.0}[kind])
                taps_paid += 1
                if log:
                    log(f"[parent] tap {kind}: paid {paid} traced prototypes "
                        f"(oxt={chem.oxt:.2f})")
        os.replace(path, done)
    return taps_paid
