# -*- coding: utf-8 -*-
"""proof_K6-05 -- a word list must not cost a restart of his microphone.

    python proof_K6-05.py <path-to-keshev6_server.py>

FAILS on the old file (lexicon imported once at boot, no reload path at all).
PASSES on the fixed one. Nothing is loaded but the module; no engine, no port.

The measured event: lexicon.py was edited on eran1 at 04:30 (three names Iddo had
just demonstrated the mic could not hear) and the running decoder kept prompting
with the previous string until the 08:06 restart -- 3.6 h of live dictation with
the stale prompt, and the only remedy on offer was restarting the decoder his
mic talks to.

Four cases:
  A  an edit to PROMPT_HE is in force without re-importing anything
  B  an edit to EXACT_REPAIRS changes what repair() actually does
  C  a BROKEN lexicon (a syntax error) is REFUSED -- the working one stays,
     and the refusal is logged rather than swallowed
  D  no edit -> no reload (mtime is the trigger, not the clock)
"""
from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


LEXICON_V1 = '''# -*- coding: utf-8 -*-
PROMPT_HE = "PROMPT-ONE"
EXACT_REPAIRS = {"aaa": "AAA"}
FUZZY_TARGETS = ("chinchilla",)
FUZZY_MIN_RATIO = 0.86
FUZZY_MIN_LEN = 4


def repair(text):
    changes = []
    out = text
    for bad, good in EXACT_REPAIRS.items():
        if bad in out:
            out = out.replace(bad, good)
            changes.append((bad, good))
    return out, changes
'''

LEXICON_V2 = LEXICON_V1.replace("PROMPT-ONE", "PROMPT-TWO").replace(
    '{"aaa": "AAA"}', '{"aaa": "AAA", "bbb": "BBB"}')

LEXICON_BROKEN = "PROMPT_HE = (unclosed\n"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="k6proof05-"))
    shutil.copy2(TARGET, tmp / "keshev6_server.py")
    (tmp / "lexicon.py").write_text(LEXICON_V1, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("k6_under_test05",
                                                  tmp / "keshev6_server.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["k6_under_test05"] = m
    spec.loader.exec_module(m)
    print("proof_K6-05 against %s" % TARGET)

    records: list[str] = []

    class Cap(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage())

    logging.getLogger("keshev6").addHandler(Cap())
    logging.getLogger("keshev6").setLevel(logging.INFO)

    has_api = hasattr(m, "reload_lexicon_if_changed") and hasattr(m, "current_lexicon")
    check("the server HAS a lexicon reload path at all", has_api,
          "" if has_api else "no reload_lexicon_if_changed/current_lexicon")
    if not has_api:
        print("\nproof_K6-05: FAIL (%d) -> %s" % (len(FAILS), FAILS))
        return 1

    m.reload_lexicon_if_changed(force=True)
    check("boot loads the lexicon on disk",
          m.current_lexicon().PROMPT_HE == "PROMPT-ONE",
          m.current_lexicon().PROMPT_HE)

    # ---- A + B: an edit lands without an import or a restart ---------------
    time.sleep(0.05)
    (tmp / "lexicon.py").write_text(LEXICON_V2, encoding="utf-8")
    os.utime(tmp / "lexicon.py", (time.time() + 1, time.time() + 1))
    changed = m.reload_lexicon_if_changed()
    lex = m.current_lexicon()
    check("A an edited PROMPT_HE is in force after a reload check",
          changed and lex.PROMPT_HE == "PROMPT-TWO",
          "changed=%r prompt=%r" % (changed, lex.PROMPT_HE))
    out, ch = lex.repair("bbb")
    check("B an added EXACT_REPAIRS entry actually repairs",
          out == "BBB" and ch == [("bbb", "BBB")], "repair('bbb') -> %r" % out)
    check("A/B the reload is LOGGED with a data fingerprint",
          any("LEXICON_RELOADED" in r and "sha=" in r for r in records),
          records[-1] if records else "(no log lines)")

    # ---- D: no edit, no reload ---------------------------------------------
    again = m.reload_lexicon_if_changed()
    check("D an unchanged file does NOT reload", again is False,
          "returned %r" % (again,))

    # ---- C: a broken edit must never reach the live decoder ----------------
    records.clear()
    time.sleep(0.05)
    (tmp / "lexicon.py").write_text(LEXICON_BROKEN, encoding="utf-8")
    os.utime(tmp / "lexicon.py", (time.time() + 2, time.time() + 2))
    try:
        broke = m.reload_lexicon_if_changed()
        raised = None
    except Exception as e:                # a raise here would kill the decoder
        broke, raised = None, type(e).__name__
    check("C a broken lexicon does not raise into the server",
          raised is None, "raised %s" % raised)
    check("C a broken lexicon is REFUSED", broke is False, "returned %r" % (broke,))
    check("C the working lexicon survives the bad edit",
          m.current_lexicon().PROMPT_HE == "PROMPT-TWO",
          m.current_lexicon().PROMPT_HE)
    check("C the refusal is logged, not swallowed",
          any("LEXICON_RELOAD_FAILED" in r for r in records),
          records[-1] if records else "(no log lines)")

    print("\nproof_K6-05: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
