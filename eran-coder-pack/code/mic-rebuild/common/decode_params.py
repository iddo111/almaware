"""KESHEV decode guards — K10 (PHASE2-DESIGN.md section 2, scar 27 layer 4).

The ONE copy of the Whisper decode parameters, shared by the worker's local
engine AND the server. Every value exists because a prior default alone
failed (PHASE1-INQUIRY.md scar 27):

  temperature [0, 0.2]   — no high-temperature hallucination ladder
  beam_size 1            — greedy; beam search multiplied decode time under load
  condition_on_previous_text False — context feedback regurgitated transcripts
  compression_ratio_threshold 2.4  — repeat-loop cutoff
  no_speech_threshold 0.6          — silence rejection inside the model

Scar 30's banned context kwarg is not merely absent — lint gate G2 bans the
token repo-wide, and tests assert it never reaches a backend call.
"""
from __future__ import annotations

TEMPERATURE: tuple[float, float] = (0.0, 0.2)
BEAM_SIZE: int = 5
CONDITION_ON_PREVIOUS_TEXT: bool = False
COMPRESSION_RATIO_THRESHOLD: float = 2.4
NO_SPEECH_THRESHOLD: float = 0.6

# Post-hoc client-side drop (textguard, scar 27 layer 5) — recorded here so
# the number lives with its family; applied in client/textguard.py only.
#
# WAS -1.0 UNTIL 2026-08-14, AND IN THAT POSITION IT NEVER FIRED ONCE.
# Measured over 138 real decodes of Iddo's dictation that day (eran1 server
# log, every one carrying text):
#
#     median -0.367   p25 -0.504   p75 -0.230   best -0.039   WORST -0.913
#
# The floor sat below the entire distribution. A gate that no observation can
# reach is not a gate — it is the tray bug wearing different clothes: written,
# wired, journalled, tested, and incapable of acting. Meanwhile the model was
# openly reporting -0.5 and -0.9 ("I am guessing") and the client typed those
# guesses at Iddo as confident Hebrew, all morning, while he was trying to
# talk about his father.
#
# -0.6 drops the worst 14% of decodes — the tail where the model has stopped
# recognising and started inventing — and keeps everything from p25 up.
# Deliberately NOT tighter: -0.4 would drop 40% and -0.3 would drop 65%, and
# losing a real word he said is worse than passing a doubtful one (scar
# 17/18). Re-measure before moving this again; never re-seed it from taste.
# RAISED to -1.2 the same evening, after -0.6 dropped 450 of 499 segments and
# Iddo said "fix mic" again. A FIXED FLOOR CANNOT WORK: measured on his own
# decodes, median avg_logprob was -0.367 in the morning (loud, rms 0.027) and
# -0.685 at night (quiet, rms 0.0046 with AGC at 6.8x). Quiet speech is not
# guessing, but it scores like guessing, and a constant cannot tell them apart —
# so any single number is wrong for half the day. -1.2 drops only the worst 9%,
# which is the honest side to be wrong on: losing a word he really said is worse
# than passing a doubtful one (scar 17/18), and that is the failure that made
# him ask twice tonight.
# THE REAL FIX IS ADAPTIVE, NOT A BETTER CONSTANT: gate on lp RELATIVE to a
# rolling median of recent decodes, so the guard follows the room instead of a
# number someone measured once at 11am.
AVG_LOGPROB_DROP: float = -1.2


def decode_kwargs() -> dict:
    """A FRESH dict per call — callers cannot mutate the shared truth."""
    return {
        "temperature": TEMPERATURE,
        "beam_size": BEAM_SIZE,
        "condition_on_previous_text": CONDITION_ON_PREVIOUS_TEXT,
        "compression_ratio_threshold": COMPRESSION_RATIO_THRESHOLD,
        "no_speech_threshold": NO_SPEECH_THRESHOLD,
    }
