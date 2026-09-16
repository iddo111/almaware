"""Fire tonight's design councils at the 4D workers, save every position.

Each council is ONE named question; the four positions land in
harness/council/<qid>-<model>.md. The KING rules afterwards in DECISIONS.md
— this script only collects advice, it decides nothing.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fleet  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "council"
OUT.mkdir(exist_ok=True)

CONTEXT = """You advise on KESHEV 2, a Windows Hebrew/English dictation app
(successor to KESHEV A, which is live). Background facts, all measured:
- The 09:46 scar: owner out of the room, a video playing, the mic typed the
  video's speech into his chat AS HIM, 8 messages with Enter in 9 seconds.
  Every existing guard passed (right device, real speech, not hallucination,
  allowed window) — nobody asked if the OWNER was present.
- Answer 1 (live in A): presence gate reading the OS last-input clock.
  idle >= 120s -> type but NEVER Enter; idle >= 600s -> type nothing.
  Fail-open on type, fail-closed on Enter when the clock is unreadable.
- Answer 2 (built in A, default OFF): ArmSwitch — ctrl+alt+a toggles armed,
  arm expires after 900s, disarmed speech is parked (never dropped). When ON,
  BOTH gates must agree. "No body, no key press, no typing."
- The owner dictates hands-free but IS at the machine; normal dictation is
  punctuated by keyboard/mouse. He hates friction and mothering.
Answer in AT MOST 200 words, format:
POSITION: <one contestable sentence>
REASONS: <up to 3 bullets>
RISKS: <up to 2 bullets you accept>"""

COUNCILS = {
    "Q1-armed-default": CONTEXT + """

THE QUESTION (Q1): In KESHEV 2, should armed mode be the DEFAULT operating
mode (mic only types while deliberately armed via hotkey, re-armed every 15
minutes), or should the presence gate alone be the default with arm as an
opt-in for risky contexts? Also recommend concrete defaults for:
enter_idle_limit_s, type_idle_limit_s, arm_timeout_s.""",

    "Q2-rival-interlock": CONTEXT + """

THE QUESTION (Q2): KESHEV 2 must structurally REFUSE to start capture while
KESHEV A (the live mic) is running — opening a second capture of the same
USB mic disrupts live dictation. A holds a named kernel mutex
Global\\ALMAWARE_KESHEV_SINGLE for its process life, and appends to a journal
file state\\events.jsonl (heartbeat every 60s). Rank these detection
mechanisms for the interlock and say which combination you would ship:
(a) OpenMutexW read-only probe of A's mutex name;
(b) scanning process list for A's python pids / command lines;
(c) A-journal freshness (heartbeat younger than N seconds);
(d) probing A's capture device handle.
Constraint: the check must NEVER itself disturb A (no CreateMutexW on A's
name — creating it would squat the name and block A's next start; no device
opens). Also: how should the verdict structurally reach the start decision
so it cannot become a guard-that-cannot-fire?""",
}


def main() -> None:
    for qid, prompt in COUNCILS.items():
        print(f"--- council {qid}")
        answers = fleet.ask_all(prompt, max_tokens=900)
        for model, text in answers.items():
            path = OUT / f"{qid}-{model}.md"
            path.write_text(text, encoding="utf-8")
            print(f"    {model}: {len(text)} chars -> {path.name}")


if __name__ == "__main__":
    main()
