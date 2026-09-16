# -*- coding: utf-8 -*-
"""ah_criterion.py - the judge for rung 1 of the coronation curriculum: /a/.

WHY THIS FILE EXISTS
--------------------
state/coronation.json crowned a queen on syllable_cos_top1 = 0.758. That number
is real and it measures PERCEPTION - whether she can tell sounds apart. Nobody
ever tested PRODUCTION. Iddo listened, and it is garbage, because
acoustic_units.synthesize_units() is not a synthesiser: it overlap-adds stored
raw PCM exemplars ("random real frames from the uncurated train pool", per the
checkpoint's own autonomy_law) and then lowpasses the mosaic at 2500 Hz. Both
facts are true at once - a good number over a bad sound. This module is the
production judge that was missing.

THE PROVENANCE PHILOSOPHY, WHICH IDDO WROTE
-------------------------------------------
The first draft of this law had an ANTI-COPY gate: penalise resemblance to
Iddo's voice. Iddo overruled it - "its ok if the queen copies me with her own
mouth that's learning isnt it" - and he is right, because that is precisely how
an infant acquires speech. So the gate is not on similarity, it is on MECHANISM.
IMITATION is reproducing the sound through her own articulators: a glottal
source, a tube, formants she controls - learning, and required. REPLAY is
splicing stored recorded waveform: a tape recorder, and forbidden. Sounding
exactly like Iddo's /a/ is the TARGET and never the crime; the only question
gate 4 asks is whether the sound was MADE or REMEMBERED. It is enforced
structurally first (a production path with no reachable waveform cannot cheat,
by construction, rather than being caught afterwards) and empirically second,
as defence in depth.

WHAT THE FOUR GATES ARE
-----------------------
  1 IDENTITY   - it must be /a/ and not some other vowel.
  2 VOICING    - a sustained, harmonically rich, plausibly pitched voice.
  3 STABILITY  - held steady; a sweep or a smear is not a vowel.
  4 PROVENANCE - made by a mouth, not spliced from a recording.

An EMPTY THRONE is the preferred outcome. Every default here fails closed:
unverified provenance is a failure, not a pass, and no threshold in this file
may be moved to make a candidate fit.

No torch. No audio device is opened - waveforms arrive as arrays and leave as
verdicts.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field

import numpy as np

import curriculum_targets as ct

# ==========================================================================
# THE TARGET  (measured; see state/curriculum-targets.json)
# ==========================================================================
# All-speakers pooled: Iddo + FLEURS he_il + Common Voice 17 he. Pooled rather
# than Iddo-only on purpose - if the colony only ever hears one man, "/a/" and
# "Iddo's voice" stay entangled. Iddo's own /a/ sits 1.44 Mahalanobis units from
# this centroid, comfortably inside it, so aiming at the shared Hebrew category
# does not exclude him.
AH_TARGET = {
    "F1": 689.0,
    "F2": 1464.0,
    "cov": [[1681.0, 214.8], [214.8, 68644.0]],       # Hz^2, measured
    "sd_F1": 41.0,
    "sd_F2": 262.0,
    "f0_median_hz": 194.2,
    "n_effective_frames": 42736,
    "source": "curriculum-targets.json rung_1_a.all_speakers_pooled",
}
_A_MU = np.array([AH_TARGET["F1"], AH_TARGET["F2"]], dtype=np.float64)
_A_COV = np.array(AH_TARGET["cov"], dtype=np.float64)
_A_INV = np.linalg.inv(_A_COV)

# The competitor set. Measured from 2,342 vowel NUCLEI pooled over 800 train
# clips (400 Iddo + 400 open-corpus), held-out sessions excluded twice - by the
# corpus split and again by curriculum_targets.filter_training_paths().
#   /i/ and /u/ are the close front and close back corners, found by the same
#       corner-selection estimator that produced the /a/ target: take the
#       extreme-F2 quantile, split it into two lobes, keep the lower-F1 one.
#   /e/ and /o/ are DERIVED, not measured: the Bark midpoints a-i and a-u.
#       Running speech does not separate them from the central mass by
#       clustering, and inventing a measurement would be worse than saying so.
#       The derivation is conservative in the right direction - it places them
#       CLOSER to /a/ than real /e/ and /o/ sit, which makes the gate stricter.
VOWEL_SPACE_HZ = {
    "i": [474.5, 2008.3],
    "e": [577.2, 1716.1],
    "a": [AH_TARGET["F1"], AH_TARGET["F2"]],
    "o": [591.5, 1233.2],
    "u": [500.9, 1031.6],
}

# ==========================================================================
# THE THRESHOLDS
# ==========================================================================
GATES = {
    # gate 1
    "md_max": 2.5,
    "nearest_margin_bark": 0.10,
    # gate 2
    "steady_ms_min": 120.0,
    "voiced_fraction_min": 0.80,
    "voicing_mean_min": 0.50,
    "f0_min_hz": 70.0,
    "f0_max_hz": 400.0,
    "cv_f0_max": 0.15,
    "harmonics_min": 3,
    # gate 3
    "cv_f1_max": 0.06,
    "cv_f2_max": 0.10,
    "drift_f1_hz_s_max": 800.0,
    "drift_f2_hz_s_max": 3200.0,
    # gate 4
    "replay_snr_db": 20.0,
}

THRESHOLD_PROVENANCE = {
    "md_max": {
        "value": 2.5,
        "source": "chi-square(2 dof) 95.6% ellipse of the MEASURED /a/ covariance "
                  "(train-fitted, pooled speakers). Cross-checked on 2,342 train "
                  "nuclei: MD<=2.0 selects 479 of them, which is close to the "
                  "expected /a/ share of a five-vowel inventory.",
    },
    "nearest_margin_bark": {
        "value": 0.10,
        "source": "tie-break only, about a tenth of a critical band; /a/ must win "
                  "the nearest-vowel comparison outright, not by a rounding error.",
    },
    "steady_ms_min": {
        "value": 120.0,
        "source": "curriculum-targets.json rung_1_a proposed acceptance; the "
                  "median steady /a/ stretch measured in the train split is "
                  "135 ms, so this asks for a normal-length vowel, not a long one.",
    },
    "voiced_fraction_min": {
        "value": 0.80,
        "source": "a sustained vowel is voiced nearly throughout; set from the "
                  "train-split steady-stretch measurement, where qualifying "
                  "windows are voiced end to end.",
    },
    "voicing_mean_min": {
        "value": 0.50,
        "source": "train split: mean normalised autocorrelation over real /a/ "
                  "stretches, p50 = 0.719. 0.50 sits well below the human "
                  "distribution and well above noise (~0.1-0.2).",
    },
    "f0_min_hz": {
        "value": 70.0,
        "source": "spans the corpus: pooled male f0 median 113 Hz, Iddo 186 Hz, "
                  "female 212 Hz. Deliberately wide - pitch is not the target.",
    },
    "f0_max_hz": {
        "value": 400.0,
        "source": "as f0_min_hz; leaves room for a child-scale tract.",
    },
    "cv_f0_max": {
        "value": 0.15,
        "source": "train split: coefficient of variation of f0 within real /a/ "
                  "stretches, p50 = 0.028, p75 = 0.049, p90 = 0.174. 0.15 sits "
                  "between p75 and p90.",
    },
    "harmonics_min": {
        "value": 3,
        "source": "physics, not a corpus fit: a glottal source through a tube "
                  "produces many partials. One partial is an oscillator. Three is "
                  "the minimum that cannot be a sine or a two-tone artefact.",
    },
    "cv_f1_max": {
        "value": 0.06,
        "source": "train split p90 of CV(F1) over real /a/ stretches (0.0588).",
    },
    "cv_f2_max": {
        "value": 0.10,
        "source": "train split p90 of CV(F2) over real /a/ stretches (0.1024).",
    },
    "drift_f1_hz_s_max": {
        "value": 800.0,
        "source": "train split p90 of |dF1/dt| over real /a/ stretches (768 Hz/s). "
                  "MEASURED CORRECTION: curriculum-targets.json proposed 400 Hz/s, "
                  "which real human /a/ exceeds about 45% of the time (p50 = 239, "
                  "p75 = 379). The proposal was too tight; CV is the binding test.",
    },
    "drift_f2_hz_s_max": {
        "value": 3200.0,
        "source": "train split p90 of |dF2/dt| (3193 Hz/s). MEASURED CORRECTION: "
                  "the proposed 900 Hz/s is exceeded by well over half of real "
                  "human /a/ (p50 = 1319 Hz/s) and would have rejected the "
                  "corpus itself.",
    },
    "replay_snr_db": {
        "value": 20.0,
        "source": "measured separation, not a guess: an exact overlap-add replay "
                  "reconstructs at the numerical-noise level while an honest "
                  "source-filter vowel aimed at the SAME target reconstructs far "
                  "below it. See MOSAIC_DETECTOR_MEASUREMENTS.",
    },
}


# ==========================================================================
# Small helpers
# ==========================================================================
def bark(f):
    f = np.asarray(f, dtype=np.float64)
    return 26.81 * f / (1960.0 + f) - 0.53


def mahalanobis_to_a(f1, f2):
    """Distance to the /a/ centroid in the metric of the MEASURED covariance.

    Why not raw Hz: the measured cluster has sd(F1) = 41 Hz and sd(F2) = 262 Hz.
    A raw-Hz Euclidean distance therefore treats a 150 Hz error in F1 - which is
    3.7 standard deviations and a completely different vowel height - as no worse
    than 150 Hz in F2, which is barely half a standard deviation. Mahalanobis
    also uses the measured F1/F2 correlation, which raw Hz throws away.
    """
    d = np.array([np.asarray(f1, float) - _A_MU[0],
                  np.asarray(f2, float) - _A_MU[1]], dtype=np.float64)
    if d.ndim == 1:
        return float(np.sqrt(d @ _A_INV @ d))
    return np.sqrt(np.einsum("ij,jk,ik->i", d.T, _A_INV, d.T))


def nearest_vowel(f1, f2):
    """Nearest vowel in the measured space, in BARK-Euclidean.

    Why Bark and not Mahalanobis here: only /a/ has a measured covariance. Using
    /a/'s covariance for /i/ or /u/ would be a fabrication, and would make every
    competitor look far away along F2 simply because /a/'s F2 spread is wide.
    Bark is perceptually uniform, so one unit means the same amount of "different
    vowel" at 500 Hz and at 2500 Hz. Returns (name, {name: distance}).
    """
    b = np.array([bark(f1), bark(f2)], dtype=np.float64)
    dists = {k: float(np.hypot(b[0] - bark(v[0]), b[1] - bark(v[1])))
             for k, v in VOWEL_SPACE_HZ.items()}
    return min(dists, key=dists.get), dists


# How the frozen law behaves on REAL HUMAN SPEECH it was never fitted to.
# Measured on the held-out sessions (2026-06-25 / 2026-06-24), which are reserved
# for evaluation and were not used to set a single threshold here.
HELDOUT_CALIBRATION = {
    "on_60_real_a_segments": {
        "how_located": "segments >= 130 ms whose formant track stays within "
                       "Mahalanobis 2.0 of the /a/ centroid - located by IDENTITY "
                       "ONLY, so the voicing and stability rates below are not "
                       "circular",
        "gate2_voicing_pass": "75%",
        "gate3_stability_pass": "87%",
        "gate1_identity_pass": "55%",
        "gates_1_to_3_all_pass": "33%",
    },
    "on_120_whole_heldout_clips": {
        "gates_1_to_3_all_pass": "3%",
        "why_so_low_and_why_that_is_correct":
            "a whole clip is a sentence of running speech. The judge picks its "
            "steadiest 120 ms window and asks whether THAT is an /a/; usually it "
            "is some other vowel, and gate 1 correctly says so (8% pass). This "
            "is a per-SOUND judge, not a per-utterance one.",
    },
    "reading": "The law does not reject human speech: on the two gates that can "
               "be scored without circularity it accepts 75% and 87% of real /a/. "
               "It is demanding end-to-end (33%) because running-speech /a/ "
               "wanders, and a queen is being asked for a deliberate sustained "
               "vowel, not a syllable snatched from a sentence.",
    "what_this_does_NOT_establish": "that any of it sounds right. Every number "
                                    "here is still a number. No candidate may be "
                                    "crowned until someone LISTENS - that is the "
                                    "whole reason this module exists.",
}

# What gate 3 can and cannot do. Written down because the alternative is a gate
# that quietly means something other than it says.
STABILITY_LIMITS = {
    "window_scope": "Gate 3 judges the steadiest 120 ms window in the candidate, "
                    "not the whole candidate. A vowel inside running speech is "
                    "exactly that - 120 ms of held tongue between two moving "
                    "neighbours - so judging the whole utterance would reject "
                    "real speech.",
    "gentle_glide_passes": True,
    "why": "A glide slower than real human /a/ varies (train medians: 239 Hz/s "
           "on F1, 1319 Hz/s on F2) cannot be rejected without rejecting the "
           "corpus. The gate catches smears FASTER than human speech, and says "
           "so rather than pretending otherwise.",
    "consequence": "A candidate that glides slowly through the /a/ centroid can "
                   "pass gates 1-3. It is gate 4 that must then establish the "
                   "sound was articulated rather than replayed, and a listening "
                   "test that ratifies the result before anyone is crowned.",
}


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""
    values: dict = field(default_factory=dict)


@dataclass
class Verdict:
    passed: bool
    gates: dict
    measurements: dict = field(default_factory=dict)

    def summary(self):
        lines = ["PASS" if self.passed else "FAIL"]
        for g in self.gates.values():
            lines.append(f"  [{'ok ' if g.passed else 'FAIL'}] {g.name}: {g.detail}")
        return "\n".join(lines)


# ==========================================================================
# Window selection
# ==========================================================================
def _track_for_judging(x, sr, floor_db=-25.0):
    """Formant track tuned for JUDGING one sound, not for mining a corpus.

    curriculum_targets.formant_track defaults to keeping only frames above the
    MEDIAN energy of the clip. On running speech that is a sensible way to skip
    the quiet parts; on a single sustained vowel it throws away half the frames
    at random, punches holes in every run and leaves nothing 120 ms long to
    judge. It cost the achievability test a false failure. Here the energy gate
    is an absolute floor relative to the loudest frame instead.
    """
    tr = ct.formant_track(x, sr, energy_pct=0.0, max_frames=None)
    if not tr:
        return []
    peak = max(f["rms"] for f in tr) or 1.0
    thr = peak * (10.0 ** (floor_db / 20.0))
    return [f for f in tr if f["rms"] >= thr]


def _contiguous_runs(track, max_gap_s=0.011):
    runs, i = [], 0
    while i < len(track):
        j = i
        while j + 1 < len(track) and \
                (track[j + 1]["t"] - track[j]["t"]) <= max_gap_s:
            j += 1
        runs.append((i, j))
        i = j + 1
    return runs


def _pick_window(track, win_s):
    """The steadiest window of at least win_s inside the longest voiced runs.

    Selection uses STABILITY ONLY. Identity, voicing richness and provenance are
    then tested on whatever this returns, without further searching - so gate 1
    stays a real test and is not handed a window chosen for being /a/-like.
    """
    best = None
    for a, b in _contiguous_runs(track):
        n = b - a + 1
        need = max(2, int(round(win_s / 0.010)))
        if n < need:
            continue
        f1 = np.array([track[k]["f1"] for k in range(a, b + 1)])
        f2 = np.array([track[k]["f2"] for k in range(a, b + 1)])
        for s in range(0, n - need + 1):
            s1, s2 = f1[s:s + need], f2[s:s + need]
            if s1.mean() <= 0 or s2.mean() <= 0:
                continue
            cv1 = s1.std() / s1.mean()
            cv2 = s2.std() / s2.mean()
            score = cv1 / GATES["cv_f1_max"] + cv2 / GATES["cv_f2_max"]
            if best is None or score < best[0]:
                best = (score, a + s, a + s + need - 1)
    if best is None:                                   # nothing long enough
        for a, b in _contiguous_runs(track):
            if best is None or (b - a) > (best[2] - best[1]):
                best = (float("inf"), a, b)
    return None if best is None else (best[1], best[2])


# ==========================================================================
# GATE 2 helpers - voicing, pitch, harmonic richness
# ==========================================================================
def harmonic_count(y, sr, f0_hz, n_max=10, within_db=30.0, above_floor_db=20.0):
    """How many harmonics of f0 carry real energy.

    This is what separates a voice from a sine. A sine is perfectly periodic and
    sails through any autocorrelation voicing test; it has ONE partial. A glottal
    source through a vocal tract has many. There is no threshold-fiddling here -
    it is the difference between a signal generator and a body.

    A harmonic counts when it is within `within_db` of the STRONGEST harmonic and
    also clear of the spectral floor. The relative test is the load-bearing one:
    an earlier version compared only against the median magnitude, and for a pure
    sine that median is numerical noise, so window leakage at 2f0 and 3f0 cleared
    it and a 700 Hz sine was credited with 4 harmonics. Measuring against the
    strongest partial cannot be fooled that way.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size < 256 or not f0_hz or f0_hz <= 0 or not np.isfinite(f0_hz):
        return 0
    w = y * np.hanning(y.size)
    mag = np.abs(np.fft.rfft(w))
    freqs = np.fft.rfftfreq(y.size, 1.0 / sr)
    band = (freqs > 0) & (freqs <= 5000.0)
    if not band.any():
        return 0
    floor = float(np.median(mag[band])) + 1e-12
    peaks = []
    for k in range(1, n_max + 1):
        fk = k * f0_hz
        if fk > min(5000.0, 0.45 * sr):
            break
        sel = (freqs >= fk - 0.3 * f0_hz) & (freqs <= fk + 0.3 * f0_hz)
        peaks.append(float(mag[sel].max()) if sel.any() else 0.0)
    if not peaks:
        return 0
    top = max(peaks)
    if top <= 0:
        return 0
    rel = top * (10.0 ** (-within_db / 20.0))
    abs_ = floor * (10.0 ** (above_floor_db / 20.0))
    return int(sum(1 for p in peaks if p >= rel and p >= abs_))


def _voicing_profile(y, sr, win_s=0.025, hop_s=0.010):
    win, hop = int(win_s * sr), int(hop_s * sr)
    if y.size < win:
        return np.array([]), np.array([])
    n = 1 + (y.size - win) // hop
    V = np.lib.stride_tricks.sliding_window_view(y, win)[::hop][:n]
    v = np.array([ct.voicing_strength(fr.astype(np.float64), sr) for fr in V])
    f0 = np.array([(ct.estimate_f0(fr.astype(np.float64), sr) or np.nan)
                   for fr in V])
    return v, f0


# ==========================================================================
# GATE 4a - PROVENANCE, STATIC: import discipline over the call graph
# ==========================================================================
FORBIDDEN_IMPORTS = (
    "wave", "soundfile", "librosa", "audioread", "pydub", "sounddevice",
    "pyaudio", "aifc", "sunau", "torchaudio", "torch", "scipy.io",
    "scipy.io.wavfile", "wavio", "pickle", "shelve", "joblib", "h5py",
)
FORBIDDEN_CALLS = (
    "open", "np.load", "numpy.load", "np.fromfile", "numpy.fromfile",
    "np.memmap", "numpy.memmap", "np.genfromtxt", "np.loadtxt",
    "json.load", "pickle.load", "wave.open", "read_wav_mono16k",
    "load_checkpoint", "synthesize_units", "reconstruct", "soundfile.read",
    "librosa.load", "wavfile.read",
)
# Any identifier or string literal matching one of these is a waveform bank by
# another name.
FORBIDDEN_TOKENS = (
    "exemplars_pcm16", "exemplars_pcm", "exemplar_pcm", "exemplars",
    "pcm16", "waveform_bank", "wav_bank", "sample_bank", "audio_bank",
)


@dataclass
class Violation:
    module: str
    lineno: int
    reason: str

    def __str__(self):
        return f"{self.module}:{self.lineno}: {self.reason}"


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def audit_production_module(path, _seen=None, _depth=0, max_depth=8):
    """Static import-discipline audit of a production module and everything it
    imports from the same tree.

    The rule is deliberately blunt and therefore unlaunderable: THE MOUTH DOES NO
    I/O. It may not import an audio library, may not open a file by any means,
    may not unpickle, and may not name an exemplar bank. It receives articulatory
    parameters as function arguments and returns a waveform. A path that cannot
    reach a recording cannot replay one - the impossibility is structural, not a
    correlation threshold that a clever mosaic might slip under.

    Returns a list of Violation. Empty list means clean.
    """
    path = os.path.abspath(str(path))
    if _seen is None:
        _seen = set()
    if path in _seen or _depth > max_depth:
        return []
    _seen.add(path)
    if not os.path.exists(path):
        return [Violation(path, 0, "module not found")]
    name = os.path.splitext(os.path.basename(path))[0]
    src = open(path, "r", encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return [Violation(name, e.lineno or 0, f"unparseable: {e}")]

    out, local_imports = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if _is_forbidden_import(a.name):
                    out.append(Violation(name, node.lineno,
                                         f"imports '{a.name}'"))
                local_imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:                              # relative import
                local_imports.append(mod.split(".")[0] if mod else "")
            if _is_forbidden_import(mod):
                out.append(Violation(name, node.lineno, f"imports '{mod}'"))
            for a in node.names:
                full = f"{mod}.{a.name}" if mod else a.name
                if _is_forbidden_import(full):
                    out.append(Violation(name, node.lineno,
                                         f"imports '{full}'"))
            local_imports.append(mod)
        elif isinstance(node, ast.Call):
            d = _dotted(node.func) or ""
            if d in FORBIDDEN_CALLS or d.split(".")[-1] in (
                    "load", "fromfile", "memmap") and d.split(".")[0] in (
                    "np", "numpy", "pickle", "json"):
                out.append(Violation(name, node.lineno, f"calls '{d}()'"))
        elif isinstance(node, (ast.Name, ast.Attribute)):
            tok = node.id if isinstance(node, ast.Name) else node.attr
            if tok in FORBIDDEN_TOKENS:
                out.append(Violation(name, node.lineno,
                                     f"names a waveform bank: '{tok}'"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in FORBIDDEN_TOKENS:
                out.append(Violation(
                    name, node.lineno,
                    f"references a waveform bank by key: '{node.value}'"))

    here = os.path.dirname(path)
    for mod in local_imports:
        if not mod:
            continue
        head = mod.split(".")[0]
        cand = os.path.join(here, *mod.split(".")) + ".py"
        cand2 = os.path.join(here, head + ".py")
        for c in (cand, cand2):
            if os.path.exists(c) and os.path.abspath(c) != path:
                out.extend(audit_production_module(c, _seen, _depth + 1,
                                                   max_depth))
                break
    return out


def _is_forbidden_import(mod):
    if not mod:
        return False
    m = mod.replace("/", ".")
    for bad in FORBIDDEN_IMPORTS:
        if m == bad or m.startswith(bad + "."):
            return True
    return False


def grep_proof(path, tokens=FORBIDDEN_TOKENS):
    """The same claim by the crudest possible instrument. If grep and the AST
    audit ever disagree, trust neither until they are reconciled."""
    hits = []
    src = open(path, "r", encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(src, 1):
        for t in tokens:
            if t in line:
                hits.append((i, t, line.strip()))
    return hits


# ==========================================================================
# GATE 4b - PROVENANCE, EMPIRICAL: is this an overlap-add of a codebook?
# ==========================================================================
def overlap_add(frames, hop, window=None):
    """Exactly the construction acoustic_units.synthesize_units() performs."""
    frames = np.asarray(frames, dtype=np.float64)
    n_f, frame = frames.shape
    win = np.maximum(np.hanning(frame), 1e-4) if window is None else window
    out = np.zeros((n_f - 1) * hop + frame)
    wsum = np.zeros_like(out)
    for i in range(n_f):
        s = i * hop
        out[s:s + frame] += frames[i] * win
        wsum[s:s + frame] += win
    return (out / np.maximum(wsum, 1e-8)).astype(np.float32)


def crossfade(a, b, overlap):
    """A lightly crossfaded two-frame mosaic - the obvious way to try to evade a
    frame-matching detector."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    overlap = int(min(overlap, len(a), len(b)))
    ramp = np.linspace(0.0, 1.0, overlap)
    out = np.concatenate([a, np.zeros(len(b) - overlap)])
    out[len(a) - overlap:len(a)] = a[len(a) - overlap:] * (1 - ramp) + \
        b[:overlap] * ramp
    out[len(a):] = b[overlap:]
    return out.astype(np.float32)


def mosaic_reconstruction_snr_db(y, codebook, frame=400, hop=200,
                                 offset_steps=4, allow_gain=True, sweeps=4):
    """How well can y be explained as an overlap-add of codebook frames?

    Matching pursuit over the exact generative model of synthesize_units():
    out += exemplar * window, then out /= sum(window). The weight profile depends
    only on the frame positions, so it is known in advance and the model is
    LINEAR in the exemplars.

    One left-to-right greedy pass is not enough and the first version of this
    function was wrong because of it: at position i the residual still contains
    the not-yet-placed left half of atom i+1, so the greedy choice can take the
    neighbour and never recover. An exact replay scored 15 dB - under the
    threshold, i.e. a false clear. The fix is cyclic coordinate descent: after
    the first pass, repeatedly remove each position's own contribution and
    re-choose it against everything else. That converges to the exact
    decomposition when one exists, which is precisely the case that matters.

    Returns SNR in dB over the interior, so OLA edge effects cannot flatter it.
    """
    y = np.asarray(y, dtype=np.float64).ravel()
    C = np.asarray(codebook, dtype=np.float64)
    if C.ndim != 2 or C.shape[1] != frame:
        raise ValueError("codebook must be (n_units, frame)")
    if y.size < frame + hop:
        return -np.inf
    win = np.maximum(np.hanning(frame), 1e-4)
    A = C * win                                          # windowed atoms
    an = np.sum(A * A, axis=1) + 1e-12
    best = -np.inf
    step = max(1, hop // max(1, offset_steps))
    for off in range(0, hop, step):
        yy = y[off:]
        n_pos = 1 + (len(yy) - frame) // hop
        if n_pos < 2:
            continue
        L = (n_pos - 1) * hop + frame
        wsum = np.zeros(L)
        for i in range(n_pos):
            wsum[i * hop:i * hop + frame] += win
        target = yy[:L] * wsum                            # the un-normalised sum
        acc = np.zeros(L)
        pick = np.zeros(n_pos, dtype=np.int64)
        gain = np.zeros(n_pos)

        def refit(i, first):
            s = i * hop
            if not first:
                acc[s:s + frame] -= gain[i] * A[pick[i]]
            resid = target[s:s + frame] - acc[s:s + frame]
            proj = A @ resid
            k = int(np.argmax(np.abs(proj) / np.sqrt(an)))
            g = proj[k] / an[k] if allow_gain else 1.0
            pick[i], gain[i] = k, g
            acc[s:s + frame] += g * A[k]

        for i in range(n_pos):
            refit(i, True)
        for _ in range(max(0, sweeps)):
            for i in range(n_pos):
                refit(i, False)

        recon = acc / np.maximum(wsum, 1e-8)
        pad = min(hop, L // 4)                            # interior only
        lo, hi = pad, L - pad
        if hi - lo < 32:
            continue
        err = yy[lo:hi] - recon[lo:hi]
        sig = float(np.dot(yy[lo:hi], yy[lo:hi]))
        e = float(np.dot(err, err))
        if sig <= 0:
            continue
        snr = 10.0 * np.log10(sig / max(e, 1e-20))
        best = max(best, snr)
    return float(best)


def candidate_hops(frame, given_hop):
    """Hop lengths to search. A splicer does not have to use the hop we guess,
    and the first version of this detector searched only one - which let a
    crossfaded mosaic escape 100% of the time whenever the fade length was not
    exactly the assumed hop. Measured, then fixed."""
    hops = {int(given_hop)}
    for d in range(1, 17):                      # frame/16 .. frame, evenly
        hops.add(max(16, int(round(frame * d / 16.0))))
    return sorted(h for h in hops if 16 <= h <= frame)


def looks_like_replay(y, codebook, frame=400, hop=200, threshold_db=None,
                      search_hops=True):
    """(flagged, snr_db). Flagged means: this waveform IS an overlap-add of that
    codebook, to within the residual a splice leaves behind."""
    thr = GATES["replay_snr_db"] if threshold_db is None else threshold_db
    hops = candidate_hops(frame, hop) if search_hops else [hop]
    best = -np.inf
    for h in hops:
        s = mosaic_reconstruction_snr_db(y, codebook, frame=frame, hop=h)
        if s > best:
            best = s
    return bool(best >= thr), float(best)


# What the empirical arm does and does not catch. MEASURED on the held-out clip
# vinput__20260625_063500 (927-frame codebook, frame 400, hop 200), reproduced by
# test_ah_criterion.py on every run. These are not estimates.
MOSAIC_DETECTOR_MEASUREMENTS = {
    "exact_ola_replay_snr_db": 139.9,
    "recorded_clip_whose_frames_are_in_the_codebook_snr_db": 193.0,
    "source_filter_synth_snr_db": 6.85,
    "threshold_db": 20.0,
    "separation_note": "Replay clears the threshold by 120 dB and honest "
                       "imitation misses it by 13 dB. The threshold is not "
                       "finely balanced between them - anywhere from 10 to "
                       "100 dB would give the same verdict on these four cases.",
}

CROSSFADE_EVASION = {
    "question": "Does the empirical arm catch a LIGHTLY CROSSFADED 2-frame "
                "mosaic - the obvious way to smooth the seams and evade a "
                "frame-matcher?",
    "caught": True,
    "answer": "Yes for a 2-frame mosaic, at every fade length measured, but only "
              "because the hop grid was widened after measurement showed it "
              "failing. It degrades on longer mosaics with longer fades.",
    "measured_catch_rate": {
        "2_frame_fade_1.6ms": "100% (median 31.9 dB, min 23.3)",
        "2_frame_fade_3.1ms": "100% (median 26.0 dB, min 22.9)",
        "2_frame_fade_6.2ms": " 92% (median 22.3 dB, min 19.9)",
        "2_frame_fade_12.5ms": " 92% (median 22.3 dB, min 19.6)",
        "8_frame_fade_1.6ms": " 92% (median 27.8 dB, min 19.7)",
        "8_frame_fade_3.1ms": " 92% (median 24.9 dB, min 19.0)",
        "8_frame_fade_6.2ms": " 83% (median 21.1 dB, min 18.3)",
        "8_frame_fade_12.5ms": " 50% (median 20.0 dB, min 18.6)",
    },
    "the_honest_part": "These sit 0-12 dB above a 20 dB threshold, against 120 dB "
                       "of margin for a raw splice. The crossfade case is the "
                       "WEAK end of this detector, not the strong end. A longer "
                       "mosaic with a 12.5 ms fade is a coin flip.",
    "why_it_works_at_all": "A crossfade is a two-atom sum inside one analysis "
                           "window and the pursuit places one atom at a time, so "
                           "the fade region leaves residual - but the flanks "
                           "outside each fade are verbatim codebook frames and "
                           "reconstruct exactly, which carries the interior SNR.",
    "a_bug_this_documents": "The first version searched ONE hop and caught 0% of "
                            "3 ms fades, because the splice's effective hop "
                            "(frame - fade) was not on the grid. looks_like_replay "
                            "now searches 16 hops. An adversary who picks a hop "
                            "between the grid points still escapes.",
    "what_it_does_NOT_catch": [
        "a mosaic built from a codebook the judge was not given - the empirical "
        "arm can only test the bank it is handed. THIS is why gate 4a "
        "(structural) is the primary defence and this arm is only defence in "
        "depth: 4a needs no guess about what the splicer did.",
        "a replay resampled, pitch-shifted, filtered or requantised after "
        "splicing - the atoms no longer match sample for sample",
        "a mosaic whose hop falls between the 16 searched values",
        "a long mosaic with fades of 10 ms or more - measured 50% at 8 frames",
        "a single frame looped, if the loop is shorter than frame + hop - the "
        "detector needs an interior to score and returns -inf instead",
    ],
}


# ==========================================================================
# THE JUDGE
# ==========================================================================
def judge_ah(x, sr=16000, *, production_module=None, codebook=None,
             codebook_frame=400, codebook_hop=200):
    """Judge a candidate /a/ against all four gates.

    production_module : path to the module that PRODUCED x. Gate 4a audits it.
    codebook          : (n_units, frame) exemplar bank the producer had access
                        to, if any. Gate 4b tries to rebuild x out of it.

    With neither, provenance is UNVERIFIED and the verdict is FAIL. That is the
    empty-throne default and it is not negotiable: an unproven mouth is not a
    mouth.
    """
    x = np.asarray(x, dtype=np.float32).ravel()
    gates, meas = {}, {}
    win_s = GATES["steady_ms_min"] / 1000.0
    total_ms = 1000.0 * len(x) / float(sr)

    track = _track_for_judging(x, sr)
    sel = _pick_window(track, win_s) if track else None

    if sel is None:
        detail = ("no voiced formant track at all"
                  if not track else "no usable window")
        if total_ms < GATES["steady_ms_min"]:
            detail = (f"duration {total_ms:.0f} ms < "
                      f"{GATES['steady_ms_min']:.0f} ms - too short to be a "
                      f"held vowel; " + detail)
        for g in ("identity", "voicing", "stability"):
            gates[g] = GateResult(g, False, detail)
        gates["provenance"] = _judge_provenance(
            x, sr, production_module, codebook, codebook_frame, codebook_hop,
            meas)
        return Verdict(False, gates, meas)

    a, b = sel
    t0, t1 = track[a]["t"], track[b]["t"] + 0.025
    dur_ms = (t1 - t0) * 1000.0
    f1 = np.array([track[k]["f1"] for k in range(a, b + 1)])
    f2 = np.array([track[k]["f2"] for k in range(a, b + 1)])
    tt = np.array([track[k]["t"] for k in range(a, b + 1)]) - t0
    y = x[int(t0 * sr):int(min(t1, len(x) / sr) * sr)]
    meas.update({"window_s": [float(t0), float(t1)],
                 "duration_ms": float(dur_ms),
                 "F1": float(f1.mean()), "F2": float(f2.mean()),
                 "n_frames": int(b - a + 1)})

    # ---- GATE 1 : IDENTITY -------------------------------------------------
    md = mahalanobis_to_a(f1.mean(), f2.mean())
    near, dists = nearest_vowel(f1.mean(), f2.mean())
    runner = min((k for k in dists if k != "a"), key=lambda k: dists[k])
    margin = dists[runner] - dists["a"]
    ok1 = (md <= GATES["md_max"] and near == "a"
           and margin >= GATES["nearest_margin_bark"])
    meas.update({"mahalanobis": float(md), "nearest_vowel": near,
                 "bark_margin_over_runner_up": float(margin),
                 "runner_up": runner})
    gates["identity"] = GateResult(
        "identity", ok1,
        f"F1={f1.mean():.0f} F2={f2.mean():.0f} Hz; Mahalanobis={md:.2f} "
        f"(max {GATES['md_max']}); nearest vowel /{near}/, "
        f"margin over /{runner}/ = {margin:.2f} Bark "
        f"(min {GATES['nearest_margin_bark']})",
        {"md": float(md), "nearest": near, "margin_bark": float(margin)})

    # ---- GATE 2 : VOICING --------------------------------------------------
    v, f0v = _voicing_profile(y, sr)
    vf = float(np.mean(v >= 0.45)) if v.size else 0.0
    vm = float(np.mean(v)) if v.size else 0.0
    f0ok = f0v[np.isfinite(f0v)]
    f0med = float(np.median(f0ok)) if f0ok.size else float("nan")
    cvf0 = float(f0ok.std() / f0ok.mean()) if f0ok.size >= 3 and \
        f0ok.mean() > 0 else float("inf")
    nh = harmonic_count(y, sr, f0med if np.isfinite(f0med) else 0.0)
    reasons = []
    if dur_ms < GATES["steady_ms_min"]:
        reasons.append(f"duration {dur_ms:.0f} ms < {GATES['steady_ms_min']:.0f}")
    if vf < GATES["voiced_fraction_min"]:
        reasons.append(f"voiced fraction {vf:.2f} < {GATES['voiced_fraction_min']}")
    if vm < GATES["voicing_mean_min"]:
        reasons.append(f"mean voicing {vm:.2f} < {GATES['voicing_mean_min']}")
    if not (GATES["f0_min_hz"] <= f0med <= GATES["f0_max_hz"]):
        reasons.append(f"f0 {f0med:.0f} Hz outside "
                       f"[{GATES['f0_min_hz']:.0f},{GATES['f0_max_hz']:.0f}]")
    if cvf0 > GATES["cv_f0_max"]:
        reasons.append(f"f0 CV {cvf0:.3f} > {GATES['cv_f0_max']}")
    if nh < GATES["harmonics_min"]:
        reasons.append(f"only {nh} harmonic(s) clear of the floor, need "
                       f"{GATES['harmonics_min']} - this is not a voice, it is "
                       f"an oscillator or noise")
    meas.update({"voiced_fraction": vf, "voicing_mean": vm, "f0_hz": f0med,
                 "cv_f0": cvf0, "harmonics": int(nh)})
    gates["voicing"] = GateResult(
        "voicing", not reasons,
        "; ".join(reasons) if reasons else
        f"{dur_ms:.0f} ms, voiced {vf:.2f}, voicing {vm:.2f}, "
        f"f0 {f0med:.0f} Hz (CV {cvf0:.3f}), {nh} harmonics",
        {"voiced_fraction": vf, "voicing_mean": vm, "f0": f0med,
         "cv_f0": cvf0, "harmonics": int(nh), "duration_ms": float(dur_ms)})

    # ---- GATE 3 : STABILITY ------------------------------------------------
    cv1 = float(f1.std() / f1.mean()) if f1.mean() > 0 else float("inf")
    cv2 = float(f2.std() / f2.mean()) if f2.mean() > 0 else float("inf")
    if tt[-1] > 0 and len(tt) >= 3:
        d1 = abs(float(np.polyfit(tt, f1, 1)[0]))
        d2 = abs(float(np.polyfit(tt, f2, 1)[0]))
    else:
        d1 = d2 = float("inf")
    r3 = []
    if cv1 > GATES["cv_f1_max"]:
        r3.append(f"CV(F1) {cv1:.3f} > {GATES['cv_f1_max']}")
    if cv2 > GATES["cv_f2_max"]:
        r3.append(f"CV(F2) {cv2:.3f} > {GATES['cv_f2_max']}")
    if d1 > GATES["drift_f1_hz_s_max"]:
        r3.append(f"F1 drift {d1:.0f} Hz/s > {GATES['drift_f1_hz_s_max']:.0f}")
    if d2 > GATES["drift_f2_hz_s_max"]:
        r3.append(f"F2 drift {d2:.0f} Hz/s > {GATES['drift_f2_hz_s_max']:.0f}")
    meas.update({"cv_f1": cv1, "cv_f2": cv2, "drift_f1_hz_s": d1,
                 "drift_f2_hz_s": d2})
    gates["stability"] = GateResult(
        "stability", not r3,
        "; ".join(r3) if r3 else
        f"CV(F1)={cv1:.3f} CV(F2)={cv2:.3f}, drift {d1:.0f}/{d2:.0f} Hz/s",
        {"cv_f1": cv1, "cv_f2": cv2, "drift_f1": d1, "drift_f2": d2})

    # ---- GATE 4 : PROVENANCE ----------------------------------------------
    gates["provenance"] = _judge_provenance(
        x, sr, production_module, codebook, codebook_frame, codebook_hop, meas)

    return Verdict(all(g.passed for g in gates.values()), gates, meas)


def _judge_provenance(x, sr, production_module, codebook, frame, hop, meas):
    parts, ok = [], True
    if production_module is None and codebook is None:
        return GateResult(
            "provenance", False,
            "UNVERIFIED: no production module to audit and no codebook to test "
            "against. An unproven mouth is not a mouth - empty throne.")
    if production_module is not None:
        viols = audit_production_module(production_module)
        meas["static_violations"] = [str(v) for v in viols]
        if viols:
            ok = False
            parts.append(f"static audit FAILED ({len(viols)}): "
                         + "; ".join(str(v) for v in viols[:4]))
        else:
            parts.append(f"static audit clean "
                         f"({os.path.basename(str(production_module))} reaches "
                         f"no recorded waveform)")
    else:
        parts.append("no production module given - structural proof MISSING")
        ok = False
    if codebook is not None:
        flagged, snr = looks_like_replay(x, codebook, frame=frame, hop=hop)
        meas["mosaic_snr_db"] = float(snr)
        if flagged:
            ok = False
            parts.append(f"REPLAY: rebuilt from the codebook at {snr:.1f} dB "
                         f"(>= {GATES['replay_snr_db']:.0f} dB) - this is spliced "
                         f"recording, not articulation")
        else:
            parts.append(f"not reconstructible from the codebook "
                         f"({snr:.1f} dB < {GATES['replay_snr_db']:.0f} dB)")
    else:
        parts.append("no codebook supplied - empirical arm not run")
    return GateResult("provenance", ok, "; ".join(parts))


# ==========================================================================
# RUNGS 2 AND 3 - declared, deliberately not implemented
# ==========================================================================
EXTRA_GATES_BA = {
    "closure": {
        "what": "a near-silent interval while the lips are sealed, 40-140 ms; "
                "voicing may persist weakly as a voice bar because /b/ is voiced",
        "measured": "Iddo n=198: median 85 ms (p25-p75 57.5-100.0)",
        "gating": True,
    },
    "burst": {
        "what": "a weak, LOW-frequency release transient. There is no cavity in "
                "front of the lips, so nothing shapes the burst: diffuse-falling, "
                "more energy low than high",
        "measured": "burst centroid median 1160 Hz (p25-p75 973-1511); "
                    "spectral tilt +26.6 dB",
        "proposed": {"burst_centroid_hz": [400, 1600], "burst_tilt_db_min": 6,
                     "vot_ms": [0, 40]},
        "gating": True,
    },
    "transition": {
        "what": "the defining cue: F2 RISES into the vowel from a low bilabial "
                "locus. Rising F2 is what makes it /b/ rather than /d/ or /g/",
        "measured": "median F2 slope +842 Hz/s - and this was NOT selected for, "
                    "the group was chosen on burst shape alone, so it is real "
                    "evidence rather than circular",
        "caveat": "per-token variance is enormous (sd ~18,500 Hz/s, p25/p75 "
                  "straddle zero). The median points the right way; slope must "
                  "NEVER gate an individual token.",
        "gating": False,
    },
    "vowel": {
        "what": "the /a/ after the stop must independently pass all four rung-1 "
                "gates. No skipping rungs.",
        "gating": True,
    },
}

EXTRA_GATES_GA = {
    "closure": {
        "what": "tongue dorsum sealed against the velum; typically shorter than "
                "bilabial closure",
        "measured": "Iddo n=167: median 67.5 ms (p25-p75 50-97.5)",
        "gating": True,
    },
    "burst": {
        "what": "STRONG and COMPACT, mid-frequency. Unlike /b/ there IS a cavity "
                "in front of the constriction and it resonates, concentrating "
                "burst energy into a single mid peak",
        "measured": "centroid median 2044 Hz vs 1160 Hz for bilabial - a full "
                    "880 Hz of separation; tilt +14 dB vs +27 dB",
        "proposed": {"burst_centroid_hz": [1500, 3000], "burst_tilt_db_max": 20,
                     "vot_ms": [10, 60]},
        "gating": True,
    },
    "transition": {
        "what": "F2 FALLS into /a/ from a high onset - the opposite direction "
                "to /ba/",
        "measured": "median F2 slope -1527 Hz/s, not selected for",
        "caveat": "same per-token variance problem as /ba/; median only",
        "gating": False,
    },
    "velar_pinch": {
        "what": "F2 and F3 converge at release, then separate. THE defining cue "
                "of a velar, scored as exp(-|F3-F2|/900)",
        "measured": "MEASUREMENT FAILED on real speech: 0.3 velar vs 0.3 "
                    "bilabial, no separation at all. The identical code returns "
                    "0.60 vs 0.20 on synthetic tokens with a known pinch, so the "
                    "metric is sound and the EXTRACTION is not - the pinch "
                    "relaxes within 20-30 ms of release while the earliest "
                    "resolvable frame is ~14 ms into the vowel.",
        "required_fix": "measure the pinch AT the burst by short-time spectral "
                        "analysis of the 5-15 ms release transient, not from the "
                        "voiced formant track; or obtain phone-aligned tokens",
        "gating": False,
    },
    "vowel": {"what": "the /a/ must independently pass rung 1", "gating": True},
}


def judge_ba(x, sr=16000, *, production_module=None, codebook=None):
    """Rung 2 - /ba/. NOT IMPLEMENTED. Rung 1 first; nobody skips.

    Signature is fixed here so the shape of the work is unambiguous. The four
    rung-1 gates apply unchanged to the vowel portion, plus EXTRA_GATES_BA:
    closure (40-140 ms of near-silence), burst (present, centroid 400-1600 Hz,
    tilt >= 6 dB, VOT 0-40 ms) and transition (F2 rising from a low bilabial
    locus - measured but NOT gating, because per-token slope variance is larger
    than the effect).
    """
    raise NotImplementedError(
        "rung 2 (/ba/) is not open: rung 1 (/a/) has not been passed by any "
        "candidate yet. Nobody skips a rung.")


def judge_ga(x, sr=16000, *, production_module=None, codebook=None):
    """Rung 3 - /ga/. NOT IMPLEMENTED, and the weakest-supported rung.

    Same four rung-1 gates on the vowel, plus EXTRA_GATES_GA: closure
    (40-120 ms), burst (centroid 1500-3000 Hz, tilt <= 20 dB, VOT 10-60 ms),
    transition (F2 falling - not gating), and velar_pinch, which is NOT GATING
    and must not become gating until the extraction failure documented in
    EXTRA_GATES_GA is fixed. Gating on a metric that cannot separate velar from
    bilabial on real speech would be exactly the sin this whole module exists to
    end: a number standing in for a sound.
    """
    raise NotImplementedError(
        "rung 3 (/ga/) is not open: rungs 1 and 2 come first, and the velar "
        "pinch extraction is still broken on real speech.")


# ==========================================================================
# Self-measurement of the empirical detector (used to fill the doc numbers)
# ==========================================================================
def measure_detector(codebook, frame=400, hop=200, seed=1):
    """Run the three reference cases and return the measured SNRs."""
    import glottis
    rng = np.random.default_rng(seed)
    ids = rng.integers(0, len(codebook), 24)
    exact = looks_like_replay(overlap_add(codebook[ids], hop),
                              codebook, frame, hop)[1]
    synth = glottis.articulate_vowel(
        f0_hz=AH_TARGET["f0_median_hz"],
        formants_hz=(AH_TARGET["F1"], AH_TARGET["F2"], 2600.0),
        duration_s=0.40, sr=16000, seed=5)
    honest = looks_like_replay(synth, codebook, frame, hop)[1]
    xf = crossfade(codebook[3], codebook[17], overlap=frame // 8)
    fade = looks_like_replay(xf, codebook, frame, hop)[1]
    return {"exact_ola_replay_snr_db": exact,
            "source_filter_synth_snr_db": honest,
            "crossfaded_two_frame_snr_db": fade,
            "threshold_db": GATES["replay_snr_db"]}
