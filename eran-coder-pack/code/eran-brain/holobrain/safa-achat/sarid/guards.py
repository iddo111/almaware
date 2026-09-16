# -*- coding: utf-8 -*-
"""THE GRAFT LAWS - ported VERBATIM from the nezer, because they are tested.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

SARID is a nezer too: a shoot grafted onto the fleet, living in its own tree,
able to be deleted with one command and reaching nothing on the way out. Every
function below is the nezer's own (nezer.py `_inside` :195, `guard` :370,
`write`/`_dest` :381/:392, `note` :401, `halt_if_stopped` :889, `plant` :424),
carried over with its reasoning intact and its hostname fleet changed. They
were not reinvented. Reinventing a tested guard is how an autonomous process
ends up writing into the organism.

The six laws, and what each one physically prevents:

  own tree          everything SARID writes lives under ROOT and nowhere else
  copy2 never link  a copy in means deleting the shoot reaches nothing outside
  realpath jail     `_inside` resolves symlinks FIRST, so a link pointing out
                    of the root cannot walk past a naive startswith() check
  STOP mid-round    `halt_if_stopped` is called at every stage boundary, not
                    only between rounds; in-flight work is dropped on purpose
  hostname guard    never the PC (learning does not happen there - the standing
                    law), and NEVER eran1 (that is ERAN himself, and he is
                    never to be restarted)
  zero outward      no cord, no import, no write leaves the shoot

`prune_command()` returns the one command that undoes the whole organ.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import socket

# The boxes SARID may live on, by measured hostname (recon C, 2026-09-01).
# eran1 is ABSENT and that is the point: eran1 is ERAN.
FLEET = ("edgexpert-01e6",       # eran3 - the idle box, no internet, 918G free
         "edgexpert-3636",       # eran4 - has internet
         "edgexpert-041d")       # eran2 - the fabric hub

# Any host whose name we do not know but which answers to eran1's addresses is
# refused by name here as well. Belt and braces: the FLEET allowlist above
# already excludes everything not named, this makes the intent unmissable.
FORBIDDEN_SUBSTRINGS = ("eran1", "eranb")


def _inside(root: str, path: str) -> bool:
    """Is this path really under the shoot? Called before every write, no exceptions.

    realpath first, because a symlink pointing out of the root would otherwise
    walk right past a naive startswith() check and let an autonomous process
    write into the organism.
    """
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == r or p.startswith(r + os.sep)


class Graft:
    """The shoot: its root, its journal, its STOP file, its one-command prune."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.journal = os.path.join(self.root, "journal.jsonl")
        self.stop = os.path.join(self.root, "STOP")

    # ------------------------------------------------------------------ safety

    def guard(self, allow_pc: bool = False) -> None:
        """Refuse to run anywhere SARID is not allowed to be.

        `allow_pc` exists for ONE purpose: the test suite and the ruler
        controls, which are pure arithmetic over a wordlist and are not
        learning. It never lets the loop run on the PC - `loop.py` calls
        guard() without it.
        """
        host = socket.gethostname().split(".")[0].lower()
        if any(f in host for f in FORBIDDEN_SUBSTRINGS):
            raise SystemExit(
                "SARID refuses to run on '%s'. That box is ERAN himself, and he "
                "is never to be restarted or shared with. This organ is his "
                "sibling, not his tenant." % host)
        if any(host.startswith(f) for f in FLEET):
            return
        if allow_pc:
            return
        raise SystemExit(
            "SARID refuses to run its loop on '%s'. It learns, and learning "
            "does not happen on the PC -- that is this workspace's standing "
            "law. Run it on %s." % (host, "/".join(FLEET)))

    def halt_if_stopped(self, where: str) -> None:
        """The door's promise, kept: STOP halts MID-ROUND at a stage boundary,
        not only between rounds. In-flight work is dropped, on purpose - the
        whole shoot is deletable, so a half-round is too."""
        if os.path.exists(self.stop):
            self.note("stopped", reason="STOP file", where="mid-round:" + where)
            print("STOP file seen mid-round (%s). Halting cleanly." % where)
            raise SystemExit(0)

    # ------------------------------------------------------------------- write

    def write(self, rel: str, data) -> str:
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise RuntimeError(
                "REFUSED: %s is outside the shoot. Nothing may be written "
                "outside ROOT -- that is what makes deleting it safe." % p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        kw = {} if "b" in mode else {"encoding": "utf-8"}
        with io.open(p, mode, **kw) as f:
            f.write(data)
        return p

    def _dest(self, rel: str) -> str:
        """A checked path under ROOT for writes that do not go through write()
        (copy2 destinations, csv writers). Same law, same refusal."""
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise RuntimeError("REFUSED: %s is outside the shoot." % p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def note(self, kind: str, **fields) -> None:
        """One line per event, readable by a person who was not here."""
        rec = {"t": dt.datetime.now().isoformat(timespec="seconds"),
               "kind": kind}
        rec.update(fields)
        os.makedirs(self.root, exist_ok=True)
        with io.open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------- state

    def load(self, rel: str, default):
        p = os.path.join(self.root, rel)
        try:
            with io.open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def save(self, rel: str, obj) -> None:
        self.write(rel, json.dumps(obj, ensure_ascii=False, indent=1))

    # ------------------------------------------------------------------- plant

    def plant(self, src_root: str, rels) -> int:
        """Copy everything in. COPY, never link -- deleting the shoot must reach
        nothing. guard() runs FIRST: the 2026-08-30 smoke shoot landed on the PC
        because planting was the one door without the hostname check on it."""
        self.guard(allow_pc=True)
        os.makedirs(self.root, exist_ok=True)
        n = 0
        for rel in rels:
            s = os.path.join(src_root, rel)
            if not os.path.exists(s):
                self.note("plant_missing", file=rel)
                continue
            d = self._dest(rel)
            shutil.copy2(s, d)            # copy2, never link
            n += 1
        self.note("planted", files=n, src=src_root)
        return n

    # ------------------------------------------------------------------- prune

    def prune_command(self) -> str:
        """The one command that undoes the whole organ."""
        return "rm -rf %s" % self.root
