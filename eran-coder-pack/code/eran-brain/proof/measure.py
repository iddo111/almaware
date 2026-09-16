"""measure.py — THE EXAMINER. Labels live HERE and nowhere else.

Labels come from corpus filenames (aa_t00_0.wav -> class 'aa'); they are
provenance and evaluation keys ONLY and never cross into the organism.

Scoring:
  (a) DEV split — a deterministic 20% of train (sha1(filename) % 5 == 0),
      used by the school's mastery gate. Prototypes are mapped to classes by
      majority vote on train-minus-dev, then dev items are classified by
      nearest prototype (effective attraction — the organism as it behaves).
  (b) the 132-item HELDOUT exam — reported results only, never trained on,
      never gated on. The vault is proof/heldout-vault/.

The FIRST line printed is always chance (4.545%) + the proven baselines —
the eran0/GROUND law: the floor of honesty comes before any achievement.

Embodies: the fixed, honest, cheap-to-consult judge (the ant-farm method).
"""
import argparse
import datetime
import gzip
import hashlib
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))

import genome                                     # noqa: E402
from ears import Ears                             # noqa: E402

HELDOUT_DIR = genome.HELDOUT_VAULT

_VEC_CACHE = {}        # (path, dim, pooling, repr) -> vector


def print_baselines_first():
    print("[examiner] chance = 4.545% (22 classes). proven baselines "
          "(132-item heldout, ant farm 2026): "
          "duration-only 5.30% | random-real-frames 46.21% | "
          "raw speech-span 53.79% | raw+loudest60 68.94%")


# ---------------------------------------------------------------- labels
def label_of(name):
    """aa_t00_0.wav -> 'aa'. Filenames are the examiner's key, only his."""
    return os.path.basename(name).split("_")[0]


def session_of(name):
    """aa_t00_0.wav -> 't00'. The RECORDING SESSION, not the class.

    The corpus is six train sessions (t00..t05) and two unseen heldout
    sessions (h00, h01), 66 files each. A session is one sitting: same room,
    same mouth, same distance — so two files from one session share far more
    than two files of the same class from different sessions.
    """
    parts = os.path.basename(name).split("_")
    return parts[1] if len(parts) >= 3 else ""


def is_dev(name):
    """Dev = a WHOLE recording session held out. Never a random file.

    SCAR, measured 2026-08-21: this used to split by sha1 of the FILENAME,
    which scattered every session across both sides of the split. A model
    could memorise a session and be scored on that same session, so every
    dev number in this estate ran about **14 points optimistic**. The
    sharpest evidence: a covariance arm scored dev 88.64% and heldout
    60.35% — a 28-point collapse, which is exactly what session
    memorisation looks like.

    Holding out a whole session also makes dev mirror the real exam, whose
    two sessions (h00, h01) the organism has never heard. A dev split that
    is easier than the exam is not a dev split; it is a flatterer.

    Selection is by the session's own number, so the same session always
    lands on the same side, and rotating genome.DEV_SESSION_PICK over
    0..DEV_SESSION_MOD-1 gives leave-one-session-out cross-validation for
    free. Filenames without a session (synthetic fixtures) fall back to the
    old hash so tests and toy corpora keep working.
    """
    base = os.path.basename(name)
    sess = session_of(base)
    digits = "".join(c for c in sess if c.isdigit())
    if digits:
        return int(digits) % genome.DEV_SESSION_MOD == genome.DEV_SESSION_PICK
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return int(h, 16) % genome.DEV_FRAC_MOD == 0


def sessions_in(folder):
    """Sorted unique recording sessions in a folder — for LOSO loops."""
    return sorted({session_of(n) for n in os.listdir(folder)
                   if n.endswith(".wav")} - {""}) if os.path.isdir(folder) else []


def wavs_in(folder):
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder))
            if n.endswith(".wav")]


# ---------------------------------------------------------------- vectors
def _vec(ears, path):
    key = (path, ears.dim, ears.pooling, ears.repr)
    if key not in _VEC_CACHE:
        _VEC_CACHE[key] = ears.utterance(path)
    return _VEC_CACHE[key]


# ------------------------------------------------------- prototype mapping
def fit_proto_labels(brain, ears, fit_paths):
    """Majority vote: which class does each prototype answer for?"""
    votes = {}
    for p in fit_paths:
        vec = _vec(ears, p)
        idx, _, _ = brain.nearest(vec)
        if idx is None:
            continue
        votes.setdefault(idx, {})
        c = label_of(p)
        votes[idx][c] = votes[idx].get(c, 0) + 1
    return {i: max(v.items(), key=lambda kv: kv[1])[0]
            for i, v in votes.items()}


def classify(brain, proto_label, vec):
    idx, _, _ = brain.nearest(vec)
    return proto_label.get(idx) if idx is not None else None


# ------------------------------------------------------------- dev scoring
def dev_scores(brain, ears, train_dir=None, units=None):
    """One pass over the dev split -> per-unit sens/spec + dev top1.

    `units` restricts the exam universe (fit AND dev) to those units — the
    school's gate passes its EXPOSURE (mastered + current), because a child
    can only be examined against sounds the curriculum has let it hear; each
    new unit must be discriminated from everything already learned. With
    units=None the exam is global over all 22 (the reported number).

    The school consumes ONLY the numbers returned here.
    """
    train_dir = train_dir or genome.FOOD_TRAIN
    all_train = wavs_in(train_dir)
    if units is not None:
        allowed = set(units)
        all_train = [p for p in all_train if label_of(p) in allowed]
    fit = [p for p in all_train if not is_dev(p)]
    dev = [p for p in all_train if is_dev(p)]
    proto_label = fit_proto_labels(brain, ears, fit)
    truths, preds = [], []
    for p in dev:
        truths.append(label_of(p))
        preds.append(classify(brain, proto_label, _vec(ears, p)))
    per_unit = {}
    exam_units = sorted(set(units)) if units is not None else genome.CLASSES
    for u in exam_units:
        tp = sum(1 for t, y in zip(truths, preds) if t == u and y == u)
        pos = sum(1 for t in truths if t == u)
        tn = sum(1 for t, y in zip(truths, preds) if t != u and y != u)
        neg = sum(1 for t in truths if t != u)
        per_unit[u] = {
            # no positives in dev -> sens 0.0 (fail-closed: cannot certify)
            "sens": tp / pos if pos else 0.0,
            # no negatives in the universe (first unit) -> vacuously 1.0
            "spec": tn / neg if neg else 1.0,
            "n_pos": pos,
        }
    top1 = (sum(1 for t, y in zip(truths, preds) if t == y) / len(truths)
            if truths else 0.0)
    return {"per_unit": per_unit, "dev_top1": top1,
            "dev_items": len(dev), "fit_items": len(fit),
            "labeled_protos": len(proto_label)}


# --------------------------------------------------------- heldout scoring
def heldout_exam(brain, ears, train_dir=None, heldout_dir=None):
    """The reported exam. Mapping fit on ALL train; heldout never trained on."""
    train_dir = train_dir or genome.FOOD_TRAIN
    heldout_dir = heldout_dir or HELDOUT_DIR
    proto_label = fit_proto_labels(brain, ears, wavs_in(train_dir))
    held = wavs_in(heldout_dir)
    per_class = {u: {"n": 0, "correct": 0} for u in genome.CLASSES}
    correct = 0
    for p in held:
        t = label_of(p)
        y = classify(brain, proto_label, _vec(ears, p))
        if t not in per_class:
            per_class[t] = {"n": 0, "correct": 0}
        per_class[t]["n"] += 1
        if y == t:
            per_class[t]["correct"] += 1
            correct += 1
    top1 = correct / len(held) if held else 0.0
    return {"heldout_top1": top1, "heldout_items": len(held),
            "per_class": {u: (c["correct"] / c["n"] if c["n"] else None)
                          for u, c in per_class.items()}}


# ------------------------------------------------------------ full report
def _latest_metrics():
    if not os.path.exists(genome.METRICS_FILE):
        return {}
    last = None
    with open(genome.METRICS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    try:
        return json.loads(last) if last else {}
    except ValueError:
        return {}


def full_exam(write=True):
    from brain import Brain
    print_baselines_first()
    if not os.path.exists(genome.BRAIN_FILE):
        print("[examiner] no brain file — the organism has not lived. FAIL.")
        return None
    brain = Brain.load()
    ears = Ears(exam=True)
    dev = dev_scores(brain, ears)
    held = heldout_exam(brain, ears)
    m = _latest_metrics()
    t1 = held["heldout_top1"]
    verdict = {
        "beats_chance": t1 > genome.BASELINES["chance"],
        "beats_duration_floor": t1 > genome.BASELINES["duration_only_floor"],
        "beats_random_real_frames":
            t1 > genome.BASELINES["random_real_frames_codebook"],
        "reaches_raw_speech_span":
            t1 > genome.BASELINES["raw_features_speech_span"],
        "reaches_raw_loudest60":
            t1 > genome.BASELINES["raw_features_loudest60"],
    }
    # Exposure. The 22-class number is the honest headline, but a child who
    # has only ever been played 3 of the 22 sounds cannot answer for the other
    # 19 — its ceiling is the fraction it has heard. Reporting both keeps the
    # headline honest AND makes real progress visible while the ladder climbs.
    exposed = []
    try:
        with open(genome.CURRICULUM_FILE, "r", encoding="utf-8") as f:
            c = json.load(f)
        exposed = sorted(set(c.get("mastered", []))
                         | set(c.get("pending_retention", {}))
                         | ({c["unit"]} if c.get("unit") else set()))
    except (OSError, ValueError, KeyError):
        pass
    pc = held["per_class"]
    hits = [pc[u] for u in exposed if pc.get(u) is not None]
    exposure = {
        "units_heard": exposed,
        "exposure_ceiling": (len(exposed) / len(genome.CLASSES)
                             if exposed else None),
        "top1_on_heard": (sum(hits) / len(hits)) if hits else None,
    }

    result = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "beats": brain.beat, "utterances_heard": brain.heard,
        "exposure": exposure,
        "prototypes": len(brain.protos), "mass": brain.total_mass(),
        "heldout_top1": t1, "heldout_items": held["heldout_items"],
        "per_class": held["per_class"],
        "dev_top1": dev["dev_top1"], "dev_sens_spec": dev["per_unit"],
        "baselines": genome.BASELINES,
        "chemistry_snapshot": {k: m.get(k) for k in
                               ("da", "ach", "ne", "sht", "oxt")},
        "verdict_honest": verdict,
    }
    print(f"[examiner] heldout top1 = {t1:.2%} on {held['heldout_items']} "
          f"items | dev top1 = {dev['dev_top1']:.2%} | "
          f"protos = {len(brain.protos)}")
    if exposure["top1_on_heard"] is not None:
        print(f"[examiner] heard {len(exposed)}/{len(genome.CLASSES)} sounds "
              f"so far ({', '.join(exposed)}); on those: "
              f"{exposure['top1_on_heard']:.2%} "
              f"(exposure ceiling {exposure['exposure_ceiling']:.2%})")
    for bar, ok in verdict.items():
        print(f"[examiner]   {bar}: {'PASS' if ok else 'FAIL'}")
    if write:
        os.makedirs(genome.RESULTS_DIR, exist_ok=True)
        out = os.path.join(genome.RESULTS_DIR, "ERANB-001.json")
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        os.replace(tmp, out)
        print(f"[examiner] wrote {out}")
    return result


def retention_exam(unit):
    """The 12-hour delayed re-exam for one unit (numbers only, printed+saved)."""
    from brain import Brain
    print_baselines_first()
    brain = Brain.load()
    ears = Ears(exam=True)
    dev = dev_scores(brain, ears)
    s = dev["per_unit"].get(unit)
    if s is None:
        print(f"[examiner] unknown unit: {unit}")
        return None
    ok = s["sens"] >= genome.SENS and s["spec"] >= genome.SPEC
    print(f"[examiner] retention {unit}: sens={s['sens']:.3f} "
          f"spec={s['spec']:.3f} -> {'PASS' if ok else 'FAIL'}")
    os.makedirs(genome.RESULTS_DIR, exist_ok=True)
    out = os.path.join(genome.RESULTS_DIR,
                       f"retention-{unit}-{datetime.date.today().isoformat()}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                   "unit": unit, "sens": s["sens"], "spec": s["spec"],
                   "pass": ok}, f, indent=1)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="the examiner")
    ap.add_argument("--retention", metavar="UNIT",
                    help="run the 12h delayed retention re-exam for one unit")
    args = ap.parse_args()
    if args.retention:
        retention_exam(args.retention)
    else:
        full_exam()
