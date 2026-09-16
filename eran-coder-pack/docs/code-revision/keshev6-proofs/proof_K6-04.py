# -*- coding: utf-8 -*-
"""proof_K6-04 -- the word list drifted while the server file did not.

    python proof_K6-04.py <path-to-a-lexicon.py>

FAILS against D:\\CLAUDE\\keshev-6\\lexicon.py.bak-rev-20260906 (this tree's copy
before the fix), PASSES against D:\\CLAUDE\\keshev-6\\lexicon.py now. Pure stdlib,
offline, nothing touched.

Measured 2026-09-06: keshev6_server.py was byte-identical between this tree and
eran1 -- so the deploy looked clean -- while lexicon.py was 4,943 B here (09-04
00:04) against 5,779 B on eran1 (09-06 04:30). The 04:30 edit added Assassin's
Creed, Meshtastic and Kropotkin, put there because Iddo demonstrated the failure
himself at 02:41: the mic could not hear "Assassin's Creed" and could hear "hi".
A redeploy from this tree would have reverted his fix and said nothing.

Cases:
  A  the three names he demonstrated are in the prompt this tree would ship
  B  the DATA fingerprint equals the one recorded from the deployed copy,
     so any future drift -- either direction -- breaks the tests
  C  the drift is DETECTABLE offline: the parity checker refuses the old copy
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

TARGET = Path(sys.argv[1]).resolve()
TREE = Path(r"D:\CLAUDE\keshev-6")
FAILS: list[str] = []

DEMONSTRATED = ("Assassin's Creed", "Meshtastic", "Kropotkin")


def check(name: str, ok: bool, detail="") -> None:
    print("  %-60s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def load(path: Path, name: str):
    tmp = Path(tempfile.mkdtemp(prefix="k6proof04-")) / (name + ".py")
    shutil.copy2(path, tmp)
    spec = importlib.util.spec_from_file_location(name, tmp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    tool = load(TREE / "tools" / "lexicon_parity.py", "lexicon_parity_probe_tool")
    lex = load(TARGET, "lexicon_under_test")
    print("proof_K6-04 against %s" % TARGET)

    missing = [n for n in DEMONSTRATED if n not in getattr(lex, "PROMPT_HE", "")]
    check("A the names Iddo demonstrated at 02:41 are in the prompt",
          not missing, "missing: %s" % ", ".join(missing) if missing else "")

    rec_path = TREE / "LEXICON-DEPLOYED.json"
    check("B a deployed fingerprint is recorded at all", rec_path.exists(),
          rec_path.name)
    if rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        mine = tool.fingerprint(lex)
        check("B this copy matches the deployed fingerprint",
              mine == rec["fingerprint"],
              "this=%s deployed=%s (recorded %s from %s)"
              % (mine, rec["fingerprint"], rec.get("recorded"), rec.get("source")))

    # C: the offline checker must actually refuse a drifted tree. Point it at
    # the file under test and see what it says -- a checker that always says OK
    # is the thing this defect is made of.
    # the tool was loaded from a temp copy, so point its two paths back at the
    # real tree before asking it anything
    tool.LOCAL = TARGET
    tool.RECORD = rec_path
    verdict = tool.check(verbose=False)
    check("C the offline parity checker agrees (0 = in sync)", verdict == 0,
          "exit %s" % verdict)

    print("\nproof_K6-04: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
