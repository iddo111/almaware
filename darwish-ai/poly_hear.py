# -*- coding: utf-8 -*-
"""poly_hear.py — the ear for tokenizer v2: real audio -> a polyphonic Score.

לזכרו של לָאוֹר ז״ל.

THE FACT THAT SHAPES EVERYTHING HERE
-------------------------------------
**There is no Darwish MIDI.** The corpus is 324 stereo MP3 mixdowns (8.6 GB) of
dense psytrance. So a "tokenizer" for this corpus is really two machines glued
together, and they fail in different ways:

    (1) THE REPRESENTATION  — can the alphabet SAY what the music contains?
    (2) THE EAR             — can the transcriber HEAR it out of a mixdown?

poly_tok.py is (1) and is exactly testable: encode a note list, decode it, and
the notes must come back identical. This file is (2), and it is inherently
approximate. Keeping them in separate files is the point — when the round trip
degrades you can tell WHICH machine did it.

WHAT IS DELIBERATELY UNCHANGED FROM midi_lean.py
-------------------------------------------------
Tempo, grid, key and the three drum bands are computed with the SAME code path
and the SAME constants as v1 (120-160 BPM window, 65th-percentile drum
threshold, 45-260 Hz bass band for the key). That is not laziness: it makes the
v1-vs-v2 comparison a controlled experiment. The only things that change are
the ALPHABET and the PITCH DETECTOR. If harmony appears, it is not because the
grid moved.

WHAT IS NEW — HOW A SECOND PITCH IS FOUND
------------------------------------------
v1 ran one autocorrelation f0 over 45-260 Hz. That is monophonic by
construction: an autocorrelation peak is a single lag, so it can only ever
return one note, and 260 Hz is a ceiling that excludes every lead.

Here the spectrum is read twice, in the two ranges psytrance actually keeps its
voices in:

  BASS  40-300 Hz, still monophonic — and that is musically CORRECT, not a
        shortcut: a psytrance bassline is one voice by genre. What is new is
        that consecutive equal pitches are MERGED INTO ONE HELD NOTE, so the
        representation finally distinguishes a held root from sixteen
        re-attacks of it.

  MID/LEAD  C3-C7, POLYPHONIC, by harmonic salience (sub-harmonic summation):

        S(p) = sum over h=1..8 of  w^(h-1) * |X(h * f_p)|

        The bass note found above has its harmonic comb SUBTRACTED FIRST, so a
        bass fundamental at 55 Hz does not get re-reported as a "lead" at its
        3rd harmonic. Then pitches are picked greedily, and each pick's own
        comb is subtracted before the next pick, which is what stops one loud
        note from being heard as a chord of its own overtones.

        Octave ambiguity is the classic failure of SHS. Guard: a candidate p is
        rejected in favour of p-12 unless p's own fundamental bin actually
        carries energy — i.e. we require the fundamental to be present, not
        merely implied by the harmonics.

HONEST LIMITS, before the numbers rather than after
----------------------------------------------------
  * Dense psytrance mixdowns are the hardest transcription case there is: kick
    and bass share an octave by design, leads are layered and drenched in FX,
    everything is sidechained. Nobody's transcriber is exact here and this one
    is not either. roundtrip.py MEASURES the error instead of asserting quality.
  * MEASURED against ground truth by ear_truth.py, and these are the numbers,
    not a claim: on synthesised audio whose notes are known, pitch-class
    PRECISION is 0.95-1.00 on every polyphonic case and the drums-only case
    leaks 0.02 phantom pitches per step. RECALL of a held chord's notes is
    0.70-0.72 -- roughly seven notes in ten. So what this ear reports is real,
    and it is INCOMPLETE. A chord it reports is a chord that was played; a
    chord it misses is still missed.
  * The weakest case is a low monophonic bassline (P 0.76, R 0.66): kick and
    bass share the octave, exactly as the genre intends.
  * Velocity for pitched notes is not estimated at all.

numpy + scipy + ffmpeg, exactly like midi_lean.py. No torch, no librosa.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

import poly_tok as PT

SR = 22050
HOP = 256

# --- pitch search ranges -------------------------------------------------
BASS_LO_HZ, BASS_HI_HZ = 40.0, 300.0
BASS_MIDI_LO, BASS_MIDI_HI = 24, 62          # C1 .. D4
LEAD_MIDI_LO, LEAD_MIDI_HI = 48, 96          # C3 .. C7
N_HARM = 8
HARM_W = 0.84
MAX_POLY = 4                                  # pitches picked per frame
SALIENCE_FLOOR = 0.18                         # fraction of the frame's best pick
NFFT = 2048

# --- the gates that stop the detector inventing chords -------------------
# Added 2026-09-05 after ear_truth.py caught the first version reporting
# polyphony 3.93 on a DRUMS-ONLY track with no pitched note in it at all, and
# 3.69 on a strictly monophonic bassline. Relative salience alone will always
# pick MAX_POLY pitches, because there is always a best-of-the-noise. A pitch
# now has to clear three ABSOLUTE tests against the local spectral floor.
#
# The five constants below were not hand-tuned to taste. They were chosen by a
# 48-point grid search scored against ear_truth.py's ground truth, maximising
# mean F1 across the pitched cases MINUS the polyphony leaked into the
# drums-only case. PRECISION was preferred over recall on purpose: a
# hallucinated chord would teach the model harmony that Darwish never played,
# which is a worse failure than missing a note he did.
PEAK_PROM = 3.2        # fundamental must stand this far above the local floor
HARM_PROM = 1.7        # what counts as "this harmonic is present"
MIN_HARMONICS = 3      # a real note shows a fundamental and at least two partials
BG_MEDIAN_BINS = 41    # width of the running median that estimates the floor
FRAME_GATE_PCTL = 25   # frames quieter than this percentile carry no lead
BASS_AC_MIN = 0.55     # autocorrelation confidence for a bass note (v1 used 0.30)
BASS_GATE_PCTL = 45    # and the bass band must actually be sounding
SUB_STRENGTH = 0.90    # how much of a picked note's comb is removed before the
                       # next pick. Too high and the second voice of a chord is
                       # erased with the first; too low and one loud note is
                       # heard as a chord of its own overtones.


# ---------------------------------------------------------------- shared dsp
# Byte-for-byte the same estimators midi_lean.py uses, so the comparison is fair.

def decode(path, sr=SR):
    import subprocess
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(path),
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def _band(x, lo, hi, sr=SR, order=4):
    nyq = sr / 2.0
    lo = max(lo / nyq, 1e-4)
    hi = min(hi / nyq, 0.999)
    sos = butter(order, [lo, hi], btype="band", output="sos")
    return sosfiltfilt(sos, x)


def _env(x, hop=HOP):
    n = len(x) // hop
    if n == 0:
        return np.zeros(0)
    return np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)


def tempo_and_grid(x, sr=SR, hop=HOP, bpm_lo=120.0, bpm_hi=160.0):
    kick = _band(x, 40.0, 120.0, sr)
    env = _env(kick, hop)
    if len(env) < 100:
        raise RuntimeError("clip too short for a tempo estimate")
    d = np.diff(env, prepend=env[0])
    d[d < 0] = 0.0
    d = d - d.mean()
    fps = sr / hop
    lags = np.arange(int(fps * 60.0 / bpm_hi), int(fps * 60.0 / bpm_lo) + 1)
    ac = np.array([np.dot(d[:-l], d[l:]) for l in lags])
    beat_lag = float(lags[int(np.argmax(ac))])
    bpm = 60.0 * fps / beat_lag
    fold = np.zeros(int(round(beat_lag)))
    for i, v in enumerate(d):
        fold[i % len(fold)] += max(v, 0.0)
    phase = int(np.argmax(fold))
    step = beat_lag / 4.0
    grid = np.arange(phase, len(env) - 1, step)
    return bpm, grid.astype(np.float64), env


def _f0(seg, sr=SR, fmin=35.0, fmax=300.0):
    seg = seg - seg.mean()
    if np.sqrt(np.mean(seg ** 2)) < 1e-4:
        return 0.0
    ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(sr / fmax), min(int(sr / fmin), len(ac) - 1)
    if hi <= lo:
        return 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    return float(sr / lag) if ac[lag] > 0.3 else 0.0


def _f0_conf(seg, sr=SR, fmin=35.0, fmax=300.0, conf=BASS_AC_MIN):
    """_f0 with the confidence threshold exposed. v1 used 0.30, which accepts
    the kick drum as a pitch; the bass detector here demands 0.55."""
    seg = seg - seg.mean()
    if np.sqrt(np.mean(seg ** 2)) < 1e-4:
        return 0.0
    ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(sr / fmax), min(int(sr / fmin), len(ac) - 1)
    if hi <= lo:
        return 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    return float(sr / lag) if ac[lag] > conf else 0.0


def estimate_key(x, sr=SR):
    b = _band(x, 45.0, 260.0, sr)
    n = len(b) // 4096
    if n < 4:
        return 0
    hist = np.zeros(12)
    for i in range(n):
        f0 = _f0(b[i * 4096:(i + 1) * 4096], sr, 35.0, 260.0)
        if f0 > 0:
            hist[int(round(69 + 12 * np.log2(f0 / 440.0))) % 12] += 1
    return int(np.argmax(hist)) if hist.sum() else 0


# ---------------------------------------------------------------- polyphony

_MIDI_HZ = 440.0 * 2.0 ** ((np.arange(0, 128) - 69) / 12.0)


def _bin_of(freqs_hz, sr, nfft):
    return freqs_hz * nfft / sr


def _interp(mag, pos):
    """Linear interpolation into a magnitude spectrum at fractional bin pos."""
    i0 = np.floor(pos).astype(int)
    frac = pos - i0
    i1 = i0 + 1
    ok = (i0 >= 0) & (i1 < mag.size)
    out = np.zeros_like(pos)
    out[ok] = mag[i0[ok]] * (1 - frac[ok]) + mag[i1[ok]] * frac[ok]
    return out


class _Salience:
    """Sub-harmonic summation with greedy comb subtraction.

    Precomputes the harmonic bin table once, so the per-frame cost is a handful
    of gathers rather than a loop over pitches.
    """

    def __init__(self, sr=SR, nfft=NFFT, lo=LEAD_MIDI_LO, hi=LEAD_MIDI_HI):
        self.sr, self.nfft = sr, nfft
        self.pitches = np.arange(lo, hi + 1)
        f = _MIDI_HZ[self.pitches]
        h = np.arange(1, N_HARM + 1)[None, :]
        self.bins = _bin_of(f[:, None] * h, sr, nfft)        # [P, H]
        self.w = HARM_W ** (h[0] - 1)
        self.fund_bin = self.bins[:, 0]
        nyq_bin = nfft // 2
        self.valid = self.bins < (nyq_bin - 1)

    def frame(self, mag, bg, max_poly=MAX_POLY):
        """-> list of MIDI pitches sounding in this frame.

        `bg` is this frame's own spectral noise floor. Every test below is
        against THAT, not against the other candidates -- which is the whole
        difference between measuring polyphony and allocating it.
        """
        work = mag.copy()
        prom_all = mag / np.maximum(bg, 1e-9)
        picked = []
        first_score = None
        for _ in range(max_poly):
            b = self.bins.reshape(-1)
            vals = _interp(work, b).reshape(self.bins.shape)
            vals = np.where(self.valid, vals, 0.0)
            score = (vals * self.w[None, :]).sum(axis=1)
            j0 = int(np.argmax(score))
            s = float(score[j0])
            if s <= 0:
                break
            if first_score is None:
                first_score = s
            elif s < SALIENCE_FLOOR * first_score:
                break
            j = self._octave_correct(prom_all, j0)
            if j is None:
                _subtract(work, self.bins[j0], self.w)
                continue
            p = int(self.pitches[j])
            if p not in picked:
                picked.append(p)
            _subtract(work, self.bins[j], self.w)
        return picked

    def _prom(self, prom_all, bins):
        """Prominence at each harmonic, taking the best of the neighbouring
        bins so a note slightly off 12-TET is not thrown away."""
        out = np.zeros(bins.size)
        for k, bb in enumerate(bins):
            i = int(round(bb))
            if i <= 0 or i >= prom_all.size:
                continue
            lo, hi = max(0, i - 1), min(prom_all.size, i + 2)
            out[k] = prom_all[lo:hi].max()
        return out

    def _is_real_note(self, prom_all, j) -> bool:
        """A fundamental standing above the local noise floor, plus at least
        MIN_HARMONICS partials that do too. Broadband noise -- a snare, a hat,
        an FX sweep -- passes neither test. That is what drums_only needed."""
        pr = self._prom(prom_all, self.bins[j][self.valid[j]])
        if pr.size == 0 or pr[0] < PEAK_PROM:
            return False
        return int((pr >= HARM_PROM).sum()) >= MIN_HARMONICS

    def _octave_correct(self, prom_all, j):
        """Sub-harmonic summation loves the octave below, and the first version
        of this method made that worse by preferring the lowest candidate that
        merely PASSED. A triad's root can pass one octave down, because the
        triad's own notes sit on that ghost's harmonics -- measured on
        ear_truth's triad case, recall 0.44.

        So: among the three octave candidates, take the one whose OWN
        FUNDAMENTAL is strongest. A ghost has no fundamental of its own; that
        is precisely what makes it a ghost."""
        best, best_f = None, 0.0
        for cand in (j - 12, j, j + 12):
            if not (0 <= cand < self.pitches.size):
                continue
            if not self._is_real_note(prom_all, cand):
                continue
            f = float(self._prom(prom_all, self.bins[cand][self.valid[cand]])[0])
            if f > best_f:
                best, best_f = cand, f
        return best


def _subtract(mag, bins, w, width=2):
    """Remove a pitch's harmonic comb so its overtones are not heard as a chord."""
    for k, b in enumerate(bins):
        i = int(round(b))
        if i <= 0 or i >= mag.size:
            continue
        lo, hi = max(0, i - width), min(mag.size, i + width + 1)
        mag[lo:hi] *= (1.0 - SUB_STRENGTH * w[k])


def _background(mag, w=BG_MEDIAN_BINS):
    """Running-median noise floor of a magnitude spectrum.

    A sinusoid occupies a few bins, so a median over a wide window is the floor
    UNDER it rather than the peak itself. One strided pass, not one median call
    per bin.
    """
    n = mag.size
    pad = w // 2
    m = np.pad(mag, pad, mode="edge")
    idx = np.arange(n)[:, None] + np.arange(w)[None, :]
    return np.median(m[idx], axis=1)


def _subtract_pitch(mag, midi, sr=SR, nfft=NFFT):
    f = _MIDI_HZ[int(np.clip(midi, 0, 127))]
    h = np.arange(1, N_HARM + 1)
    _subtract(mag, _bin_of(f * h, sr, nfft), HARM_W ** (h - 1))


# ---------------------------------------------------------------- the ear

def hear(path, max_seconds: float | None = None, verbose=False) -> PT.Score:
    """Real audio -> Score with polyphony and note durations."""
    x = decode(path)
    if max_seconds:
        x = x[: int(max_seconds * SR)]
    if len(x) < SR * 5:
        raise RuntimeError("clip under 5 s")

    bpm, grid, _ = tempo_and_grid(x)
    key = estimate_key(x)

    kick_e = _env(_band(x, 40.0, 120.0), HOP)
    body_e = _env(_band(x, 200.0, 2000.0), HOP)
    hat_e = _env(_band(x, 6000.0, 11000.0), HOP)
    bass_x = _band(x, BASS_LO_HZ, BASS_HI_HZ)

    def levels(e):
        return (float(np.percentile(e, 65)),
                float(np.percentile(e, 82)),
                float(np.percentile(e, 93)))

    lk, lb, lh = levels(kick_e), levels(body_e), levels(hat_e)
    win = int(HOP * 3)
    sal = _Salience()
    window = np.hanning(NFFT)

    # Absolute energy gates computed from THIS track rather than a constant, so
    # a quiet intro is not transcribed as a chord and a loud drop is not
    # rejected. Neither gate existed before ear_truth.py.
    lead_e = _env(_band(x, 250.0, 5000.0), HOP)
    lead_gate = float(np.percentile(lead_e, FRAME_GATE_PCTL))
    bass_e = _env(bass_x, HOP)
    bass_gate = float(np.percentile(bass_e, BASS_GATE_PCTL))

    drums: list[PT.Drum] = []
    bass_seq: list[int] = []          # midi per step, 0 = rest
    lead_frames: list[list[int]] = []

    n_steps = 0
    for i, g in enumerate(grid):
        f = int(round(g))
        if f >= len(kick_e):
            break
        n_steps = i + 1

        for which, e, lv in ((0, kick_e, lk), (1, body_e, lb), (2, hat_e, lh)):
            v = e[f]
            if v > lv[0]:
                drums.append(PT.Drum(i, which, 2 if v > lv[2] else (1 if v > lv[1] else 0)))

        s0 = f * HOP
        seg = bass_x[s0:s0 + win]
        bm = 0
        if len(seg) == win and bass_e[f] > bass_gate:
            f0 = _f0_conf(seg, SR, 35.0, BASS_HI_HZ, BASS_AC_MIN)
            if f0 > 0:
                m = int(round(69 + 12 * np.log2(f0 / 440.0)))
                if BASS_MIDI_LO <= m <= BASS_MIDI_HI:
                    bm = m
        bass_seq.append(bm)

        c0 = s0 - NFFT // 2
        if c0 < 0 or c0 + NFFT > len(x) or lead_e[f] <= lead_gate:
            lead_frames.append([])
            continue
        fr = x[c0:c0 + NFFT] * window
        mag = np.abs(np.fft.rfft(fr))
        if mag.max() <= 1e-9:
            lead_frames.append([])
            continue
        mag = mag / mag.max()
        if bm:
            _subtract_pitch(mag, bm)            # do not re-hear the bass as a lead
        lead_frames.append(sal.frame(mag, _background(mag)))

    notes: list[PT.Note] = []
    notes += _merge_runs([(i, m) for i, m in enumerate(bass_seq) if m], n_steps)
    notes += _merge_poly(lead_frames, n_steps)

    sc = PT.Score(round(bpm, 2), key, n_steps, notes, drums, str(path))
    return sc.normalised()


def _merge_runs(pairs, n_steps):
    """Consecutive equal pitches become ONE held note. This is where duration
    stops being a fiction: v1 could only ever emit a re-attack per sixteenth."""
    out = []
    if not pairs:
        return out
    start, cur, last = pairs[0][0], pairs[0][1], pairs[0][0]
    for i, m in pairs[1:]:
        if m == cur and i == last + 1:
            last = i
            continue
        out.append(PT.Note(start, cur, max(1, last - start + 1)))
        start, cur, last = i, m, i
    out.append(PT.Note(start, cur, max(1, last - start + 1)))
    return out


def _merge_poly(frames, n_steps):
    """Track each pitch across frames independently -> overlapping held notes."""
    out = []
    open_at: dict[int, tuple[int, int]] = {}       # midi -> (start, last_seen)
    for i, ps in enumerate(frames):
        for p in ps:
            if p in open_at:
                s, _ = open_at[p]
                open_at[p] = (s, i)
            else:
                open_at[p] = (i, i)
        for p in list(open_at):
            if p not in ps:
                s, last = open_at.pop(p)
                out.append(PT.Note(s, p, max(1, last - s + 1)))
    for p, (s, last) in open_at.items():
        out.append(PT.Note(s, p, max(1, last - s + 1)))
    return out


# ---------------------------------------------------------------- v1 control

def hear_v1(path, max_seconds: float | None = None) -> PT.Score:
    """midi_lean.py's ear and alphabet, decoded into the SAME Score type.

    This exists so the control is measured with the same ruler as the treatment
    rather than quoted from an old report. A v1 token carries no duration, so
    every note here is exactly one sixteenth long — which is the finding, not a
    limitation of this function.
    """
    x = decode(path)
    if max_seconds:
        x = x[: int(max_seconds * SR)]
    bpm, grid, _ = tempo_and_grid(x)
    key = estimate_key(x)
    kick_e = _env(_band(x, 40.0, 120.0), HOP)
    body_e = _env(_band(x, 200.0, 2000.0), HOP)
    hat_e = _env(_band(x, 6000.0, 11000.0), HOP)
    bass = _band(x, 45.0, 260.0)
    tk, tb, th = (float(np.percentile(e, 65)) for e in (kick_e, body_e, hat_e))
    win = int(HOP * 3)

    notes, drums = [], []
    n_steps = 0
    for i, g in enumerate(grid):
        f = int(round(g))
        if f >= len(kick_e):
            break
        n_steps = i + 1
        if kick_e[f] > tk:
            drums.append(PT.Drum(i, 0, 1))
        if body_e[f] > tb:
            drums.append(PT.Drum(i, 1, 1))
        if hat_e[f] > th:
            drums.append(PT.Drum(i, 2, 1))
        seg = bass[f * HOP:f * HOP + win]
        if len(seg) == win:
            f0 = _f0(seg, SR, 35.0, 260.0)
            if f0 > 0:
                # v1 stores deg = (round(midi) - key) % 12 + 1 -- the octave is
                # DESTROYED here. Reconstructing it is guesswork; the bug in
                # body/midi_out.py of 2026-09-05 came from exactly this.
                deg = int(round(69 + 12 * np.log2(f0 / 440.0)) - key) % 12
                notes.append(PT.Note(i, 36 + key + deg, 1))
    return PT.Score(round(bpm, 2), key, n_steps, notes, drums, str(path)).normalised()
