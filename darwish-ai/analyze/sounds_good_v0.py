#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sounds_good_v0.py -- "does it sound good to a human ear, in Darwish's world?"  0..100

לזכרו של לָאוֹר ז״ל.

                  *** THIS WHOLE FILE IS A HYPOTHESIS (v0) ***

It is a transparent, hand-weighted blend of numbers that darwish_math.py
MEASURED from audio. The blend -- which numbers, which anchors, which weights --
is a GUESS about what a human ear likes. It becomes a "reliable" score only after
it agrees with Iddo's ear on blind pairs (BLIND-EAR-PROTOCOL.md, next to this
file). Until then: never steer training with it, never call a render "good"
because of it, never report it without the word HYPOTHESIS.

NOT A SECOND JUDGE
------------------
judge/judge.py (owner: claude-cli-SONNET-darwishjudge) is untouched and not
imported. judge.py scores one sample against a scale YOU name; this file places an
already-analysed clip against the MEASURED Darwish corpus profile. It decodes no
audio at all: its only input is darwish_math.py's JSON in out/. That judge was
calibrated against Iddo's taps and BENCHED (kappa 0.0, accuracy 0.09) -- a
warning that a sensible-looking blend can still miss his ear completely.

FIVE COMPONENTS (each 0..1), blended by the named weights below
  profile     distance to the Darwish window profile, feature by feature,
              averaged inside each group (rhythm/tonality/melody/harmony/energy),
              then across groups
  scale       in-scale note share + how well the tonic-relative pitch-class
              hierarchy correlates with Darwish's ("tonal relations")
  groove      tempo inside Darwish's band + pulse strength + onsets on the 16th grid
  consonance  vertical tension no worse than Darwish's own 95th percentile +
              vertical interval-class colour vs Darwish's
  form        on a clip this is ENERGY sanity: loudness in band, short-term
              dynamics neither flat nor cliffed, bass weight above Darwish's floor.
              Whole-track form (drops, sections) cannot exist in a 60 s clip; it
              is reported for long files as a diagnostic and never scored.

FAIRNESS RULES (why the Darwish sanity number is not circular)
  * Each Darwish track is scored against a profile built from the OTHER half of
    the corpus (2-fold split by filename hash), never against itself. The
    in-sample number is reported next to it so the size of the circularity shows.
  * Everything is scored per 60 s window, the same unit for real and ours. Real
    tracks have up to 12 windows, renders usually 1, and a median over 12 windows
    is calmer than one window -- so the PRIMARY Darwish number is ONE
    seeded-random window per track.
  * Inclusion = corpus_profile.json's rules, applied by calling darwish_math's own
    beat_ok() and _dedupe() (the filename curation already happened at analyse time).

USAGE
  python sounds_good_v0.py                           # score out/ -> out/sounds_good_v0.json
  python sounds_good_v0.py --one out/ours__NAME.json # explain one analysed clip
A NEW render: analyse it first, on eran2 at nice 19 (not the PC):
  python darwish_math.py analyze --kind ours --list list.txt --out out
then bring the JSON into out/ and run --one on it.

Compute: JSON only, one BLAS thread, BELOW_NORMAL on Windows / nice 19 on Linux.
No subprocess, no audio device, no network.
"""
from __future__ import annotations

import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import darwish_math as dm  # noqa: E402  -- the measurements, inclusion rules and stats, reused

SCORE_VERSION = "sounds_good_v0 (2026-09-15)"
LABEL = "HYPOTHESIS v0 -- a hand-weighted guess, NOT validated against Iddo's ear"

# =============================================================================
# THE BLEND -- five weights, sum 1.0. Every one of them is a HYPOTHESIS.
# =============================================================================
W_PROFILE = 0.35     # "in Darwish's world" is the order itself and the widest evidence (~50 features); held to a third because distance alone did NOT separate real Darwish from ours (capped |z| 0.87 vs 1.08, overlapping)
W_SCALE = 0.20       # wrong notes against the mode are what a listener hears first in modal psytrance ("no scale" was Iddo's verdict on ARRANGED); below judge.py's 0.30 because the audio key/mode label is weak (median margin 0.03)
W_GROOVE = 0.20      # psytrance lives on a locked 4/4 pulse; tempo/grid are the best-validated estimators (BPM 21/21 synthetic, 0/46 renders wrong after the fix)
W_CONSONANCE = 0.15  # harshness is audible, but Darwish himself sits at ~35% dissonant vertical intervals, so only going BEYOND him is punished
W_FORM = 0.10        # least measurable on a 60 s clip -- here it only catches broken energy (too quiet/loud, flat or cliffed dynamics, no bass)
WEIGHTS = {"profile": W_PROFILE, "scale": W_SCALE, "groove": W_GROOVE,
           "consonance": W_CONSONANCE, "form": W_FORM}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# =============================================================================
# PROFILE component
# =============================================================================
PROFILE_GROUPS = ("rhythm", "tonality", "melody", "harmony", "energy")  # equal weight each: nothing measured says one group matters more to the ear
ROBUST_SIGMAS_IN_P5_P95 = 3.29   # a normal distribution's 5th-95th percentile span is 3.29 sigma; robust to skewed features like low_share
PROFILE_Z_FREE = 1.0             # inside +-1 robust sigma (the central ~68% of Darwish minutes) a feature costs nothing
PROFILE_Z_ZERO = 4.0             # 4 robust sigmas out a feature scores 0 -- the same cap darwish_math compare uses
PROFILE_MIN_WINDOWS = 20         # same minimum as darwish_math compare: fewer reference windows = no z
PROFILE_EXCLUDE = {              # MEASURED reasons (README of the 2026-09-15 run); darwish_math.NOT_Z is excluded too
    "rhythm.rolling_bass_index": "barely works on real mixes: corpus median 1.06 vs 2.23 on a clean synthetic loop",
    "rhythm.four_on_floor_share": "16th-slot kick detection leaks bass (kick-on-beat share reads 0.28)",
    "rhythm.kick_quarter_share": "same leaky kick-slot detection",
    "rhythm.kick_offquarter_hit_rate": "same leaky kick-slot detection",
    "rhythm.offbeat_bass_share": "same slot grid as the rolling-bass index",
    "rhythm.kicks_per_s": "kick-band onset count, also fed by the bass",
    "rhythm.swing_ms": "duplicate of swing_pct in milliseconds",
    "harmony.chord_change_per_bar_audio": "audio threshold too strict: 0.03/bar vs 2.24 from notes",
    "harmony.poly_max": "saturates at the transcriber's 5-voice cap",
    "melody.bass_pitch_p5": "transcriber range edge, not music",
    "melody.bass_pitch_p95": "transcriber range edge (corpus std 0.31) -- z explodes on nothing",
    "melody.lead_pitch_p5": "transcriber range floor (C3), not music",
    "energy.rms_dbfs": "duplicate of energy.lufs",
}

# =============================================================================
# SCALE component
# =============================================================================
SCALE_SUB = {"in_scale_share": 0.5, "tonal_hierarchy": 0.5}  # equal: one says "wrong notes", the other "wrong centre of gravity"; neither is validated
SCALE_SHARE_ZERO = 0.65          # MEASURED by simulation 2026-09-15: a uniform random 12-tone stream of ~300 notes scores 0.643 best-of-84-templates share (0.626 at 600 notes)
TONAL_HIERARCHY_ZERO_R = 0.0     # Pearson 0 = no relation to Darwish's tonic-relative pitch-class weights (tonic 0.243, fifth 0.161, ...)
# full marks for both = the reference corpus's own median window (measured at run time)

# =============================================================================
# GROOVE component
# =============================================================================
GROOVE_SUB = {"tempo_in_band": 1 / 3, "pulse": 1 / 3, "grid": 1 / 3}  # equal: no measurement ranks them
BPM_FALLOFF = 12.0               # 12 BPM outside Darwish's p5..p95 band (~128-147) = no longer the genre's tempo; HYPOTHESIS
PULSE_ZERO = 0.0                 # beat autocorrelation strength 0 = no pulse at all
GRID_TOL_MS = 20.0               # the tolerance grid_regularity_20ms was measured with
# grid zero = CHANCE: uniformly random onsets land within +-20 ms of a 16th with probability 40 ms / 16th length (0.37 at 140 BPM)

# =============================================================================
# CONSONANCE component
# =============================================================================
CONSONANCE_SUB = {"tension_not_beyond_darwish": 0.5, "interval_colour": 0.5}  # equal; neither validated
TENSION_ZERO = 0.70              # darwish_math IC_TENSION of a major second: a texture whose AVERAGE interval is a whole-tone clash scores 0
INTERVAL_COLOUR_ZERO_R = 0.0     # Pearson 0 against Darwish's mean vertical interval-class histogram = unrelated colour

# =============================================================================
# FORM (energy sanity on a clip)
# =============================================================================
FORM_SUB = {"loudness_in_band": 1 / 3, "dynamics_sane": 1 / 3, "bass_weight": 1 / 3}
LOUDNESS_FALLOFF_LU = 6.0        # 6 LU outside Darwish's window p5..p95 = clearly mis-levelled (a 2x-4x loudness step)
DYN_FLAT_ZERO_DB = 0.0           # 0 dB of 1 s RMS movement = a dead-flat block
DYN_CLIFF_FALLOFF_DB = 15.0      # 15 dB beyond Darwish's p95 movement = dropouts / cliffs (step96000 reads 29.7 dB)
BASS_ZERO_SHARE = 0.0            # no energy under 250 Hz at all
LONG_FILE_S = 300.0              # only files this long get the whole-track form diagnostic (not scored)

CONTROL_RX = re.compile(r"^human\d$")
CATEGORIES = [("transformer checkpoint", re.compile(r"step\d+")),
              ("mode / rescale preview", re.compile(r"darwish-(mode|rescale-excerpt)-")),
              ("Chai / psy_render / other render", re.compile(r"."))]

# Iddo's ONE blind ordinal judgement on record (darwish-ab, 2026-09-05 08:54): best "psy v4", worst "psy v2",
# of v2/v3/v4 -> a complete order of 3. Blind clips A/B/C.mp3 are byte-identical to hub/darwish_v2/3/4.mp3
# (SHA1 verified 2026-09-15). The 24 s cuts machine1/2/3 are the same three renders per darwish_ab2.py's key.
BLIND_ORDER_20260905 = [
    ("darwish_v4.mp3", "darwish_v3.mp3"), ("darwish_v4.mp3", "darwish_v2.mp3"), ("darwish_v3.mp3", "darwish_v2.mp3"),
    ("machine3.mp3", "machine2.mp3"), ("machine3.mp3", "machine1.mp3"), ("machine2.mp3", "machine1.mp3"),
]


# ============================================================== small pieces

def _finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(float(v))


def ramp(v, zero, full):
    """0 at `zero`, 1 at `full`, linear between, clipped. Either direction."""
    if not (_finite(v) and _finite(zero) and _finite(full)):
        return None
    if full == zero:
        return 1.0 if v >= full else 0.0
    return float(min(1.0, max(0.0, (v - zero) / (full - zero))))


def band(v, lo, hi, zero_lo, zero_hi):
    """1 inside [lo, hi]; linear down to 0 at zero_lo (below) or zero_hi (above)."""
    if not (_finite(v) and _finite(lo) and _finite(hi)):
        return None
    if v < lo:
        return ramp(v, zero_lo, lo) if _finite(zero_lo) else 1.0
    if v > hi:
        return ramp(v, zero_hi, hi) if _finite(zero_hi) else 1.0
    return 1.0


def wmean(parts, weights):
    """Weighted mean over the parts that exist; weights renormalised and reported."""
    have = {k: v for k, v in parts.items() if v is not None}
    if not have:
        return None, {}
    ws = sum(weights[k] for k in have)
    return float(sum(weights[k] * v for k, v in have.items()) / ws), {k: weights[k] / ws for k in have}


def dist(vals):
    v = np.asarray([x for x in vals if _finite(x)], float)
    if v.size == 0:
        return {"n": 0}
    q = np.percentile(v, [5, 25, 50, 75, 95])
    return {"n": int(v.size), "mean": float(v.mean()), "std": float(v.std()), "min": float(v.min()),
            "p5": float(q[0]), "p25": float(q[1]), "p50": float(q[2]), "p75": float(q[3]), "p95": float(q[4]),
            "max": float(v.max())}


def auc(pos, neg):
    """P(score of a random `pos` > score of a random `neg`), ties count half."""
    pos = [p for p in pos if _finite(p)]
    neg = [n for n in neg if _finite(n)]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _h(name):
    return int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16)


def fold_of(name):
    return _h(name) % 2


# ============================================================== reference

def build_ref(tracks):
    """Window-level reference stats, every window weighted 1/K so each track counts
    once -- the same weighting as corpus_profile.json."""
    vals, wts, vecs = {}, {}, {}
    for r in tracks:
        ws = r.get("windows") or []
        if not ws:
            continue
        wt = 1.0 / len(ws)
        for w in ws:
            for k, v in dm.flat_window(w).items():
                if isinstance(v, list):
                    vecs.setdefault(k, []).append((np.asarray(v, float), wt))
                else:
                    vals.setdefault(k, []).append(v)
                    wts.setdefault(k, []).append(wt)
    stats = {k: dm._stats(vals[k], wts[k]) for k in vals}
    mv = {}
    for k, pairs in vecs.items():
        if len({a.size for a, _ in pairs}) == 1:
            mv[k] = np.average(np.array([a for a, _ in pairs]), axis=0, weights=[w for _, w in pairs])
    ref = {"stats": stats, "vectors": mv, "n_tracks": len(tracks)}
    # derived per-window correlations, so their "full marks" anchor is the reference median
    hier, colour, hw, cw = [], [], [], []
    for r in tracks:
        ws = r.get("windows") or []
        for w in ws:
            a = _hier_r(w, ref)
            b = _colour_r(w, ref)
            if a is not None:
                hier.append(a)
                hw.append(1.0 / len(ws))
            if b is not None:
                colour.append(b)
                cw.append(1.0 / len(ws))
    stats["derived.tonal_hierarchy_r"] = dm._stats(hier, hw) if hier else None
    stats["derived.interval_colour_r"] = dm._stats(colour, cw) if colour else None
    # whole-track form stats (diagnostic only)
    tv = {}
    for r in tracks:
        for k, v in dm.flat_track(r).items():
            tv.setdefault(k, []).append(v)
    ref["track_stats"] = {k: dm._stats(v) for k, v in tv.items()}
    return ref


def _p(ref, key, q):
    st = ref["stats"].get(key)
    return st.get(q) if st else None


def _hier_r(w, ref):
    v = (w.get("tonality") or {}).get("pc_hist_rel_tonic")
    m = ref["vectors"].get("tonality.pc_hist_rel_tonic")
    if not v or m is None or len(v) != m.size or not np.sum(v) > 0:
        return None
    return dm._corr(v, m)


def _colour_r(w, ref):
    v = (w.get("harmony") or {}).get("vertical_ic_hist")
    m = ref["vectors"].get("harmony.vertical_ic_hist")
    if not v or m is None or len(v) != m.size or not np.sum(v) > 0:
        return None
    return dm._corr(v, m)


# ============================================================== components

def comp_profile(w, ref):
    flat = dm.flat_window(w)
    per_group, devs = {}, []
    for k, v in flat.items():
        if isinstance(v, list) or k in dm.NOT_Z or k in PROFILE_EXCLUDE:
            continue
        st = ref["stats"].get(k)
        if not st or st["n"] < PROFILE_MIN_WINDOWS:
            continue
        sig = (st["p95"] - st["p5"]) / ROBUST_SIGMAS_IN_P5_P95
        if not sig > 0:
            continue
        z = (v - st["p50"]) / sig
        s = 1.0 - min(1.0, max(0.0, abs(z) - PROFILE_Z_FREE) / (PROFILE_Z_ZERO - PROFILE_Z_FREE))
        g = k.split(".")[0]
        per_group.setdefault(g, []).append(s)
        devs.append({"feature": k, "value": v, "darwish_p50": st["p50"], "robust_z": z})
    groups = {g: float(np.mean(per_group[g])) for g in PROFILE_GROUPS if g in per_group}
    score = float(np.mean(list(groups.values()))) if groups else None
    devs.sort(key=lambda d: -abs(d["robust_z"]))
    return {"score": score, "parts": {"by_group": groups, "n_features": len(devs)}, "top_deviations": devs[:6]}


def comp_scale(w, ref):
    t = w.get("tonality") or {}
    share = t.get("scale_share_notes_best_any_template")
    hr = _hier_r(w, ref)
    parts = {"in_scale_share": ramp(share, SCALE_SHARE_ZERO, _p(ref, "tonality.scale_share_notes_best_any_template", "p50")),
             "tonal_hierarchy": ramp(hr, TONAL_HIERARCHY_ZERO_R, _p(ref, "derived.tonal_hierarchy_r", "p50"))}
    score, used = wmean(parts, SCALE_SUB)
    return {"score": score, "parts": parts | {"raw_in_scale_share": share, "raw_tonal_hierarchy_r": hr,
                                               "key_mode_label": f'{t.get("tonic_name")} {t.get("mode")}',
                                               "key_mode_margin": t.get("confidence_margin")}, "weights_used": used}


def comp_groove(w, ref):
    r = w.get("rhythm") or {}
    if not r.get("grid_found"):
        parts = {"tempo_in_band": 0.0, "pulse": ramp(r.get("beat_strength"), PULSE_ZERO, _p(ref, "rhythm.beat_strength", "p50")),
                 "grid": 0.0}
        score, used = wmean(parts, GROOVE_SUB)
        return {"score": score, "parts": parts | {"note": "no beat grid found in this window"}, "weights_used": used}
    bpm = r.get("bpm")
    lo, hi = _p(ref, "rhythm.bpm", "p5"), _p(ref, "rhythm.bpm", "p95")
    chance = GRID_TOL_MS * 2 / (60000.0 / bpm / 4.0) if _finite(bpm) and bpm > 0 else None
    full_grid = _p(ref, "rhythm.grid_regularity_20ms", "p50")
    parts = {"tempo_in_band": band(bpm, lo, hi, (lo or 0) - BPM_FALLOFF, (hi or 0) + BPM_FALLOFF),
             "pulse": ramp(r.get("beat_strength"), PULSE_ZERO, _p(ref, "rhythm.beat_strength", "p50")),
             "grid": ramp(r.get("grid_regularity_20ms"), chance, full_grid)
             if _finite(chance) and _finite(full_grid) and full_grid > chance else None}
    score, used = wmean(parts, GROOVE_SUB)
    return {"score": score, "parts": parts | {"raw_bpm": bpm, "raw_beat_strength": r.get("beat_strength"),
                                               "raw_grid_regularity_20ms": r.get("grid_regularity_20ms"),
                                               "grid_chance_level": chance}, "weights_used": used}


def comp_consonance(w, ref):
    h = w.get("harmony") or {}
    ten = h.get("tension_index")
    p95 = _p(ref, "harmony.tension_index", "p95")
    cr = _colour_r(w, ref)
    parts = {"tension_not_beyond_darwish": (1.0 if _finite(ten) and _finite(p95) and ten <= p95 else ramp(ten, TENSION_ZERO, p95)),
             "interval_colour": ramp(cr, INTERVAL_COLOUR_ZERO_R, _p(ref, "derived.interval_colour_r", "p50"))}
    score, used = wmean(parts, CONSONANCE_SUB)
    return {"score": score, "parts": parts | {"raw_tension_index": ten, "darwish_tension_p95": p95,
                                               "raw_interval_colour_r": cr}, "weights_used": used}


def comp_form(w, ref):
    e = w.get("energy") or {}
    lufs, rng, low = e.get("lufs"), e.get("rms_1s_range_db_p95_p10"), e.get("low_share")
    l5, l95 = _p(ref, "energy.lufs", "p5"), _p(ref, "energy.lufs", "p95")
    r5, r95 = _p(ref, "energy.rms_1s_range_db_p95_p10", "p5"), _p(ref, "energy.rms_1s_range_db_p95_p10", "p95")
    b5 = _p(ref, "energy.low_share", "p5")
    parts = {"loudness_in_band": band(lufs, l5, l95, (l5 or 0) - LOUDNESS_FALLOFF_LU, (l95 or 0) + LOUDNESS_FALLOFF_LU),
             "dynamics_sane": band(rng, r5, r95, DYN_FLAT_ZERO_DB, (r95 or 0) + DYN_CLIFF_FALLOFF_DB),
             "bass_weight": (1.0 if _finite(low) and _finite(b5) and low >= b5 else ramp(low, BASS_ZERO_SHARE, b5))}
    score, used = wmean(parts, FORM_SUB)
    return {"score": score, "parts": parts | {"raw_lufs": lufs, "raw_rms_1s_range_db": rng, "raw_low_share": low},
            "weights_used": used}


COMPONENTS = {"profile": comp_profile, "scale": comp_scale, "groove": comp_groove,
              "consonance": comp_consonance, "form": comp_form}


def score_window(w, ref):
    comps = {k: f(w, ref) for k, f in COMPONENTS.items()}
    total, used = wmean({k: c["score"] for k, c in comps.items()}, WEIGHTS)
    return {"start_s": w.get("start_s"), "score": None if total is None else 100.0 * total,
            "components": {k: c["score"] for k, c in comps.items()}, "weights_used": used,
            "detail": {k: {kk: vv for kk, vv in c.items() if kk != "score"} for k, c in comps.items()}}


def form_full_diagnostic(rec, ref):
    """Whole-track form vs the reference tracks. NOT part of the score."""
    t = rec.get("track") or {}
    if (t.get("duration_s") or 0) < LONG_FILE_S or t.get("form_comparable_to_full_tracks") is False:
        return None
    ft = dm.flat_track(rec)
    out = {}
    for k in ("form.drops_per_10min", "form.section_len_median_s", "form.sections_per_min"):
        st = ref["track_stats"].get(k)
        if st and k in ft:
            out[k] = {"value": ft[k], "darwish_p5": st["p5"], "darwish_p95": st["p95"],
                      "inside_p5_p95": bool(st["p5"] <= ft[k] <= st["p95"])}
    return out or None


def score_record(rec, ref):
    wins = [score_window(w, ref) for w in (rec.get("windows") or [])]
    return [w for w in wins if w["score"] is not None]


def _median_window(wins):
    s = sorted(wins, key=lambda w: w["score"])
    return s[len(s) // 2]


# ============================================================== corpus

def load_corpus(out_dir):
    recs = dm._load_out(out_dir, "darwish")
    music = sorted([r for r in recs if dm.beat_ok(r)], key=lambda r: r["file"])
    kept, dups = dm._dedupe(music)
    return kept, {"n_analysed": len(recs), "n_low_beat_dropped": len(recs) - len(music),
                  "n_duplicates_dropped": len(dups), "n_included": len(kept)}


def consistency_check(out_dir, full_ref, inclusion):
    """The reference rebuilt here must equal corpus_profile.json (same rules, same data)."""
    p = Path(out_dir) / "corpus_profile.json"
    if not p.exists():
        return {"corpus_profile_json": "missing"}
    prof = json.loads(p.read_text(encoding="utf-8"))
    diffs = []
    for k, st in prof.get("window_features", {}).items():
        mine = full_ref["stats"].get(k)
        if st and mine:
            diffs.append(abs(mine["p50"] - st["p50"]))
    worst = max(diffs) if diffs else None
    # both JSONs store floats rounded to 5 decimals (darwish_math._clean), so equality means |diff| <= 1e-5
    return {"profile_n_included_tracks": prof["inclusion"]["n_included_tracks"],
            "rebuilt_n_included_tracks": inclusion["n_included"],
            "n_features_compared": len(diffs),
            "max_abs_p50_difference": worst,
            "match": (prof["inclusion"]["n_included_tracks"] == inclusion["n_included"]
                      and worst is not None and worst <= 1e-5)}


def category(name):
    stem = Path(name).stem
    if CONTROL_RX.match(stem):
        return "real Darwish control clip"
    for label, rx in CATEGORIES:
        if rx.search(stem):
            return label
    return "other"


def run(out_dir, write=True):
    t0 = time.time()
    kept, inclusion = load_corpus(out_dir)
    full_ref = build_ref(kept)
    folds = {f: build_ref([r for r in kept if fold_of(r["file"]) != f]) for f in (0, 1)}
    cons = consistency_check(out_dir, full_ref, inclusion)

    darwish_rows = []
    for r in kept:
        f = fold_of(r["file"])
        held = score_record(r, folds[f])
        ins = score_record(r, full_ref)
        if not held:
            continue
        pick = int(np.random.default_rng(_h(r["file"])).integers(len(held)))
        w = held[pick]
        darwish_rows.append({
            "file": r["file"], "fold": f, "n_windows": len(held),
            "score_random_window_heldout": w["score"], "random_window_start_s": w["start_s"],
            "score_median_of_windows_heldout": float(np.median([x["score"] for x in held])),
            "score_random_window_insample": ins[pick]["score"] if pick < len(ins) else None,
            "components_random_window": w["components"],
            "all_window_scores_heldout": [x["score"] for x in held],
            "form_full_diagnostic": form_full_diagnostic(r, folds[f]),
        })

    ratings = dm._ratings()
    ours_rows = []
    for r in dm._load_out(out_dir, "ours"):
        wins = score_record(r, full_ref)
        if not wins:
            continue
        mw = _median_window(wins)
        ours_rows.append({
            "file": r["file"], "label": r.get("label"), "category": category(r["file"]),
            "duration_s": r["track"].get("duration_s"), "n_windows": len(wins),
            "score": float(np.median([x["score"] for x in wins])),
            "window_scores": [x["score"] for x in wins],
            "components": mw["components"], "weights_used": mw["weights_used"],
            "detail_median_window": mw["detail"],
            "iddo_ear": ratings.get(r["file"]),
            "form_full_diagnostic": form_full_diagnostic(r, full_ref),
        })
    ours_rows.sort(key=lambda z: -z["score"])

    controls = [o for o in ours_rows if o["category"] == "real Darwish control clip"]
    renders = [o for o in ours_rows if o["category"] != "real Darwish control clip"]
    d_rand = [d["score_random_window_heldout"] for d in darwish_rows]

    def comp_medians(rows, key):
        return {c: (float(np.median([r[key][c] for r in rows if _finite(r[key].get(c))]))
                    if any(_finite(r[key].get(c)) for r in rows) else None) for c in WEIGHTS}

    by_cat = {}
    for o in renders:
        by_cat.setdefault(o["category"], []).append(o["score"])

    rated = [o for o in ours_rows if o["iddo_ear"]]
    goods = [o["score"] for o in rated if o["iddo_ear"]["iddo_pct"] >= 50]
    bads = [o["score"] for o in rated if o["iddo_ear"]["iddo_pct"] < 50]
    byname = {o["file"]: o["score"] for o in ours_rows}
    blind = []
    for win, lose in BLIND_ORDER_20260905:
        if win in byname and lose in byname:
            blind.append({"iddo_preferred": win, "over": lose, "v0_agrees": byname[win] > byname[lose],
                          "v0_scores": [byname[win], byname[lose]]})

    res = {
        "version": SCORE_VERSION, "label": LABEL, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "measurements_from": dm.VERSION,
        "honesty": ("Inputs are MEASURED by darwish_math.py. The 0-100 blend, its anchors and weights are a "
                    "HYPOTHESIS about a human ear. Darwish scoring high here shows only that the score rewards "
                    "Darwish-likeness; it does not show that it predicts what Iddo hears as good."),
        "weights": WEIGHTS,
        "sub_weights": {"scale": SCALE_SUB, "groove": GROOVE_SUB, "consonance": CONSONANCE_SUB, "form": FORM_SUB},
        "anchors": {"PROFILE_Z_FREE": PROFILE_Z_FREE, "PROFILE_Z_ZERO": PROFILE_Z_ZERO,
                    "SCALE_SHARE_ZERO": SCALE_SHARE_ZERO, "TONAL_HIERARCHY_ZERO_R": TONAL_HIERARCHY_ZERO_R,
                    "BPM_FALLOFF": BPM_FALLOFF, "PULSE_ZERO": PULSE_ZERO, "GRID_TOL_MS": GRID_TOL_MS,
                    "TENSION_ZERO": TENSION_ZERO, "INTERVAL_COLOUR_ZERO_R": INTERVAL_COLOUR_ZERO_R,
                    "LOUDNESS_FALLOFF_LU": LOUDNESS_FALLOFF_LU, "DYN_FLAT_ZERO_DB": DYN_FLAT_ZERO_DB,
                    "DYN_CLIFF_FALLOFF_DB": DYN_CLIFF_FALLOFF_DB, "BASS_ZERO_SHARE": BASS_ZERO_SHARE},
        "profile_excluded_features": PROFILE_EXCLUDE,
        "inclusion": inclusion, "consistency_with_corpus_profile_json": cons,
        "fold_sizes": {f: folds[f]["n_tracks"] for f in (0, 1)},
        "distributions": {
            "darwish_heldout_one_random_window_per_track (PRIMARY)": dist(d_rand),
            "darwish_heldout_median_of_windows_per_track": dist([d["score_median_of_windows_heldout"] for d in darwish_rows]),
            "darwish_heldout_all_windows": dist([s for d in darwish_rows for s in d["all_window_scores_heldout"]]),
            "darwish_INSAMPLE_one_random_window_per_track (circular, for comparison)": dist([d["score_random_window_insample"] for d in darwish_rows]),
            "real_darwish_control_clips_human1_3": dist([o["score"] for o in controls]),
            "our_renders_all": dist([o["score"] for o in renders]),
            **{f"our_renders: {k}": dist(v) for k, v in sorted(by_cat.items())},
        },
        "component_medians": {"darwish_heldout_random_window": comp_medians(
            [{"c": d["components_random_window"]} for d in darwish_rows], "c"),
            "our_renders": comp_medians([{"c": o["components"]} for o in renders], "c")},
        "separation_MEASURED": {
            "auc_darwish_random_window_vs_our_renders": auc(d_rand, [o["score"] for o in renders]),
            "our_renders_scoring_above_darwish_heldout_median": sum(1 for o in renders if o["score"] > np.median(d_rand)),
            "n_renders": len(renders),
            "meaning": "How well v0 tells real Darwish minutes from our renders. This measures Darwish-likeness, NOT 'sounds good'.",
        },
        "ear_checks_NOT_EVIDENCE": {
            "ratings_csv": {"n_good": len(goods), "n_bad": len(bads), "auc_good_scores_higher": auc(goods, bads),
                            "rated": [{"file": o["file"], "iddo_pct": o["iddo_ear"]["iddo_pct"], "v0": o["score"]} for o in rated]},
            "blind_order_20260905": {"pairs": blind, "n_agree": sum(p["v0_agrees"] for p in blind), "n_pairs": len(blind),
                                     "note": "darwish_v2/3/4.mp3 and machine1/2/3.mp3 are the SAME three renders at two lengths, so these are 3 independent judgements, not 6."},
            "verdict": "NOT EVIDENCE: 1 good vs 10 bad taps plus one 3-item blind ranking. v0 stays a HYPOTHESIS until BLIND-EAR-PROTOCOL.md is run.",
        },
        "darwish_tracks": darwish_rows,
        "our_renders": ours_rows,
        "runtime_s": time.time() - t0,
    }
    if write:
        dm.write_json_atomic(Path(out_dir) / "sounds_good_v0.json", res)
    return res


def cmd_one(path, out_dir):
    kept, _ = load_corpus(out_dir)
    ref = build_ref(kept)
    rec = json.loads(Path(path).read_text(encoding="utf-8"))
    wins = score_record(rec, ref)
    print(json.dumps(dm._clean({"label": LABEL, "file": rec.get("file"),
                                "score_median_of_windows": float(np.median([w["score"] for w in wins])) if wins else None,
                                "windows": wins}), ensure_ascii=False, indent=1))
    return 0


def main():
    dm.utf8()
    dm.lower_priority()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--one", default=None, help="explain one analysed JSON (ours__*.json or darwish__*.json)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    if a.one:
        return cmd_one(a.one, a.out)
    res = run(a.out, write=not a.no_write)
    brief = {k: res[k] for k in ("label", "inclusion", "consistency_with_corpus_profile_json", "fold_sizes",
                                 "distributions", "component_medians", "separation_MEASURED")}
    brief["ear_checks_NOT_EVIDENCE"] = {k: v for k, v in res["ear_checks_NOT_EVIDENCE"].items()}
    brief["renders_ranked"] = [(round(o["score"], 1), o["category"][:12], o["file"],
                                (o["iddo_ear"] or {}).get("iddo_pct")) for o in res["our_renders"]]
    print(json.dumps(dm._clean(brief), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
