# -*- coding: utf-8 -*-
"""audioqc.py -- pure-numpy quality metrics for 16 kHz mono audio.

numpy only (numpy>=1.26,<3). No torch, no scipy.

Thresholds were calibrated on:
  * known-good speech : voice-ant-farm/recordings (the current 253 s corpus)
  * known music       : eran-audio/heard_music_wav/{bach,hamalach}
  * known silence     : eran-audio/heard_a70/*
NOTE: synthetic ant/Eran babble PASSES these metrics by design -- it imitates
speech. Synthetic material must be excluded by PATH, never by metric.
"""
import numpy as np

SR = 16000
WIN = 400          # 25 ms
HOP = 160          # 10 ms
EPS = 1e-12


def _frame(x, win=WIN, hop=HOP):
    if len(x) < win:
        x = np.pad(x, (0, win - len(x)))
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def frame_energy_db(x, sr=SR):
    F = _frame(x)
    w = np.hamming(WIN)
    Fw = F * w
    e = np.sum(Fw * Fw, axis=1) / WIN
    return 10.0 * np.log10(e + EPS), F, Fw


def frame_energy_db_streaming(x, win=WIN, hop=HOP, chunk_frames=20000):
    """Memory-safe frame energy for arbitrarily long signals.

    Materialising (n_frames, 400) for an 83-minute file would need ~GB; this
    walks the signal in blocks and only ever keeps the energy envelope.
    """
    n = 1 + (len(x) - win) // hop if len(x) >= win else 0
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    out = np.empty(n, dtype=np.float64)
    w = np.hamming(win).astype(np.float32)
    i = 0
    while i < n:
        k = min(chunk_frames, n - i)
        s0 = i * hop
        s1 = (i + k - 1) * hop + win
        blk = np.ascontiguousarray(x[s0:s1], dtype=np.float32)
        V = np.lib.stride_tricks.sliding_window_view(blk, win)[::hop]
        V = V[:k] * w
        out[i:i + k] = np.sum(V.astype(np.float64) ** 2, axis=1) / win
        i += k
    return 10.0 * np.log10(out + EPS)


def analyze(x, sr=SR):
    """x: float mono in [-1,1]. Returns dict of metrics."""
    x = np.asarray(x, dtype=np.float32)
    out = {}
    n = len(x)
    out['duration'] = n / float(sr)
    if n < WIN:
        out['empty'] = True
        out['rms_dbfs'] = -120.0
        return out

    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    out['peak'] = peak
    out['rms_dbfs'] = 20.0 * np.log10(rms + EPS)
    out['dc_offset'] = float(np.mean(x))

    # ---- clipping: runs of >=3 consecutive samples at the rail ----
    at_rail = np.abs(x) >= 0.992
    out['clip_frac'] = float(np.mean(at_rail))
    if at_rail.any():
        d = np.diff(np.concatenate(([0], at_rail.astype(np.int8), [0])))
        runs = np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
        out['clip_runs_ge3'] = int(np.sum(runs >= 3))
        out['clip_frac_runs'] = float(np.sum(runs[runs >= 3]) / n)
    else:
        out['clip_runs_ge3'] = 0
        out['clip_frac_runs'] = 0.0

    edb, F, Fw = frame_energy_db(x, sr)
    nf = float(np.percentile(edb, 10))
    sp = float(np.percentile(edb, 95))
    out['noise_floor_db'] = nf
    out['speech_level_db'] = sp
    out['snr_db'] = sp - nf          # envelope dynamic range; music sits near 0

    thr = nf + max(6.0, 0.35 * (sp - nf))
    active = edb > thr
    out['speech_frac'] = float(np.mean(active))

    # ---- voicing: FFT autocorrelation, batched over active frames ----
    lag_lo = int(sr / 400.0)   # 40  -> 400 Hz
    lag_hi = int(sr / 70.0)    # 228 -> 70 Hz
    act_idx = np.flatnonzero(active)
    if len(act_idx) > 600:
        act_idx = act_idx[np.linspace(0, len(act_idx) - 1, 600).astype(int)]
    if len(act_idx):
        A = F[act_idx].astype(np.float32)
        A = A - A.mean(axis=1, keepdims=True)
        d0 = np.sum(A * A, axis=1)
        keep = d0 > 1e-9
        A, d0 = A[keep], d0[keep]
    else:
        A = np.zeros((0, WIN), np.float32)
    if len(A):
        nfft = 1 << int(np.ceil(np.log2(2 * WIN)))
        P = np.abs(np.fft.rfft(A, n=nfft, axis=1)) ** 2
        ac = np.fft.irfft(P, n=nfft, axis=1)[:, :WIN]
        seg = ac[:, lag_lo:lag_hi + 1]
        k = np.argmax(seg, axis=1)
        vp = seg[np.arange(len(seg)), k] / d0
        f0 = sr / (lag_lo + k).astype(np.float64)
        voiced = vp > 0.35
        out['voiced_frac'] = float(np.mean(voiced))
        out['ac_peak_mean'] = float(np.mean(vp))
        if voiced.any():
            fv = f0[voiced]
            out['f0_median'] = float(np.median(fv))
            out['f0_iqr'] = float(np.percentile(fv, 75) - np.percentile(fv, 25)) if len(fv) > 3 else 0.0
        else:
            out['f0_median'] = 0.0
            out['f0_iqr'] = 0.0
    else:
        out.update(voiced_frac=0.0, ac_peak_mean=0.0, f0_median=0.0, f0_iqr=0.0)

    # ---- syllabic (2-8 Hz) modulation of the energy envelope ----
    env = edb - edb.mean()
    L = len(env)
    if L >= 64:
        se = np.abs(np.fft.rfft(env * np.hanning(L)))
        fe = np.fft.rfftfreq(L, d=HOP / float(sr))    # envelope rate = 100 Hz
        band = (fe >= 2.0) & (fe <= 8.0)
        ref = (fe >= 0.3) & (fe <= 20.0)
        out['mod_2_8_ratio'] = float(np.sum(se[band] ** 2) / (np.sum(se[ref] ** 2) + EPS))
        out['mod_peak_hz'] = float(fe[ref][int(np.argmax(se[ref]))]) if ref.any() else 0.0
    else:
        out['mod_2_8_ratio'] = 0.0
        out['mod_peak_hz'] = 0.0

    # ---- spectral behaviour ----
    S = np.abs(np.fft.rfft(Fw, axis=1)).astype(np.float32) + 1e-7
    freqs = np.fft.rfftfreq(WIN, 1.0 / sr)
    Pw = S ** 2
    cen = (Pw * freqs).sum(1) / Pw.sum(1)
    if active.sum() > 5:
        ca = cen[active]
        out['centroid_mean'] = float(np.mean(ca))
        out['centroid_cv'] = float(np.std(ca) / (np.mean(ca) + EPS))
        Pa = Pw[active]
        out['flatness_mean'] = float(np.mean(np.exp(np.mean(np.log(Pa), 1)) / (np.mean(Pa, 1) + EPS)))
    else:
        out.update(centroid_mean=0.0, centroid_cv=0.0, flatness_mean=0.0)
    out['lowband_ratio'] = float(Pw[:, freqs <= 4000].sum() / (Pw.sum() + EPS))
    return out


# ------------------------- accept / reject policy -------------------------
MIN_DUR = 1.0
MIN_RMS_DBFS = -48.0
MAX_CLIP_RUN_FRAC = 0.005
MIN_SNR_DB = 12.0
MIN_SPEECH_FRAC = 0.10
MIN_VOICED_FRAC = 0.12
MIN_MOD_2_8 = 0.07
MOD_MIN_DUR = 4.0          # envelope FFT is unreliable on very short clips


def verdict(m):
    """Return (ok, reason)."""
    if m.get('empty') or m.get('duration', 0.0) < MIN_DUR:
        return False, 'too_short'
    if m.get('rms_dbfs', -120.0) < MIN_RMS_DBFS:
        return False, 'silence_low_level'
    if m.get('clip_frac_runs', 0.0) > MAX_CLIP_RUN_FRAC:
        return False, 'clipped'
    if m.get('speech_frac', 0.0) < MIN_SPEECH_FRAC:
        return False, 'no_speech_activity'
    if m.get('snr_db', 0.0) < MIN_SNR_DB:
        return False, 'low_snr_or_continuous'
    if m.get('voiced_frac', 0.0) < MIN_VOICED_FRAC:
        return False, 'not_speech_unvoiced'
    if m.get('duration', 0.0) >= MOD_MIN_DUR and m.get('mod_2_8_ratio', 0.0) < MIN_MOD_2_8:
        return False, 'not_speech_no_syllabic_rhythm'
    if (m.get('voiced_frac', 0.0) > 0.85 and m.get('centroid_cv', 1.0) < 0.40
            and m.get('snr_db', 99.0) < 20.0):
        return False, 'music_like'
    return True, 'ok'


# ------------------------- VAD segmentation (long-form) -------------------------
def segment_speech(x, sr=SR, max_len=20.0, min_len=1.0, merge_gap=0.35, pad=0.20):
    """Split a long recording into speech spans. Returns [(start_s, end_s), ...]."""
    edb = frame_energy_db_streaming(x)
    if len(edb) == 0:
        return []
    nf = float(np.percentile(edb, 10))
    sp = float(np.percentile(edb, 95))
    thr = nf + max(6.0, 0.35 * (sp - nf))
    a = (edb > thr).astype(np.int8)
    if not a.any():
        return []
    d = np.diff(np.concatenate(([0], a, [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    fps = sr / float(HOP)
    spans = [[s / fps, e / fps] for s, e in zip(starts, ends)]
    # merge spans separated by a short gap
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s - merged[-1][1] <= merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    dur = len(x) / float(sr)
    out = []
    for s, e in merged:
        s = max(0.0, s - pad)
        e = min(dur, e + pad)
        if e - s < min_len:
            continue
        # hard-split anything longer than max_len at its quietest interior frame
        while e - s > max_len:
            lo = int((s + max_len * 0.6) * fps)
            hi = min(int((s + max_len) * fps), len(edb) - 1)
            cut = (lo + int(np.argmin(edb[lo:hi + 1]))) / fps if hi > lo else s + max_len
            out.append((s, cut))
            s = cut
        if e - s >= min_len:
            out.append((s, e))
    return out
