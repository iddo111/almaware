#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

MODEH — the Master Modeler's corpus-teachability organ  (מודה אני)
==================================================================
מאסטר-מודלר → מודיליאני → מודה אני.  The conductor over the models carries
thanksgiving in its name; this is the part of it that decides what ERAN is
allowed to be grateful FOR.

THE JOB IS NOT "pick the best teacher". It is the harder half:
**detect a teacher with nothing to teach.**

Why it exists (2026-09-05). ERAN ate `facebook/mms-tts-heb` output for a month
believing it was a human mouth. Iddo listened to ten clips blind and 0/10
matched their labels. Nineteen of his own 25 syllable units hold 3 clips that
are near-duplicates of each other — about ONE independent example, not three.
And `ta` vs `tha` — the same phone — "separated" at 100%, which is impossible
for a corpus that carries only sound. Every accuracy number built on that
corpus was noise wearing a suit.

WHAT IT MEASURES (five probes, in the order that would have caught the TTS)
--------------------------------------------------------------------------
  1. PROVENANCE   — read the manifests/READMEs that ship with the corpus and
                    look for a generator. A corpus that names a TTS model is
                    rejected before a single sample is loaded. This is the
                    cheapest probe and the ONLY one that catches a
                    self-consistent synthetic corpus.
  2. REDUNDANCY   — per unit, mean pairwise cosine w between clips, and the
                    effective independent count  n_eff = k / (1 + (k-1)*w).
                    Three identical clips give n_eff = 1, not 3.
  3. ARTEFACT     — the identical-phone probe. Label pairs that are the SAME
                    sound (ta/tha, ka/qa, aa/ah) MUST NOT be separable. If they
                    are, the corpus carries a nuisance channel and every
                    between-class number on it is measuring that channel.
  4. SIGNAL       — leave-group-out nearest-centroid accuracy vs chance, with
                    an exact binomial p. Is there anything learnable at all
                    under an honest split?
  5. LEAKAGE      — random-split accuracy MINUS leave-group-out accuracy. How
                    much of the reported number was session memorisation.

HARD SAFETY (inherited from master_modeler.py, unchanged)
---------------------------------------------------------
Read-only. It opens wav files and json manifests and nothing else. It never
writes into any corpus, never kills or starts a trainer, never opens a
microphone, never touches ERAN's live run on eran1. Its only writes are into
its own runs/ directory. On Windows it drops itself to BELOW_NORMAL priority
so it can never starve the mic (feedback_pc_heavy_work_below_normal).

REUSE, NOT DUPLICATION
----------------------
The percept is ERAN'S OWN EAR — eran-brain/body/ears.py, the frozen cochlea
(24 bands x 8 slices = 192 dims, loudest60 pooling). Nothing is reimplemented.
If a corpus is unteachable to that ear, it is unteachable to ERAN, which is
the only question worth asking.

USAGE
    python teachability.py judge --all                 # the whole registry
    python teachability.py judge tts-vault t06-rich    # named corpora
    python teachability.py units t06-starved           # per-unit table
    python teachability.py forget tts-vault            # emit a forget-set
    python teachability.py contamination               # is a rejected clip in the food?
    python teachability.py --json judge --all          # machine-readable
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                              # D:\CLAUDE
ERAN_BRAIN = ROOT / "eran-brain"
REGISTRY = HERE / "corpora.json"
RUNS = HERE / "runs"


# ---- honour feedback_pc_heavy_work_below_normal ---------------------------- #
def _below_normal():
    if os.name != "nt":
        try:
            os.nice(10)
            return "nice+10"
        except Exception:
            return "priority-unchanged"
    try:
        import ctypes
        BELOW_NORMAL = 0x00004000
        k32 = ctypes.windll.kernel32
        # HANDLE is pointer-sized; the default c_int restype truncates it on
        # 64-bit and SetPriorityClass then silently fails. This is why the law
        # says test the REAL output, not `health: ok`.
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        ok = k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL)
        return "BELOW_NORMAL" if ok else "priority-unchanged"
    except Exception as exc:                                   # pragma: no cover
        return f"priority-unchanged ({exc})"


if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# The ear — ERAN's own, imported not rebuilt.
# --------------------------------------------------------------------------- #
class Ear:
    """Thin wrapper over eran-brain/body/ears.py. Reports honestly which ear it
    got; if the real one cannot be imported it REFUSES rather than silently
    substituting a different ear and calling the numbers ERAN's."""

    def __init__(self):
        body = ERAN_BRAIN / "body"
        if str(body) not in sys.path:
            sys.path.insert(0, str(body))
        try:
            import genome                                        # noqa: F401
            from ears import Ears
        except Exception as exc:
            raise SystemExit(
                f"[MODEH] cannot import ERAN's ear from {body}: {exc}\n"
                f"        This organ measures teachability TO ERAN. Without his\n"
                f"        ear there is no honest number to report. Refusing.")
        # exam=True: the examiner may read the heldout vault. The organism may
        # not, and this tool is never the organism.
        self.ears = Ears(exam=True)
        self.desc = (f"eran-brain/body/ears.py repr={self.ears.repr} "
                     f"bands={self.ears.n_bands} pool={self.ears.pooling} "
                     f"dim={self.ears.dim}")
        self.dim = self.ears.dim

    def vec(self, path):
        return np.asarray(self.ears.utterance(str(path)), dtype=np.float64)


# --------------------------------------------------------------------------- #
# Corpus loading — label and group come from the FILENAME, never from a model.
# --------------------------------------------------------------------------- #
_UNDERSCORE = re.compile(r"^([A-Za-z]+)_([A-Za-z]\d+)_")
_FLEURS = re.compile(r"^([A-Z]+)__([^_]+)__")


def parse_underscore(path: Path):
    """aa_t06_0.wav -> label 'aa', group 't06' (the sitting / the TTS seed)."""
    m = _UNDERSCORE.match(path.name)
    return (m.group(1), m.group(2)) if m else None


def parse_fleurs(path: Path):
    """B__fleurs-100__u00393__00287.wav -> label 'B', group = the SPEAKER id."""
    m = _FLEURS.match(path.name)
    return (m.group(1), m.group(2)) if m else None


_DICT = re.compile(r"^([a-z]+)__(\d{8})")


def parse_dictation(path: Path):
    """almamic__20260628_200830_790927.wav -> label = the capture rig,
    group = the DAY it was captured."""
    m = _DICT.match(path.name)
    return (m.group(1), m.group(2)) if m else None


PARSERS = {"underscore": parse_underscore, "fleurs": parse_fleurs,
           "dictation": parse_dictation}


def load_registry(scratch=None):
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    scratch = scratch or os.environ.get("MODEH_SCRATCH", "")
    for c in reg["corpora"]:
        c["root"] = c["root"].replace("@SCRATCH@", scratch)
    return reg


def collect(spec, reg=None):
    """-> (items, notes). items = [(Path, label, group)]. Pure filesystem read."""
    root = Path(spec["root"])
    if not root.is_absolute():
        root = ROOT / root
    notes = []
    if not root.exists():
        return [], [f"root does not exist: {root}"]
    parser = PARSERS[spec.get("parse", "underscore")]
    raw = []
    for p in sorted(root.rglob("*.wav")):
        got = parser(p)
        if got is None:
            notes.append(f"unparsed filename skipped: {p.name}")
            continue
        raw.append((p, got[0], got[1]))
    drop = set(spec.get("drop_labels", []))
    raw = [r for r in raw if r[1] not in drop]
    # unit-count filters let ONE directory expose two honest sub-corpora
    counts = {}
    for _, lab, _g in raw:
        counts[lab] = counts.get(lab, 0) + 1
    lo, hi = spec.get("min_per_unit"), spec.get("max_per_unit")
    if lo is not None:
        raw = [r for r in raw if counts[r[1]] >= lo]
    if hi is not None:
        raw = [r for r in raw if counts[r[1]] <= hi]
    cap = spec.get("cap_per_unit")
    if cap:
        seen, kept = {}, []
        for r in raw:
            n = seen.get(r[1], 0)
            if n < cap:
                kept.append(r)
                seen[r[1]] = n + 1
        raw = kept
    return raw, notes


# --------------------------------------------------------------------------- #
# PROBE 1 — provenance. The only probe that catches a self-consistent fake.
# --------------------------------------------------------------------------- #
SYNTH_MARKERS = [
    ("mms-tts", "names facebook/mms-tts (a TTS model)"),
    ("tts-heb", "names a Hebrew TTS model"),
    ("vits", "names VITS (a speech synthesiser)"),
    ("torch_seed", "clips are indexed by a torch RNG seed, i.e. generated"),
    ("base_rendering_id", "clips are renderings, not recordings"),
    ("speaking_rate", "a synthesiser parameter is recorded per clip"),
    ("noise_scale", "a synthesiser parameter is recorded per clip"),
    ("tokenizer_strips_niqqud", "the generator's own note that the vowels were lost"),
    ("synthetic tts", "the corpus's own record calls itself synthetic TTS"),
    ("synthetic seeds", "the corpus's own record calls its talkers synthetic seeds"),
]
HUMAN_MARKERS = [
    ("speaker", "clips carry speaker identity"),
    ("fleurs", "FLEURS -- a published human-read corpus"),
    ("recorded", "the record says recorded"),
    ("recording", "the record says recording"),
    ("microphone", "a microphone is named"),
    ("keshev", "captured through the KESHEV booth"),
]
META_NAMES = ("manifest.json", "README.md", "ATTRIBUTION.txt", "PROVENANCE.jsonl",
              "SOURCE.json", "LICENCE.json", "index.json",
              "README-DICTIONARY.md", "RECORDING-PLAN.md", "CORPUS-LICENCE.md")


def probe_provenance(root: Path):
    """Read whatever record ships WITH the corpus, up to 3 levels up. Verdict is
    SYNTHETIC / HUMAN-CLAIMED / UNKNOWN plus the exact quoted evidence."""
    root = Path(root)
    seen, synth, human = [], [], []
    levels = [root] + list(root.parents)[:3]
    for depth, d in enumerate(levels):
        for name in META_NAMES:
            f = d / name
            if not f.exists() or f.stat().st_size > 8_000_000:
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            seen.append(str(f))
            low = txt.lower()
            # ASYMMETRY, on purpose: evidence that a corpus is DIRTY counts from
            # anywhere above it, because contamination flows downhill. Evidence
            # that it is CLEAN counts only from its own folder or its parent --
            # a README three levels up saying 'recorded' says nothing about the
            # clips in this folder, and treating it as a clearance is exactly
            # how a synthetic corpus gets called human.
            for marker, why in SYNTH_MARKERS:
                if marker in low:
                    idx = low.index(marker)
                    quote = " ".join(txt[max(0, idx - 60): idx + 90].split())
                    synth.append({"file": str(f), "marker": marker,
                                  "why": why, "quote": quote})
            # A clean bill of health counts only if the record is plausibly
            # ABOUT these clips: it sits in the folder or its parent, or it
            # names the folder in its text (the booth's README says where it
            # writes). Anything vaguer is somebody else's paperwork.
            names_it = (root.name.lower() in low
                        or f"{root.parent.name}/{root.name}".lower() in low
                        or f"{root.parent.name}\\{root.name}".lower() in low)
            if depth <= 1 or names_it:
                for marker, why in HUMAN_MARKERS:
                    if marker in low:
                        human.append({"file": str(f), "marker": marker,
                                      "why": why, "depth": depth})
    verdict = "SYNTHETIC" if synth else ("HUMAN-CLAIMED" if human else "UNKNOWN")
    uniq, taken = [], set()
    for s in synth:
        if s["marker"] in taken:
            continue
        taken.add(s["marker"])
        uniq.append(s)
    return {"verdict": verdict, "records_read": seen, "synthetic_evidence": uniq,
            "human_markers": sorted({h["marker"] for h in human})}


# --------------------------------------------------------------------------- #
# PROBE 2 — redundancy / effective independent examples
# --------------------------------------------------------------------------- #
def unit_redundancy(V, floor=0.0):
    """V = (k, d) already globally standardised. Returns (w_raw, w_excess, n_eff).

    w_raw    = mean pairwise cosine between the unit's clips.
    floor    = the corpus's BETWEEN-unit mean cosine, i.e. how alike two clips
               are when they are not even the same syllable. Subtracting it is
               what makes these numbers comparable BETWEEN corpora; a raw
               cosine is not, because it rides on whatever the corpus's overall
               variance happens to be.
    w_excess = (w_raw - floor) / (1 - floor), clipped to [0, 1].
    n_eff    = k / (1 + (k-1) * w_excess)  -- effective sample size under
               equicorrelation. k identical clips give n_eff = 1; k clips no
               more alike than random give n_eff = k. This is the number that
               says 'you have one example, not three'.
    """
    k = V.shape[0]
    if k < 2:
        return float("nan"), float("nan"), float(k)
    N = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-12)
    S = N @ N.T
    iu = np.triu_indices(k, 1)
    w = float(np.mean(S[iu]))
    ex = (w - floor) / (1.0 - floor) if floor < 1.0 else 0.0
    ex = min(1.0, max(0.0, ex))
    n_eff = k / (1.0 + (k - 1) * ex)
    return w, ex, float(n_eff)


def between_unit_floor(X, y, max_pairs=200000, seed=0):
    """Mean cosine between clips of DIFFERENT units -- the corpus's 'everything
    here sounds a bit alike' baseline."""
    N = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    n = len(y)
    if n < 4:
        return 0.0
    rng = np.random.default_rng(seed)
    S = N @ N.T
    iu = np.triu_indices(n, 1)
    diff = np.array([y[i] != y[j] for i, j in zip(*iu)])
    vals = S[iu][diff]
    if vals.size == 0:
        return 0.0
    if vals.size > max_pairs:
        vals = vals[rng.choice(vals.size, size=max_pairs, replace=False)]
    return float(np.mean(vals))


def block_confound(items, y):
    """Were the units recorded as CONTIGUOUS BLOCKS in time?

    The booth writes one unit at a time: say 'aa' twelve times, then say 'ah'
    twelve times. If every unit occupies its own untouched slice of the clock,
    then inside a single sitting 'different unit' and 'different minute' are
    the same variable, and NO between-unit number from that corpus can tell a
    phone apart from mic drift, voice warmth or posture.

    Heuristic, and honest about it: it reads file mtimes, which survive being
    written in place but are destroyed by some copies. Degenerate cases (all
    mtimes equal) return None rather than a number.
    """
    times = {}
    for (p, lab, _g) in items:
        try:
            t = p.stat().st_mtime
        except Exception:
            return None
        times.setdefault(lab, []).append(t)
    spans = {L: (min(v), max(v)) for L, v in times.items() if v}
    if len(spans) < 2:
        return None
    allt = [t for v in times.values() for t in v]
    if max(allt) - min(allt) < 1.0:
        return None                      # all one timestamp -- probe unusable
    labs = sorted(spans)
    tot = sep = 0
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = spans[labs[i]], spans[labs[j]]
            tot += 1
            if a[1] < b[0] or b[1] < a[0]:
                sep += 1
    return {"unit_pairs": tot, "disjoint_in_time": sep,
            "block_fraction": round(sep / tot, 4) if tot else None,
            "span_seconds": round(max(allt) - min(allt), 1)}


def drift_floor(X, items, y, min_k=6):
    """THE TIME-ONLY CONTROL -- the vanilla arm of the identical-phone probe.

    Take ONE unit, sort its own clips by mtime, call the first half 'early' and
    the second half 'late', and try to separate those. Same syllable, same
    mouth, same label: the ONLY thing that differs is when it was said. Whatever
    accuracy that reaches is the corpus's drift floor -- the score any pair of
    units recorded one after the other gets for free.

    An identical-phone pair only proves a nuisance channel if it beats THIS,
    not if it beats a coin flip (feedback_clean_experiments: a claim without a
    param-matched control is not a result).
    """
    times = {}
    for i, (p, lab, _g) in enumerate(items):
        try:
            times.setdefault(lab, []).append((p.stat().st_mtime, i))
        except Exception:
            return None
    ok = tot = 0
    per = []
    for L, tv in times.items():
        if len(tv) < min_k:
            continue
        tv.sort()
        idx = [i for _t, i in tv]
        half = len(idx) // 2
        yy = ["early"] * half + ["late"] * (len(idx) - half)
        acc, o, t = loo_accuracy(X[idx], yy)
        if acc is None:
            continue
        ok += o
        tot += t
        per.append({"unit": L, "k": len(idx), "accuracy": round(acc, 4)})
    if not tot:
        return None
    return {"floor": round(ok / tot, 4), "correct": ok, "n": tot,
            "units_used": len(per), "per_unit": per}


def twin_fraction(V, thresh=0.90):
    k = V.shape[0]
    if k < 2:
        return 0.0
    N = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-12)
    S = N @ N.T
    iu = np.triu_indices(k, 1)
    return float(np.mean(S[iu] > thresh))


# --------------------------------------------------------------------------- #
# Classifier — nearest class centroid. Deliberately the weakest honest model:
# if THIS finds signal the signal is real; if it finds none we say 'none found
# by a nearest-centroid ear', never 'none exists'.
# --------------------------------------------------------------------------- #
def _nc_predict(Xtr, ytr, Xte):
    labs = sorted(set(ytr))
    cent = np.stack([Xtr[[i for i, y in enumerate(ytr) if y == L]].mean(axis=0)
                     for L in labs])
    cent = cent / (np.linalg.norm(cent, axis=1, keepdims=True) + 1e-12)
    Xn = Xte / (np.linalg.norm(Xte, axis=1, keepdims=True) + 1e-12)
    return [labs[i] for i in np.argmax(Xn @ cent.T, axis=1)]


def logo_accuracy(X, y, g, max_folds=40, seed=0):
    """Leave-one-GROUP-out. A group is a whole recording sitting / speaker / TTS
    seed, never a random file. Holding out a random FILE lets a model be scored
    on the sitting it memorised -- the 14-point scar of 2026-08-21."""
    groups = sorted(set(g))
    if len(groups) < 2:
        return None, 0, 0, "single group -- leave-group-out impossible"
    if len(groups) > max_folds:
        rng = np.random.default_rng(seed)
        groups = [groups[i] for i in
                  rng.choice(len(groups), size=max_folds, replace=False)]
    ok = tot = 0
    for G in groups:
        te = [i for i in range(len(y)) if g[i] == G]
        tr = [i for i in range(len(y)) if g[i] != G]
        trl = set(y[i] for i in tr)
        te = [i for i in te if y[i] in trl]
        if not te or not tr:
            continue
        pred = _nc_predict(X[tr], [y[i] for i in tr], X[te])
        ok += sum(1 for p, i in zip(pred, te) if p == y[i])
        tot += len(te)
    return (ok / tot if tot else None), ok, tot, ""


def loo_accuracy(X, y, max_n=900, seed=0):
    """Leave-one-CLIP-out. Used only where the corpus is a single sitting, and
    flagged as such -- it cannot see session leakage, by construction."""
    n = len(y)
    idx = list(range(n))
    if n > max_n:
        rng = np.random.default_rng(seed)
        idx = sorted(rng.choice(n, size=max_n, replace=False).tolist())
    ok = tot = 0
    for i in idx:
        tr = [j for j in range(n) if j != i]
        if y[i] not in set(y[j] for j in tr):
            continue
        pred = _nc_predict(X[tr], [y[j] for j in tr], X[[i]])
        ok += int(pred[0] == y[i])
        tot += 1
    return (ok / tot if tot else None), ok, tot


def random_split_accuracy(X, y, folds=5, seed=0):
    """Same held-out sizes as LOGO but folds drawn at RANDOM, ignoring the
    group. The gap between this and LOGO is the leakage."""
    rng = np.random.default_rng(seed)
    n = len(y)
    chunks = np.array_split(rng.permutation(n), folds)
    ok = tot = 0
    for c in chunks:
        te_set = set(int(i) for i in c)
        tr = [i for i in range(n) if i not in te_set]
        trl = set(y[i] for i in tr)
        te = [i for i in sorted(te_set) if y[i] in trl]
        if not te or not tr:
            continue
        pred = _nc_predict(X[tr], [y[i] for i in tr], X[te])
        ok += sum(1 for p, i in zip(pred, te) if p == y[i])
        tot += len(te)
    return (ok / tot if tot else None), ok, tot


# --------------------------------------------------------------------------- #
# exact binomial tail -- stdlib, no scipy
# --------------------------------------------------------------------------- #
def binom_sf(k, n, p):
    """P(X >= k) for X ~ Bin(n, p). One-sided: 'is this above chance at all?'"""
    if n <= 0:
        return 1.0
    k = int(math.ceil(k))
    if k <= 0:
        return 1.0
    return float(sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
                     for i in range(k, n + 1)))


# --------------------------------------------------------------------------- #
# PROBE 3 — the identical-phone probe
# --------------------------------------------------------------------------- #
def probe_artefact(X, y, g, pairs, floor=None):
    """For each pair of labels that are THE SAME SOUND: try to tell them apart.
    Success is failure. A corpus that can separate ta from tha is not carrying
    phonetics, it is carrying a fingerprint of how the clips were made.

    `floor` is the measured time-only control (drift_floor). The verdict is
    taken against THAT where it exists, and against a coin flip only where it
    does not -- and the report says which."""
    out = []
    fl = floor["floor"] if floor else None
    for a, b, why in pairs:
        idx = [i for i in range(len(y)) if y[i] in (a, b)]
        if len({y[i] for i in idx}) < 2 or len(idx) < 6:
            continue
        Xp, yp, gp = X[idx], [y[i] for i in idx], [g[i] for i in idx]
        acc, ok, tot, _note = logo_accuracy(Xp, yp, gp)
        how = "leave-group-out"
        if acc is None:
            acc, ok, tot = loo_accuracy(Xp, yp)
            how = "leave-one-clip-out (single group)"
        if acc is None:
            continue
        p_coin = binom_sf(ok, tot, 0.5)
        rec = {"pair": f"{a}/{b}", "why_identical": why, "n": tot,
               "accuracy": round(acc, 4), "correct": ok, "how": how,
               "p_vs_coinflip": p_coin, "drift_floor": fl}
        if fl is not None and fl > 0.5:
            p_drift = binom_sf(ok, tot, min(0.999, fl))
            rec["p_vs_drift_floor"] = p_drift
            rec["separable"] = bool(p_drift < 0.01 and acc > fl)
            rec["compared_to"] = f"the measured drift floor {fl:.3f}"
        else:
            rec["p_vs_drift_floor"] = None
            rec["separable"] = bool(p_coin < 0.01 and acc > 0.70)
            rec["compared_to"] = ("a coin flip (no drift floor measurable -- "
                                  "units too small for a time-only control)")
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# The judgement
# --------------------------------------------------------------------------- #
THRESH = {
    # Fewer than 3 effectively-independent examples means a class's spread
    # cannot even be ESTIMATED (a variance needs 3 points), so whatever the
    # model learns about that class's variation is assumed, never measured.
    # That is the statistical reason for the number, not a fitted one.
    "n_eff_starved": 3.0,
    "artefact_p": 0.01,        # identical phones must not separate at p<0.01
    "artefact_acc": 0.70,      # ...and above 70%
    "signal_p": 0.01,          # signal must beat chance at p<0.01
    "leak_warn": 0.15,         # 15 points of random-vs-honest split gap
    "block_frac": 0.90,        # 90% of unit pairs disjoint in time = block-recorded
}


_JUDGED = {}          # root -> result, so a cascade never re-measures a source


def source_of(root):
    """If this corpus was BUILT from another one, return that other one's path.
    Provenance is a graph, not a label: rejecting a source has to reject its
    children, or 'unlearning' means nothing."""
    rel = str(Path(root)).replace("\\", "/")
    for d in DERIVATIONS:
        if rel.endswith(d["to"]) and (ROOT / d["from"]).exists():
            return ROOT / d["from"], d
    return None, None


def judge(spec, reg, ear, verbose=True, _depth=0):
    t0 = time.time()
    root = Path(spec["root"])
    if not root.is_absolute():
        root = ROOT / root
    items, notes = collect(spec)
    res = {"id": spec["id"], "what": spec.get("what", ""), "root": str(root),
           "n_clips": len(items), "notes": notes[:5], "ear": ear.desc}
    res["provenance"] = prov = probe_provenance(root)
    if not items:
        res["verdict"] = "UNKNOWN"
        res["reasons"] = ["no clips found"]
        res["signal"] = {"accuracy": None, "n": 0, "how": "-", "p_vs_chance": None}
        res["leakage"] = {"gap": None, "why": "no clips"}
        return res

    labels = sorted({l for _, l, _ in items})
    groups = sorted({g for _, _, g in items})
    res.update(n_units=len(labels), n_groups=len(groups), units=labels,
               groups=groups[:12] + (["..."] if len(groups) > 12 else []))

    if verbose:
        print(f"  [{spec['id']}] {len(items)} clips, {len(labels)} units, "
              f"{len(groups)} groups -- hearing with ERAN's ear...", flush=True)
    X = np.stack([ear.vec(p) for p, _, _ in items])
    y = [l for _, l, _ in items]
    g = [gg for _, _, gg in items]
    # global standardisation: every dim gets equal say, so 'similar' means
    # similar in the ear's own units, not in whichever band happens to be loud.
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)

    # ---- probe 2: redundancy, per unit (excess over the corpus's own floor)
    floor = between_unit_floor(X, y)
    res["between_unit_cosine"] = round(floor, 4)
    per_unit = []
    for L in labels:
        ix = [i for i in range(len(y)) if y[i] == L]
        w, ex, ne = unit_redundancy(X[ix], floor)
        per_unit.append({"unit": L, "k": len(ix),
                         "within_cosine": None if math.isnan(w) else round(w, 4),
                         "excess": None if math.isnan(ex) else round(ex, 4),
                         "n_eff": round(ne, 2),
                         "twin_frac": round(twin_fraction(X[ix]), 3)})
    res["per_unit"] = per_unit
    ws = [u["within_cosine"] for u in per_unit if u["within_cosine"] is not None]
    exs = [u["excess"] for u in per_unit if u["excess"] is not None]
    nes = [u["n_eff"] for u in per_unit if u["k"] >= 2]
    res["within_cosine_mean"] = round(float(np.mean(ws)), 4) if ws else None
    res["excess_mean"] = round(float(np.mean(exs)), 4) if exs else None
    res["n_eff_median"] = round(float(np.median(nes)), 2) if nes else None
    res["k_median"] = int(np.median([u["k"] for u in per_unit]))
    res["twin_frac_mean"] = round(
        float(np.mean([u["twin_frac"] for u in per_unit])), 3)

    # ---- probe 6 FIRST: the time-only control, so probe 3 can be judged
    #      against a measured floor instead of against a coin flip.
    res["block"] = blk = block_confound(items, y)
    res["drift"] = drift = drift_floor(X, items, y)

    # ---- probe 3: identical phones, scored against the drift floor
    pairs = spec.get("identical_phones") or reg["identical_phones_default"]
    res["artefact"] = probe_artefact(X, y, g, [tuple(p) for p in pairs], drift)
    confounded = bool(blk and blk["block_fraction"] is not None
                      and blk["block_fraction"] >= THRESH["block_frac"]
                      and drift and drift["floor"] > 0.75)
    res["artefact_confounded"] = confounded

    # ---- probe 4/5: signal + leakage
    chance = 1.0 / len(labels)
    res["chance"] = round(chance, 4)
    acc, ok, tot, _note = logo_accuracy(X, y, g)
    how = "leave-group-out"
    if acc is None:
        acc, ok, tot = loo_accuracy(X, y)
        how = "leave-one-clip-out (single group -- leakage untestable)"
    res["signal"] = {"accuracy": None if acc is None else round(acc, 4),
                     "n": tot, "how": how,
                     "p_vs_chance": None if acc is None else binom_sf(ok, tot, chance)}
    if len(groups) >= 2 and acc is not None:
        racc, _rok, _rtot = random_split_accuracy(X, y)
        res["leakage"] = {"random_split_accuracy": round(racc, 4),
                          "honest_split_accuracy": round(acc, 4),
                          "gap": round(racc - acc, 4)}
    else:
        res["leakage"] = {"gap": None,
                          "why": "single group -- cannot measure session leakage"}

    # ---- the verdict
    reasons, flags = [], []
    if prov["verdict"] == "SYNTHETIC":
        ev = prov["synthetic_evidence"][0]
        reasons.append(f"PROVENANCE: the corpus's own record names a generator "
                       f"('{ev['marker']}' -- {ev['why']})")
        flags.append("SYNTHETIC")
    for a in res["artefact"]:
        if a["separable"]:
            reasons.append(
                f"ARTEFACT: {a['pair']} are the same sound ({a['why_identical']}) "
                f"yet separate at {a['accuracy'] * 100:.1f}% (n={a['n']}) -- above "
                f"{a['compared_to']} "
                f"(p={(a['p_vs_drift_floor'] if a['p_vs_drift_floor'] is not None else a['p_vs_coinflip']):.2g})"
                f" -- a nuisance channel, not phonetics")
            flags.append("ARTEFACT")
        elif a["accuracy"] > 0.70 and a["p_vs_coinflip"] < 0.01:
            reasons.append(
                f"CONFOUNDED: {a['pair']} separate at {a['accuracy'] * 100:.1f}%, "
                f"but this corpus's own time-only control already reaches "
                f"{a['drift_floor'] * 100:.1f}% -- early clips of ONE unit can be "
                f"told from late clips of the SAME unit. The separation is real; "
                f"nothing here shows it is phonetic. Re-record interleaved to "
                f"decide it.")
            flags.append("CONFOUNDED")
    if confounded and not any(f in flags for f in ("ARTEFACT", "CONFOUNDED")):
        reasons.append(
            f"CONFOUNDED: units were recorded in contiguous blocks "
            f"({blk['disjoint_in_time']}/{blk['unit_pairs']} unit pairs never "
            f"overlap in time) and the time-only control reaches "
            f"{drift['floor'] * 100:.1f}%. Any between-unit number from this "
            f"corpus is partly a clock reading.")
        flags.append("CONFOUNDED")
    if (res["n_eff_median"] is not None and res["k_median"] >= 2
            and res["n_eff_median"] < THRESH["n_eff_starved"]):
        reasons.append(f"STARVED: median unit holds {res['k_median']} clips but only "
                       f"{res['n_eff_median']} independent examples "
                       f"(within-unit cosine {res['within_cosine_mean']}, "
                       f"corpus floor {res['between_unit_cosine']}, "
                       f"excess {res['excess_mean']}). Below 3 you cannot even "
                       f"estimate what the unit's variation IS.")
        flags.append("STARVED")
    if res["signal"]["accuracy"] is None:
        reasons.append("SIGNAL: not measurable")
        flags.append("UNKNOWN")
    elif res["signal"]["p_vs_chance"] >= THRESH["signal_p"]:
        reasons.append(f"NO SIGNAL: {res['signal']['accuracy'] * 100:.1f}% vs "
                       f"{chance * 100:.1f}% chance under {how} "
                       f"(p={res['signal']['p_vs_chance']:.2g}) -- nothing to learn")
        flags.append("NO-SIGNAL")
    lg = res["leakage"].get("gap")
    if lg is not None and lg > THRESH["leak_warn"]:
        reasons.append(f"LEAKAGE: a random split scores {lg * 100:.1f} points higher "
                       f"than an honest one -- that much of any number reported on "
                       f"this corpus was session memorisation")
        flags.append("LEAKY")

    # ---- the cascade: a corpus built from a rejected corpus is rejected too.
    # This is the forgetting rule doing real work inside the judge -- without
    # it, revoking a source leaves every dish cooked from it on the table.
    src, edge = source_of(root)
    if src is not None and _depth < 1:
        key = str(src)
        if key in _JUDGED:
            sv = _JUDGED[key]
        else:
            sspec = {"id": f"{spec['id']}<-source", "root": str(src),
                     "parse": spec.get("parse", "underscore"),
                     "what": f"source of {spec['id']}"}
            sv = judge(sspec, reg, ear, verbose=False, _depth=_depth + 1)
            _JUDGED[key] = sv
        res["source"] = {"path": str(src), "verdict": sv["verdict"],
                         "by": edge["by"], "note": edge["note"]}
        if sv["verdict"] in ("REJECT", "STARVED"):
            reasons.append(
                f"CASCADE: built from {edge['from']} by {edge['by']}, and that "
                f"source is {sv['verdict']}. {edge['note']}")
            flags.append("CASCADE-REJECT" if sv["verdict"] == "REJECT"
                         else "CASCADE-STARVED")

    if {"SYNTHETIC", "ARTEFACT", "NO-SIGNAL", "CASCADE-REJECT"} & set(flags):
        verdict = "REJECT"
    elif {"STARVED", "CASCADE-STARVED"} & set(flags):
        verdict = "STARVED"
    elif {"LEAKY", "CONFOUNDED"} & set(flags):
        verdict = "WEAK"
    elif "UNKNOWN" in flags:
        verdict = "UNKNOWN"
    else:
        verdict = "ACCEPT"
    if verdict == "ACCEPT" and prov["verdict"] == "UNKNOWN":
        verdict = "ACCEPT-UNVERIFIED"
        reasons.append("PROVENANCE: no record ships with this corpus, so nothing "
                       "proves the audio is what the labels claim. The acoustics "
                       "are clean; the paperwork is missing.")
    res["flags"] = flags
    res["verdict"] = verdict
    res["reasons"] = reasons or ["all five probes passed"]

    # what to DO about it -- the 2026-09-05 growth finding, applied
    if verdict == "REJECT" and "NO-SIGNAL" in flags:
        res["prescription"] = (
            "Do not size a fixed wide model on this. Measured 2026-09-05: on a "
            "corpus with no signal a model GROWN on underfit lands on the floor, "
            "while a fixed wide model falls 0.1429 BELOW it. Growing buys damage "
            "limitation when there is nothing to learn.")
    elif verdict == "REJECT":
        res["prescription"] = ("Revoke the source and everything derived from it "
                               "(`teachability.py forget <id>`), then re-measure "
                               "every number that stood on it.")
    elif verdict == "STARVED":
        res["prescription"] = ("Do not augment -- augmentation raises k without "
                               "raising n_eff. Record more real takes.")
    res["seconds"] = round(time.time() - t0, 1)
    return res


# --------------------------------------------------------------------------- #
# FORGETTING — data-level unlearning: a forget-set keyed by provenance, plus the
# derived-file cascade and a contamination check.
# Weight-level unlearning (gradient ascent on a forget set, SISA, influence
# functions) is NOT implemented here and is not claimed.
# --------------------------------------------------------------------------- #
DERIVATIONS = [
    {"from": "eran-brain/food/train", "to": "eran-brain/food/words",
     "by": "eran-brain/proof/make_words.py",
     "note": "words are concatenated FROM train clips -- rejecting train rejects words"},
    {"from": "eran-brain/proof/heldout-vault", "to": "eran-brain/state/metrics.jsonl",
     "by": "eran-brain/proof/measure.py",
     "note": "every reported heldout number was computed on this vault"},
    {"from": "eran-brain/food/train", "to": "eran-brain/state/curriculum.json",
     "by": "eran-brain/body/school.py",
     "note": "the mastery gate (and '13 syllables mastered') is a DEV split of train"},
]

FOOD_DIRS = ["eran-brain/food/train", "eran-brain/food/words"]


def cmd_forget(args, reg, ear):
    out = {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "sets": []}
    for cid in args.corpus:
        spec = next((c for c in reg["corpora"] if c["id"] == cid), None)
        if spec is None:
            raise SystemExit(f"unknown corpus id: {cid}")
        v = judge(spec, reg, ear, verbose=not args.json)
        items, _ = collect({**spec, "root": v["root"]})
        entry = {"corpus": cid, "verdict": v["verdict"], "reasons": v["reasons"],
                 "root": v["root"], "n_files": len(items),
                 "files": [str(p) for p, _, _ in items] if args.files
                          else "(re-run with --files)",
                 "derived": []}
        rel = str(Path(v["root"])).replace("\\", "/")
        for d in DERIVATIONS:
            if rel.endswith(d["from"]):
                tgt = ROOT / d["to"]
                entry["derived"].append({"path": str(tgt), "by": d["by"],
                                         "note": d["note"], "exists": tgt.exists()})
        out["sets"].append(entry)
    RUNS.mkdir(exist_ok=True)
    p = RUNS / "forget-set.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"\nFORGET-SET  ->  {p}")
        for s in out["sets"]:
            print(f"  {s['corpus']}: {s['verdict']}  {s['n_files']} files")
            for r in s["reasons"]:
                print(f"      - {r}")
            for d in s["derived"]:
                print(f"      CASCADE -> {d['path']}")
                print(f"                 {d['note']}")
        print("\n  This is a DATA-level revocation list plus its derived cascade.")
        print("  It removes nothing and it does NOT unlearn weights.")
    return out


def cmd_contamination(args, reg, ear):
    """The check that would have caught the TTS entering the food: is any file
    from a REJECTED corpus (byte-identical) sitting inside a food dir?"""
    import hashlib

    def sha(p):
        try:
            return hashlib.sha1(p.read_bytes()).hexdigest()
        except Exception:
            return None

    food_paths = set()
    for fd in FOOD_DIRS:
        d = ROOT / fd
        if d.exists():
            food_paths |= {p.resolve() for p in d.rglob("*.wav")}

    rejected, direct = {}, []
    for spec in reg["corpora"]:
        v = judge(spec, reg, ear, verbose=False)
        if v["verdict"] != "REJECT":
            continue
        root = Path(v["root"]).resolve()
        if any(str(root) == str((ROOT / fd).resolve()) for fd in FOOD_DIRS):
            direct.append({"food_dir": str(root), "corpus": spec["id"],
                           "reasons": v["reasons"], "n_clips": v["n_clips"]})
            continue                      # not a smuggled copy -- it IS the food
        items, _ = collect({**spec, "root": v["root"]})
        for p, _, _ in items:
            if p.resolve() in food_paths:
                continue                  # same file seen through another name
            h = sha(p)
            if h:
                rejected.setdefault(h, []).append(spec["id"])

    smuggled = []
    for p in sorted(food_paths):
        h = sha(p)
        if h and h in rejected:
            smuggled.append({"food_file": str(p), "same_bytes_as": rejected[h][0]})

    out = {"food_dirs": FOOD_DIRS, "food_clips": len(food_paths),
           "food_dirs_that_are_themselves_rejected": direct,
           "rejected_clip_hashes": len(rejected), "smuggled_copies": smuggled}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    print(f"\nCONTAMINATION CHECK -- {len(food_paths)} clips in the food dirs")
    if direct:
        for d in direct:
            print(f"  BROKEN WINDOW: {d['food_dir']} IS a rejected corpus "
                  f"({d['n_clips']} clips, registered as '{d['corpus']}')")
            for r in d["reasons"]:
                print(f"      - {r}")
    else:
        print("  no food dir is itself a rejected corpus")
    if smuggled:
        print(f"  BROKEN WINDOW: {len(smuggled)} clips from a rejected corpus "
              f"elsewhere have been copied into the food:")
        for h in smuggled[:20]:
            print(f"    {h['food_file']}   == {h['same_bytes_as']}")
    else:
        print(f"  no clip from any OTHER rejected corpus was copied in "
              f"({len(rejected)} such clips hashed and checked)")
    return out


# --------------------------------------------------------------------------- #
def print_report(v):
    print("=" * 78)
    print(f"{v['id']}  --  {v['what']}")
    print(f"  {v['root']}")
    print(f"  {v['n_clips']} clips / {v.get('n_units', '?')} units / "
          f"{v.get('n_groups', '?')} groups")
    p = v["provenance"]
    tail = ""
    if p["synthetic_evidence"]:
        e = p["synthetic_evidence"][0]
        tail = f"  <- '{e['marker']}': {e['why']}"
    print(f"  PROVENANCE   {p['verdict']}{tail}")
    if v.get("source"):
        s = v["source"]
        print(f"  SOURCE       built by {s['by']} from a corpus judged "
              f"{s['verdict']}")
    print(f"  REDUNDANCY   within {v.get('within_cosine_mean')} vs corpus floor "
          f"{v.get('between_unit_cosine')} -> excess {v.get('excess_mean')} | "
          f"median unit {v.get('k_median')} clips -> {v.get('n_eff_median')} "
          f"independent | twin-pairs {v.get('twin_frac_mean')}")
    d = v.get("drift")
    if d:
        print(f"  DRIFT FLOOR  {d['floor'] * 100:.1f}%  -- early vs late clips of the "
              f"SAME unit, {d['units_used']} units, n={d['n']} (the score any pair "
              f"gets for free)")
    else:
        print("  DRIFT FLOOR  not measurable (units too small for a time-only control)")
    if v.get("artefact"):
        for a in v["artefact"]:
            if a["separable"]:
                mark = "SEPARABLE (bad)"
            elif a["accuracy"] > 0.70:
                mark = "high but within the drift floor"
            else:
                mark = "not separable (good)"
            pv = (a["p_vs_drift_floor"] if a.get("p_vs_drift_floor") is not None
                  else a["p_vs_coinflip"])
            print(f"  ARTEFACT     {a['pair']:<10}{a['accuracy'] * 100:6.1f}%  "
                  f"n={a['n']:<5} p={pv:.2g}   {mark}")
    else:
        print("  ARTEFACT     no identical-phone pair present in this corpus")
    b = v.get("block")
    if b:
        print(f"  BLOCK        {b['disjoint_in_time']}/{b['unit_pairs']} unit pairs "
              f"never overlap in time (block fraction {b['block_fraction']}, "
              f"span {b['span_seconds']}s)")
    else:
        print("  BLOCK        recording order unreadable (mtimes flat or missing)")
    s = v["signal"]
    if s["accuracy"] is not None:
        print(f"  SIGNAL       {s['accuracy'] * 100:.2f}% vs chance "
              f"{v['chance'] * 100:.2f}%  (n={s['n']}, p={s['p_vs_chance']:.2g}, "
              f"{s['how']})")
    else:
        print(f"  SIGNAL       not measurable ({s['how']})")
    lk = v["leakage"]
    if lk.get("gap") is not None:
        print(f"  LEAKAGE      random split {lk['random_split_accuracy'] * 100:.2f}% "
              f"vs honest {lk['honest_split_accuracy'] * 100:.2f}%  -> gap "
              f"{lk['gap'] * 100:+.2f} points")
    else:
        print(f"  LEAKAGE      {lk.get('why')}")
    print(f"  VERDICT      >>> {v['verdict']} <<<")
    for r in v["reasons"]:
        print(f"      - {r}")
    if v.get("prescription"):
        print(f"      Rx: {v['prescription']}")


def main():
    ap = argparse.ArgumentParser(
        description="MODEH -- the Master Modeler's corpus-teachability organ")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--scratch", default=os.environ.get("MODEH_SCRATCH", ""))
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    j.add_argument("corpus", nargs="*")
    j.add_argument("--all", action="store_true")
    u = sub.add_parser("units")
    u.add_argument("corpus")
    f = sub.add_parser("forget")
    f.add_argument("corpus", nargs="+")
    f.add_argument("--files", action="store_true")
    sub.add_parser("contamination")
    sub.add_parser("list")
    a = ap.parse_args()

    prio = _below_normal()
    reg = load_registry(a.scratch)

    if a.cmd == "list":
        for c in reg["corpora"]:
            print(f"{c['id']:<16} {c['root']}")
            print(f"{'':<16} {c['what']}")
        return

    ear = Ear()
    if not a.json:
        print(f"[MODEH] priority={prio}  ear={ear.desc}")
        print("[MODEH] read-only: opens wav + json, writes only under runs/\n")

    if a.cmd == "judge":
        ids = ([c["id"] for c in reg["corpora"]]
               if (a.all or not a.corpus) else a.corpus)
        out, used = [], []
        for cid in ids:
            spec = next((c for c in reg["corpora"] if c["id"] == cid), None)
            if spec is None:
                print(f"unknown corpus id: {cid}", file=sys.stderr)
                continue
            v = judge(spec, reg, ear, verbose=not a.json)
            out.append(v)
            used.append(cid)
            if not a.json:
                print_report(v)
        RUNS.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = RUNS / f"judge-{stamp}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("\n" + "=" * 78)
            print(f"{'corpus':<16}{'MODEH verdict':<20}{'n_eff':<8}{'signal':<10}"
                  f"{'what the human record already said'}")
            for v, cid in zip(out, used):
                spec = next(c for c in reg["corpora"] if c["id"] == cid)
                s = v["signal"]["accuracy"]
                sig = ("%.1f%%" % (s * 100)) if s is not None else "-"
                print(f"{v['id']:<16}{v['verdict']:<20}"
                      f"{str(v.get('n_eff_median')):<8}{sig:<10}"
                      f"{spec.get('expect', '')[:46]}")
            print(f"\nwritten: {path}")
        return

    if a.cmd == "units":
        spec = next((c for c in reg["corpora"] if c["id"] == a.corpus), None)
        if spec is None:
            raise SystemExit(f"unknown corpus id: {a.corpus}")
        v = judge(spec, reg, ear, verbose=not a.json)
        if a.json:
            print(json.dumps(v["per_unit"], ensure_ascii=False, indent=2))
        else:
            print(f"\n{v['id']} -- per unit")
            print(f"{'unit':<8}{'clips':>6}{'cosine':>9}{'n_eff':>8}{'twins':>8}")
            for un in sorted(v["per_unit"], key=lambda x: -x["k"]):
                print(f"{un['unit']:<8}{un['k']:>6}{str(un['within_cosine']):>9}"
                      f"{un['n_eff']:>8}{un['twin_frac']:>8}")
        return

    if a.cmd == "forget":
        cmd_forget(a, reg, ear)
        return
    if a.cmd == "contamination":
        cmd_contamination(a, reg, ear)
        return


if __name__ == "__main__":
    main()
