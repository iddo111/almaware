# -*- coding: utf-8 -*-
"""gates_v3.py -- Ear v3's calibrated structural gates + the splice lesson.

G1-G4: wired straight from ~/ear-v3/ear3-calib.json (calib.py calibrated
them ONCE on Iddo's real takes -- joint pass ah .95 / ba .97 / ih .95 /
ma .97 / abba .97 / ima .95; 6/6 archived v1 cheats fail the campaign
criterion). NOTHING IS RETUNED HERE: this module loads, checks, and
charges GATE_PENALTY=50 -- the fixed price no timbre can buy back
(the v1 "abba" scar: a weighted dim can be traded, a gate cannot).

G5 -- HNR, THE WALKIE-TALKIE LESSON (2026-08-26). Iddo's ears rejected
two review candidates the wdist objective liked: a 340 Hz robotic /ah/
("רע ברמות", pre-fence) and a 136 Hz /ah/ at wdist 5.12 that sounded
like "כחכוח של ווקי-טוקי" -- walkie-talkie crackle. Diagnosis: the t06
targets carry room noise and breath; wdist rewards matching that noise,
so the search learns to crackle. G5 is a deterministic
harmonics-to-noise-ratio gate calibrated on the REAL clips' own voiced
spans (calibrate_hnr(), thresholds in calib/hnr-calib.json): candidates
whose cleanest voicing is dirtier than 90% of Iddo's real takes pay the
same GATE_PENALTY. Judge unchanged; objective's structural term only.

Recipe (numpy only, no randomness): speech span by the stage-A rule
(10 ms windows, live > 10% of peak RMS, first to last); frames of 32 ms
every 10 ms inside the span; per frame the NORMALIZED autocorrelation
peak r in the 60-360 Hz lag band (exact normalization, FFT autocorr /
cumulative energies); frames with r > 0.3 are voiced and score
HNR = 10*log10(r/(1-r)); the clip's HNR = the 90th PERCENTILE over
voiced frames (-99.0 dB when no frame is voiced -- unvoiced fails).

WHY p90 AND NOT THE MEDIAN (measured 2026-08-26, the honest part):
on the clip-MEDIAN statistic the two rejected candidates sit INSIDE
the real distribution (robotic -1.08..-1.37 dB = the 37th percentile
of real ah takes; crackle -1.66..-1.67 = the 11th) -- failing both
would have cost 37% of Iddo's real voice. A real human take always
carries SOME cleanly voiced frames even in a noisy room (real ah
clip-p90: p10 = 1.42 dB, median 4.97); the noisy renders never voice
cleanly ANYWHERE (robotic p90 0.86-1.17, crackle p90 -0.49). So the
gated statistic is "the take's cleanest sustained voicing" and the
threshold is the 10th percentile of real takes (90% of real clips
pass -- tightened from the 5%/median plan and SAID SO, because the
5th-pct median gate verifiably failed NEITHER rejected candidate).

THE SPLICE LESSON (test_splice.py 2026-08-26): a real-/ah/ + silence +
real-/ah/ fake PASSED all four gates (spliced silence makes a perfect
dip) and was caught only by wdist. Its wdist was 11.74 = 3x the real
mean -- but a future cheat may land CLOSE. Hence the DISTANCE-SANITY
term: any candidate whose wdist comes in at or under REVIEW_RATIO x the
unit's real-clip mean -- i.e. anything that would qualify as a WIN -- is
auto-flagged into review/ (wav + full report) and marked
review_flagged=true. It is NEVER auto-celebrated; Iddo's listen is the
only promotion. Murmur-energy-inside-the-dip stays the named future
gate (now G8) if the splice cheat appears in the wild.

G6+G7 -- THE AIR-SQUEAK LESSON (2026-08-26, fence change 3). Iddo's
verdict on the best ma review candidate (ma-free-1, wdist 3.849):
"בסוף יש הרבה חריקת אוויר, והמָא קצר מדי" -- (1) a long air-squeak
after the voicing ends, (2) the ma itself too short against his real
ma. Two structural gates, calibrated per unit on the REAL t06 takes
(calib/duration-calib.json), judge unchanged:

  G6_duration -- MEASURED DEVIATION from the ordered recipe, in the
  open (the G3_LO_FLOOR precedent). The order said: speech-span
  duration (stage-A rule) within [p10, p90] of real takes. MEASURED
  2026-08-26: the rejected ma's span is 0.450 s = the 36th percentile
  of real ma spans -- the span does NOT separate, because Iddo's real
  takes trail off in long natural breath/murmur that keeps the span
  alive (real ma spans are bimodal, p10 0.34 / median 1.18). No honest
  percentile of span duration fails a candidate at the 36th pctile.
  What DOES separate is the STRONG-VOICED CORE duration: frames voiced
  per the exact G5 recipe AND frame RMS >= 25% of the take's peak
  frame RMS -- the part of the take you can actually hear as the unit.
  Rejected ma core: 0.182 s; real ma core p5 = 0.252 s; exactly 1 of
  100 real takes sits below the candidate. G6 = core_s within
  [p5, p95] of the real takes' core durations (p5/p95, not the ordered
  p10/p90, so the marginal real cost stays 10% -- SAID SO).

  G7_clean_tail -- as ordered: after the LAST voiced frame (voiced per
  the exact G5 recipe), the tail's RMS ratio (tail RMS from the end of
  that frame to the clip end, over the voiced-span RMS) must be <= p90
  of the real takes' same measure. HONEST FINDING (2026-08-26): this
  gate does NOT catch the rejected ma -- its squeak is QUIETER than
  Iddo's natural breath (tail_rms_ratio 0.115 = the 15th pctile of
  real; the ordered alternative, max 32ms-frame RMS vs voiced median,
  is 0.401 = also inside real). NEITHER ordered measure separates,
  and neither do tail tonal-fraction, tail centroid, or tail duration
  (all measured; real tails overlap the squeak on every one). The
  squeaky-short candidate is caught by G6, decisively. G7 ships as
  the standing guard it CAN be: a render whose tail comes in LOUDER
  than his natural breath levels pays the penalty. Unvoiced clips get
  sentinel ratio 999.0.

G8 -- VOICED DOMINANCE (2026-08-26, same fence change). Iddo rejected
the best clean-era ah (ah-free-0, wdist 4.06): "אוויר ו-10% אה -- לא
ברור מה זה" -- mostly air, barely any vowel. Root cause: G5's clip
statistic is the p90 of voiced-frame HNRs, so a clip whose FEW best
frames voice cleanly passes even when most of the take is breath. G8
demands the take be DOMINATED by voicing, two conditions, both
calibrated per unit at p10 of the real takes (same calib file):
  (a) voiced_frac   -- voiced frames (G5 recipe) / all span frames
  (b) voiced_energy_share -- voiced frames' share of total span
      frame energy (sum of frame RMS^2 over voiced / over all)
Real takes carry their breath AROUND a dominant voiced core; a render
that is air with a vowel flicker fails one or both. No voiced frame
at all = 0.0 on both = fail (consistent with G5's unvoiced sentinel).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

EAR_DIR = os.path.expanduser("~/ear-v3")
if EAR_DIR not in sys.path:
    sys.path.insert(0, EAR_DIR)

from ear3 import calib as C                      # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
HNR_CALIB_PATH = os.path.join(_HERE, "calib", "hnr-calib.json")
DURTAIL_CALIB_PATH = os.path.join(_HERE, "calib", "duration-calib.json")

GATE_PENALTY = C.GATE_PENALTY                    # 50.0, the v2 convention
REVIEW_RATIO = 1.3                               # the campaign's own win bar

# ---- G5 recipe constants (frozen; changing any = a fence change) ----
HNR_FS = 16000
HNR_FRAME_S = 0.032          # 32 ms analysis frame
HNR_HOP_S = 0.010            # 10 ms hop
HNR_F_LO, HNR_F_HI = 60.0, 360.0   # pitch-lag search band (Hz)
HNR_VOICED_R = 0.3           # frames with r_peak above this are voiced
HNR_CLIP_PCT = 90.0          # clip stat = p90 of voiced-frame HNRs
                             # ("cleanest sustained voicing" -- see
                             # WHY p90 in the module docstring)
HNR_UNVOICED_DB = -99.0      # sentinel: no voiced frame at all

# ---- G6/G7 recipe constants (frozen; changing any = a fence change) ----
TAIL_SENTINEL = 999.0        # no voiced frame at all -> G7 fails
CORE_RMS_FRAC = 0.25         # G6 core frame: voiced AND rms >= 25% of the
                             # take's peak 32ms-frame RMS (-12 dB)

_GATES = None
_HNR = None
_DURTAIL = None


def load_gates():
    """The frozen per-unit thresholds. Loaded once, never retuned."""
    global _GATES
    if _GATES is None:
        _GATES = C.load_calib()["gates"]
    return _GATES


def load_hnr(path=HNR_CALIB_PATH):
    """The frozen per-unit G5 thresholds (calibrate_hnr wrote them once)."""
    global _HNR
    if _HNR is None:
        with open(path, encoding="utf-8") as f:
            _HNR = json.load(f)
    return _HNR


def load_durtail(path=DURTAIL_CALIB_PATH):
    """The frozen per-unit G6/G7 thresholds (calibrate_durtail wrote them)."""
    global _DURTAIL
    if _DURTAIL is None:
        with open(path, encoding="utf-8") as f:
            _DURTAIL = json.load(f)
    return _DURTAIL


def span_tail_stats(y, fs=HNR_FS):
    """G6/G7 statistics -- deterministic, scale-invariant, numpy only.

    span_s          speech-span duration (stage-A rule, seconds; diagnostic)
    core_s          STRONG-VOICED CORE duration: first to last frame that is
                    voiced (exact G5 recipe) AND has frame RMS >= 25% of the
                    take's peak frame RMS. The audible unit. G6's statistic.
    tail_rms_ratio  RMS(after last voiced frame .. clip end) / RMS(voiced span)
    tail_max_ratio  max 32ms-frame RMS in that tail / median voiced-frame RMS
    voiced_frac     voiced frames / all span frames          (G8a)
    voiced_energy_share  voiced frames' share of span frame energy (G8b)
    No voiced frame -> core_s 0.0, voiced_frac/share 0.0 and sentinel
    tail ratios (fails G6+G7+G8)."""
    x = np.asarray(y, dtype=np.float64)
    out = {"span_s": 0.0, "core_s": 0.0, "tail_rms_ratio": TAIL_SENTINEL,
           "tail_max_ratio": TAIL_SENTINEL,
           "voiced_frac": 0.0, "voiced_energy_share": 0.0}
    if x.size == 0:
        return out
    hop = int(round(fs * HNR_HOP_S))
    nf = x.size // hop
    s0 = 0
    span = x
    if nf > 0:
        fr = np.sqrt((x[:nf * hop].reshape(nf, hop) ** 2).mean(axis=1))
        idx = np.where(fr > float(fr.max()) * C.SPEECH_FRAC)[0]
        if len(idx) > 0:
            s0 = idx[0] * hop
            span = x[s0:(idx[-1] + 1) * hop]
    out["span_s"] = span.size / float(fs)
    frame = int(round(fs * HNR_FRAME_S))
    lmin = int(np.ceil(fs / HNR_F_HI))
    lmax = int(np.floor(fs / HNR_F_LO))
    starts = (range(0, span.size - frame + 1, hop) if span.size >= frame
              else [0])
    f_starts, f_rms, f_voiced = [], [], []
    for s in starts:
        seg = span[s:s + frame]
        m = seg.size
        if m <= lmin + 8:
            continue
        segz = seg - seg.mean()
        nfft = 1
        while nfft < 2 * m:
            nfft <<= 1
        sp = np.fft.rfft(segz, nfft)
        rr = np.fft.irfft(sp * np.conj(sp), nfft)[:m]
        c = np.concatenate(([0.0], np.cumsum(segz * segz)))
        hi = min(lmax, m - 8)
        lags = np.arange(lmin, hi + 1)
        denom = np.sqrt((c[m] - c[lags]) * c[m - lags]) + 1e-12
        r_peak = float(np.max(rr[lags] / denom))
        f_starts.append(s)
        f_rms.append(float(np.sqrt(np.mean(seg ** 2))))
        f_voiced.append(r_peak > HNR_VOICED_R)
    if not any(f_voiced):
        return out                # unvoiced clip: fails G6 (core 0) and G7
    f_starts = np.asarray(f_starts)
    f_rms = np.asarray(f_rms)
    f_voiced = np.asarray(f_voiced)
    # ---- G8 voiced dominance: fraction of frames + share of energy
    out["voiced_frac"] = float(f_voiced.mean())
    energy = f_rms ** 2
    tot = float(energy.sum())
    out["voiced_energy_share"] = (float(energy[f_voiced].sum()) / tot
                                  if tot > 0.0 else 0.0)
    # ---- G6 core: voiced AND loud (>= CORE_RMS_FRAC of peak frame RMS)
    core = f_voiced & (f_rms >= CORE_RMS_FRAC * float(f_rms.max()))
    if core.any():
        ci = np.where(core)[0]
        out["core_s"] = ((f_starts[ci[-1]] + frame) - f_starts[ci[0]]) \
            / float(fs)
    # ---- G7 tail: after the LAST voiced frame (pure G5 recipe voicing)
    vi = np.where(f_voiced)[0]
    v_end = s0 + int(f_starts[vi[-1]]) + frame   # clip-domain end
    voiced_span = x[s0 + int(f_starts[vi[0]]):v_end]
    vs_rms = float(np.sqrt(np.mean(voiced_span ** 2)))
    v_med = float(np.median(f_rms[vi]))
    tail = x[v_end:]
    if tail.size == 0 or vs_rms <= 0.0:
        out["tail_rms_ratio"] = 0.0
        out["tail_max_ratio"] = 0.0
        return out
    out["tail_rms_ratio"] = float(np.sqrt(np.mean(tail ** 2))) / (vs_rms
                                                                  + 1e-12)
    if tail.size >= frame:
        mx = max(float(np.sqrt(np.mean(tail[s:s + frame] ** 2)))
                 for s in range(0, tail.size - frame + 1, hop))
        # end-anchored frame too, so a squeal at the very clip end counts
        mx = max(mx, float(np.sqrt(np.mean(tail[-frame:] ** 2))))
    else:
        mx = float(np.sqrt(np.mean(tail ** 2)))
    out["tail_max_ratio"] = mx / (v_med + 1e-12)
    return out


def hnr_db(y, fs=HNR_FS):
    """Deterministic clip-level HNR in dB (see module docstring recipe).

    Scale-invariant (normalized autocorrelation), so raw wavs and
    SPL-gained renders measure identically."""
    x = np.asarray(y, dtype=np.float64)
    if x.size == 0:
        return HNR_UNVOICED_DB
    # speech span: the stage-A rule (ear3.calib.speech_span_rms's span)
    hop = int(round(fs * HNR_HOP_S))
    nf = x.size // hop
    if nf > 0:
        fr = np.sqrt((x[:nf * hop].reshape(nf, hop) ** 2).mean(axis=1))
        idx = np.where(fr > float(fr.max()) * C.SPEECH_FRAC)[0]
        if len(idx) > 0:
            x = x[idx[0] * hop:(idx[-1] + 1) * hop]
    frame = int(round(fs * HNR_FRAME_S))
    lmin = int(np.ceil(fs / HNR_F_HI))            # 45 @ 16 kHz
    lmax = int(np.floor(fs / HNR_F_LO))           # 266 @ 16 kHz
    starts = (range(0, x.size - frame + 1, hop) if x.size >= frame
              else [0])                           # short span = one frame
    vals = []
    for s in starts:
        seg = x[s:s + frame]
        m = seg.size
        if m <= lmin + 8:
            continue
        seg = seg - seg.mean()
        nfft = 1
        while nfft < 2 * m:
            nfft <<= 1
        sp = np.fft.rfft(seg, nfft)
        rr = np.fft.irfft(sp * np.conj(sp), nfft)[:m]
        c = np.concatenate(([0.0], np.cumsum(seg * seg)))
        hi = min(lmax, m - 8)
        lags = np.arange(lmin, hi + 1)
        denom = np.sqrt((c[m] - c[lags]) * c[m - lags]) + 1e-12
        r_peak = float(np.max(rr[lags] / denom))
        if r_peak > HNR_VOICED_R:
            r_peak = min(r_peak, 1.0 - 1e-6)      # cap: 60 dB ceiling
            vals.append(10.0 * np.log10(r_peak / (1.0 - r_peak)))
    if not vals:
        return HNR_UNVOICED_DB
    return float(np.percentile(vals, HNR_CLIP_PCT))


def gate_stats(aux, y=None):
    """features_with_aux() aux (+ the waveform for G5) -> gate statistics.

    Callers that pass y (run_worker) get the "hnr" stat and therefore the
    G5 check; callers that don't (legacy sanity paths) keep G1-G4 only."""
    gs = C.gate_stats(aux)
    if y is not None:
        gs["hnr"] = float(hnr_db(y))
        gs.update(span_tail_stats(y))    # span_s, tail_*_ratio (G6/G7)
    return gs


def check(unit, gs):
    """(all_pass, per-gate detail) against the frozen thresholds."""
    ok, detail = C.check_gates(unit, gs, load_gates())
    if "hnr" in gs:
        t = load_hnr()["units"].get(unit)
        if t is not None:
            detail = dict(detail)
            g5 = gs["hnr"] >= t["hnr_min"]
            if t.get("hnr_max") is not None:
                g5 = g5 and gs["hnr"] <= t["hnr_max"]
            detail["G5_hnr"] = bool(g5)
            ok = bool(ok and g5)
    if "core_s" in gs:
        try:
            dt = load_durtail()
        except FileNotFoundError:
            dt = None
        t = dt["units"].get(unit) if dt else None
        if t is not None:
            detail = dict(detail)
            g6 = t["dur_lo"] <= gs["core_s"] <= t["dur_hi"]
            key = dt["recipe"]["tail_measure"]
            g7 = gs[key] <= t["tail_max"]
            g8 = (gs["voiced_frac"] >= t["vf_min"]
                  and gs["voiced_energy_share"] >= t["ves_min"])
            detail["G6_duration"] = bool(g6)
            detail["G7_clean_tail"] = bool(g7)
            detail["G8_voiced_dominance"] = bool(g8)
            ok = bool(ok and g6 and g7 and g8)
    return ok, detail


def penalty(unit, gs):
    """0.0 or GATE_PENALTY. The search objective's structural term."""
    ok, _ = check(unit, gs)
    return 0.0 if ok else GATE_PENALTY


def review_flag(wd, stats):
    """True when a candidate scores WELL ENOUGH TO WIN (<= 1.3x real-clip
    mean). Winners go to the review folder for human ears, never to a
    headline. (Distance-sanity: the splice fake taught us gates alone
    cannot certify a win.)"""
    return wd <= REVIEW_RATIO * float(stats["real_wdist_mean"])


def calibrate_hnr(pct=10.0, write=True, path=HNR_CALIB_PATH):
    """Measure hnr_db (clip = p90 of voiced-frame HNRs) over every t06
    clip of the 6 big units; per unit hnr_min = the pct-th percentile,
    nudged down 1e-9 (the ima rounding scar). pct=10 is the HONEST
    TIGHTENING from the 5% house plan: at 5%/median the gate verifiably
    failed NEITHER rejected candidate (see module docstring); at
    10%/p90 it fails BOTH and 90% of real takes still pass."""
    from ear3 import features as F
    out = {"recipe": {"frame_s": HNR_FRAME_S, "hop_s": HNR_HOP_S,
                      "f_lo": HNR_F_LO, "f_hi": HNR_F_HI,
                      "voiced_r": HNR_VOICED_R,
                      "clip_stat_pct": HNR_CLIP_PCT,
                      "unvoiced_db": HNR_UNVOICED_DB,
                      "percentile": pct},
           "note": "G5 clean-voicing gate, calibrated 2026-08-26 on the "
                   "REAL t06 clips' voiced spans (walkie-talkie lesson: "
                   "wdist rewards the targets' room noise; this floor "
                   "pushes the search toward clean voicing). Clip stat = "
                   "p90 of voiced-frame HNRs; threshold = p10 of real "
                   "takes -- tightened from p5/median, which failed "
                   "neither rejected candidate (regression anchors: "
                   "robotic ah p90 0.86-1.17 dB, crackle ah p90 -0.49).",
           "units": {}}
    for u in C.UNITS:
        vals = np.array([hnr_db(F.read_wav(p)) for p in C.clips(u)])
        out["units"][u] = {
            "n_clips": int(vals.size),
            "hnr_min": float(np.percentile(vals, pct)) - 1e-9,
            "hnr_max": None,
            "real_p5": round(float(np.percentile(vals, 5.0)), 3),
            "real_p10": round(float(np.percentile(vals, 10.0)), 3),
            "real_min": round(float(vals.min()), 3),
            "real_median": round(float(np.median(vals)), 3),
            "real_p95": round(float(np.percentile(vals, 95.0)), 3),
            "real_max": round(float(vals.max()), 3),
        }
    if write:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    return out


def calibrate_durtail(dur_lo_pct=5.0, dur_hi_pct=95.0, tail_pct=90.0,
                      g8_pct=10.0, tail_measure="tail_rms_ratio", write=True,
                      path=DURTAIL_CALIB_PATH):
    """G6/G7 calibration on the REAL t06 clips (fence change 3).

    G6 window = [dur_lo_pct, dur_hi_pct] percentiles of the real takes'
    STRONG-VOICED CORE durations (core_s -- see the module docstring's
    measured deviation: span duration verifiably does NOT separate the
    rejected ma, core duration does), nudged 1e-9 outward (the ima
    rounding scar). G7 threshold = tail_pct percentile of the real
    takes' tail measure, nudged 1e-9 up. BOTH tail measures' and BOTH
    duration measures' distributions are recorded so the separation
    checks that made the choices stay auditable."""
    from ear3 import features as F
    out = {"recipe": {"span_rule": "stage-A (10ms windows, live > 10% of "
                                   "peak RMS, first to last)",
                      "voiced_rule": "exact G5 recipe (32ms/10ms frames, "
                                     "normalized autocorr peak r>0.3 in "
                                     "60-360 Hz lag band)",
                      "duration_measure": "core_s (strong-voiced core: "
                                          "voiced AND frame rms >= 25% of "
                                          "peak frame rms, first to last)",
                      "core_rms_frac": CORE_RMS_FRAC,
                      "tail": "from end of LAST voiced frame to clip end",
                      "tail_measure": tail_measure,
                      "tail_sentinel": TAIL_SENTINEL,
                      "dur_lo_pct": dur_lo_pct, "dur_hi_pct": dur_hi_pct,
                      "tail_pct": tail_pct, "g8_pct": g8_pct,
                      "g8": "voiced_frac >= vf_min AND voiced_energy_share "
                            ">= ves_min (both p10 of real takes; the "
                            "mostly-air ah lesson)"},
           "note": "G6 duration + G7 clean-tail gates, calibrated "
                   "2026-08-26 on the real t06 clips (air-squeak lesson: "
                   "Iddo rejected the best ma candidate, wdist 3.849 -- "
                   "trailing frication squeak after voicing, and too "
                   "short). MEASURED: span duration puts that candidate at "
                   "the 36th pctile of real ma (no separation); core "
                   "duration puts it below 99% of real takes. Neither "
                   "ordered tail measure separates it (squeak QUIETER than "
                   "his real breath: tail_rms 0.115 = real p15); G7 stands "
                   "as the louder-than-breath guard, G6 carries the catch.",
           "units": {}}
    for u in C.UNITS:
        rows = [span_tail_stats(F.read_wav(p)) for p in C.clips(u)]
        dur = np.array([r["core_s"] for r in rows])
        span = np.array([r["span_s"] for r in rows])
        t_rms = np.array([r["tail_rms_ratio"] for r in rows])
        t_max = np.array([r["tail_max_ratio"] for r in rows])
        vf = np.array([r["voiced_frac"] for r in rows])
        ves = np.array([r["voiced_energy_share"] for r in rows])
        chosen = {"tail_rms_ratio": t_rms, "tail_max_ratio": t_max}[
            tail_measure]

        def q(a, p):
            return round(float(np.percentile(a, p)), 4)

        out["units"][u] = {
            "n_clips": int(dur.size),
            "dur_lo": float(np.percentile(dur, dur_lo_pct)) - 1e-9,
            "dur_hi": float(np.percentile(dur, dur_hi_pct)) + 1e-9,
            "tail_max": float(np.percentile(chosen, tail_pct)) + 1e-9,
            "core_p5": q(dur, 5), "core_p10": q(dur, 10),
            "core_median": q(dur, 50), "core_p90": q(dur, 90),
            "core_p95": q(dur, 95), "core_min": round(float(dur.min()), 4),
            "core_max": round(float(dur.max()), 4),
            "span_p10": q(span, 10), "span_median": q(span, 50),
            "span_p90": q(span, 90),
            "tail_rms_median": q(t_rms, 50), "tail_rms_p90": q(t_rms, 90),
            "tail_rms_max": round(float(t_rms.max()), 4),
            "tail_maxfr_median": q(t_max, 50), "tail_maxfr_p90": q(t_max, 90),
            "tail_maxfr_max": round(float(t_max.max()), 4),
            "vf_min": float(np.percentile(vf, g8_pct)) - 1e-9,
            "ves_min": float(np.percentile(ves, g8_pct)) - 1e-9,
            "vf_min_real": q(vf, 0), "vf_p10": q(vf, 10),
            "vf_median": q(vf, 50),
            "ves_min_real": q(ves, 0), "ves_p10": q(ves, 10),
            "ves_median": q(ves, 50),
        }
    if write:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate-durtail":
        meas = sys.argv[2] if len(sys.argv) > 2 else "tail_rms_ratio"
        res = calibrate_durtail(tail_measure=meas)
        for u, t in res["units"].items():
            print("  %-5s core [%.3f, %.3f] s  tail_max %.4f (%s)  "
                  "vf>=%.3f ves>=%.3f  [rms med %.4f p90 %.4f max %.4f | "
                  "maxfr med %.4f p90 %.4f max %.4f]"
                  % (u, t["dur_lo"], t["dur_hi"], t["tail_max"], meas,
                     t["vf_min"], t["ves_min"],
                     t["tail_rms_median"], t["tail_rms_p90"],
                     t["tail_rms_max"], t["tail_maxfr_median"],
                     t["tail_maxfr_p90"], t["tail_maxfr_max"]))
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate-hnr":
        pct = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
        res = calibrate_hnr(pct=pct)
        for u, t in res["units"].items():
            print("  %-5s hnr_min %8.3f dB  (real min %7.3f p5 %7.3f "
                  "median %7.3f max %7.3f)"
                  % (u, t["hnr_min"], t["real_min"], t["real_p5"],
                     t["real_median"], t["real_max"]))
        sys.exit(0)
    g = load_gates()
    print("gates_v3: GATE_PENALTY=%.0f REVIEW_RATIO=%.1f" %
          (GATE_PENALTY, REVIEW_RATIO))
    for u, t in g.items():
        print("  %-5s joint_real_pass %.2f  min_dip %.4f  g3 [%.1f, %.0f]"
              % (u, t["joint_real_pass"], t["min_dip"], t["g3_lo"],
                 t["g3_hi"]))
    try:
        h = load_hnr()
        for u, t in sorted(h["units"].items()):
            print("  %-5s G5 hnr_min %.3f dB%s"
                  % (u, t["hnr_min"],
                     ("" if t.get("hnr_max") is None
                      else "  hnr_max %.3f dB" % t["hnr_max"])))
    except FileNotFoundError:
        print("  G5: no calib/hnr-calib.json yet -- run "
              "'python3 gates_v3.py calibrate-hnr'")
    try:
        d = load_durtail()
        meas = d["recipe"]["tail_measure"]
        for u, t in sorted(d["units"].items()):
            print("  %-5s G6 core [%.3f, %.3f] s  G7 tail_max %.4f (%s)  "
                  "G8 vf>=%.3f ves>=%.3f"
                  % (u, t["dur_lo"], t["dur_hi"], t["tail_max"], meas,
                     t["vf_min"], t["ves_min"]))
    except FileNotFoundError:
        print("  G6/G7: no calib/duration-calib.json yet -- run "
              "'python3 gates_v3.py calibrate-durtail'")
    print(json.dumps({"loaded_units": sorted(g)}, indent=None))
