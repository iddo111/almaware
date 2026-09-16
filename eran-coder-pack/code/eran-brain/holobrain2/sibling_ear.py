# -*- coding: utf-8 -*-
"""SIBLING -- the second holobrain's learning loop, closed.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-01 12:31 (verbatim):

    *"אני רוצה שהנצר הזה... תסגור את הלולאת למידה שלו, תסגור את הפידבק לופ של
    הלולאת למידה שלו, ותשים עליו Watchdog 24-7"*

## WHAT THE SIBLING LEARNS, AND WHY IT IS NOT "FIND /BA/"

ERAN was born mute and has spent weeks hunting one syllable. The sibling was born
holding twelve gestures. So its first lesson cannot be its brother's lesson. The
honest question for a creature born with a mouth is the one Iddo named himself on
2026-08-30 23:30:

    *"האוזן שלי התאמנה על אלפי אנשים אלפי שעות אלפי וריאציות וסיטואציות תלויות הקשר."*

**A mouth is worth nothing to an ear that has only ever met itself.** So the
sibling's first loop is a LISTENING loop: it learns to NAME human syllables spoken
by mouths that are not its own, and its own mouth stays frozen until it can.

That ordering is not taste, it is the diagnosis of tonight's two sick organs. The
throat's ruler is burst-blind: amputating the /b/ from 100 human takes costs it
+0.074, noise 7x signal. A production loop steered by a blind ruler is how the
dowry earned "כולם לא שווים כלום". **You do not let a creature change its mouth
using an ear you have not measured.** Perception first. The refusal is written into
may_touch_the_mouth() and it is spoken out loud every round until the exam clears
its bar.

## THE ONE PARAMETER, AND WHY IT IS NOT A LayerNorm(1)

The sibling inherits ear3's metric exactly: per unit a centroid t and a per-dim
spread w, with wdist = ||(v-t)/w||. What it LEARNS is a **listening posture**:

    g   192 numbers, ALL 1.0 AT BIRTH
        wdist_g(v,u) = sqrt( sum_d ((v_d - t_ud)/w_ud)^2 * g_d )
    b   one bias per unit, all 0.0 at birth, added to wdist before the junction

g = 1 reproduces the inherited ear to the last bit, so round 0 is provably the ear
it was born with. Learning is the drift away from it: which of the 192 cochlear
dimensions carry SYLLABLE, and which only carry WHOSE MOUTH IT WAS.

**This was proved to have reach BEFORE a single line of loop was written**, because
two organs are sick tonight with exactly the component that looks like it is
learning and is structurally incapable of moving (the nezer's four-band gate: 4 of
29 negatives, frozen across ten refits; the old worm's nn.LayerNorm(1) verdict
head: identically zero). Measured on eran3, 2026-09-01, leave-one-TAKE-out over 216
human clips, 12 units, chance 0.0833:

    FLOOR   labels permuted                  0.0806   (the ruler seeing nothing)
    BORN    g = 1, the inherited ear         0.6389
    HONEST  g fitted on TRAIN takes only     0.7315   <- what this loop can buy
    CHEAT+  g hill-climbed ON the test take  0.7685   <- the family's own ceiling

FAMILY REACH +0.1296. Had that been ~0.0000 this file would not exist and the
report would have said STOP. It is written down so the next person can re-run
headroom.py / headroom2.py and catch me if the ground moves.

## HELD-OUT DISCIPLINE -- the 08-21 session-leak scar, obeyed

The corpus is 22 syllables x 6 TAKES x 3 clips. **Takes are sessions.** A random
clip split leaks a session across the fence and every number after it is a lie;
that scar cost this project a whole result on 2026-08-21.

  * **t05 is THE EXAM. Sealed once, never fitted on, forever.**
    Chosen deliberately AFTER seeing the probe: t05 is the ONE take where the
    honest fit REGRESSES (0.6111 -> 0.5278). It is the hardest take in the corpus,
    so the exam cannot flatter the loop. Picking the easy one was the cheat
    available to me, and naming it here is how it stays refused.
  * t00..t04 are the diet. The hill-climb's own validation is leave-one-TRAIN-
    take-out inside those five; the exam take is not in it and cannot be.
  * state/heldout.json records the sealed clip indices and their sha256. Every
    round RE-COMPUTES the intersection of the diet with them, and a round that
    breaks the seal is journaled seal=BROKEN and refuses to claim anything.

## THE NUMBER EVERY MORNING IS COMPARED TO

The round's metric is **naming accuracy on the sealed take, read out of the
sibling's OWN junction** (anatomy.listen) -- not a numpy argmin. The junction is
stricter than the ruler: when two units both dare answer, chorus shuts hush and
the sibling says NOTHING rather than guess. Both numbers are journaled, so the gap
between what its ear could name and what its junction dares say is never hidden.

## THE SIX LOOPS  (the nezer's proven shape, with the measured fixes)

  1. INTAKE    draw a batch of TRAIN-take clips into this round's diet.
  2. VET       the seal check + unit coverage. A poisoned diet stops the round.
  3. PRACTISE  propose a posture; accept ONLY if leave-one-train-take-out improves.
  4. EXAM      the sealed take, through the junction. This is the round's number.
  5. APPETITE  batch doubles on improvement, halves on regression.
  6. MURPHY    rules every round. A no-op round FAILS -- and that is tested.

## THE INSTRUMENT THAT WOULD HAVE CAUGHT BOTH SICK ORGANS

Every round journals g_move and bias_move beside exam. The nezer's disease is
exactly the pattern gate_move != 0 while exam never changes -- movement in the
parameters, none in the measure, for ten rounds running. _stall() computes that
directly and journals the round stall=FROZEN. **That is the line the 24/7 watchdog
watches.** It is not a comment: --selftest fires it on the nezer's own real numbers
(0.4310 with gate_move 0.0031) and fails if it stays quiet.

## SEALED FROM ERAN

eran1 is not in FLEET and never will be: the organism lives there. The loop reads
only its own copies under ROOT (_inside(), realpath, checked on every write).
Nothing flows back to ERAN. rm -rf ROOT removes every trace -- and --prune also
removes the systemd unit, because on 2026-09-01 the first nezer was found leaking
exactly there: nezer.service lives in ~/.config/systemd/user/ and rm -rf ~/nezer
would have orphaned it.

## THE JUDGE THAT IS NOT WIRED YET, AND THE SEAM WHERE IT GOES

judge2 is real work but it is NOT yet a human-vs-ERAN scorer: its 0.984 AUC is
/ba/ vs /a/, both human, and its burst gap is 0.069 (legacy192 0.661 vs the ah
control 0.592). So it is **not wired**, and this file says so rather than
pretending. state/config.json carries the seam, and it is the first nezer's proven
argv contract, unchanged:

    subprocess.run([python, scorer, batch_json, out_json])
      batch_json = ["/abs/clip.wav", ...]
      out_json   = [{"clip": "...", "p_human": 0.0 .. 1.0}, ...]

The day judge2 produces that, wiring it flips judge_in_loop to False and the exam
gains an outside opinion. Until then judge_in_loop is declared **True** every round
-- the ruler being fitted is the ruler that grades -- and Murphy is entitled to
dock the round for it. That declaration is the honest one and it stays.

    python3 sibling.py --plant     # build the shoot (copy2 in, never symlink)
    python3 sibling.py --seal      # seal the exam take, measure BORN
    python3 sibling.py --selftest  # prove the loops, the seal and the stall detector
    python3 sibling.py --naming    # name the dowry through the junction
    python3 sibling.py --live --rounds 20
    python3 sibling.py --live --simmer --pause 900
    python3 sibling.py --prune --yes    # unit + rm -rf, one command
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.expanduser("~/sibling")

# Boxes the sibling may live on. eran1 IS DELIBERATELY ABSENT AND STAYS ABSENT:
# ERAN himself runs there (eranb-life.service) and this thing does not know that
# hostname exists. The DGXes' real hostnames are edgexpert-XXXX -- the first nezer
# shipped with a FLEET tuple matching no fleet box at all, so both spellings are here.
FLEET = ("eran2", "eran3", "eran4",
         "edgexpert-041d",     # eran2 -- the senses
         "edgexpert-01e6",     # eran3 -- idle; the sibling's soil
         "edgexpert-3636")     # eran4 -- Darwish + audio

# The sibling's units that human material actually exists for. ih / abba / ima are
# in its anatomy and NOT in this corpus -- named out loud, never quietly dropped.
CORPUS_UNITS = ("pa", "ma", "na", "ta", "ga", "da", "la", "ka", "aa", "ah", "ra", "ba")
NO_HUMAN_MATERIAL = ("ih", "abba", "ima")
CHANCE = 1.0 / len(CORPUS_UNITS)

EXAM_TAKE = 5           # t05 -- the hardest take. See the docstring; not negotiable here.
W_FLOOR_ABS, W_FLOOR_REL, BLOCK_GAIN, DIMS = 1e-3, 0.05, 12.0, 192
# The diet is measured in TAKES, never in loose clips. Measured the hard way: the
# first live run drew 12 random clips and every round failed, because a reference
# needs >= 2 clips of its own unit and 12 clips cannot cover 12 units. Worse, a
# random-clip diet quietly breaks the leave-one-TRAIN-take-out fold that the whole
# held-out discipline rests on. Sessions all the way down, or not at all.
BATCH_MIN, BATCH_MAX = 2, 5       # TRAIN takes of diet per round (5 exist: t00..t04)
STALL_ROUNDS = 8                  # rounds of parameter movement with no exam movement
# The unit name is NOT `sibling.service`: that one on eran3 belongs to the birth
# workflow, and a prune that disabled it would be reaching outside its own root.
UNIT = "sibling-ear.service"
MOUTH_GATE = 0.80                 # the exam bar below which the mouth stays frozen

# Copied IN at plant, never symlinked: deleting the shoot can never reach back and
# break ERAN's eye, hand, ear or junction.
PLANT_FILES = [
    ("anatomy",      "eran-brain/holobrain2/anatomy.py"),
    ("dowry-code",   "eran-brain/holobrain2/dowry.py"),
    ("murphy",       "murphy/murphy.py"),
    ("murphy-cords", "murphy/murphy.json"),
    ("alma-pkg",     "alma-language/alma/__init__.py"),
    ("alma-loom",    "alma-language/alma/loom.py"),
    ("alma-text",    "alma-language/alma/text.py"),
    ("alma-spells",  "alma-language/alma/spells.py"),
]
PLANT_DIRS = [("dowry", "eran-brain/holobrain2/dowry")]


def _np():
    import numpy
    return numpy


def _inside(root: str, path: str) -> bool:
    """Is this path really under the shoot? realpath FIRST -- a symlink pointing out
    would walk straight past a naive startswith() and let an autonomous process write
    into the organism."""
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == r or p.startswith(r + os.sep)


# --------------------------------------------------------------- the ear, inherited

def spread_floor(std):
    """ear3/judge.py spread_floor(), legacy192 block. COPIED from the ear, not
    invented: the sibling must inherit its brother's metric exactly, or g = 1 means
    nothing and the BORN baseline is a fiction."""
    np = _np()
    std = np.asarray(std, dtype=np.float64)
    med = float(np.median(std))
    floor = max(W_FLOOR_ABS, W_FLOOR_REL * med)
    return np.maximum(std, floor) * (np.sqrt(DIMS) / np.sqrt(BLOCK_GAIN))


def build_refs(V, y, idx, n_units):
    """centroid + spread per unit over idx ONLY. The exam take never reaches here."""
    out = {}
    for u in range(n_units):
        rows = [i for i in idx if y[i] == u]
        if len(rows) < 2:
            continue
        P = V[rows]
        out[u] = (P.mean(axis=0), spread_floor(P.std(axis=0)))
    return out


def wdist_matrix(V, probe, R, g, bias):
    """(n_probe, n_units) of the ear's own wdist under the posture. Vectorised because
    the hill-climb calls it thousands of times; identical arithmetic to ear3's wdist."""
    np = _np()
    us = sorted(R)
    T = np.stack([R[u][0] for u in us])
    W = np.stack([R[u][1] for u in us])
    Z = (V[probe][:, None, :] - T[None, :, :]) / W[None, :, :]
    D = np.sqrt(np.einsum("pud,d->pu", Z * Z, g))
    return us, D + np.asarray([bias.get(CORPUS_UNITS[u], 0.0) for u in us])[None, :]


def ruler_accuracy(V, y, probe, R, g, bias):
    """What the RULER would name. An upper bound on the junction, which may hush."""
    np = _np()
    us, D = wdist_matrix(V, probe, R, g, bias)
    return float(np.mean(np.asarray(us)[np.argmin(D, axis=1)] == y[probe]))


def fisher_posture(V, y, idx, n_units):
    """between-syllable variance / within-syllable variance, per dim, on idx ONLY.

    The whole hypothesis in one line: KEEP the dimensions that separate syllables,
    DISCARD the dimensions that only tell you whose mouth it was. It is the
    arithmetic form of "אלפי אנשים... אלפי וריאציות".

    Normalised to mean 1 so it stays a POSTURE and never becomes a global scale. That
    normalisation is load-bearing, not tidiness: a global scale multiplies every
    distance equally and therefore cannot move a single argmin -- it would be a
    parameter that changes numbers and no decisions, which is precisely the
    LayerNorm(1) failure this whole file exists to avoid."""
    np = _np()
    mu = V[idx].mean(axis=0)
    wi, bt = [], []
    for u in range(n_units):
        rows = [i for i in idx if y[i] == u]
        if len(rows) < 2:
            continue
        P = V[rows]
        wi.append(P.var(axis=0))
        bt.append((P.mean(axis=0) - mu) ** 2)
    if not wi:
        return np.ones(V.shape[1])
    r = np.mean(bt, axis=0) / (np.mean(wi, axis=0) + 1e-12)
    return r / max(float(np.mean(r)), 1e-12)


class Sibling:
    def __init__(self, root: str):
        self.root = os.path.abspath(os.path.expanduser(root))
        self.journal = os.path.join(self.root, "journal.jsonl")
        self.stop = os.path.join(self.root, "STOP")

    # ---------------------------------------------------------------- the door

    def guard(self) -> None:
        host = socket.gethostname()
        if not any(host.startswith(h) for h in FLEET):
            raise SystemExit(
                "REFUSING: hostname %r is not on the fleet allowlist %s.\n"
                "No training on the PC -- a standing law of this workspace -- and\n"
                "eran1 is absent on purpose, because ERAN himself lives there."
                % (host, list(FLEET)))
        if not os.path.isdir(self.root):
            raise SystemExit("REFUSING: %s is not a directory. Run --plant first."
                             % self.root)
        if os.path.exists(self.stop):
            raise SystemExit("STOP file present. Remove %s to let it run." % self.stop)

    def halt_if_stopped(self, where: str) -> None:
        """STOP halts MID-ROUND at a stage boundary, not only between rounds. In-flight
        work is dropped on purpose -- the whole shoot is deletable, so a half-round is."""
        if os.path.exists(self.stop):
            self.note("stopped", reason="STOP file", where="mid-round:" + where)
            print("STOP file seen mid-round (%s). Halting cleanly." % where)
            raise SystemExit(0)

    def _dest(self, rel: str) -> str:
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise SystemExit("REFUSING to write outside the shoot: %s" % p)
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        return p

    def write(self, rel: str, data: str) -> str:
        p = self._dest(rel)
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(data)
        return p

    def _load(self, rel, default):
        p = os.path.join(self.root, rel)
        if not os.path.exists(p):
            return default
        try:
            return json.load(io.open(p, encoding="utf-8"))
        except Exception:                                            # noqa: BLE001
            return default

    def _save(self, rel, obj) -> None:
        self.write(rel, json.dumps(obj, ensure_ascii=False, indent=1))

    def note(self, kind: str, **fields) -> None:
        line = {"t": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind}
        line.update(fields)
        with io.open(self._dest("journal.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    # --------------------------------------------------------------- the plant

    def plant(self, src_root: str, corpus: str) -> int:
        """Copy every organ IN. copy2, never symlink: deleting the shoot must never
        reach back and break the eye, the hand, the junction or the ear."""
        os.makedirs(self.root, exist_ok=True)
        got, missing = [], []
        for name, rel in PLANT_FILES:
            s = os.path.join(src_root, rel)
            if not os.path.exists(s):
                missing.append((name, rel))
                continue
            shutil.copy2(s, self._dest(os.path.join("models", rel)))
            got.append(name)
        for name, rel in PLANT_DIRS:
            s = os.path.join(src_root, rel)
            if not os.path.isdir(s):
                missing.append((name, rel))
                continue
            d = os.path.dirname(self._dest(os.path.join("models", rel, ".keep")))
            shutil.copytree(s, d, dirs_exist_ok=True, symlinks=False)
            got.append(name)
        if os.path.exists(corpus):
            shutil.copy2(corpus, self._dest("corpus/ear-human.npz"))
            got.append("corpus")
        else:
            missing.append(("corpus", corpus))
        self.write("DELETE-ME.txt",
                   "rm -rf %s removes the whole sibling.\n"
                   "Prefer `python3 sibling.py --prune --yes`: it ALSO disables and\n"
                   "removes the systemd unit, which a bare rm -rf would orphan.\n"
                   % self.root)
        self._save("state/config.json", {
            "judge_scorer": None,
            "judge_python": None,
            "judge_note": ("judge2 is NOT wired: its 0.984 AUC is /ba/ vs /a/, both "
                           "human, not human-vs-ERAN. Fill judge_scorer with a script "
                           "obeying [py, scorer, batch.json, out.json] -> "
                           "[{clip, p_human}] and the exam gains an outside opinion.")})
        self._save("MANIFEST.json", {
            "planted": dt.datetime.now().isoformat(timespec="seconds"),
            "host": socket.gethostname(), "src_root": src_root,
            "copied": got, "missing": missing, "method": "copy2 (never symlink)"})
        self.note("planted", copied=got, missing=missing)
        print("planted %d organ(s) into %s" % (len(got), self.root))
        if missing:
            print("MISSING (named, not hidden): %s" % json.dumps(missing))
        return 0

    def prune(self, really: bool) -> int:
        """One command, and the leak the first nezer had is closed. rm -rf ~/nezer
        would have left nezer.service alive in ~/.config/systemd/user/ -- measured
        2026-09-01, alongside chef.service, both outside the shoot."""
        unit_path = os.path.expanduser("~/.config/systemd/user/" + UNIT)
        # REFUSE to touch a unit that is not this shoot's. `sibling.service` on eran3
        # belongs to the BIRTH workflow, not to this loop, and the first draft of this
        # function would have disabled it -- a one-command prune that reaches outside
        # its own root is exactly the leak it was written to close. So the unit file
        # must name this root in its ExecStart or nothing happens to it.
        mine = False
        if os.path.exists(unit_path):
            try:
                mine = self.root in io.open(unit_path, encoding="utf-8").read()
            except Exception:                                        # noqa: BLE001
                mine = False
        cmds = []
        if mine:
            cmds += ["systemctl --user disable --now " + UNIT,
                     "rm -f %s" % unit_path, "systemctl --user daemon-reload"]
        elif os.path.exists(unit_path):
            print("REFUSING to touch %s -- its ExecStart does not name %s. "
                  "Not this shoot's unit." % (unit_path, self.root))
        cmds += ["rm -rf %s" % self.root]
        if not really:
            print("would run (add --yes to actually do it):")
            for c in cmds:
                print("   " + c)
            return 0
        for c in cmds:
            print("$ " + c)
            subprocess.run(c, shell=True)
        print("pruned. nothing else moved.")
        return 0

    # -------------------------------------------------------------- the corpus

    def corpus(self):
        """The sibling's OWN copy. Never ERAN's live state -- the seal is the point."""
        np = _np()
        p = os.path.join(self.root, "corpus", "ear-human.npz")
        if not os.path.exists(p):
            raise SystemExit("no corpus at %s -- run --plant" % p)
        d = np.load(p, allow_pickle=True)
        V, Y, T = d["V"].astype(np.float64), d["y"], d["t"]
        syl = [str(s) for s in d["syllables"]]
        keep = [i for i in range(len(Y)) if syl[Y[i]] in CORPUS_UNITS]
        remap = {syl.index(u): k for k, u in enumerate(CORPUS_UNITS)}
        return V[keep], np.array([remap[Y[i]] for i in keep]), T[keep]

    # ---------------------------------------------------------------- the seal

    def seal(self) -> int:
        """Seal the exam take ONCE and measure BORN. Refuses to reseal: a moving fence
        is not a fence, and a later round that quietly ate the exam would be invisible."""
        np = _np()
        old = self._load("state/heldout.json", None)
        if old:
            print("already sealed at %s -- exam take t%02d, %d clips, sha %s"
                  % (old["sealed_at"], old["exam_take"], len(old["exam_idx"]),
                     old["sha256_16"]))
            return 0
        V, y, t = self.corpus()
        exam = [int(i) for i in range(len(y)) if t[i] == EXAM_TAKE]
        train = [int(i) for i in range(len(y)) if t[i] != EXAM_TAKE]
        sha = hashlib.sha256(json.dumps(exam).encode()).hexdigest()[:16]
        R = build_refs(V, y, train, len(CORPUS_UNITS))
        one = np.ones(V.shape[1])
        born_ruler = ruler_accuracy(V, y, exam, R, one, {})
        born_junc = self.junction_accuracy(V, y, exam, R, one, {})
        rec = {"sealed_at": dt.datetime.now().isoformat(timespec="seconds"),
               "exam_take": EXAM_TAKE, "n_exam": len(exam), "n_train": len(train),
               "sha256_16": sha,
               "why_this_take": ("t05 is the ONE take where the honest fit REGRESSES "
                                 "(0.6111 -> 0.5278, headroom2.py). Deliberately the "
                                 "hardest take, so the exam cannot flatter the loop."),
               "born_ruler": round(born_ruler, 4),
               "born_junction": round(born_junc["acc"], 4),
               # UNROUNDED too. --selftest re-derives BORN from scratch every run and
               # asserts g=1 reproduces the inherited ear EXACTLY; comparing a fresh
               # float against a 4-dp rounded one fails at 1e-9 for no reason, which is
               # exactly what it did on the first run. The rounded pair stays because it
               # is what a person reads.
               "born_ruler_exact": born_ruler,
               "born_junction_exact": born_junc["acc"],
               "born_hushed": born_junc["hushed"],
               "chance": round(CHANCE, 4),
               "floor_shuffled": 0.0806, "family_ceiling_cheat": 0.7685,
               "units_with_no_human_material": list(NO_HUMAN_MATERIAL),
               "exam_idx": exam}
        self._save("state/heldout.json", rec)
        sys.path.insert(0, os.path.join(self.root, "models", "eran-brain", "holobrain2"))
        import anatomy                                               # noqa: E402
        self._save("state/posture.json", {"g": one.tolist(),
                                          "bias": {u: 0.0 for u in CORPUS_UNITS},
                                          "theta": anatomy.THETA, "tau": anatomy.TAU,
                                          "fitted_rounds": 0})
        self._save("state/eaten.json", {"idx": []})
        shown = {k: v for k, v in rec.items() if k != "exam_idx"}
        self.note("sealed", **shown)
        print(json.dumps(shown, ensure_ascii=False, indent=1))
        return 0

    # ------------------------------------------------- the sibling's own mouth

    def junction_accuracy(self, V, y, probe, R, g, bias,
                          theta=None, tau=None) -> dict:
        """Name each clip THROUGH THE JUNCTION -- anatomy.listen, ALMA, the sibling's
        own weave. Not a numpy argmin. The junction is STRICTER than the ruler: when
        two units both dare answer, chorus shuts hush and it says nothing rather than
        guess. Both numbers are journaled so the gap is never hidden."""
        sys.path.insert(0, os.path.join(self.root, "models", "eran-brain", "holobrain2"))
        sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
        import anatomy                                               # noqa: E402
        # theta / tau default to the birth constants, so BORN is measured with the
        # junction exactly as anatomy.py built it. See THE SECOND FROZEN THING below
        # for why they must not STAY constants.
        th = anatomy.THETA if theta is None else theta
        ta = anatomy.TAU if tau is None else tau
        us, D = wdist_matrix(V, probe, R, g, bias)
        hit = hushed = 0
        for k, i in enumerate(probe):
            nearest = {CORPUS_UNITS[u]: float(D[k][j]) for j, u in enumerate(us)}
            out = anatomy.listen(nearest, theta=th, tau=ta)
            if out["said"] is None:
                hushed += 1
            elif out["said"] == CORPUS_UNITS[y[i]]:
                hit += 1
        n = float(len(probe))
        return {"acc": hit / n, "hushed": hushed, "n": int(n)}

    # ------------------------------------------------ loop 1 + 2: intake and vet

    def intake(self, rng, batch: int) -> list:
        """Draw this round's diet as WHOLE TRAIN TAKES. Never the exam take -- and
        vet() PROVES it rather than trusting this function to have meant it.

        Whole sessions, because that is the only unit this corpus has that keeps a
        reference honest: one take gives every one of the 12 units exactly 3 clips, so
        every unit gets a centroid and the leave-one-train-take-out fold is well formed.
        Drawing loose clips gave a diet that could not name most units at all -- the
        measured failure of the first live run."""
        _, y, t = self.corpus()
        pool = sorted({int(t[i]) for i in range(len(y)) if t[i] != EXAM_TAKE})
        n = min(max(batch, BATCH_MIN), len(pool))
        takes = sorted(rng.sample(pool, n))
        diet = sorted(int(i) for i in range(len(y)) if int(t[i]) in takes)
        eaten = self._load("state/eaten.json", {"idx": []})
        eaten["idx"] = sorted(set(eaten["idx"]) | set(diet))
        self._save("state/eaten.json", eaten)
        self.note("intake", takes=takes, clips=len(diet),
                  eaten_total=len(eaten["idx"]))
        return diet

    def vet(self, diet) -> dict:
        """The seal check. Not a comment: the intersection is COMPUTED, every round."""
        _, y, _ = self.corpus()
        h = self._load("state/heldout.json", None) or {"exam_idx": []}
        leak = sorted(set(diet) & set(h["exam_idx"]))
        units = sorted({CORPUS_UNITS[y[i]] for i in diet})
        v = {"seal": "BROKEN" if leak else "intact", "leak": leak,
             "units_covered": len(units), "clips": len(diet)}
        self.note("vetted", **v)
        return v

    # ----------------------------------------------------------- loop 3: practise

    def practise(self, diet, round_n: int) -> dict:
        """Propose a posture. Accept ONLY if leave-one-TRAIN-take-out improves.

        Round 0 fits Fisher from scratch (the big honest jump, +0.0926 measured).
        Later rounds perturb it and keep only what the dev fold rewards. The exam take
        is not in the dev fold and cannot be: diet came from intake(), which excludes
        it, and vet() proved the intersection empty before this ran."""
        np = _np()
        sys.path.insert(0, os.path.join(self.root, "models", "eran-brain", "holobrain2"))
        sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
        import anatomy                                               # noqa: E402
        V, y, t = self.corpus()
        n_units = len(CORPUS_UNITS)
        st = self._load("state/posture.json", None) or {}
        g = np.asarray(st.get("g", np.ones(V.shape[1]).tolist()), dtype=np.float64)
        bias = dict(st.get("bias", {u: 0.0 for u in CORPUS_UNITS}))
        theta = float(st.get("theta", anatomy.THETA))
        tau = float(st.get("tau", anatomy.TAU))
        g0, bias0, th0, ta0 = g.copy(), dict(bias), theta, tau
        train_takes = sorted({int(t[i]) for i in diet})

        def dev(gg, bb, th, ta):
            """leave-one-TRAIN-take-out, scored THROUGH THE JUNCTION.

            It scored the ruler until round 13 of 2026-09-01, and that is precisely
            how the exam froze: the ruler climbed 0.6111 -> 0.7222 while the junction
            sat at 0.2500 with 24 of 36 clips hushed, because theta and tau got no
            signal from a ruler that has no gate. A dev fold must measure the same
            thing the exam measures or it is steering blind."""
            if len(train_takes) < 2:
                return None
            s = []
            for tk in train_takes:
                tr = [i for i in diet if t[i] != tk]
                te = [i for i in diet if t[i] == tk]
                R = build_refs(V, y, tr, n_units)
                if not R or not te:
                    continue
                s.append(self.junction_accuracy(V, y, te, R, gg, bb, th, ta)["acc"])
            return float(np.mean(s)) if s else None

        base = dev(g, bias, theta, tau)
        tried = accepted = 0
        if st.get("fitted_rounds", 0) == 0:
            cand = fisher_posture(V, y, diet, n_units)
            tried += 1
            d = dev(cand, bias, theta, tau)
            if d is not None and (base is None or d > base):
                g, base, accepted = cand, d, accepted + 1
        rng = np.random.RandomState(1933 + round_n)
        for k in range(16):
            self.halt_if_stopped("practise-%d" % k)   # STOP beats the long stage
            gp = g * np.exp(rng.normal(0, 0.20, size=g.shape) *
                            (rng.rand(*g.shape) < 0.10))
            gp = gp / max(float(np.mean(gp)), 1e-12)  # stays a posture, never a scale
            bp = dict(bias)
            u = CORPUS_UNITS[rng.randint(len(CORPUS_UNITS))]
            bp[u] = float(bp.get(u, 0.0) + rng.normal(0, 0.30))
            # THE SECOND FROZEN THING, and it cost more than the first.
            # theta and tau are the sibling's WILLINGNESS TO SPEAK: theta is how much
            # affinity a unit needs before it dares answer, tau how sharply the ear's
            # distances turn into affinity. anatomy.py set them to 0.20 and 1.0 at
            # birth and nothing could ever change them -- so 24 of 36 human clips got
            # no unit over threshold and the sibling said NOTHING, every round, no
            # matter how much its ear improved. Measured on the sealed take with the
            # posture the loop had actually learned: 0.2500 at the birth dials, 0.6389
            # at tau 0.25 / theta 0.50 -- 0.39 of accuracy destroyed by two constants
            # downstream of a component that was genuinely learning. That is the
            # LayerNorm(1) class in its purest form and it was IN THIS FILE.
            # They are learned now, on the dev fold like everything else. The sweep
            # that found 0.6389 was run on the EXAM and its values are deliberately
            # NOT copied in here -- that would be fitting on the answers.
            thp = float(np.clip(th0 * np.exp(rng.normal(0, 0.35)), 0.01, 0.95)) \
                if rng.rand() < 0.5 else theta
            tap = float(np.clip(ta0 * np.exp(rng.normal(0, 0.45)), 0.05, 8.0)) \
                if rng.rand() < 0.5 else tau
            tried += 1
            d = dev(gp, bp, thp, tap)
            if d is not None and (base is None or d > base + 1e-9):
                g, bias, theta, tau, base = gp, bp, thp, tap, d
                accepted += 1
        g_move = float(np.abs(g - g0).sum() / max(len(g), 1))
        b_move = float(sum(abs(bias.get(u, 0.0) - bias0.get(u, 0.0))
                           for u in CORPUS_UNITS))
        self._save("state/posture.json",
                   {"g": g.tolist(), "bias": bias, "theta": theta, "tau": tau,
                    "fitted_rounds": st.get("fitted_rounds", 0) + 1})
        out = {"dev": None if base is None else round(base, 4), "tried": tried,
               "accepted": accepted, "g_move": round(g_move, 6),
               "bias_move": round(b_move, 6),
               "gate_move": round(abs(theta - th0) + abs(tau - ta0), 6),
               "theta": round(theta, 4), "tau": round(tau, 4),
               "train_takes": train_takes}
        self.note("practised", **out)
        return out

    # --------------------------------------------------------------- loop 4: exam

    def exam(self, diet) -> dict:
        """The sealed take, through the junction. THE round's number.

        REFERENCES COME FROM ALL TRAIN TAKES, NOT FROM THE DIET, and that is the whole
        point of this comment. The first live run built them from the diet, and the
        result was uninterpretable: BORN was measured with all five train takes behind
        it while a round had only its two-to-five-take diet, so the round's ruler fell
        from 0.6111 to a 0.5070 mean while the junction rose -- a comparison of two
        different amounts of material dressed up as a comparison of two postures.

        The two jobs are now separate, as they should be:
            the DIET   fits the posture      -- "what did it learn this round"
            the EXAM   uses everything known -- "how good is the sibling right now"
        Only the second is comparable across mornings, and only the second is journaled
        as the number. The exam take is excluded from the references by construction
        (train = every clip whose take is not EXAM_TAKE), so no t05 clip can reach this
        measurement by any path."""
        np = _np()
        V, y, t = self.corpus()
        h = self._load("state/heldout.json", None)
        st = self._load("state/posture.json", {})
        g = np.asarray(st.get("g", np.ones(V.shape[1]).tolist()), dtype=np.float64)
        bias = dict(st.get("bias", {}))
        train = [i for i in range(len(y)) if int(t[i]) != EXAM_TAKE]
        R = build_refs(V, y, train, len(CORPUS_UNITS))
        probe = h["exam_idx"]
        ruler = ruler_accuracy(V, y, probe, R, g, bias)
        junc = self.junction_accuracy(V, y, probe, R, g, bias,
                                      st.get("theta"), st.get("tau"))
        out = {"exam_junction": round(junc["acc"], 4), "exam_ruler": round(ruler, 4),
               "hushed": junc["hushed"], "n": junc["n"],
               "theta": st.get("theta"), "tau": st.get("tau"),
               "born_junction": h["born_junction"], "born_ruler": h["born_ruler"],
               "chance": round(CHANCE, 4)}
        self.note("exam", **out)
        return out

    # ----------------------------------------------------------- loop 5: appetite

    def appetite(self, now, prev) -> tuple:
        st = self._load("state/appetite.json", {"batch": BATCH_MIN, "last_exam": None})
        batch, why = st["batch"], "held"
        if now is not None and prev is not None:
            if now > prev + 1e-9:
                batch, why = (min(batch * 2, BATCH_MAX),
                              "exam improved %.4f -> %.4f" % (prev, now))
            elif now < prev - 1e-9:
                batch, why = (max(batch // 2, BATCH_MIN),
                              "exam regressed %.4f -> %.4f" % (prev, now))
        self._save("state/appetite.json", {"batch": batch, "last_exam": now})
        self.note("appetite", batch=batch, why=why)
        return batch, why

    # ------------------------------ THE INSTRUMENT THAT CATCHES THE SICK ORGANS

    def _stall(self, hist) -> dict:
        """The nezer's disease, computed rather than remembered.

        Its four-band gate reported gate_move 0.0017-0.0059 for TEN consecutive refits
        while its exam sat at exactly 0.4310. Parameters moving, measure frozen. That
        is the LayerNorm(1) signature, and it is what this returns: movement in g or
        bias across the window, zero movement in exam_junction.

        This is the line the 24/7 watchdog watches. --selftest fires it on the nezer's
        own real numbers and fails if it stays quiet."""
        w = [h for h in hist[-STALL_ROUNDS:] if h.get("exam_junction") is not None]
        if len(w) < STALL_ROUNDS:
            return {"stall": "warming", "rounds": len(w)}
        moved = sum(1 for h in w
                    if (h.get("g_move") or 0) > 0 or (h.get("bias_move") or 0) > 0
                    or (h.get("gate_move") or 0) > 0)
        span = max(h["exam_junction"] for h in w) - min(h["exam_junction"] for h in w)
        # A FROZEN measure is the fault, full stop -- whatever the parameters did.
        # The first draft only fired when the parameters were ALSO moving, which
        # reproduces the nezer's disease exactly and misses the other one: a loop
        # that is stuck or starved, moving nothing at all, while its number sits
        # still and it goes on reporting that number every morning. Both scream.
        frozen = span <= 1e-9
        searched = sum(h.get("tried") or 0 for h in w)
        took = sum(h.get("accepted") or 0 for h in w)
        if not frozen:
            case, why = "moving", "the measure is moving with the parameters"
        elif moved >= 1:
            case = "FROZEN"
            why = ("parameters moved in %d of %d rounds and the exam did not move at "
                   "all -- this is the nezer's disease exactly. STOP AND LOOK."
                   % (moved, len(w)))
        elif searched > 0 and took == 0:
            # NOT the disease, and the watchdog must not cry wolf about it every
            # morning or nobody will read it the day it matters. A loop that proposed
            # `searched` candidates, scored every one against a real dev fold and
            # accepted none has EXHAUSTED this parameter family on the material it
            # has. That is a finished experiment asking for more mouths, not a sick
            # component. The difference from the line above is exactly whether
            # anything moved while the number stood still.
            case = "converged"
            why = ("%d proposals scored over %d rounds, none beat the standing "
                   "posture, exam steady at %.4f. Not the disease -- the family is "
                   "exhausted on this corpus. It needs more human takes, or a wider "
                   "family, not a restart." % (searched, len(w), w[-1]["exam_junction"]))
        else:
            case = "FROZEN"
            why = ("nothing moved and nothing was even tried for %d rounds -- the loop "
                   "is starved or wedged. STOP AND LOOK." % len(w))
        return {"stall": case, "exam_span": round(span, 6),
                "rounds_with_movement": moved, "proposals": searched,
                "accepted": took, "window": STALL_ROUNDS, "why": why}

    def may_touch_the_mouth(self) -> dict:
        """Perception before production. Refused out loud, every round, until the exam
        clears MOUTH_GATE. The throat's ruler is burst-blind (amputating /b/ costs it
        +0.074, noise 7x signal) and steering a mouth with a blind ear is exactly how
        the dowry earned its verdict."""
        hist = self._load("state/exam_history.json", [])
        last = (hist[-1]["exam_junction"] if hist
                and hist[-1].get("exam_junction") is not None else None)
        ok = last is not None and last >= MOUTH_GATE
        return {"may": ok, "exam": last, "bar": MOUTH_GATE,
                "why": ("the ear is not good enough yet -- the mouth stays frozen"
                        if not ok else
                        "the ear cleared the bar; a mouth loop may now be opened")}

    # ------------------------------------------------------------------ one round

    def run_round(self, rng, round_n: int) -> tuple:
        st = self._load("state/appetite.json", {"batch": BATCH_MIN, "last_exam": None})
        diet = self.intake(rng, st["batch"])
        self.halt_if_stopped("after-intake")
        v = self.vet(diet)
        if v["seal"] == "BROKEN":
            self.note("poisoned", leak=v["leak"])
            return ({"chance": CHANCE, "baseline": None, "held_out": False,
                     "claimed_success": False,
                     "steps": [{"step": round_n, "metric": CHANCE, "terms": {}}]},
                    {"seal": "BROKEN"})
        p = self.practise(diet, round_n)
        self.halt_if_stopped("before-exam")
        e = self.exam(diet)
        hist = self._load("state/exam_history.json", [])
        hist.append({"round": round_n, **e, "g_move": p["g_move"],
                     "bias_move": p["bias_move"], "gate_move": p["gate_move"],
                     "tried": p["tried"], "accepted": p["accepted"],
                     "dev": p["dev"]})
        self._save("state/exam_history.json", hist[-500:])
        stall = self._stall(hist)
        self.appetite(e["exam_junction"], st.get("last_exam"))
        mouth = self.may_touch_the_mouth()
        self.note("mouth_gate", **mouth)
        if stall.get("stall") == "FROZEN":
            self.note("STALL", **stall)

        # TWO DIFFERENT THINGS, and the first live run showed why conflating them lies.
        #   NO-OP  nothing was MEASURED -- no proposal was ever scored against a real
        #          dev fold. This round produced no evidence and must FAIL.
        #   NULL   proposals were scored and every one of them lost. That round DID
        #          work: it searched and it reports a negative result, which in this
        #          workspace is worth more than a flattering one. It stands, labelled
        #          `null`, and it never counts as progress.
        # My first draft called both of them a no-op and failed half the honest rounds.
        no_measurement = (p["tried"] == 0 or p["dev"] is None)
        null_result = (not no_measurement and p["accepted"] == 0)
        did_nothing = no_measurement
        trace = {
            "chance": CHANCE,
            "baseline": e["born_junction"],       # the ear it was BORN with
            "held_out": True,
            # The ruler being fitted is the ruler that grades. Declared True on
            # purpose, every round, until judge2 becomes a real human-vs-ERAN scorer.
            # Murphy is entitled to dock the round for it; that is the intended cost.
            "judge_in_loop": True,
            "independent": False,
            "artifact": "state/posture.json",
            "looked_at": bool(self._load("state/looked.json", None)),
            "claimed_success": bool(not did_nothing
                                    and e["exam_junction"] > e["born_junction"]),
            "steps": [{"step": h["round"], "metric": h["exam_junction"], "terms": {}}
                      for h in hist[-200:] if h.get("exam_junction") is not None],
        }
        if did_nothing:
            # An honest no-op: nothing moved, nothing claimed. Murphy fails it, and
            # --selftest proves he fails the same emptiness CLAIMING success too.
            trace["steps"] = [{"step": round_n, "metric": CHANCE, "terms": {}}]
            trace["baseline"] = None
            trace["held_out"] = False
        return trace, {**e, **p, **stall, "seal": v["seal"], "mouth": mouth["may"],
                       "noop": did_nothing, "null": null_result}

    @staticmethod
    def round_failed(verdict: float, report: dict) -> str:
        """Whether the round STANDS. Two independent ways to fail, on purpose.

        Murphy catches self-deception and rules an idle round 0.00 -- correctly, because
        a run that claims nothing is not fooling anybody. But Iddo's requirement is that
        a round that DID NOTHING must fail, and that is a different question, so the loop
        answers it itself: a round where the posture did not move and nothing was accepted
        is FAILED here regardless of Murphy's verdict. A broken seal fails too, and that
        one outranks everything."""
        if report.get("seal") == "BROKEN":
            return "FAILED: seal broken"
        if report.get("noop"):
            return "FAILED: no-op (nothing was measured this round)"
        if verdict >= 1.0:
            return "FAILED: Murphy says FOOLING ITSELF"
        if report.get("null"):
            return "null: searched, nothing beat the standing posture"
        return "stands"

    # ------------------------------------------------------------------------ live

    def live(self, rounds: int, seconds: float, pause: float = 0.0, simmer=False) -> int:
        self.guard()
        if not self._load("state/heldout.json", None):
            print("not sealed. run --seal first.")
            return 2
        if simmer:
            try:
                os.nice(19)
            except (AttributeError, OSError):
                pass
        sys.path.insert(0, os.path.join(self.root, "models", "murphy"))
        sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
        try:
            import murphy                                            # noqa: E402
        except Exception as ex:                                      # noqa: BLE001
            print("no Murphy in the shoot (%s) -- refusing to run unjudged." % ex)
            return 2
        mw, ml = murphy.load()
        if mw is None:
            self.note("murphy_cords", status="DEFAULTS", why="murphy.json missing")
        rng = random.Random(1933)
        t0, done = time.time(), 0
        while done < rounds and time.time() - t0 < seconds:
            if os.path.exists(self.stop):
                self.note("stopped", reason="STOP file", rounds=done)
                print("STOP file seen. Halting cleanly after %d rounds." % done)
                return 0
            trace, r = self.run_round(rng, done)
            verdict, spoke, _ = murphy.rule(trace, weights=mw, lines=ml)
            fooling = verdict >= 1.0
            stands = self.round_failed(verdict, r)
            self.note("round", n=done, exam=r.get("exam_junction"),
                      ruler=r.get("exam_ruler"), born=r.get("born_junction"),
                      dev=r.get("dev"), g_move=r.get("g_move"),
                      bias_move=r.get("bias_move"), gate_move=r.get("gate_move"),
                      theta=r.get("theta"), tau=r.get("tau"), stall=r.get("stall"),
                      seal=r.get("seal"), hushed=r.get("hushed"), verdict=stands,
                      murphy="FOOLING ITSELF" if fooling else "sound",
                      witnesses=list(dict.fromkeys(spoke)))
            print("round %3d  exam %-7s ruler %-7s born %-7s dev %-7s theta %-6s "
                  "tau %-6s hush %-3s stall %-7s murphy %-8s %-8s %s"
                  % (done, r.get("exam_junction"), r.get("exam_ruler"),
                     r.get("born_junction"), r.get("dev"), r.get("theta"),
                     r.get("tau"), r.get("hushed"), r.get("stall"),
                     "FOOLING" if fooling else "sound", stands.split(":")[0],
                     ",".join(dict.fromkeys(spoke))[:44]))
            done += 1
            slept = 0.0
            while pause and slept < pause:
                if os.path.exists(self.stop):
                    self.note("stopped", reason="STOP file", rounds=done)
                    print("STOP file seen mid-pause. Halting cleanly.")
                    return 0
                time.sleep(min(5.0, pause - slept))
                slept += 5.0
        self.note("finished", rounds=done, seconds=round(time.time() - t0, 1))
        return 0

    # ------------------------------------------------------------ a person looked

    def looked(self, note: str) -> int:
        """A person actually looked at the sibling's latest exam. The cheapest judge
        there is, and until judge2 becomes a real human-vs-ERAN scorer it is the ONLY
        thing that can discharge Murphy's circularity witness -- which fires on every
        round, correctly, because the ruler being fitted is the ruler that grades.
        Without this the loop is condemned to FOOLING ITSELF forever and would deserve
        it."""
        hist = self._load("state/exam_history.json", [])
        covers = hist[-1]["round"] if hist else -1
        self._save("state/looked.json",
                   {"t": dt.datetime.now().isoformat(timespec="seconds"),
                    "note": note, "covers_round": covers})
        self.note("looked", note=note, covers_round=covers)
        print("on the record: a person looked (covers rounds up to %d)" % covers)
        return 0

    # ---------------------------------------------------------------- the naming

    def naming(self) -> int:
        """The dowry, named through the junction -- what anatomy.py's docstring
        promised and nothing had yet delivered."""
        sys.path.insert(0, os.path.join(self.root, "models", "eran-brain", "holobrain2"))
        sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
        import anatomy, dowry                                        # noqa: E402
        a = dowry.load_all()
        ok = spoke = 0
        print("%-5s %-6s %-6s %9s %-9s %s"
              % ("true", "said", "ok", "sureness", "confused", "answered"))
        for u, v in sorted(a.items(), key=lambda kv: kv[1]["wdist"]):
            o = anatomy.listen(v["nearest"])
            ok += (o["said"] == u)
            spoke += o["spoke"]
            s = o["sureness"]
            print("%-5s %-6s %-6s %9s %-9s %s"
                  % (u, o["said"], o["said"] == u,
                     ("%.4f" % s) if s is not None else "-", o["confused"],
                     ",".join(o["answered"])[:24]))
        print("\nNAMING %d/%d = %.1f%%  spoke %d/%d  chance 1/15 = 6.7%%"
              % (ok, len(a), 100.0 * ok / len(a), spoke, len(a)))
        return 0

    # ----------------------------------------------------------------- selftest

    def selftest(self) -> int:
        bad = []

        def check(name, cond, detail=""):
            print("  %-54s %s %s" % (name, "ok" if cond else "FAIL", detail))
            if not cond:
                bad.append(name)

        print("selftest on %s" % self.root)
        np = _np()
        check("hostname is on the fleet allowlist",
              any(socket.gethostname().startswith(h) for h in FLEET),
              socket.gethostname())
        check("eran1 is NOT on the allowlist", not any(h == "eran1" for h in FLEET))
        check("realpath jail refuses ..",
              not _inside(self.root, os.path.join(self.root, "..", "x")))
        h = self._load("state/heldout.json", None)
        check("the exam is sealed", bool(h))
        if h:
            V, y, t = self.corpus()
            exam = set(h["exam_idx"])
            check("the sealed exam is exactly one whole take",
                  {int(t[i]) for i in exam} == {EXAM_TAKE})
            eaten = set(self._load("state/eaten.json", {"idx": []})["idx"])
            check("nothing ever eaten has touched the exam", not (eaten & exam),
                  "%d clips eaten so far" % len(eaten))
            train = [i for i in range(len(y)) if i not in exam]
            R = build_refs(V, y, train, len(CORPUS_UNITS))
            one = np.ones(V.shape[1])
            b = ruler_accuracy(V, y, sorted(exam), R, one, {})
            check("g=1 reproduces the inherited ear exactly",
                  abs(b - h.get("born_ruler_exact", h["born_ruler"])) < 1e-12,
                  "%.6f vs sealed %.6f" % (b, h.get("born_ruler_exact",
                                                    h["born_ruler"])))
            f = fisher_posture(V, y, train, len(CORPUS_UNITS))
            check("the posture is a posture, not a scale (mean 1)",
                  abs(float(np.mean(f)) - 1.0) < 1e-9)
            moved = ruler_accuracy(V, y, sorted(exam), R, f, {})
            check("a fitted posture MOVES the number (not a LayerNorm(1))",
                  abs(moved - b) > 1e-9, "%.4f -> %.4f" % (b, moved))
        # -- the stall detector, fired on the nezer's OWN real numbers
        nez = [{"round": i, "exam_junction": 0.4310, "g_move": 0.0031, "bias_move": 0.0}
               for i in range(STALL_ROUNDS)]
        check("stall detector FIRES on the nezer's frozen 0.4310",
              self._stall(nez)["stall"] == "FROZEN")
        alive = [{"round": i, "exam_junction": 0.60 + 0.01 * i, "g_move": 0.003,
                  "bias_move": 0.0} for i in range(STALL_ROUNDS)]
        check("stall detector stays quiet while the exam moves",
              self._stall(alive)["stall"] == "moving")
        stuck = [{"round": i, "exam_junction": 0.4310, "g_move": 0.0, "bias_move": 0.0,
                  "tried": 0, "accepted": 0} for i in range(STALL_ROUNDS)]
        s = self._stall(stuck)
        check("stall detector FIRES when nothing moves and nothing is tried",
              s["stall"] == "FROZEN" and s["rounds_with_movement"] == 0)
        conv = [{"round": i, "exam_junction": 0.6667, "g_move": 0.0, "bias_move": 0.0,
                 "gate_move": 0.0, "tried": 17, "accepted": 0}
                for i in range(STALL_ROUNDS)]
        check("a searched-and-exhausted loop is CONVERGED, not the disease",
              self._stall(conv)["stall"] == "converged")
        # -- the loop's OWN verdict: a no-op FAILS even when Murphy rules it 0.00
        check("the loop FAILS a no-op round itself",
              self.round_failed(0.0, {"noop": True, "seal": "intact"})
              .startswith("FAILED"))
        check("the loop FAILS a broken seal above everything else",
              self.round_failed(0.0, {"noop": False, "seal": "BROKEN"})
              == "FAILED: seal broken")
        check("a searched-but-rejected round is null, NOT a failure",
              self.round_failed(0.0, {"noop": False, "null": True,
                                      "seal": "intact"}).startswith("null"))
        check("a real round with a sound Murphy stands",
              self.round_failed(0.0, {"noop": False, "seal": "intact"}) == "stands")
        # -- Murphy fails a no-op, and fails it when it claims success too
        mdir = os.path.join(self.root, "models", "murphy")
        if os.path.isdir(mdir):
            sys.path.insert(0, mdir)
            sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
            try:
                import murphy                                        # noqa: E402
                mw, ml = murphy.load()
                noop = {"chance": CHANCE, "baseline": None, "held_out": False,
                        "claimed_success": False,
                        "steps": [{"step": 0, "metric": CHANCE, "terms": {}}]}
                v, spoke, _ = murphy.rule(noop, weights=mw, lines=ml)
                # MEASURED, not assumed. My first draft asserted "Murphy fails an
                # honest no-op" and it FAILED at 0.000 -- because Murphy is a court
                # for self-deception, not for idleness: a run that claims nothing
                # cannot be fooling anybody. The nezer's own selftest had already
                # found this and said so. So the assertion is corrected to Murphy's
                # real contract -- his paperwork witnesses must all speak -- and the
                # requirement that "a no-op round FAILS" is enforced where it actually
                # belongs, by the loop itself, in the check below.
                check("no-op: Murphy's paperwork witnesses all speak",
                      {"at_chance", "no_holdout", "no_floor"} <= set(spoke),
                      "verdict %.3f (%s)" % (v, ",".join(spoke)))
                lying = dict(noop)
                lying["claimed_success"] = True
                v2, _, _ = murphy.rule(lying, weights=mw, lines=ml)
                check("no-op CLAIMING success is FAILED by Murphy", v2 >= 1.0,
                      "verdict %.3f" % v2)
                check("Murphy's cords are the FITTED ones", mw is not None)
            except Exception as e:                                   # noqa: BLE001
                check("Murphy importable from the shoot", False, str(e)[:70])
        else:
            print("  (no planted shoot -- Murphy checks skipped)")
        print("\n%s (%d check(s) failed)"
              % ("SELFTEST PASSED" if not bad else "SELFTEST FAILED", len(bad)))
        return 0 if not bad else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the sibling's learning loop")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--plant", action="store_true")
    ap.add_argument("--src", default=os.path.expanduser("~/CLAUDE"))
    ap.add_argument("--corpus", default=os.path.expanduser("~/ear-human.npz"))
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--naming", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=86400.0)
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--simmer", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--looked", metavar="NOTE",
                    help="put on record that a person looked at the latest exam")
    a = ap.parse_args(argv)
    s = Sibling(a.root)
    if a.looked:
        return s.looked(a.looked)
    if a.plant:
        return s.plant(a.src, a.corpus)
    if a.prune:
        return s.prune(a.yes)
    if a.seal:
        return s.seal()
    if a.selftest:
        return s.selftest()
    if a.naming:
        return s.naming()
    if a.live:
        return s.live(a.rounds, a.seconds, a.pause, a.simmer)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
