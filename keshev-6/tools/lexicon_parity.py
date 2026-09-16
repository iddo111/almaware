# -*- coding: utf-8 -*-
"""lexicon_parity.py -- which copy of the word list is the truth?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy (`health: ok` != working).

K6-04 (2026-09-06). keshev6_server.py was byte-identical between this tree and
eran1, so everything looked in sync -- but the DATA file had drifted. The
2026-09-06 04:30 edit (Assassin's Creed, Meshtastic, Kropotkin, added because
Iddo demonstrated at 02:41 that the mic could not hear "Assassin's Creed" and
could hear "hi") existed ONLY on eran1. This tree still held the 09-04 00:04
version. A redeploy from here would have silently reverted his fix, and nothing
in the repo could have told you.

Two doors:

    python tools/lexicon_parity.py --check
        OFFLINE. Compares this tree's lexicon.py against the fingerprint
        recorded in LEXICON-DEPLOYED.json. Exit 0 in sync, 1 drifted. This is
        what tests/test_contract_parity.py runs, so drift breaks the tests.

    python tools/lexicon_parity.py --fetch [--record]
        Reaches eran1 over ssh, compares the two copies for real, prints the
        diff, and says WHICH IS AHEAD by mtime. With --record it writes the
        deployed fingerprint into LEXICON-DEPLOYED.json (do that only after you
        have made the two copies agree).

THE SOURCE OF TRUTH IS eran1:/home/eran1/keshev6/lexicon.py -- that is the file
the live decoder reads, and since K6-05 it re-reads it within 30 s of an edit
without a restart. This tree is the copy. Sync THIS WAY, and never the other way
without looking at what you are about to overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LOCAL = HERE / "lexicon.py"
RECORD = HERE / "LEXICON-DEPLOYED.json"
REMOTE = "eran1:/home/eran1/keshev6/lexicon.py"


def load_lexicon(path: Path):
    """Load a lexicon from ANY filename.

    The loader is named explicitly because the copies worth comparing are often
    called lexicon.py.bak-rev-20260906 or lexicon.py.bak-games-20260906, and
    spec_from_file_location returns None for an extension it does not know --
    which surfaces four frames later as `'NoneType' has no attribute 'loader'`
    and tells you nothing."""
    path = Path(path)
    loader = importlib.machinery.SourceFileLoader("lexicon_parity_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def fingerprint(mod) -> str:
    """The DATA only, exactly as keshev6_server._lexicon_fingerprint computes it
    -- so a comment edit is not mistaken for a behaviour change, and a behaviour
    change can never hide behind an unchanged file size."""
    h = hashlib.sha256()
    h.update(getattr(mod, "PROMPT_HE", "").encode("utf-8"))
    for k, v in sorted(getattr(mod, "EXACT_REPAIRS", {}).items()):
        h.update(("%s>%s\n" % (k, v)).encode("utf-8"))
    for t in getattr(mod, "FUZZY_TARGETS", ()):
        h.update(("~%s\n" % t).encode("utf-8"))
    return h.hexdigest()[:12]


def local_fingerprint() -> str:
    return fingerprint(load_lexicon(LOCAL))


def check(verbose: bool = True) -> int:
    if not RECORD.exists():
        if verbose:
            print("NO RECORD: %s is missing. Run --fetch --record." % RECORD.name)
        return 1
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    mine = local_fingerprint()
    ok = mine == rec.get("fingerprint")
    if verbose:
        print("local      %s  (%s)" % (mine, LOCAL))
        print("deployed   %s  (recorded %s from %s)"
              % (rec.get("fingerprint"), rec.get("recorded"), rec.get("source")))
        print("PARITY %s" % ("OK" if ok else
                             "DRIFTED -- run --fetch to see which way"))
    return 0 if ok else 1


def fetch(record: bool) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lexparity-")) / "lexicon.py"
    try:
        subprocess.run(["scp", "-q", REMOTE, str(tmp)], check=True, timeout=60)
        stat = subprocess.run(
            ["ssh", "eran1", "stat -c '%y' /home/eran1/keshev6/lexicon.py"],
            capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        print("could not reach %s: %r" % (REMOTE, e))
        return 2
    remote_fp = fingerprint(load_lexicon(tmp))
    mine = local_fingerprint()
    print("local     %s  mtime %s" % (
        mine, datetime.fromtimestamp(LOCAL.stat().st_mtime).isoformat(" ", "seconds")))
    print("eran1     %s  mtime %s" % (remote_fp, stat))
    if mine == remote_fp:
        print("PARITY OK -- the two copies carry the same prompt and repair maps")
    else:
        print("DRIFTED. eran1 is the source of truth; the diff (local -> eran1):")
        import difflib
        for ln in difflib.unified_diff(
                LOCAL.read_text(encoding="utf-8").splitlines(),
                tmp.read_text(encoding="utf-8").splitlines(),
                "keshev-6/lexicon.py", "eran1:keshev6/lexicon.py", lineterm=""):
            print("  " + ln)
    if record:
        RECORD.write_text(json.dumps(
            {"fingerprint": remote_fp, "source": REMOTE,
             "remote_mtime": stat,
             "recorded": datetime.now().astimezone().isoformat(timespec="seconds"),
             "note": "eran1 is the source of truth; sync THIS tree from it."},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("recorded %s in %s" % (remote_fp, RECORD.name))
    return 0 if mine == remote_fp else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="offline, against the record")
    ap.add_argument("--fetch", action="store_true", help="ssh to eran1 and compare")
    ap.add_argument("--record", action="store_true", help="with --fetch: update the record")
    a = ap.parse_args()
    if a.fetch:
        return fetch(a.record)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
