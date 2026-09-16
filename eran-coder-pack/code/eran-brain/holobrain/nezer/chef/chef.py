#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CHEF — הַשֶּׁף — the nezer's private cook. It keeps the shoot fed, and it is not the shoot.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-01 07:58:  *"תסדר לנצר שף פרטי"*

The nezer ate its four starter files and then starved. Measured, not guessed — from its
own journal on eran3 at 07:55:22:

    {"kind": "chose", "what": "digest: refit gate + exam, pantry empty",
     "why": "no unfed food; last exam 0.4828", "batch": 0}

Its whole pantry was 15 files. Its appetite had grown to 6 and had nothing to bite. The
exam has been frozen at 0.4828 across rounds because the shoot is re-digesting the same
mouths. A shoot whose entire job is *"more mouths, more hours, more situations"* cannot
do that job without a kitchen behind it. This is the kitchen.

## THE SHAPE — three places, and that is the whole safety argument

    ~/nezer-chef/          THE KITCHEN   (this file, its menu, its ledgers, its larder)
    ~/nezer-food/chef-*/   THE COUNTER   (flat .wav dirs the nezer reads as its pantry)
    ~/nezer/               THE SHOOT     (the diner — untouched but for one merged file)

The chef **never writes inside the shoot** except one file, `corpus/sources.json`, and
there it *merges*: it owns only entries it stamped `"chef": true`, and copies every other
entry through untouched, so the exam source and the exam-negative source and anything
Iddo adds by hand survive every reconcile. Everything else it writes lands in the kitchen
or on the counter, and `_may_write()` refuses any path outside those three — realpath
first, on every write — the same law the nezer keeps on itself.

**Prune symmetry, which is the property being bought:**

  * `rm -rf ~/nezer` — the chef keeps running. It logs that there is no diner, stops
    serving, and the moment a shoot is replanted there it re-declares its shelves and
    starts serving again. Nothing in the kitchen is lost.
  * `rm -rf ~/nezer-chef` — the nezer keeps eating. The counter is not in the kitchen,
    so every file already served is still sitting on it and `corpus/sources.json` still
    points at those directories. The shoot degrades to "no NEW food" — where it was this
    morning — not to broken.

Both directions are proved in `--selftest`, not asserted here.

## WHAT IT SERVES, AND WHAT IT WILL NOT

The nezer's door is a hard law and the chef does not weaken it: every source it declares
carries `human: true` and a real licence string, so intake accepts it for the right
reason. On its own side, before a byte moves, the chef also refuses:

  * **the exam.** The held-out session 2026-07-04 is blocked four ways — by the exact
    sha256 of all six of its WAVs, by filename prefix, by the date appearing ANYWHERE in
    a filename, and by `exclude_dates` on every entry the chef writes.
  * **the leak sessions** 2026-06-25 and 2026-07-01, which `cafe_eval.py` on eran4
    reserves verbatim: *"permanently excluded from any training pool"*.
  * **anything synthetic.** The chef has no code path that can declare `human: false`.
    ERAN's own mouth productions stay exam negatives, placed by hand, as they are now.
  * **anything it has already served**, ever, keyed by content sha256 and not by name.

**The substring rule was not foresight — it was a hole the first real tick opened.** The
voice-ant-farm train split holds `iddo1__cafe-20260704__00124.wav`: a clip cut out of the
nezer's own held-out exam, invisible to a prefix test and — being a resampled segment —
invisible to the exam WAVs' sha256 too. 26 of its 405 files are that. Another 150 have
manifest `speaker_id: "head-sim"`: ERAN's simulated mouth, not a human at all. A split
labelled "train" is not a promise about provenance. So shelves may carry `deny_contains`
and, better, `allow_contains` — naming what may pass is stronger than listing what may
not — and `--audit` re-judges everything already on the counter whenever a rule tightens.

## POLITENESS, BECAUSE THE FLEET IS BUSY

nice 19, one small batch per tick, a pause between file copies, a hard cap on the bytes
allowed to sit on the counter, and a free-space floor beneath which it stops entirely. It
touches no GPU and starts no model. Every decision — served, skipped, refused, capped,
pruned — lands as one JSON line in `log/chef.jsonl`.

    python3 chef.py --selftest              # prove every law on a throwaway root
    python3 chef.py --tick                  # one round of cooking, then exit
    python3 chef.py --run --pause 900       # the standing kitchen (systemd runs this)
    python3 chef.py --status                # what is on the counter right now
    python3 chef.py --audit                 # re-judge the counter after a menu change
    touch ~/nezer-chef/STOP                 # halts it at the next checkpoint
"""

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

# The chef may cook on the senses box, the shoot's box, or the audio box. NEVER on the PC
# (workspace law: bulk work does not happen on Iddo's machine) and NEVER on eran1, whose
# hostname is deliberately absent here exactly as it is absent from nezer.py: the organism
# lives there and this thing does not know that hostname exists.
FLEET = ("eran2", "eran3", "eran4",
         "edgexpert-041d",     # eran2 — the senses
         "edgexpert-01e6",     # eran3 — the shoot's soil, and the kitchen's
         "edgexpert-3636")     # eran4 — Darwish + audio

DEFAULTS = {
    "nezer_root": "~/nezer",
    "pantry_root": "~/nezer-food",
    "larder_root": "~/nezer-chef/larder",
    "target_depth": 40,        # keep at least this many UNSERVED files on the counter
    "serve_batch": 12,         # never place more than this per tick
    "tick_seconds": 900,
    "counter_cap_gb": 8.0,     # hard cap on the bytes sitting on the counter
    "min_free_gb": 100.0,      # stop cooking if the disk gets tighter than this
    "copy_pause_ms": 400,      # breathe between files — bandwidth-gentle by construction
    "prune_eaten": True,
    "prune_after_hours": 1.0,
    "nice": 19,
    "never_serve": {"sha256": [], "hash_dirs": [],
                    "filename_prefixes": [], "filename_contains": []},
    "shelves": [],
}


# ------------------------------------------------------------------ small honest helpers

def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _under(root: str, path: str) -> bool:
    """realpath first: a symlink out of the tree must not walk past a naive startswith."""
    try:
        r = os.path.realpath(root)
        p = os.path.realpath(path)
    except OSError:
        return False
    return p == r or p.startswith(r + os.sep)


def _expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def _spread_key(name: str) -> str:
    """Deterministic shuffle of a shelf's filenames.

    FLEURS ships `u00000.wav … u03241.wav` in speaker order, so serving alphabetically
    would feed the shoot one mouth at a time — the precise failure this whole kitchen
    exists to end. Ordering by a hash of the NAME (not the bytes: no I/O) mixes speakers
    across the counter while staying reproducible across restarts.
    """
    return hashlib.sha1(name.encode("utf-8")).hexdigest()


def _dir_bytes(d: str) -> int:
    tot = 0
    if not os.path.isdir(d):
        return 0
    for f in os.listdir(d):
        p = os.path.join(d, f)
        try:
            if os.path.isfile(p):
                tot += os.path.getsize(p)
        except OSError:
            pass
    return tot


def _free_bytes(d: str) -> int:
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    try:
        s = os.statvfs(d)
        return s.f_bavail * s.f_frsize
    except (OSError, AttributeError):
        return 1 << 60          # not measurable (Windows) -> do not fabricate a limit


# --------------------------------------------------------------------------- the kitchen

class Chef:
    def __init__(self, root: str, menu_path: str = None):
        self.root = _expand(root)
        self.menu_path = (_expand(menu_path) if menu_path
                          else os.path.join(self.root, "menu.json"))
        self.logp = os.path.join(self.root, "log", "chef.jsonl")
        self.stop = os.path.join(self.root, "STOP")
        self.menu = dict(DEFAULTS)
        self._block = None
        self._name_blocked = {}

    # ------------------------------------------------------------------ safety

    def guard(self) -> None:
        host = socket.gethostname().split(".")[0].lower()
        if not any(host.startswith(f) for f in FLEET):
            raise SystemExit(
                "chef refuses to run on '%s'. Bulk file work does not happen on the PC, "
                "and eran1 runs the organism. Run it on %s." % (host, "/".join(FLEET)))

    def stopped(self) -> bool:
        return os.path.exists(self.stop)

    def _may_write(self, path: str) -> bool:
        """Three places and nothing else: the kitchen, the counter, the one merged file."""
        p = os.path.abspath(path)
        if _under(self.root, p):
            return True
        try:
            if os.path.realpath(p) == os.path.realpath(self._sources_path()):
                return True
        except OSError:
            pass
        pr = _expand(self.menu["pantry_root"])
        if _under(pr, p):
            rel = os.path.relpath(os.path.realpath(p),
                                  os.path.realpath(pr)).replace("\\", "/").split("/")
            return bool(rel) and rel[0].startswith("chef-")
        return False

    def _write(self, path: str, data, binary: bool = False) -> None:
        if not self._may_write(path):
            raise RuntimeError(
                "REFUSED: %s is outside the kitchen, the counter and the one merged "
                "sources file. The chef does not write there." % path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        mode = "wb" if binary else "w"
        kw = {} if binary else {"encoding": "utf-8"}
        with io.open(tmp, mode, **kw) as f:
            f.write(data)
        os.replace(tmp, path)

    def _write_json(self, path: str, obj) -> None:
        self._write(path, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")

    def _copy(self, src: str, dst: str) -> None:
        if not self._may_write(dst):
            raise RuntimeError("REFUSED: %s is outside the chef's three places." % dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)                       # copy2, never link — the nezer's law

    def log(self, kind: str, **fields) -> dict:
        rec = {"t": _now(), "kind": kind}
        rec.update(fields)
        try:
            os.makedirs(os.path.dirname(self.logp), exist_ok=True)
            with io.open(self.logp, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return rec

    # -------------------------------------------------------------------- menu

    def load_menu(self) -> dict:
        m = dict(DEFAULTS)
        if os.path.exists(self.menu_path):
            with io.open(self.menu_path, encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                m[k] = v
        ns = dict(DEFAULTS["never_serve"])
        ns.update(m.get("never_serve", {}))
        m["never_serve"] = ns
        self.menu = m
        return m

    def shelves(self, enabled_only: bool = True) -> list:
        out = []
        for s in self.menu.get("shelves", []):
            if enabled_only and not s.get("enabled", True):
                continue
            if not s.get("name") or not s.get("license"):
                self.log("refused_shelf", name=s.get("name"),
                         why="a shelf needs a name and a licence, or the nezer's door "
                             "would refuse it anyway")
                continue
            out.append(s)
        return out

    def larder_dir(self, shelf: dict) -> str:
        return _expand(shelf.get("larder") or
                       os.path.join(self.menu["larder_root"], shelf["name"]))

    def source_name(self, shelf: dict) -> str:
        return "chef-" + shelf["name"]

    def counter_dir(self, shelf: dict) -> str:
        return os.path.join(_expand(self.menu["pantry_root"]), self.source_name(shelf))

    # ------------------------------------------------------------- the diner's state

    def _sources_path(self) -> str:
        return os.path.join(_expand(self.menu["nezer_root"]), "corpus", "sources.json")

    def nezer_seen(self):
        """The shoot's intake ledger, read-only and defensively. None = cannot tell."""
        p = os.path.join(_expand(self.menu["nezer_root"]), "state", "intake.json")
        try:
            with io.open(p, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def reconcile_sources(self) -> str:
        """Merge the chef's shelves into the shoot's pantry declaration. Idempotent.

        Entries WITHOUT `"chef": true` are copied through untouched — that is how the
        exam source, the exam negatives and anything Iddo writes by hand survive.
        """
        sp = self._sources_path()
        if not os.path.isdir(os.path.dirname(sp)):
            return "absent"
        try:
            with io.open(sp, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            self.log("sources_unreadable", where=sp, why=str(e)[:160])
            return "unreadable"
        keep = [s for s in cfg.get("sources", []) if not s.get("chef")]
        mine = []
        for sh in self.shelves():
            d = self.counter_dir(sh)
            os.makedirs(d, exist_ok=True)
            excl = sorted(set(list(self.menu["never_serve"].get("filename_prefixes", [])) +
                              list(sh.get("exclude_prefixes", []))))
            mine.append({
                "name": self.source_name(sh),
                "dir": d,
                "role": "intake",
                "human": True,                        # the door's law, never weakened
                "speaker": sh.get("speaker", "?"),
                "license": sh["license"],
                "exclude_dates": excl,
                "chef": True,
            })
        new = dict(cfg)
        new["sources"] = keep + mine
        if json.dumps(new, sort_keys=True) == json.dumps(cfg, sort_keys=True):
            return "unchanged"
        self._write_json(sp, new)
        self.log("sources_reconciled", kept=len(keep), chef_entries=len(mine))
        return "written"

    # --------------------------------------------------------------- the ledgers

    def _sload(self, name, default):
        p = os.path.join(self.root, "state", name)
        try:
            with io.open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _ssave(self, name, obj):
        self._write_json(os.path.join(self.root, "state", name), obj)

    def blocklist(self) -> set:
        """sha256 of everything that must never reach the counter. Cached by size+mtime."""
        if self._block is not None:
            return self._block
        cache = self._sload("blocklist.json", {"stamp": {}, "sha": []})
        block = set(self.menu["never_serve"].get("sha256", []))
        block |= set(cache.get("sha", []))
        stamp = dict(cache.get("stamp", {}))
        changed = False
        for d in self.menu["never_serve"].get("hash_dirs", []):
            d = _expand(d)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if not os.path.isfile(p):
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                key = "%s:%d:%d" % (p, st.st_size, int(st.st_mtime))
                if key in stamp:
                    block.add(stamp[key])
                    continue
                h = _sha256(p)
                stamp[key] = h
                block.add(h)
                changed = True
        if changed or not os.path.exists(os.path.join(self.root, "state",
                                                      "blocklist.json")):
            self._ssave("blocklist.json", {"stamp": stamp, "sha": sorted(block)})
        self._block = block
        return block

    # ------------------------------------------------------------------ cooking

    def _known(self):
        return self._sload("known.json", {})       # "<shelf>/<basename>" -> sha256

    def _served(self):
        return self._sload("served.json", {})      # sha256 -> {shelf, file, bytes, t}

    def _blocked_name(self, shelf: dict, name: str) -> str:
        """'' if the name is allowed, else the reason it is not.

        The prefix rule alone is not enough, and that was caught the hard way on the very
        first real tick (2026-09-01 08:24). The voice-ant-farm train split names a clip
        `iddo1__cafe-20260704__00124.wav` — cut FROM the nezer's held-out exam session,
        invisible to a startswith() test and, being a resampled segment, invisible to the
        exam files' sha256 as well. The same split also holds 150 clips whose manifest
        speaker_id is `head-sim` — ERAN's own simulated mouth, not a human at all.
        So: substrings anywhere in the name, and a positive allow-list per shelf, because
        naming what MAY pass is stronger than listing what may not.
        """
        pre = tuple(list(self.menu["never_serve"].get("filename_prefixes", [])) +
                    list(shelf.get("exclude_prefixes", [])))
        if pre and name.startswith(pre):
            return "reserved filename prefix"
        for sub in (list(self.menu["never_serve"].get("filename_contains", [])) +
                    list(shelf.get("deny_contains", []))):
            if sub in name:
                return "denied substring %r" % sub
        allow = shelf.get("allow_contains")
        if allow and not any(a in name for a in allow):
            return "not on this shelf's allow-list %r" % (list(allow),)
        return ""

    def candidates(self, shelf: dict) -> list:
        d = self.larder_dir(shelf)
        if not os.path.isdir(d):
            return []
        names = [f for f in os.listdir(d) if f.lower().endswith(".wav")]
        keep, why = [], {}
        for f in names:
            r = self._blocked_name(shelf, f)
            if r:
                why[r] = why.get(r, 0) + 1
            else:
                keep.append(f)
        self._name_blocked[shelf["name"]] = why
        keep.sort(key=_spread_key)
        return keep

    def depth(self, shelf: dict, seen) -> tuple:
        """(unserved, total) on this shelf's counter, counted exactly as the nezer would."""
        d = self.counter_dir(shelf)
        if not os.path.isdir(d):
            return (0, 0)
        files = [f for f in os.listdir(d) if f.lower().endswith(".wav")]
        if seen is None:
            return (len(files), len(files))
        n = self.source_name(shelf)
        un = 0
        for f in files:
            try:
                key = "%s:%s:%d" % (n, f, os.path.getsize(os.path.join(d, f)))
            except OSError:
                continue
            if key not in seen:
                un += 1
        return (un, len(files))

    def prune_eaten(self, seen) -> int:
        """Clear plates. A file the shoot has taken is a copy it already owns."""
        if seen is None or not self.menu.get("prune_eaten", True):
            return 0
        grace = float(self.menu.get("prune_after_hours", 1.0)) * 3600.0
        gone = 0
        for sh in self.shelves():
            d = self.counter_dir(sh)
            if not os.path.isdir(d):
                continue
            n = self.source_name(sh)
            for f in sorted(os.listdir(d)):
                if not f.lower().endswith(".wav"):
                    continue
                p = os.path.join(d, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if "%s:%s:%d" % (n, f, st.st_size) not in seen:
                    continue
                if time.time() - st.st_mtime < grace:
                    continue
                if not self._may_write(p):
                    continue
                try:
                    os.remove(p)
                    gone += 1
                except OSError:
                    pass
        if gone:
            self.log("pruned_eaten", files=gone)
        return gone

    @staticmethod
    def _allocate(need: int, avail: list) -> dict:
        """avail: [(name, weight, n_candidates)] -> {name: n}. Largest remainder, then
        fill the leftover round-robin so a light shelf never blocks a hungry counter."""
        live = [(n, float(w), c) for n, w, c in avail if c > 0 and float(w) > 0]
        if need <= 0 or not live:
            return {}
        cap = {n: c for n, _, c in live}
        tot = sum(w for _, w, _ in live)
        raw = {n: need * w / tot for n, w, _ in live}
        alloc = {n: min(int(v), cap[n]) for n, v in raw.items()}
        rem = need - sum(alloc.values())
        # Largest RELATIVE remainder: a tie on the absolute fraction (3:1 over 6 leaves
        # both shelves owed exactly 0.5) goes to the shelf for whom that half-file is the
        # bigger share of its meal. Leftovers drift toward variety, deterministically.
        order = sorted(live, key=lambda t: (-((raw[t[0]] - int(raw[t[0]])) / raw[t[0]]),
                                            t[0]))
        while rem > 0:
            progressed = False
            for n, _, c in order:
                if rem <= 0:
                    break
                if alloc[n] < c:
                    alloc[n] += 1
                    rem -= 1
                    progressed = True
            if not progressed:
                break
        return {k: v for k, v in alloc.items() if v > 0}

    def tick(self) -> dict:
        self.load_menu()
        if self.stopped():
            return self.log("stopped", why="STOP file present at %s" % self.stop)
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        state = self.reconcile_sources()
        self.audit()
        seen = self.nezer_seen()
        self.prune_eaten(seen)

        counter_bytes = sum(_dir_bytes(self.counter_dir(s)) for s in self.shelves())
        cap = float(self.menu["counter_cap_gb"]) * (1 << 30)
        free = _free_bytes(_expand(self.menu["pantry_root"]))
        floor = float(self.menu["min_free_gb"]) * (1 << 30)

        depths = {s["name"]: self.depth(s, seen) for s in self.shelves()}
        total_unserved = sum(v[0] for v in depths.values())
        target = int(self.menu["target_depth"])

        if state == "absent":
            return self.log("idle", why="no shoot at %s — nothing to feed; the kitchen "
                                        "keeps running" % self.menu["nezer_root"],
                            unserved=total_unserved)
        if counter_bytes >= cap:
            return self.log("capped", unserved=total_unserved,
                            why="counter holds %.2f GB, cap %.2f GB"
                                % (counter_bytes / (1 << 30), cap / (1 << 30)))
        if free < floor:
            return self.log("disk_floor", unserved=total_unserved,
                            why="only %.1f GB free, floor %.1f GB"
                                % (free / (1 << 30), floor / (1 << 30)))
        if total_unserved >= target:
            return self.log("full", unserved=total_unserved, target=target,
                            why="the counter is stocked; the shoot's appetite governs")

        need = min(int(self.menu["serve_batch"]), target - total_unserved)
        known, served, block = self._known(), self._served(), self.blocklist()
        avail, pool = [], {}
        for sh in self.shelves():
            cands = []
            for name in self.candidates(sh):
                h = known.get("%s/%s" % (sh["name"], name))
                if h is not None and (h in served or h in block):
                    continue
                cands.append(name)
            pool[sh["name"]] = cands
            avail.append((sh["name"], sh.get("weight", 1), len(cands)))
        alloc = self._allocate(need, avail)

        placed, refused = [], []
        pause = float(self.menu["copy_pause_ms"]) / 1000.0
        by_name = {s["name"]: s for s in self.shelves()}
        for shelf_name, n in sorted(alloc.items()):
            sh = by_name[shelf_name]
            src_dir, dst_dir = self.larder_dir(sh), self.counter_dir(sh)
            os.makedirs(dst_dir, exist_ok=True)
            done = 0
            for name in pool[shelf_name]:
                if done >= n or self.stopped():
                    break
                sp = os.path.join(src_dir, name)
                key = "%s/%s" % (shelf_name, name)
                try:
                    h = known.get(key) or _sha256(sp)
                except OSError as e:
                    refused.append({"file": key, "why": str(e)[:80]})
                    continue
                known[key] = h
                if h in block:
                    refused.append({"file": key,
                                    "why": "blocklisted sha256 — exam or reserved session"})
                    continue
                if h in served:
                    continue
                dp = os.path.join(dst_dir, name)
                if os.path.exists(dp):
                    served[h] = {"shelf": shelf_name, "file": name,
                                 "bytes": os.path.getsize(dp), "t": _now()}
                    continue
                try:
                    self._copy(sp, dp)
                except (OSError, RuntimeError) as e:
                    refused.append({"file": key, "why": str(e)[:120]})
                    continue
                sz = os.path.getsize(dp)
                served[h] = {"shelf": shelf_name, "file": name, "bytes": sz, "t": _now()}
                counter_bytes += sz
                placed.append(key)
                done += 1
                self._provenance(sh, name, h, sp, sz)
                if counter_bytes >= cap:
                    self.log("capped_mid", why="hit the counter cap while placing food")
                    break
                if pause:
                    time.sleep(pause)
            if counter_bytes >= cap:
                break

        self._ssave("known.json", known)
        self._ssave("served.json", served)
        for sh in self.shelves():
            self._attribution(sh)
        return self.log("served", n=len(placed), files=placed[:20], alloc=alloc,
                        unserved_before=total_unserved, target=target,
                        refused=refused[:10], sources=state,
                        name_blocked={k: v for k, v in self._name_blocked.items() if v},
                        counter_gb=round(counter_bytes / (1 << 30), 3))

    def _provenance(self, shelf: dict, name: str, sha: str, origin: str, size: int) -> None:
        p = os.path.join(self.counter_dir(shelf), "PROVENANCE.jsonl")
        if not self._may_write(p):
            return
        line = json.dumps({"t": _now(), "file": name, "sha256": sha, "bytes": size,
                           "origin": origin, "shelf": shelf["name"], "human": True,
                           "speaker": shelf.get("speaker", "?"),
                           "license": shelf["license"]}, ensure_ascii=False) + "\n"
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with io.open(p, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def _attribution(self, shelf: dict) -> None:
        p = os.path.join(self.counter_dir(shelf), "ATTRIBUTION.txt")
        txt = ("%s\n\nlicence: %s\nspeaker: %s\nlarder:  %s\n\n"
               "Every clip cut from this food carries the licence line above. It does not\n"
               "stop travelling because the clip got shorter.\n"
               % (self.source_name(shelf), shelf["license"],
                  shelf.get("speaker", "?"), self.larder_dir(shelf)))
        try:
            if os.path.exists(p):
                with io.open(p, encoding="utf-8") as f:
                    if f.read() == txt:
                        return
            self._write(p, txt)
        except (OSError, RuntimeError):
            pass

    def audit(self) -> dict:
        """Re-judge everything already on the counter against the CURRENT menu.

        Rules get tightened after something is discovered — that is the normal case, not
        the exceptional one. Anything that would be refused today is recalled from the
        counter now. It stays in the served ledger, so a recall is permanent: the file is
        never placed again. Runs at the top of every tick, and standalone via --audit.
        """
        self.load_menu()
        block = self.blocklist()
        pulled = []
        for sh in self.shelves(enabled_only=False):
            d = self.counter_dir(sh)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.lower().endswith(".wav"):
                    continue
                p = os.path.join(d, f)
                why = self._blocked_name(sh, f)
                if not why:
                    try:
                        if _sha256(p) in block:
                            why = "blocklisted sha256"
                    except OSError:
                        continue
                if not why or not self._may_write(p):
                    continue
                try:
                    os.remove(p)
                    pulled.append({"file": "%s/%s" % (sh["name"], f), "why": why})
                except OSError:
                    pass
        if pulled:
            self.log("recalled", n=len(pulled), files=pulled[:20])
        return {"recalled": len(pulled), "files": pulled}

    # ------------------------------------------------------------------- drive

    def run(self, pause: float = None, rounds: int = 0) -> int:
        self.guard()
        self.load_menu()
        try:
            os.nice(int(self.menu.get("nice", 19)))
        except (AttributeError, OSError):
            pass
        pause = float(pause if pause is not None else self.menu["tick_seconds"])
        self.log("kitchen_open", host=socket.gethostname(), root=self.root,
                 pause_s=pause, pid=os.getpid())
        n = 0
        while True:
            if self.stopped():
                self.log("stopped", why="STOP file present")
                return 0
            try:
                self.tick()
            except Exception as e:                                    # noqa: BLE001
                self.log("tick_error", why="%s: %s" % (type(e).__name__, str(e)[:200]))
            n += 1
            if rounds and n >= rounds:
                return 0
            slept = 0.0
            while slept < pause:
                time.sleep(min(5.0, pause - slept))
                slept += 5.0
                if self.stopped():
                    self.log("stopped", why="STOP file appeared mid-pause")
                    return 0

    def status(self) -> int:
        self.load_menu()
        seen = self.nezer_seen()
        served = self._served()
        nz = _expand(self.menu["nezer_root"])
        print("chef   root=%s  host=%s" % (self.root, socket.gethostname()))
        print("shoot  %s   (%s)" % (nz, "present" if os.path.isdir(nz) else "ABSENT"))
        print("served ever: %d files, %.2f GB"
              % (len(served), sum(v.get("bytes", 0) for v in served.values()) / (1 << 30)))
        tot_un = 0
        for sh in self.shelves(enabled_only=False):
            on = sh.get("enabled", True)
            un, tot = self.depth(sh, seen) if on else (0, 0)
            tot_un += un
            print("  %-14s w=%-3s larder=%-6d counter=%-5d unserved=%-5d %s"
                  % (sh.get("name"), sh.get("weight", 1),
                     len(self.candidates(sh)) if on else 0, tot, un,
                     "" if on else "(disabled)"))
        print("counter unserved total: %d   (target %d)"
              % (tot_un, self.menu["target_depth"]))
        print("free on the pantry filesystem: %.1f GB   (floor %.1f GB)"
              % (_free_bytes(_expand(self.menu["pantry_root"])) / (1 << 30),
                 float(self.menu["min_free_gb"])))
        return 0


# ---------------------------------------------------------------------------- the proofs

def selftest() -> int:
    """Every law, on a throwaway root, with real files. PASS/FAIL per check, no narration."""
    import struct
    import tempfile
    import wave

    fails, ok = [], []

    def check(name, cond, detail=""):
        (ok if cond else fails).append(name)
        print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                              ("   [%s]" % detail) if detail and not cond else ""))

    def mkwav(path, seed=1, secs=0.2):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        n = int(16000 * secs)
        frames = b"".join(struct.pack("<h", ((i * seed) % 2000) - 1000) for i in range(n))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(frames)

    def wavs(d):
        return sorted(f for f in os.listdir(d) if f.lower().endswith(".wav"))

    tmp = tempfile.mkdtemp(prefix="chef-selftest-")
    try:
        kitchen = os.path.join(tmp, "nezer-chef")
        pantry = os.path.join(tmp, "nezer-food")
        shoot = os.path.join(tmp, "nezer")
        os.makedirs(os.path.join(shoot, "corpus"))
        os.makedirs(os.path.join(shoot, "state"))
        exam = os.path.join(pantry, "exam-20260704")
        for i in range(2):
            mkwav(os.path.join(exam, "202607041700%02d.wav" % i), seed=90 + i)
        with io.open(os.path.join(shoot, "corpus", "sources.json"), "w",
                     encoding="utf-8") as f:
            json.dump({"ear3_python": "/x/py", "sources": [
                {"name": "held-exam", "dir": exam, "role": "exam", "human": True,
                 "speaker": "iddo", "license": "held out, never fed"},
                {"name": "negs", "dir": os.path.join(pantry, "negs"),
                 "role": "exam-negative", "human": False, "synthetic": True,
                 "license": "ERAN's own mouth productions"}]}, f)
        os.makedirs(os.path.join(pantry, "negs"))
        with io.open(os.path.join(shoot, "state", "intake.json"), "w",
                     encoding="utf-8") as f:
            json.dump({}, f)

        larder = os.path.join(kitchen, "larder")
        for i in range(30):
            mkwav(os.path.join(larder, "many", "u%05d.wav" % i), seed=i + 3)
        for i in range(20):
            mkwav(os.path.join(larder, "mine", "20260626_%03d.wav" % i), seed=i + 40)
        # the traps. 1+2: the exam session itself, once by its own name and once renamed.
        shutil.copy2(os.path.join(exam, "20260704170000.wav"),
                     os.path.join(larder, "mine", "20260704170000.wav"))
        shutil.copy2(os.path.join(exam, "20260704170001.wav"),
                     os.path.join(larder, "mine", "innocent-looking-name.wav"))
        exam_sha = {_sha256(os.path.join(exam, f)) for f in os.listdir(exam)}
        # 3: the trap that was real, and that a prefix test cannot see — a SEGMENT cut
        # from the exam session, resampled (so a different sha256) and named the way the
        # voice-ant-farm split names it. Caught on the first live tick, 2026-09-01 08:24.
        mkwav(os.path.join(larder, "mine", "iddo1__cafe-20260704__00124.wav"),
              seed=7, secs=0.11)
        # 4: not a human at all — manifest speaker_id "head-sim", ERAN's simulated mouth.
        for i in range(3):
            mkwav(os.path.join(larder, "mine", "head-sim__mouth-20260808__0000%d.wav" % i),
                  seed=60 + i)

        menu = {
            "nezer_root": shoot, "pantry_root": pantry, "larder_root": larder,
            "target_depth": 10, "serve_batch": 6, "copy_pause_ms": 0,
            "counter_cap_gb": 100.0, "min_free_gb": 0.0, "prune_after_hours": 0.0,
            "never_serve": {"hash_dirs": [exam],
                            "filename_prefixes": ["20260625", "20260701", "20260704"],
                            "filename_contains": ["20260625", "20260701", "20260704"]},
            "shelves": [
                {"name": "many", "larder": os.path.join(larder, "many"), "weight": 3,
                 "speaker": "many-mouths", "license": "TEST corpus — CC0-1.0"},
                {"name": "mine", "larder": os.path.join(larder, "mine"), "weight": 1,
                 "speaker": "iddo", "license": "TEST — Iddo's own recordings",
                 "deny_contains": ["head-sim"]}]}
        os.makedirs(kitchen, exist_ok=True)
        with io.open(os.path.join(kitchen, "menu.json"), "w", encoding="utf-8") as f:
            json.dump(menu, f)

        def setmenu(**kw):
            m = json.load(io.open(os.path.join(kitchen, "menu.json"), encoding="utf-8"))
            m.update(kw)
            with io.open(os.path.join(kitchen, "menu.json"), "w", encoding="utf-8") as f:
                json.dump(m, f)

        def eat_everything():
            """Stand in for the shoot: record every file on the counter as taken, using
            the exact key nezer.py's intake() writes -- name:basename:size."""
            seen = {}
            for d in ("chef-many", "chef-mine"):
                dd = os.path.join(pantry, d)
                if not os.path.isdir(dd):
                    continue
                for f in wavs(dd):
                    seen["%s:%s:%d" % (d, f, os.path.getsize(os.path.join(dd, f)))] = {}
            with io.open(os.path.join(shoot, "state", "intake.json"), "w",
                         encoding="utf-8") as f:
                json.dump(seen, f)
            return seen

        print("\n-- the door, and what lands on the counter")
        c = Chef(kitchen)
        c.tick()
        cfg = json.load(io.open(os.path.join(shoot, "corpus", "sources.json"),
                                encoding="utf-8"))
        names = [s["name"] for s in cfg["sources"]]
        check("hand-written sources survive reconcile",
              "held-exam" in names and "negs" in names, str(names))
        check("chef declared its own shelves",
              "chef-many" in names and "chef-mine" in names, str(names))
        chef_e = [s for s in cfg["sources"] if s.get("chef")]
        check("every chef entry says human:true + a licence",
              bool(chef_e) and all(s["human"] is True and s["license"] for s in chef_e))
        check("every chef entry excludes the reserved dates",
              all({"20260625", "20260701", "20260704"} <= set(s["exclude_dates"])
                  for s in chef_e))
        check("unrelated keys preserved (ear3_python)", cfg.get("ear3_python") == "/x/py")
        check("chef never declares synthetic food",
              not any(s.get("synthetic") or s.get("human") is False for s in chef_e))

        served1 = c._served()
        check("served exactly one serve_batch", len(served1) == 6, str(len(served1)))
        n_many = sum(1 for v in served1.values() if v["shelf"] == "many")
        n_mine = sum(1 for v in served1.values() if v["shelf"] == "mine")
        check("weights honoured 3:1 -> 4 many / 2 mine",
              (n_many, n_mine) == (4, 2), "%d/%d" % (n_many, n_mine))
        check("provenance + attribution written beside the food",
              os.path.exists(os.path.join(pantry, "chef-many", "PROVENANCE.jsonl")) and
              os.path.exists(os.path.join(pantry, "chef-many", "ATTRIBUTION.txt")))
        att = io.open(os.path.join(pantry, "chef-many", "ATTRIBUTION.txt"),
                      encoding="utf-8").read()
        check("the attribution file carries the licence string", "CC0-1.0" in att)

        print("\n-- never twice, and the diner's appetite still governs")
        c.tick()                       # tops the counter up to target_depth = 10
        before = len(c._served())
        r = c.tick()
        check("a stocked counter is not restocked",
              len(c._served()) == before and r["kind"] == "full",
              "%s / %d" % (r["kind"], before))
        seenmap = eat_everything()
        eaten_n = len(seenmap)
        c.tick()
        still = [f for f in wavs(os.path.join(pantry, "chef-many"))
                 if "chef-many:%s:%d" % (f, os.path.getsize(
                     os.path.join(pantry, "chef-many", f))) in seenmap]
        check("the shoot had really eaten something", eaten_n > 0, str(eaten_n))
        check("eaten plates are cleared from the counter", still == [], str(still))
        keys = ["%s/%s" % (v["shelf"], v["file"]) for v in c._served().values()]
        check("no file served twice, ever", len(keys) == len(set(keys)))
        check("restocking resumed after the plates were cleared",
              len(c._served()) > before, "%d -> %d" % (before, len(c._served())))

        print("\n-- the exam is unreachable, three ways (drain the whole larder at it)")
        setmenu(target_depth=500, serve_batch=200)
        for _ in range(4):
            eat_everything()
            Chef(kitchen).tick()
        c = Chef(kitchen)
        served = c._served()
        larder_n = len(os.listdir(os.path.join(larder, "many"))) + \
            len(os.listdir(os.path.join(larder, "mine")))
        check("the whole larder really was walked past the traps",
              len(served) == larder_n - 6, "%d served of %d in the larder"
              % (len(served), larder_n))
        check("no exam sha256 was ever served", not (exam_sha & set(served)))
        placed = {v["file"] for v in served.values()}
        check("the RENAMED exam file was refused (by hash)",
              "innocent-looking-name.wav" not in placed)
        check("the 20260704-named file was refused (by prefix)",
              "20260704170000.wav" not in placed)
        check("a SEGMENT of the exam was refused (date inside the name)",
              "iddo1__cafe-20260704__00124.wav" not in placed)
        check("the simulated mouth was refused (deny_contains head-sim)",
              not any("head-sim" in f for f in placed),
              str([f for f in placed if "head-sim" in f]))
        on_counter = {_sha256(os.path.join(pantry, d, f))
                      for d in ("chef-many", "chef-mine")
                      for f in wavs(os.path.join(pantry, d))}
        check("nothing sitting on the counter hashes to the exam",
              not (exam_sha & on_counter))
        log = io.open(os.path.join(kitchen, "log", "chef.jsonl"), encoding="utf-8").read()
        check("the refusal is on the record in chef.jsonl", "blocklisted sha256" in log)
        setmenu(target_depth=10, serve_batch=6)
        # restock the larder the way a delivery would, and let the kitchen fill both
        # counters again -- the later prune-symmetry proof needs real food sitting there
        for i in range(30, 42):
            mkwav(os.path.join(larder, "many", "u%05d.wav" % i), seed=i + 3)
        for i in range(20, 28):
            mkwav(os.path.join(larder, "mine", "20260626_%03d.wav" % i), seed=i + 40)
        eat_everything()
        Chef(kitchen).tick()
        with io.open(os.path.join(shoot, "state", "intake.json"), "w",
                     encoding="utf-8") as f:
            json.dump({}, f)
        Chef(kitchen).tick()
        check("a fresh delivery is picked up on the next tick",
              all(wavs(os.path.join(pantry, d)) for d in ("chef-many", "chef-mine")),
              str({d: len(wavs(os.path.join(pantry, d)))
                   for d in ("chef-many", "chef-mine")}))

        print("\n-- --audit: a rule tightened AFTER the fact reaches back")
        cur = json.load(io.open(os.path.join(kitchen, "menu.json"), encoding="utf-8"))
        victim = wavs(os.path.join(pantry, "chef-many"))[0]
        ns = dict(cur["never_serve"])
        ns["filename_contains"] = list(ns.get("filename_contains", [])) + [victim]
        setmenu(never_serve=ns)
        r = Chef(kitchen).audit()
        check("a newly-forbidden file is recalled from the counter",
              victim not in wavs(os.path.join(pantry, "chef-many")) and
              r["recalled"] == 1, json.dumps(r))
        check("the recall is permanent: it stays in the served ledger",
              victim in {v["file"] for v in Chef(kitchen)._served().values()})
        Chef(kitchen).tick()
        check("a later tick does not put the recalled file back",
              victim not in wavs(os.path.join(pantry, "chef-many")))
        ns["filename_contains"] = [x for x in ns["filename_contains"] if x != victim]
        setmenu(never_serve=ns)

        print("\n-- the caps")
        setmenu(counter_cap_gb=0.0000001)
        n0 = len(Chef(kitchen)._served())
        r = Chef(kitchen).tick()
        check("the counter cap stops the kitchen",
              len(Chef(kitchen)._served()) == n0 and r["kind"] == "capped", r["kind"])
        setmenu(counter_cap_gb=100.0, min_free_gb=10.0 ** 9)
        if hasattr(os, "statvfs"):
            n0 = len(Chef(kitchen)._served())
            r = Chef(kitchen).tick()
            check("the free-space floor stops the kitchen",
                  len(Chef(kitchen)._served()) == n0 and r["kind"] == "disk_floor",
                  r["kind"])
        else:
            print("  SKIP  free-space floor — os.statvfs does not exist on this OS, so "
                  "_free_bytes honestly returns 'unmeasurable' rather than a fake limit "
                  "(the kitchen's real home is Linux, where this check runs)")
        setmenu(min_free_gb=0.0)
        open(os.path.join(kitchen, "STOP"), "w").close()
        n0 = len(Chef(kitchen)._served())
        r = Chef(kitchen).tick()
        check("the STOP file halts the kitchen",
              len(Chef(kitchen)._served()) == n0 and r["kind"] == "stopped", r["kind"])
        os.remove(os.path.join(kitchen, "STOP"))

        print("\n-- the write jail")
        c3 = Chef(kitchen)
        c3.load_menu()
        for label, path in (
                ("outside everything", os.path.join(tmp, "elsewhere", "x.json")),
                ("inside the shoot (not sources.json)",
                 os.path.join(shoot, "journal.jsonl")),
                ("a pantry dir it does not own",
                 os.path.join(pantry, "exam-20260704", "x.wav")),
                ("the exam-negatives dir", os.path.join(pantry, "negs", "x.wav"))):
            try:
                c3._write(path, "no")
                check("refuses to write: %s" % label, False, path)
            except RuntimeError:
                check("refuses to write: %s" % label, True)
        check("but DOES allow the one merged sources.json",
              c3._may_write(c3._sources_path()))

        print("\n-- the hostname guard")
        real = socket.gethostname
        for host in ("IDDO1-pc", "eran1", "edgexpert-9999"):
            socket.gethostname = (lambda h: (lambda: h))(host)
            try:
                Chef(kitchen).guard()
                check("guard refuses %s" % host, False)
            except SystemExit:
                check("guard refuses %s" % host, True)
        socket.gethostname = lambda: "edgexpert-01e6"
        try:
            Chef(kitchen).guard()
            check("guard admits eran3 (edgexpert-01e6)", True)
        except SystemExit:
            check("guard admits eran3 (edgexpert-01e6)", False)
        socket.gethostname = real

        print("\n-- PRUNE SYMMETRY, both directions, measured")
        shutil.rmtree(shoot)
        r = Chef(kitchen).tick()
        check("rm -rf the shoot: the kitchen survives and says why it is idle",
              r.get("kind") == "idle", r.get("kind"))
        r = Chef(kitchen).tick()
        check("rm -rf the shoot: a second tick still does not crash",
              r.get("kind") == "idle", r.get("kind"))
        check("rm -rf the shoot: the kitchen's ledgers are intact",
              len(Chef(kitchen)._served()) > 0)
        os.makedirs(os.path.join(shoot, "corpus"))
        os.makedirs(os.path.join(shoot, "state"))
        with io.open(os.path.join(shoot, "corpus", "sources.json"), "w",
                     encoding="utf-8") as f:
            json.dump({"sources": []}, f)
        Chef(kitchen).tick()
        cfg2 = json.load(io.open(os.path.join(shoot, "corpus", "sources.json"),
                                 encoding="utf-8"))
        check("replant the shoot: the kitchen re-declares its shelves unasked",
              len([s for s in cfg2["sources"] if s.get("chef")]) == 2,
              str([s["name"] for s in cfg2["sources"]]))

        before_files = {d: wavs(os.path.join(pantry, d))
                        for d in ("chef-many", "chef-mine")}
        shutil.rmtree(kitchen)
        after_files = {d: wavs(os.path.join(pantry, d))
                       for d in ("chef-many", "chef-mine")}
        check("rm -rf the kitchen: the shoot is untouched", os.path.isdir(shoot))
        check("rm -rf the kitchen: food already served stays on the counter",
              before_files == after_files and sum(map(len, after_files.values())) > 0,
              str({k: len(v) for k, v in after_files.items()}))
        cfg3 = json.load(io.open(os.path.join(shoot, "corpus", "sources.json"),
                                 encoding="utf-8"))
        alive = [s for s in cfg3["sources"] if s.get("chef") and os.path.isdir(s["dir"])]
        check("rm -rf the kitchen: the shoot's pantry still points at real food",
              len(alive) == 2 and all(wavs(s["dir"]) for s in alive),
              str([(s["name"], os.path.isdir(s["dir"])) for s in cfg3["sources"]]))

        print("\n-- the REAL nezer's own door (set NEZER_PY to run it)")
        nz = os.environ.get("NEZER_PY", "")
        if nz and os.path.exists(nz):
            import importlib.util
            spec = importlib.util.spec_from_file_location("nezer_mod", nz)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            probe = os.path.join(tmp, "probe")
            os.makedirs(os.path.join(probe, "corpus"))
            shutil.copy2(os.path.join(shoot, "corpus", "sources.json"),
                         os.path.join(probe, "corpus", "sources.json"))
            got = mod.Nezer(probe).sources()["sources"]
            accepted = [s for s in got if s.get("chef")]
            check("the REAL nezer door accepts every chef entry",
                  len(accepted) == len(alive), "%d accepted of %d"
                  % (len(accepted), len(alive)))
            files = mod.Nezer(probe)._pantry_files(accepted[0]) if accepted else []
            check("the REAL nezer can list the food on the counter", len(files) > 0,
                  str(len(files)))
        else:
            print("  SKIP  NEZER_PY unset or absent — optional by design "
                  "(the kitchen must not depend on the shoot)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(ok), len(fails)))
    for f in fails:
        print("   FAILED: %s" % f)
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CHEF — keeps the nezer's pantry stocked.")
    ap.add_argument("--root", default=os.environ.get("CHEF_ROOT", "~/nezer-chef"))
    ap.add_argument("--menu", default=None)
    ap.add_argument("--tick", action="store_true", help="cook one round and exit")
    ap.add_argument("--run", action="store_true", help="the standing kitchen")
    ap.add_argument("--rounds", type=int, default=0)
    ap.add_argument("--pause", type=float, default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--audit", action="store_true",
                    help="re-judge the counter against the current menu and recall "
                         "anything that would be refused today")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    c = Chef(a.root, a.menu)
    if a.status:
        return c.status()
    if a.audit:
        c.guard()
        print(json.dumps(c.audit(), ensure_ascii=False))
        return 0
    if a.tick:
        c.guard()
        c.load_menu()
        try:
            os.nice(int(c.menu.get("nice", 19)))
        except (AttributeError, OSError):
            pass
        print(json.dumps(c.tick(), ensure_ascii=False))
        return 0
    if a.run:
        return c.run(pause=a.pause, rounds=a.rounds)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
