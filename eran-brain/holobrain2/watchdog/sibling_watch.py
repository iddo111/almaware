# -*- coding: utf-8 -*-
"""
THE SIBLING'S WATCHDOG  --  an instrument, not a nurse.

Iddo, 2026-09-01 12:31: "tasim alav Watchdog 24-7".

WHY IT EXISTS
-------------
Two of this project's organs are sick in the same way tonight, and both
diseases hid for weeks because nothing outside them was looking:

  * the THROAT's wdist ruler is burst-blind (amputating the /b/ from 100 human
    takes costs +0.074, 2% of the band, noise 7x signal) -- six consecutive
    ear-rejections of clips it had approved.
  * the NEZER's 4-band gate detects 4 of 29 negatives, FROZEN across ten
    refits since birth.  Exam pinned at 0.431, below chance 0.5.

Both are the LayerNorm(1) scar: a component that LOOKS like it is learning and
is structurally incapable of moving.  A number that never moves is not a stable
number -- it is a dead wire, and by eye it takes weeks to notice.

So this process reads the sibling's own artifacts from OUTSIDE it, every few
minutes, forever, and says the true thing out loud.

THE SIX THINGS IT WATCHES
-------------------------
  1 FROZEN     the objective unchanged (|delta| < eps) across N rounds
  2 DEAD       a sub-score that has never moved in the WHOLE history
  3 DIVERGE    the objective below its honest floor, below its birth value,
               or falling away from its own best
  4 STALL      no round in the expected window / unit inactive / PID gone /
               disk filling / the tree missing or shrinking / code swapped
  5 SEAL       any symlink, any realpath escaping the tree, any hardlink, any
               file descriptor of the organism outside its own root or inside
               ERAN's trees.  Checked EVERY cycle, never once.
  6 BLIND      the watchdog auditing ITSELF: every detector is run against a
               synthetic fixture each cycle and must still fire, and must stay
               silent on the healthy twin of that fixture.  A detector that has
               gone quiet is the same disease, one level up.

WHAT IT WILL NEVER DO
---------------------
It never restarts, never repairs, never touches the organism.  Every command it
runs is a read (systemctl show / is-active, /proc, statvfs, open 'r').  Its ONLY
writes are inside its own root: _write() refuses every other path, and
--selfaudit greps this source for repair verbs.  A watchdog that fixes things in
the dark is how a project starts lying to itself.

LAWS: eran1 is never reached (FORBIDDEN_HOSTS refuses to start there).  The
sibling stays sealed.  Pure stdlib.  PYTHONIOENCODING=utf-8.
"""

import argparse
import io
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
import datetime as dt

HOME = os.path.expanduser("~")
WATCH_ROOT = os.path.join(HOME, "sibling-watch")

# ERAN himself lives on eran1.  This never runs there and never reaches it.
FORBIDDEN_HOSTS = ("eran1", "spark-eran1")

# Trees the sibling may not touch -- not even read.  Its licence to exist is
# that it reads its OWN copies, never ERAN's live state.
FORBIDDEN_PREFIXES = [
    os.path.join(HOME, "eran"),
    os.path.join(HOME, "eran-eye"),
    os.path.join(HOME, "eran-cortex"),
    os.path.join(HOME, "ear-v3"),
]

# --------------------------------------------------------------------------
# thresholds -- every one is a claim, so every one is named here
# --------------------------------------------------------------------------
FROZEN_WINDOW = 6         # rounds the objective must be still before we shout
FROZEN_EPS = 1e-9         # "unchanged" means unchanged, not "small"
DEAD_MIN_HIST = 6         # history a series needs before DEAD is a fair verdict
DECLINE_DELTA = 0.05      # this far under its own best ...
DECLINE_WINDOW = 5        # ... sustained this many rounds = divergence
STALL_TOL = 2.5           # a round may be this many periods late
DISK_WARN = 85
DISK_ALARM = 92
REPOST_HOURS = 6          # a standing alarm re-reaches RAMCHAT this often
LOG_BYTES = 1000000
LOG_KEEP = 5

ALARM, WARN, OK = "ALARM", "WARN", "OK"
RANK = {OK: 0, WARN: 1, ALARM: 2}


# --------------------------------------------------------------------------
# The organisms.  Declared, not guessed -- including which series are ALLOWED
# to be constant, each with its reason, so "constant by design" can never
# become a hiding place for a dead wire.
# --------------------------------------------------------------------------
def default_organs():
    return [
        {
            "name": "ear",
            "what": "the sibling's learning loop -- naming human syllables",
            "root": os.path.join(HOME, "sibling-ear"),
            "code": "/home/eran3/sibling_ear.py",
            "unit": "sibling-ear.service",
            "journal": "journal.jsonl",
            "round_kind": ["kind", "round"],
            "period_s": 3600,
            "objective": "exam",
            "floors": {"chance": 0.0833, "shuffled": 0.0806},
            "born_field": "born",
            "series": {
                "exam": {"must_move": True},
                "ruler": {"must_move": True},
                "dev": {"must_move": True},
                "g_move": {"must_move": True},
                "bias_move": {"must_move": True},
                "gate_move": {"must_move": True},
                "theta": {"must_move": True},
                "tau": {"must_move": True},
                "hushed": {"must_move": False,
                           "why": "reaching 0 and staying there is the GOAL. "
                                  "Flat at 0 is health; flat above 0 is not, and "
                                  "the frozen detector still reads it."},
                "born": {"must_move": False,
                         "why": "the inherited ear, measured once at birth. If "
                                "this ever moves, the baseline was rewritten."},
            },
        },
        {
            "name": "birth",
            "what": "the sibling itself -- the second whole holobrain",
            "root": os.path.join(HOME, "sibling"),
            "code": os.path.join(HOME, "sibling", "sibling.py"),
            "unit": "sibling.service",
            "journal": "journal.jsonl",
            "round_kind": ["event", "round"],
            "period_s": 1800,
            "objective": "correct",
            "floors": {},
            "born_field": None,
            "series": {
                "correct": {"must_move": True},
                "n": {"must_move": False,
                      "why": "the size of the exam, 12 units. A count, not a score."},
            },
        },
    ]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def now():
    return dt.datetime.now()


def iso(t=None):
    return (t or now()).strftime("%Y-%m-%dT%H:%M:%S")


def human_age(seconds):
    seconds = int(max(0, seconds))
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%dm" % (seconds // 60)
    if seconds < 172800:
        return "%.1fh" % (seconds / 3600.0)
    return "%.1fd" % (seconds / 86400.0)


def parse_ts(rec):
    """The two organisms journal time differently ('t' local, 'utc' with Z).
    Read both rather than demanding they agree."""
    for key in ("t", "utc", "ts", "time"):
        v = rec.get(key)
        if not isinstance(v, str):
            continue
        s = v.strip()
        try:
            if s.endswith("Z"):
                d = dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
                return d.replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
            d = dt.datetime.fromisoformat(s)
            if d.tzinfo is not None:
                d = d.astimezone().replace(tzinfo=None)
            return d
        except Exception:
            continue
    return None


def read_rounds(path, kind_field, kind_value):
    """Every well-formed round record, oldest first.  A malformed line is
    counted, never fatal: this reads a file the organism is appending to."""
    rounds, bad = [], 0
    if not os.path.isfile(path):
        return rounds, bad
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                if rec.get(kind_field) == kind_value:
                    rounds.append(rec)
    except Exception:
        bad += 1
    return rounds, bad


def series_of(rounds, name):
    out = []
    for r in rounds:
        v = r.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out.append(float(v))
    return out


class Finding(object):
    __slots__ = ("level", "code", "organ", "series", "msg", "nums", "key")

    def __init__(self, level, code, organ, msg, series=None, nums=None, key=None):
        self.level, self.code, self.organ = level, code, organ
        self.series, self.msg, self.nums = series, msg, nums or {}
        self.key = key

    def sig(self):
        return "%s/%s/%s" % (self.organ, self.code, self.series or "-")

    def stable(self):
        """SCAR, 2026-09-01 13:47.  Alarms were de-duplicated by comparing the
        rendered message -- but a FROZEN message carries a LIVE AGE ("14m",
        "15m"), so no two cycles ever matched, and RAMCHAT would have been told
        the same thing every three minutes forever.  An alarm nobody can bear
        to read has been silenced just as surely as one that never fires.

        Identity is now an explicit key chosen by the detector: what the alarm
        is ABOUT, with the ticking parts left out."""
        k = self.key if self.key is not None else re.sub(r"[0-9]+", "#", self.msg)
        return self.sig() + "|" + k

    def line(self):
        who = self.organ if not self.series else "%s.%s" % (self.organ, self.series)
        return "%-5s %-8s %-16s %s" % (self.level, self.code, who, self.msg)

    def as_dict(self):
        return {"level": self.level, "code": self.code, "organ": self.organ,
                "series": self.series, "msg": self.msg, "nums": self.nums}


# ==========================================================================
# THE DETECTORS
#
# Each is a pure function of already-read facts.  Pure on purpose: the same
# function that judges the live organism is the one the fixtures exercise
# every cycle, so a detector cannot rot in the dark.
# ==========================================================================

def detect_frozen(organ, rounds, blind=()):
    """1 FROZEN -- the objective has not moved for FROZEN_WINDOW rounds.

    A frozen objective is not automatically a disease: an organism that has
    genuinely converged also stops moving.  So the verdict is decided by what
    is happening INSIDE it.

      * objective still, some learnable sub-score still moving -> WARN.
        Plateau; the machinery is alive.
      * objective still AND every learnable sub-score still -> ALARM.
        That is the nezer exactly: it eats and learns nothing.
    """
    out = []
    if "frozen" in blind:
        return out
    name = organ["objective"]
    vals = series_of(rounds, name)
    if len(vals) < FROZEN_WINDOW:
        return out
    win = vals[-FROZEN_WINDOW:]
    spread = max(win) - min(win)
    if spread > FROZEN_EPS:
        return out

    # how long has it been still?  walk back while it stays equal
    v = win[-1]
    held = 0
    for x in reversed(vals):
        if abs(x - v) <= FROZEN_EPS:
            held += 1
        else:
            break
    since = None
    if len(rounds) >= held:
        since = parse_ts(rounds[len(rounds) - held])
    age = ("%s, since %s" % (human_age((now() - since).total_seconds()), iso(since))
           if since else "unknown age")

    movers, stills = [], []
    for s, cfg in organ["series"].items():
        if s == name or not cfg.get("must_move"):
            continue
        sv = series_of(rounds, s)
        if len(sv) < FROZEN_WINDOW:
            continue
        w = sv[-FROZEN_WINDOW:]
        (movers if (max(w) - min(w)) > FROZEN_EPS else stills).append(s)

    said = {}
    for k in ("stall", "verdict", "murphy", "seal"):
        if k in rounds[-1]:
            said[k] = rounds[-1][k]
    nums = {"objective": name, "value": v, "rounds_held": held,
            "window": FROZEN_WINDOW, "still_inside": stills,
            "moving_inside": movers, "it_says_of_itself": said}
    if movers:
        out.append(Finding(
            WARN, "FROZEN", organ["name"], series=name, nums=nums,
            key="plateau@%.6f" % v,
            msg="%s = %.4f unchanged for %d rounds (%s), but %s still moving "
                "-- plateau, machinery alive" % (name, v, held, age, "+".join(movers))))
    else:
        out.append(Finding(
            ALARM, "FROZEN", organ["name"], series=name, nums=nums,
            key="stuck@%.6f" % v,
            msg="%s = %.4f unchanged for %d rounds (%s) AND every learnable "
                "sub-score is still too (%s). It is eating and learning nothing "
                "-- this is the nezer's shape." % (name, v, held, age,
                                                   "+".join(stills) or "none measurable")))
    return out


def detect_dead(organ, rounds, blind=()):
    """2 DEAD -- a sub-score that has NEVER moved across the whole history.

    This is the detector that would have caught both of tonight's diseases
    weeks earlier: LayerNorm(1) returning a constant, and TN=4 for ten refits.
    Series declared constant-by-design are reported, with their reason, but
    never alarmed on -- and the declaration is in the config where it can be
    read and argued with.
    """
    out = []
    if "dead" in blind:
        return out
    for s, cfg in sorted(organ["series"].items()):
        vals = series_of(rounds, s)
        if len(vals) < DEAD_MIN_HIST:
            continue
        if (max(vals) - min(vals)) > FROZEN_EPS:
            continue
        if not cfg.get("must_move"):
            continue
        first = parse_ts(rounds[0])
        span = human_age((now() - first).total_seconds()) if first else "?"
        out.append(Finding(
            ALARM, "DEAD", organ["name"], series=s,
            key="dead@%.6f" % vals[0],
            nums={"value": vals[0], "history": len(vals), "span": span},
            msg="%s = %.6f in ALL %d rounds on record (%s). It has never moved "
                "once. A dead wire, not a stable number -- the LayerNorm(1) scar."
                % (s, vals[0], len(vals), span)))
    return out


def detect_diverge(organ, rounds, blind=()):
    """3 DIVERGE -- the objective below an honest floor, below what it was
    born with, or falling away from its own best."""
    out = []
    if "diverge" in blind:
        return out
    name = organ["objective"]
    vals = series_of(rounds, name)
    if not vals:
        return out
    last = vals[-1]

    for label, floor in sorted((organ.get("floors") or {}).items()):
        if last < float(floor) - 1e-12:
            out.append(Finding(
                ALARM, "DIVERGE", organ["name"], series=name,
                key="below-%s@%.4f" % (label, last),
                nums={"value": last, "floor": floor, "floor_name": label},
                msg="%s = %.4f is BELOW its %s floor %.4f. Worse than not "
                    "trying." % (name, last, label, float(floor))))

    bf = organ.get("born_field")
    if bf:
        born = series_of(rounds, bf)
        if born and last < born[-1] - 1e-12:
            out.append(Finding(
                ALARM, "DIVERGE", organ["name"], series=name,
                key="below-born@%.4f" % last,
                nums={"value": last, "born": born[-1]},
                msg="%s = %.4f is BELOW the value it was BORN with (%.4f). "
                    "Everything it has learned made it worse."
                    % (name, last, born[-1])))

    if len(vals) >= DECLINE_WINDOW + 1:
        best = max(vals)
        tail = vals[-DECLINE_WINDOW:]
        if best - max(tail) > DECLINE_DELTA:
            out.append(Finding(
                ALARM, "DIVERGE", organ["name"], series=name,
                key="backwards@%.4f" % best,
                nums={"best": best, "recent_best": max(tail),
                      "drop": best - max(tail), "window": DECLINE_WINDOW},
                msg="%s peaked at %.4f and has not been within %.3f of it for "
                    "%d rounds (recent best %.4f). It is going backwards."
                    % (name, best, DECLINE_DELTA, DECLINE_WINDOW, max(tail))))
    return out


def detect_stall(organ, facts, blind=()):
    """4 STALL -- the organism stopped, or the ground under it moved.

    facts is a dict gathered by look_at(); this stays pure so the fixtures can
    drive it with hand-made facts.
    """
    out = []
    if "stall" in blind:
        return out
    o = organ["name"]

    if not facts.get("root_exists"):
        out.append(Finding(ALARM, "STALL", o, key="tree-gone",
                           msg="its tree %s IS GONE." % organ["root"]))
        return out

    if facts.get("stop_file"):
        out.append(Finding(WARN, "STALL", o, key="stop-file",
                           msg="a STOP file is present -- somebody halted it on "
                               "purpose. Not a fault, but it is not running."))

    if facts.get("journal_missing"):
        out.append(Finding(ALARM, "STALL", o, key="journal-missing",
                           msg="journal.jsonl is missing from %s." % organ["root"]))

    n = facts.get("n_rounds", 0)
    age = facts.get("last_round_age_s")
    period = organ["period_s"]
    if n == 0:
        out.append(Finding(WARN, "STALL", o, key="no-rounds-ever",
                           msg="no round has ever been journalled."))
    elif age is None:
        out.append(Finding(WARN, "STALL", o, key="no-timestamp",
                           msg="the last round carries no readable timestamp."))
    elif age > period * STALL_TOL and not facts.get("stop_file"):
        out.append(Finding(
            ALARM, "STALL", o, key="round-overdue",
            nums={"age_s": age, "period_s": period},
            msg="no round for %s. Expected one every %s (tolerance x%.1f)."
                % (human_age(age), human_age(period), STALL_TOL)))

    st = facts.get("unit_active")
    if st is not None and st != "active":
        out.append(Finding(
            ALARM, "STALL", o, key="unit-%s" % st,
            nums={"ActiveState": st, "unit": organ["unit"]},
            msg="systemd unit %s is %s (sub=%s, %d restarts). It is not running."
                % (organ["unit"], st, facts.get("unit_sub"), facts.get("unit_nrestarts", 0))))
    elif st == "active" and facts.get("pid_alive") is False:
        out.append(Finding(
            ALARM, "STALL", o, key="pid-gone", nums={"MainPID": facts.get("pid")},
            msg="systemd calls %s active but MainPID %s is not in /proc."
                % (organ["unit"], facts.get("pid"))))

    if facts.get("restarts_recent"):
        out.append(Finding(
            WARN, "STALL", o, key="restarts",
            nums={"NRestarts": facts.get("unit_nrestarts")},
            msg="the unit has restarted %d times. Something keeps killing it."
                % facts.get("unit_nrestarts", 0)))

    base = facts.get("baseline_files")
    have = facts.get("n_files")
    if base and have is not None and have < base * 0.9:
        out.append(Finding(
            ALARM, "STALL", o, key="tree-shrunk",
            nums={"files_now": have, "files_baseline": base},
            msg="its tree has SHRUNK: %d files now, %d at baseline. Something is "
                "deleting it." % (have, base)))

    if facts.get("code_missing"):
        out.append(Finding(ALARM, "STALL", o, key="code-missing",
                           msg="its code %s is missing." % organ["code"]))
    elif facts.get("code_changed"):
        out.append(Finding(
            WARN, "STALL", o,
            key="code-changed@%s" % (facts.get("code_sha") or "?")[:12],
            nums={"sha_now": facts.get("code_sha"),
                                    "sha_baseline": facts.get("code_sha_baseline")},
            msg="its code %s CHANGED under the running process (sha %s -> %s). "
                "The numbers before and after are not comparable."
                % (organ["code"], (facts.get("code_sha_baseline") or "?")[:12],
                   (facts.get("code_sha") or "?")[:12])))
    return out


def detect_seal(organ, facts, blind=()):
    """5 SEAL -- the sibling's whole licence to exist.  Checked every cycle.

    A symlink, a realpath leaving the tree, a hardlink (the birth's law is
    copy2-never-link), or a file descriptor of the living process outside its
    own root -- especially one inside ERAN's trees.
    """
    out = []
    if "seal" in blind:
        return out
    o = organ["name"]
    for p in facts.get("symlinks", []):
        out.append(Finding(ALARM, "SEAL", o, key="symlink:" + p[0],
                           nums={"path": p[0], "target": p[1]},
                           msg="SYMLINK inside the sealed tree: %s -> %s" % (p[0], p[1])))
    for p in facts.get("escapes", []):
        out.append(Finding(ALARM, "SEAL", o, key="escape:" + p[0],
                           nums={"path": p[0], "real": p[1]},
                           msg="a path ESCAPES the tree: %s really lives at %s"
                               % (p[0], p[1])))
    for p in facts.get("hardlinks", []):
        out.append(Finding(ALARM, "SEAL", o, key="hardlink:" + p[0],
                           nums={"path": p[0], "nlink": p[1]},
                           msg="HARDLINK (nlink=%d): %s. The birth's law is "
                               "copy2-never-link -- this file is shared with "
                               "something outside." % (p[1], p[0])))
    for fd in facts.get("fd_escapes", []):
        out.append(Finding(
            ALARM, "SEAL", o, key="fd:" + str(fd.get("target")), nums=fd,
            msg=(fd["note"] + ": " + fd.get("target")) if fd.get("note") else
                ("pid %s holds %s open on %s -- OUTSIDE its own root%s"
                 % (fd.get("pid"), fd.get("mode"), fd.get("target"),
                    ". THAT IS ERAN'S TREE." if fd.get("forbidden") else "."))))
    return out


# --------------------------------------------------------------------------
# 6 BLIND -- the watchdog audits itself, every cycle
# --------------------------------------------------------------------------
def _fixture_organ():
    return {
        "name": "FIXTURE", "what": "synthetic", "root": "/nonexistent",
        "code": "/nonexistent", "unit": "none", "journal": "journal.jsonl",
        "round_kind": ["kind", "round"], "period_s": 60, "objective": "exam",
        "floors": {"chance": 0.10}, "born_field": "born",
        "series": {"exam": {"must_move": True}, "sub": {"must_move": True},
                   "born": {"must_move": False, "why": "fixture constant"}},
    }


def _fixture_rounds(mode):
    """mode 'sick' must set every detector off; mode 'well' must set none."""
    base = now() - dt.timedelta(seconds=30)
    rs = []
    for i in range(12):
        t = iso(base)
        if mode == "sick":
            rs.append({"t": t, "kind": "round", "exam": 0.05, "sub": 1.0, "born": 0.2})
        else:
            rs.append({"t": t, "kind": "round", "exam": 0.30 + 0.01 * i,
                       "sub": 1.0 + 0.5 * i, "born": 0.2})
    return rs


def _fixture_facts(mode):
    if mode == "sick":
        return {"root_exists": True, "n_rounds": 12, "last_round_age_s": 99999,
                "unit_active": "failed", "unit_sub": "dead", "unit_nrestarts": 9,
                "pid_alive": False, "pid": 1234, "restarts_recent": True,
                "baseline_files": 100, "n_files": 3, "code_changed": True,
                "code_sha": "b" * 64, "code_sha_baseline": "a" * 64,
                "symlinks": [("/x/link", "/home/eran3/eran-eye")],
                "escapes": [("/x/f", "/tmp/f")],
                "hardlinks": [("/x/h", 2)],
                "fd_escapes": [{"pid": 1, "mode": "w", "target": "/home/eran3/eran/x",
                                "forbidden": True}]}
    return {"root_exists": True, "n_rounds": 12, "last_round_age_s": 10,
            "unit_active": "active", "unit_sub": "running", "unit_nrestarts": 0,
            "pid_alive": True, "pid": 1234, "restarts_recent": False,
            "baseline_files": 100, "n_files": 100, "code_changed": False,
            "symlinks": [], "escapes": [], "hardlinks": [], "fd_escapes": []}


def audit_detectors(blind=()):
    """Run every detector against a sick fixture and a well fixture.

    A detector that fails to fire on the sick fixture has itself become the
    disease it is there to catch -- so it raises BLIND, loudly, naming which
    detector went quiet.  A detector that fires on the WELL fixture is crying
    wolf, which is just as corrosive, and raises too.
    """
    org = _fixture_organ()
    checks = [
        ("frozen", lambda m: detect_frozen(org, _fixture_rounds(m), blind)),
        ("dead", lambda m: detect_dead(org, _fixture_rounds(m), blind)),
        ("diverge", lambda m: detect_diverge(org, _fixture_rounds(m), blind)),
        ("stall", lambda m: detect_stall(org, _fixture_facts(m), blind)),
        ("seal", lambda m: detect_seal(org, _fixture_facts(m), blind)),
    ]
    out, report = [], {}

    # --- the allowlist property test -------------------------------------
    # Written because the fixtures above fed detect_seal() ready-made facts and
    # never exercised the code that GATHERS them -- which is where the scar of
    # 2026-09-01 13:41 lived. A detector is not covered until the gathering half
    # is covered too.
    try:
        bad_root = os.path.join(HOME, "any-sealed-root")
        _, refused = sane_allowlist(bad_root, [HOME, "/", FORBIDDEN_PREFIXES[0]])
        ok_allowed, ok_refused = sane_allowlist(bad_root, [os.path.join(HOME, "x.py")])
        report["fd_allowlist"] = {"refused": len(refused), "kept": len(ok_allowed)}
        if len(refused) != 3 or ok_refused:
            out.append(Finding(
                ALARM, "BLIND", "watchdog", series="fd_allowlist",
                msg="the fd allowlist guard is not holding: HOME / root / an "
                    "ERAN tree were not all refused (refused=%d of 3). The seal "
                    "check can be silently whitelisted again." % len(refused)))
    except Exception as e:
        out.append(Finding(ALARM, "BLIND", "watchdog", series="fd_allowlist",
                           msg="the fd allowlist guard CRASHED: %s" % e))

    for name, fn in checks:
        try:
            sick = fn("sick")
            well = fn("well")
        except Exception as e:
            out.append(Finding(ALARM, "BLIND", "watchdog", series=name,
                               msg="detector '%s' CRASHED on its fixture: %s"
                                   % (name, e)))
            report[name] = "crash"
            continue
        n_sick = len([f for f in sick if f.level == ALARM])
        report[name] = {"fired_on_sick": n_sick, "fired_on_well": len(well)}
        if n_sick == 0:
            out.append(Finding(
                ALARM, "BLIND", "watchdog", series=name,
                msg="detector '%s' did NOT fire on a fixture built to set it "
                    "off. The instrument is blind -- every OK it printed is "
                    "worthless until this is fixed." % name))
        if well:
            out.append(Finding(
                ALARM, "BLIND", "watchdog", series=name,
                msg="detector '%s' fired on the HEALTHY fixture (%s). It is "
                    "crying wolf." % (name, well[0].code)))
    return out, report


# SCAR, 2026-09-01 13:43.  The first pattern here could not cross a quote, so
# the ordinary argv form ["systemctl", "--user", "restart", u] walked straight
# past it: a tampered copy carrying exactly that line audited CLEAN.  The
# patterns now span quotes and commas.  They also match their own definitions,
# so the block is fenced and audit_source() cuts it out before searching --
# the fence is why the sentinels below are load-bearing, not decoration.
# AUDIT-PATTERNS-BEGIN
SOURCE_FORBIDDEN = [
    (r"systemctl[\s\S]{0,120}?\b(restart|reload|enable|disable)\b",
     "it would command systemd"),
    (r"[\"']systemctl[\"'][\s\S]{0,160}?[\"'](start|stop|restart|reload)[\"']",
     "it would command systemd through argv"),
    (r"\bsubprocess\.[a-z_]+\([^)]*\bkill\b", "it would kill a process"),
    (r"\bos\.kill\b", "it would kill a process"),
    (r"\bshutil\.rmtree\b", "it would delete a tree"),
    (r"\bos\.remove\b|\bos\.unlink\b", "it would delete a file"),
]
# AUDIT-PATTERNS-END


def audit_source():
    """--selfaudit: this source may not contain a repair verb.

    'It never repairs' is a promise, and a promise nobody checks is decoration.
    """
    out = []
    try:
        src = io.open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    except Exception as e:
        return [Finding(WARN, "BLIND", "watchdog",
                        msg="could not read own source to audit it: %s" % e)], {}
    # cut the fenced pattern block out, then the comments: what is left is the
    # code that actually runs, and that is what gets searched.
    keep, inside = [], False
    for l in src.splitlines():
        t = l.strip()
        if t == "# AUDIT-PATTERNS-BEGIN":
            inside = True
            continue
        if t == "# AUDIT-PATTERNS-END":
            inside = False
            continue
        if inside or t.startswith("#"):
            continue
        keep.append(l)
    if inside:
        return [Finding(ALARM, "BLIND", "watchdog",
                        msg="the audit-pattern fence is unclosed -- the source "
                            "audit just searched nothing. Treat it as failed.")], {}
    body = "\n".join(keep)
    hits = {}
    for pat, why in SOURCE_FORBIDDEN:
        m = re.search(pat, body)
        if m:
            hits[pat] = m.group(0)
            out.append(Finding(ALARM, "BLIND", "watchdog",
                               msg="this watchdog's own source contains %r -- %s. "
                                   "It is no longer only an observer."
                                   % (m.group(0), why)))
    return out, {"patterns_checked": len(SOURCE_FORBIDDEN), "hits": hits}


# ==========================================================================
# LOOKING -- every call here is a read
# ==========================================================================
def sh(args, timeout=15):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except Exception as e:
        return -1, str(e)


def unit_facts(unit):
    rc, out = sh(["systemctl", "--user", "show", unit,
                  "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
                  "-p", "NRestarts", "-p", "LoadState"])
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    if d.get("LoadState") in (None, "not-found"):
        return {"unit_active": "not-found", "unit_sub": "-", "unit_nrestarts": 0,
                "pid": 0, "pid_alive": None, "restarts_recent": False}
    pid = int(d.get("MainPID") or 0)
    nres = int(d.get("NRestarts") or 0)
    return {"unit_active": d.get("ActiveState"), "unit_sub": d.get("SubState"),
            "unit_nrestarts": nres, "pid": pid,
            "pid_alive": (os.path.isdir("/proc/%d" % pid) if pid else False),
            "restarts_recent": nres > 0}


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def walk_seal(root):
    """Symlinks, realpath escapes, hardlinks.  os.walk with followlinks=False."""
    symlinks, escapes, hardlinks, n_files, nbytes = [], [], [], 0, 0
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for nm in list(dirnames):
            p = os.path.join(dirpath, nm)
            if os.path.islink(p):
                symlinks.append((p, os.path.realpath(p)))
                dirnames.remove(nm)
        for nm in filenames:
            p = os.path.join(dirpath, nm)
            if os.path.islink(p):
                symlinks.append((p, os.path.realpath(p)))
                continue
            n_files += 1
            rp = os.path.realpath(p)
            if not (rp == real_root or rp.startswith(real_root + os.sep)):
                escapes.append((p, rp))
            try:
                st = os.lstat(p)
                nbytes += st.st_size
                if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                    hardlinks.append((p, st.st_nlink))
            except Exception:
                pass
    return {"symlinks": symlinks, "escapes": escapes, "hardlinks": hardlinks,
            "n_files": n_files, "bytes": nbytes}


def pid_family(pid):
    """The process and its children -- a leak can happen in a worker too."""
    if not pid or not os.path.isdir("/proc/%d" % pid):
        return []
    fam = [pid]
    try:
        for e in os.listdir("/proc"):
            if not e.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % e, "r") as f:
                    parts = f.read().rsplit(")", 1)[1].split()
                if int(parts[1]) == pid:
                    fam.append(int(e))
            except Exception:
                continue
    except Exception:
        pass
    return fam


def sane_allowlist(root, extra):
    """SCAR, 2026-09-01 13:41.  The first version of fd_escapes() was handed
    os.path.dirname(code) as an allowance.  The ear's code is
    /home/eran3/sibling_ear.py, so the allowance was /home/eran3 -- THE WHOLE
    HOME, ERAN's trees included.  The detector reported seal=intact while a
    process held /home/eran3/eran-eye/eye.py open.  It looked like a check and
    was structurally incapable of firing: the LayerNorm(1) scar, in the
    watchdog itself, caught only because a real fd was injected.

    So an allowance is now refused if it is HOME, or /, or an ancestor of any
    forbidden tree.  The refusal is returned, not swallowed, and raises BLIND.
    """
    real_root = os.path.realpath(root)
    forbidden = [os.path.realpath(p) for p in FORBIDDEN_PREFIXES]
    home = os.path.realpath(HOME)
    allowed, refused = [real_root], []
    for p in extra:
        rp = os.path.realpath(p)
        if rp in ("/", home):
            refused.append((rp, "it is HOME or / -- it would allow everything"))
            continue
        if any(f == rp or f.startswith(rp + os.sep) for f in forbidden):
            refused.append((rp, "it contains one of ERAN's trees"))
            continue
        allowed.append(rp)
    return allowed, refused


def fd_escapes(pids, root, extra_allowed=()):
    """Every file descriptor of the organism that resolves outside its own
    root.  Sockets, pipes, /dev/null and the interpreter's own libraries are
    excused by name; everything else is named out loud.

    A path inside one of ERAN's trees is judged FIRST and can never be excused
    by any allowance -- that ordering is the whole point of the seal."""
    real_root = os.path.realpath(root)
    allowed, refused = sane_allowlist(root, extra_allowed)
    out = []
    for rp, why in refused:
        out.append({"pid": 0, "fd": "-", "mode": "config", "target": rp,
                    "forbidden": True,
                    "note": "REFUSED as an allowance: %s" % why})
    for pid in pids:
        fddir = "/proc/%d/fd" % pid
        if not os.path.isdir(fddir):
            continue
        try:
            entries = os.listdir(fddir)
        except Exception:
            continue
        for e in entries:
            try:
                tgt = os.readlink(os.path.join(fddir, e))
            except Exception:
                continue
            if not tgt.startswith("/") or tgt.startswith(("/dev/", "/proc/", "/sys/",
                                                          "/usr/", "/lib", "/etc/",
                                                          "/memfd:")):
                continue
            # ERAN's trees are judged BEFORE any allowance. Nothing excuses them.
            forbidden = any(tgt == p or tgt.startswith(p + os.sep)
                            for p in [os.path.realpath(q) for q in FORBIDDEN_PREFIXES])
            if not forbidden and any(tgt == a or tgt.startswith(a + os.sep)
                                     for a in allowed):
                continue
            mode = "r"
            try:
                for line in open("/proc/%d/fdinfo/%s" % (pid, e)):
                    if line.startswith("flags:"):
                        fl = int(line.split()[1], 8)
                        mode = "w" if (fl & 3) in (1, 2) else "r"
            except Exception:
                pass
            out.append({"pid": pid, "fd": e, "mode": mode, "target": tgt,
                        "forbidden": forbidden})
    return out


def look_at(organ, baselines):
    """Gather every fact about one organism.  Reads only."""
    root = organ["root"]
    f = {"root_exists": os.path.isdir(root)}
    if not f["root_exists"]:
        return f, []
    jpath = os.path.join(root, organ["journal"])
    f["journal_missing"] = not os.path.isfile(jpath)
    f["stop_file"] = os.path.exists(os.path.join(root, "STOP"))

    kf, kv = organ["round_kind"]
    rounds, bad = read_rounds(jpath, kf, kv)
    f["n_rounds"] = len(rounds)
    f["bad_lines"] = bad
    last_ts = parse_ts(rounds[-1]) if rounds else None
    f["last_round_at"] = iso(last_ts) if last_ts else None
    f["last_round_age_s"] = ((now() - last_ts).total_seconds() if last_ts else None)

    f.update(unit_facts(organ["unit"]))
    f.update(walk_seal(root))
    f["baseline_files"] = (baselines.get(organ["name"], {}) or {}).get("n_files")

    code = organ["code"]
    f["code_missing"] = not os.path.isfile(code)
    if not f["code_missing"]:
        f["code_sha"] = sha256_of(code)
        b = (baselines.get(organ["name"], {}) or {}).get("code_sha")
        f["code_sha_baseline"] = b
        f["code_changed"] = bool(b and f["code_sha"] and b != f["code_sha"])

    fam = pid_family(f.get("pid"))
    f["pids"] = fam
    # the code FILE, never its directory -- see the scar in sane_allowlist()
    f["fd_escapes"] = fd_escapes(fam, root, extra_allowed=([code] if code else []))
    return f, rounds


def disk_findings():
    out = []
    try:
        st = os.statvfs(HOME)
        used = 100.0 * (st.f_blocks - st.f_bfree) / max(1, st.f_blocks)
        free_gb = st.f_bavail * st.f_frsize / 1e9
        nums = {"used_pct": round(used, 1), "free_gb": round(free_gb, 1)}
        if used >= DISK_ALARM:
            out.append(Finding(ALARM, "STALL", "host", key="disk-full", nums=nums,
                               msg="disk %.1f%% full, %.0f GB left. The journals "
                                   "stop when it fills." % (used, free_gb)))
        elif used >= DISK_WARN:
            out.append(Finding(WARN, "STALL", "host", key="disk-warn", nums=nums,
                               msg="disk %.1f%% full, %.0f GB left." % (used, free_gb)))
        return out, nums
    except Exception as e:
        return [Finding(WARN, "STALL", "host", msg="cannot read disk: %s" % e)], {}


# ==========================================================================
# WRITING -- only ever inside WATCH_ROOT
# ==========================================================================
def _write(path, text, mode="w"):
    """The one door out.  Refuses any path outside the watchdog's own root, so
    'it never touches the organism' is enforced, not promised."""
    rp = os.path.realpath(path)
    root = os.path.realpath(WATCH_ROOT)
    if not (rp == root or rp.startswith(root + os.sep)):
        raise RuntimeError("REFUSED: the watchdog may only write inside %s, "
                           "never %s" % (root, rp))
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with io.open(rp, mode, encoding="utf-8") as f:
        f.write(text)


def rotate(path):
    try:
        if os.path.getsize(path) < LOG_BYTES:
            return
    except Exception:
        return
    for i in range(LOG_KEEP - 1, 0, -1):
        a, b = "%s.%d" % (path, i), "%s.%d" % (path, i + 1)
        if os.path.exists(a):
            os.replace(a, b)
    os.replace(path, path + ".1")


def log(msg):
    p = os.path.join(WATCH_ROOT, "watch.log")
    rotate(p)
    _write(p, "%s %s\n" % (iso(), msg), mode="a")


# ==========================================================================
# ONE CYCLE
# ==========================================================================
def load_json(path, default):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def cycle(organs, blind=(), quiet=False):
    findings = []
    bpath = os.path.join(WATCH_ROOT, "baselines.json")
    baselines = load_json(bpath, {})

    bf, breport = audit_detectors(blind)
    sf, sreport = audit_source()
    findings += bf + sf

    dfind, disk = disk_findings()
    findings += dfind

    organ_report = {}
    for organ in organs:
        facts, rounds = look_at(organ, baselines)
        findings += detect_stall(organ, facts, blind)
        if facts.get("root_exists"):
            findings += detect_seal(organ, facts, blind)
            findings += detect_frozen(organ, rounds, blind)
            findings += detect_dead(organ, rounds, blind)
            findings += detect_diverge(organ, rounds, blind)

        obj = organ["objective"]
        vals = series_of(rounds, obj)
        moving, still, constant = [], [], []
        for s, cfg in sorted(organ["series"].items()):
            sv = series_of(rounds, s)
            if len(sv) < 2:
                continue
            alive = (max(sv) - min(sv)) > FROZEN_EPS
            if not cfg.get("must_move"):
                constant.append("%s=%s%s" % (s, sv[-1], "" if not alive else " (MOVED!)"))
            elif alive:
                moving.append(s)
            else:
                still.append(s)
        organ_report[organ["name"]] = {
            "what": organ["what"], "root": organ["root"], "unit": organ["unit"],
            "unit_active": facts.get("unit_active"), "pid": facts.get("pid"),
            "rounds": facts.get("n_rounds"), "last_round_at": facts.get("last_round_at"),
            "last_round_age": (human_age(facts["last_round_age_s"])
                               if facts.get("last_round_age_s") is not None else None),
            "objective": obj,
            "objective_now": (vals[-1] if vals else None),
            "objective_best": (max(vals) if vals else None),
            "files": facts.get("n_files"), "bytes": facts.get("bytes"),
            "seal": ("intact" if not (facts.get("symlinks") or facts.get("escapes")
                                      or facts.get("hardlinks") or facts.get("fd_escapes"))
                     else "BREACHED"),
            "series_moving": moving, "series_still": still,
            "series_constant_by_design": constant,
            "stop_file": facts.get("stop_file"),
            "it_says_of_itself": ({k: rounds[-1][k] for k in
                                   ("stall", "verdict", "murphy", "seal")
                                   if k in rounds[-1]} if rounds else {}),
        }

        # baseline, written once, so a shrinking tree or a swapped code file
        # has something honest to be compared against
        b = baselines.setdefault(organ["name"], {})
        if facts.get("n_files") and not b.get("n_files"):
            b["n_files"] = facts["n_files"]
            b["first_seen"] = iso()
        if facts.get("code_sha") and not b.get("code_sha"):
            b["code_sha"] = facts["code_sha"]

    _write(bpath, json.dumps(baselines, indent=1, ensure_ascii=False))

    findings.sort(key=lambda f: -RANK[f.level])
    verdict = ALARM if any(f.level == ALARM for f in findings) else (
        WARN if any(f.level == WARN for f in findings) else OK)

    status = {
        "ts": iso(), "host": socket.gethostname(), "verdict": verdict,
        "n_alarm": len([f for f in findings if f.level == ALARM]),
        "n_warn": len([f for f in findings if f.level == WARN]),
        "findings": [f.as_dict() for f in findings],
        "organs": organ_report, "disk": disk,
        "self_audit": {"detectors": breport, "source": sreport,
                       "blinded_on_purpose": list(blind)},
        "interval_s": None,
    }
    _write(os.path.join(WATCH_ROOT, "status.json"),
           json.dumps(status, indent=1, ensure_ascii=False))
    _write(os.path.join(WATCH_ROOT, "status.txt"), status_text(status))
    new = publish_alarms(findings)
    for f in findings:
        log(f.line())
    if not quiet:
        sys.stdout.write(status_text(status))
    return status, new


def status_text(st):
    L = []
    L.append("%s  SIBLING WATCH  %s  on %s   (%d alarm, %d warn)\n"
             % (headline_mark(st["verdict"]), st["ts"], st["host"],
                st["n_alarm"], st["n_warn"]))
    for name, o in st["organs"].items():
        L.append("  %-6s %-9s rounds=%-4s last=%-6s %s=%s (best %s) seal=%s\n"
                 % (name, o.get("unit_active"), o.get("rounds"),
                    o.get("last_round_age") or "-", o.get("objective"),
                    fmt(o.get("objective_now")), fmt(o.get("objective_best")),
                    o.get("seal")))
        # whole-history, not the window: "ever moved" answers the DEAD question,
        # the FROZEN finding below answers the window question. Two different
        # questions, so they get two different words.
        L.append("         ever moved : %s\n" % (", ".join(o["series_moving"]) or "NOTHING"))
        L.append("         NEVER moved: %s\n" % (", ".join(o["series_still"]) or "-"))
        if o.get("it_says_of_itself"):
            L.append("         it says    : %s\n"
                     % json.dumps(o["it_says_of_itself"], ensure_ascii=False))
    if st["findings"]:
        L.append("\n")
        for f in st["findings"]:
            who = f["organ"] if not f["series"] else "%s.%s" % (f["organ"], f["series"])
            L.append("  %-5s %-8s %-16s %s\n" % (f["level"], f["code"], who, f["msg"]))
    else:
        L.append("\n  nothing to report. Every detector fired on its fixture.\n")
    return "".join(L)


def fmt(v):
    return "-" if v is None else ("%.4f" % v if isinstance(v, float) else str(v))


def headline_mark(v):
    return {"OK": "[GREEN]", "WARN": "[YELLOW]", "ALARM": "[RED]"}.get(v, v)


def publish_alarms(findings):
    """Append NEW or REFRESHED alarms to alarms.jsonl, for the PC relay to
    carry into RAMCHAT.  A standing alarm is repeated every REPOST_HOURS -- it
    is never silenced, and it never becomes a stuck key either."""
    path = os.path.join(WATCH_ROOT, "alarms.jsonl")
    seen = load_json(os.path.join(WATCH_ROOT, "seen.json"), {})
    new = []
    t = time.time()
    for f in findings:
        if f.level != ALARM:
            continue
        s = f.stable()
        prev = seen.get(s)
        if prev and (t - prev.get("last", 0) < REPOST_HOURS * 3600):
            continue
        rec = f.as_dict()
        rec["t"] = iso()
        rec["first_seen"] = (prev or {}).get("first_seen", iso())
        rec["repeat"] = bool(prev)
        new.append(rec)
        seen[s] = {"last": t, "msg": f.msg,
                   "first_seen": rec["first_seen"]}
    for s in list(seen):
        if s not in {f.stable() for f in findings if f.level == ALARM}:
            seen.pop(s)
    _write(os.path.join(WATCH_ROOT, "seen.json"),
           json.dumps(seen, indent=1, ensure_ascii=False))
    if new:
        _write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new),
               mode="a")
    return new


# ==========================================================================
def guard_host():
    h = socket.gethostname().lower()
    for bad in FORBIDDEN_HOSTS:
        if bad in h:
            raise SystemExit("REFUSED: this is %s. ERAN himself lives on eran1 "
                             "and nothing of the sibling's runs there." % h)


def main():
    ap = argparse.ArgumentParser(description="the sibling's 24/7 watchdog")
    ap.add_argument("--once", action="store_true", help="one cycle and exit")
    ap.add_argument("--status", action="store_true", help="one line, for a human")
    ap.add_argument("--selfaudit", action="store_true",
                    help="prove every detector still fires, and that this source "
                         "contains no repair verb")
    ap.add_argument("--config", default=None,
                    help="JSON list of organs, for injecting faults into a decoy")
    ap.add_argument("--blind", default="",
                    help="comma list of detectors to disable ON PURPOSE, to prove "
                         "the self-audit catches a blind instrument")
    ap.add_argument("--watch-root", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    guard_host()
    global WATCH_ROOT
    if a.watch_root:
        WATCH_ROOT = os.path.abspath(a.watch_root)
    os.makedirs(WATCH_ROOT, exist_ok=True)

    blind = tuple(x.strip() for x in a.blind.split(",") if x.strip())
    organs = load_json(a.config, None) if a.config else default_organs()
    if organs is None:
        raise SystemExit("could not read --config %s" % a.config)

    if a.status:
        st = load_json(os.path.join(WATCH_ROOT, "status.json"), None)
        if not st:
            print("[GREY] no status yet -- the watchdog has not run.")
            return 3
        age = (now() - dt.datetime.strptime(st["ts"], "%Y-%m-%dT%H:%M:%S")).total_seconds()
        stale = "  (STALE by %s -- the watchdog itself may be down)" % human_age(age) \
            if age > 900 else ""
        top = ""
        for f in st["findings"]:
            if f["level"] == ALARM:
                top = "  <- %s %s: %s" % (f["code"], f["organ"], f["msg"])
                break
        print("%s %s  %d alarm / %d warn  checked %s ago%s%s"
              % (headline_mark(st["verdict"]), st["host"], st["n_alarm"],
                 st["n_warn"], human_age(age), stale, top))
        return {"OK": 0, "WARN": 1, "ALARM": 2}.get(st["verdict"], 3)

    if a.selfaudit:
        f1, r1 = audit_detectors(blind)
        f2, r2 = audit_source()
        for f in f1 + f2:
            print(f.line())
        print(json.dumps({"detectors": r1, "source": r2}, indent=1))
        if not (f1 + f2):
            print("SELF-AUDIT PASSED: every detector fired on its sick fixture, "
                  "stayed silent on the well one, and this source holds no "
                  "repair verb.")
        return 2 if (f1 + f2) else 0

    st, _ = cycle(organs, blind, quiet=a.quiet)
    return {"OK": 0, "WARN": 1, "ALARM": 2}.get(st["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
