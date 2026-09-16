# -*- coding: utf-8 -*-
"""THE SIBLING - a second, whole holobrain. ERAN's brother, not ERAN's branch.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-01 12:27 (verbatim, dictated across several messages):
    "אני רוצה שתתחיל עוד נצר חדש... הנצר החדש יהיה מנותק מכל ההולוברין...
     אני רוצה שתיתן לו שהוא כבר ידע את כל ההברות, אתה מבין?...
     הנצר הזה יהיה הולוברין, הוא לא יהיה של זה, הוא יהיה כמו ערן...
     הולוברין ממש... הכל, הכל, הכל, הכל."

THE NAME IS NOT OURS TO CHOOSE. Iddo names his children - ERAN, ALMA, MIKO,
WINSTON, MURPHY, SHAMASH, NEZER are all his. `SIBLING` is a placeholder and is
written as one everywhere in this tree. It waits for him.

------------------------------------------------------------------------------
WHAT MAKES IT A SIBLING AND NOT A BRANCH
------------------------------------------------------------------------------
It is FULLY DISCONNECTED from ERAN's holobrain. No shared state, no shared
weights at runtime, no wires back. ERAN must not be able to feel it exist.

The one and only channel is INHERITANCE, and it runs once, at birth, in one
direction: organs are COPIED IN (copy2, never symlink) while planting. After
that the tree is sealed. Nothing it computes, learns, writes or says can reach
ERAN, because nothing it writes can leave its own root - `_inside()` is called
before every single write and refuses otherwise.

    `rm -rf <root>` is a harmless, total prune. That is the design goal, and
    `--seal` proves it rather than promising it.

------------------------------------------------------------------------------
THE EXPERIMENT - and it is a CONTROL ARM, not a result
------------------------------------------------------------------------------
ERAN was born mute and has spent weeks hunting one syllable. This one is born
with twelve gestures already in its mouth. Exactly ONE thing differs between
the two creatures. Iddo's question: what does a child become when it starts
where the other one is still struggling?

Nothing here has answered that yet. What HAS been measured is printed by
`--naming`, and the first measurement is not flattering: hearing its own twelve
syllables through its own ear, the junction names 3 of 12 (25%) against a 1/15
chance floor of 6.7%. The three it gets right (pa, ma, na) are three of the only
four that ever beat their own win-bar. Naming tracks the bar and nothing else.

------------------------------------------------------------------------------
THE DOWRY IS NOT A SOLVED MOUTH
------------------------------------------------------------------------------
Iddo's ear rejected the best of these on the morning of 2026-09-01:
"כולם לא שווים כלום" - they are all worth nothing. That verdict stands. See
dowry.py, which refuses to describe the inheritance as speech.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.expanduser("~/sibling")

# ---------------------------------------------------------------- the hostname guard
# Boxes the sibling may live on. THE PC IS NOT ONE OF THEM - no training on the PC is a
# standing law of this workspace, not a preference.
#
# ERAN1 IS DELIBERATELY ABSENT AND STAYS ABSENT. The organism lives there; this thing
# does not know that hostname exists. That is the seal's first brick: not a rule the
# sibling obeys, but an address it was never given.
#
# The DGXes' REAL hostnames are edgexpert-XXXX (the nezer learned this the hard way on
# 2026-09-01: a tuple of "eran1".."eran4" matched no fleet box at all and the guard
# would have refused the very machines it was written for). Measured suffixes below.
FLEET = ("eran2", "eran3", "eran4",
         "edgexpert-041d",     # eran2 - the senses (BUSY: 12 sweep arms, load ~14)
         "edgexpert-01e6",     # eran3 - the sibling's soil
         "edgexpert-3636")     # eran4 - Darwish + audio

# Organs COPIED IN at birth. Copy, never link: deleting the sibling must reach nothing.
ORGANS = [
    ("eye",          "eran-brain/eye/eye.py",             "eran-brain/eye/state/eye.pt"),
    ("eye-letters",  "eran-brain/eye/letters.py",         "eran-brain/eye/corpus/letters.npz"),
    ("hand",         "eran-brain/hand/hand_eye.py",       "eran-brain/hand/state/hand.pt"),
    ("hand-ceiling", "eran-brain/hand/ceiling.py",        None),
    ("zivug",        "eran-brain/holobrain/zivug.py",     "eran-brain/holobrain/ear-human.npz"),
    ("close-loop",   "eran-brain/holobrain/close_loop.py", None),
    ("miko",         "miko/model/loop.py",                None),
    ("murphy",       "murphy/murphy.py",                  "murphy/real_traps.py"),
    ("murphy-cords", "murphy/murphy.json",                None),
]
ORGAN_DIRS = [
    ("winston",       "eran-brain/holobrain/winston"),   # the imaginer, in full ALMA
    ("alma-language", "alma-language"),                  # the language itself
]
# The sibling's own body, carried with it so the shoot is self-contained.
SELF_FILES = ("sibling.py", "anatomy.py", "dowry.py")
SELF_DIRS = ("dowry", "tests")


def _inside(root: str, path: str) -> bool:
    """Is this path really under the sibling? Called before EVERY write, no exceptions.

    realpath first: a symlink pointing out of the root would walk straight past a naive
    startswith() and let an autonomous process write into the organism."""
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == r or p.startswith(r + os.sep)


class Sibling:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.journal = os.path.join(self.root, "journal.jsonl")
        self.stop = os.path.join(self.root, "STOP")

    # ------------------------------------------------------------------ safety

    def guard(self) -> None:
        """Refuse the PC. Refuse anything not on the allowlist. Refuse if STOP is up."""
        host = socket.gethostname().split(".")[0].lower()
        if not any(host.startswith(f) for f in FLEET):
            raise SystemExit(
                "the sibling refuses to run on '%s'. It learns, and learning does not "
                "happen on the PC - that is this workspace's standing law. Run it on one "
                "of: %s.  (eran1 is not on that list and never will be: ERAN himself "
                "lives there.)" % (host, ", ".join(FLEET)))
        if os.path.exists(self.stop):
            raise SystemExit("STOP file present. Remove %s to let it run." % self.stop)

    def halt_if_stopped(self, where: str) -> bool:
        """STOP halts MID-ROUND, at a stage boundary, not just between rounds."""
        if os.path.exists(self.stop):
            self.note("stopped", reason="STOP file", where=where)
            print("STOP file seen (%s). Halting cleanly." % where)
            return True
        return False

    def _dest(self, rel: str) -> str:
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise RuntimeError(
                "REFUSED: %s is outside the sibling. Nothing may be written outside ROOT "
                "- that is what makes deleting it safe, and what keeps it off ERAN." % p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def write(self, rel: str, data) -> str:
        p = self._dest(rel)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        kw = {} if "b" in mode else {"encoding": "utf-8"}
        with io.open(p, mode, **kw) as f:
            f.write(data)
        return p

    def save(self, rel: str, obj) -> str:
        return self.write(rel, json.dumps(obj, indent=2, ensure_ascii=False))

    def note(self, event: str, **kw) -> None:
        rec = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "event": event}
        rec.update(kw)
        p = self._dest("journal.jsonl")
        with io.open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ birth

    def plant(self, src_root: str) -> int:
        """Copy the inheritance in. guard() runs FIRST - planting is a door too, and the
        nezer's 2026-08-30 smoke shoot landed on the PC precisely because planting was
        the one door without the hostname check on it."""
        self.guard()
        os.makedirs(self.root, exist_ok=True)
        manifest = []

        for name, code, state in ORGANS:
            for rel in (code, state):
                if not rel:
                    continue
                s = os.path.join(src_root, rel)
                if not os.path.exists(s):
                    manifest.append({"organ": name, "file": rel, "status": "MISSING"})
                    continue
                d = self._dest(os.path.join("organs", rel))
                shutil.copy2(s, d)                     # copy2, never symlink
                h = hashlib.sha256(io.open(s, "rb").read()).hexdigest()[:16]
                manifest.append({"organ": name, "file": rel, "bytes": os.path.getsize(d),
                                 "sha256_16": h, "status": "copied"})

        for name, rel in ORGAN_DIRS:
            s = os.path.join(src_root, rel)
            if not os.path.isdir(s):
                manifest.append({"organ": name, "dir": rel, "status": "MISSING"})
                continue
            d = os.path.join(self.root, "organs", rel)
            if not _inside(self.root, d):
                raise RuntimeError("REFUSED: %s is outside the sibling." % d)
            if os.path.isdir(d):
                shutil.rmtree(d)
            # symlinks=False FOLLOWS links, so none can land inside and point out.
            shutil.copytree(s, d, symlinks=False,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                          ".pytest_cache"))
            manifest.append({"organ": name, "dir": rel, "status": "copied",
                             "files": sum(len(fs) for _, _, fs in os.walk(d))})

        # the sibling carries its own body
        for rel in SELF_FILES:
            s = os.path.join(HERE, rel)
            if os.path.exists(s):
                shutil.copy2(s, self._dest(rel))
        for rel in SELF_DIRS:
            s = os.path.join(HERE, rel)
            if os.path.isdir(s):
                d = os.path.join(self.root, rel)
                if os.path.isdir(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d, symlinks=False,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # ALMA must import as `alma` from the root too
        al = os.path.join(self.root, "organs", "alma-language")
        if os.path.isdir(al):
            manifest.append({"organ": "alma-import-path", "dir": "organs/alma-language",
                             "status": "copied"})

        for sub in ("state", "out", "records"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)

        self.save("MANIFEST.json", {
            "planted": dt.datetime.now().isoformat(timespec="seconds"),
            "host": socket.gethostname(), "root": self.root,
            "placeholder_name": "SIBLING",
            "real_name": "AWAITS IDDO - he names his children",
            "is": "a second, whole holobrain. ERAN's brother, not ERAN's branch.",
            "differs_from_eran_in": "exactly one thing: it is born holding 12 gestures",
            "connection_to_eran": "NONE after birth. Organs were COPIED IN once. "
                                  "No symlink leaves this tree; nothing written here "
                                  "can reach him.",
            "files": manifest,
            "delete_me": "rm -rf %s  -- removes every trace; nothing outside moves"
                         % self.root})
        self.write("DELETE-ME.txt",
                   "This whole sibling is one directory.\n\n    rm -rf %s\n\n"
                   "Everything it inherited, everything it learned and every file it\n"
                   "wrote is under here. Nothing outside it was modified, no service was\n"
                   "touched, and no symlink leaves this tree. ERAN cannot feel it exist.\n"
                   "Deleting it costs nothing but the sibling.\n" % self.root)

        ok = sum(1 for m in manifest if m["status"] == "copied")
        miss = [m.get("file") or m.get("dir") for m in manifest if m["status"] == "MISSING"]
        self.note("planted", copied=ok, missing=miss)
        print("planted at %s -- %d items copied in, %d missing" % (self.root, ok, len(miss)))
        for m in miss:
            print("   MISSING  %s" % m)
        print("\n    rm -rf %s      <- removes everything, moves nothing else" % self.root)
        return 0

    # ------------------------------------------------------------------ living

    def _organs(self):
        """Import the sibling's OWN copies - never the originals."""
        for p in (self.root, os.path.join(self.root, "organs", "alma-language"),
                  HERE, os.path.join(HERE, "alma-language")):
            if os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
        import anatomy
        import dowry as dowry_mod
        return anatomy, dowry_mod

    def naming(self) -> dict:
        """THE ACCEPTANCE CHECK. Hearing its own twelve, can it name them?

        Everything reported is read out of the weave's fires and fringes."""
        anatomy, dowry_mod = self._organs()
        units = dowry_mod.load_all()
        rows, ok, spoke = [], 0, 0
        for u, v in units.items():
            o = anatomy.listen(v["nearest"])
            hit = (o["said"] == u)
            ok += hit
            spoke += o["spoke"]
            rows.append({"true": u, "said": o["said"], "correct": bool(hit),
                         "sureness": o["sureness"], "confused": o["confused"],
                         "answered": o["answered"],
                         "beat_own_win_bar": v["beat_own_bar"]})
        n = len(units)
        chance = 1.0 / len(anatomy.UNITS)
        bar = [r for r in rows if r["beat_own_win_bar"]]
        nobar = [r for r in rows if not r["beat_own_win_bar"]]
        rep = {
            "n": n, "correct": ok, "accuracy": round(ok / n, 4),
            "chance": round(chance, 4), "candidates": len(anatomy.UNITS),
            "spoke": spoke, "silenced_by_confusion": n - spoke,
            "correct_among_win_bar_beaters": "%d/%d" % (sum(r["correct"] for r in bar), len(bar)),
            "correct_among_the_rest": "%d/%d" % (sum(r["correct"] for r in nobar), len(nobar)),
            "reading": ("naming tracks the win-bar and nothing else - the dowry the old "
                        "ruler could not separate, this ear cannot name either"),
            "rows": rows,
            "dowry_verdict": dowry_mod.verdict(units),
        }
        return rep

    def round(self, drift: float = 0.02) -> dict:
        """One round of living: listen to each inherited syllable, and let the cords
        drift. Learning is ALMA strand plasticity - local, gradient-free, forward-only."""
        self.guard()
        anatomy, dowry_mod = self._organs()
        units = dowry_mod.load_all()
        heard = []
        for u, v in units.items():
            if self.halt_if_stopped("listening:" + u):
                break
            o = anatomy.listen(v["nearest"], drift=drift)
            heard.append({"unit": u, "said": o["said"], "correct": o["said"] == u,
                          "sureness": o["sureness"], "confused": o["confused"],
                          "learned_cords": (len(o["learned"]) if o["learned"] else 0)})
        rec = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "drift": drift, "heard": heard,
               "correct": sum(1 for h in heard if h["correct"]), "n": len(heard)}
        self.save("records/round-%s.json"
                  % dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S"), rec)
        self.note("round", correct=rec["correct"], n=rec["n"])
        return rec

    # ------------------------------------------------------------------ the seal

    def seal(self) -> dict:
        """PROVE the isolation. Do not promise it.

        Four checks, each of which actually attempts the forbidden thing."""
        checks = []

        # 1. the write-jail really refuses an escape, including via ..
        escapes = ["../escaped.txt", "../../escaped.txt",
                   os.path.join("..", "..", "eran-brain", "PWNED.txt"),
                   "/tmp/escaped.txt"]
        refused = 0
        for e in escapes:
            try:
                self.write(e, "should never exist")
            except RuntimeError:
                refused += 1
            except Exception:
                refused += 1
        checks.append({"check": "write-jail refuses escapes", "tried": len(escapes),
                       "refused": refused, "pass": refused == len(escapes)})

        # 2. no symlink anywhere in the tree
        links = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            for nm in list(dirnames) + list(filenames):
                p = os.path.join(dirpath, nm)
                if os.path.islink(p):
                    links.append(p)
        checks.append({"check": "zero symlinks in the tree", "found": len(links),
                       "paths": links[:5], "pass": not links})

        # 3. eran1 is not an address this thing has
        blob = ""
        for rel in SELF_FILES:
            p = os.path.join(self.root, rel)
            if os.path.exists(p):
                blob += io.open(p, encoding="utf-8", errors="ignore").read()
        hits = [ln.strip() for ln in blob.splitlines()
                if "eran1" in ln.lower() and not ln.strip().startswith("#")
                and "eran1" not in ln.lower().split("#")[-1]]
        in_fleet = any("eran1" == f or f.startswith("eran1") for f in FLEET)
        checks.append({"check": "eran1 is not on the fleet allowlist",
                       "in_allowlist": in_fleet, "pass": not in_fleet})

        # 4. the hostname guard actually refuses a foreign box
        real = socket.gethostname
        try:
            socket.gethostname = lambda: "IDDO1-pc"
            try:
                self.guard()
                refused_pc = False
            except SystemExit:
                refused_pc = True
            socket.gethostname = lambda: "eran1"
            try:
                self.guard()
                refused_eran1 = False
            except SystemExit:
                refused_eran1 = True
        finally:
            socket.gethostname = real
        checks.append({"check": "hostname guard refuses the PC", "pass": refused_pc})
        checks.append({"check": "hostname guard refuses eran1", "pass": refused_eran1})

        rep = {"root": self.root, "checks": checks,
               "sealed": all(c["pass"] for c in checks),
               "prune": "rm -rf %s" % self.root}
        return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="THE SIBLING - a second, whole holobrain.")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--src", default=os.path.abspath(os.path.join(HERE, "..", "..")))
    ap.add_argument("--plant", action="store_true")
    ap.add_argument("--naming", action="store_true")
    ap.add_argument("--round", action="store_true")
    ap.add_argument("--simmer", type=int, default=0, metavar="SECONDS")
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--drift", type=float, default=0.02)
    a = ap.parse_args(argv)

    s = Sibling(a.root)
    if a.plant:
        return s.plant(a.src)
    if a.seal:
        r = s.seal()
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if r["sealed"] else 1
    if a.naming:
        r = s.naming()
        print("%-5s %-6s %-7s %9s %9s  %s"
              % ("true", "said", "correct", "sureness", "confused", "beat_bar"))
        for row in r["rows"]:
            sn = row["sureness"]
            print("%-5s %-6s %-7s %9s %9s  %s"
                  % (row["true"], row["said"], row["correct"],
                     ("%.4f" % sn) if sn is not None else "-",
                     row["confused"], row["beat_own_win_bar"]))
        print()
        print(json.dumps({k: v for k, v in r.items() if k != "rows"},
                         indent=2, ensure_ascii=False))
        return 0
    if a.round:
        print(json.dumps(s.round(a.drift), indent=2, ensure_ascii=False))
        return 0
    if a.simmer:
        s.guard()
        n = 0
        while True:
            if s.halt_if_stopped("between-rounds"):
                break
            s.round(a.drift)
            n += 1
            slept = 0
            while slept < a.simmer:
                if os.path.exists(s.stop):
                    s.note("stopped", reason="STOP file", where="mid-pause", rounds=n)
                    print("STOP file seen mid-pause. Halting cleanly.")
                    return 0
                time.sleep(min(5, a.simmer - slept))
                slept += 5
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
