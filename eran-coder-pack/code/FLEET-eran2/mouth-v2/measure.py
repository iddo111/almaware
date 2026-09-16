# -*- coding: utf-8 -*-
"""measure.py -- measurement helpers for the MOUTH v2 validation gates.

MEASUREMENT CODE ONLY. The mouth itself (glottis/tract_core/mouth2)
stays pure numpy + one resample_poly; this file is what the validate/
scripts use to LOOK at renders, so it may use scipy.signal and
matplotlib freely -- it is never imported by the organ and never ships
to a worker.

Formant measurement is Welch peak-pick, NO LPC (the plan's order:
tract.py's formants() history shows LPC hides its own failure modes;
the ear judges spectra, so we measure spectra).

Resonances are measured with a WHITE-NOISE probe pushed through the
IDENTICAL tract path (tract_core.render + decimate_16k): a voiced
render's spectrum only samples the envelope at f0 harmonics (260 Hz
apart -- up to ~130 Hz quantization on a peak), so the noise probe is
the honest way to locate the resonances of the same rendering chain.
The voiced render is measured too where a gate asks for it.
"""
from __future__ import annotations

import os
import wave

import numpy as np
from scipy.signal import welch, find_peaks

import tract_core as T


def save_wav(path, y, sr=16000):
    y = np.asarray(y, dtype=np.float64)
    pcm = (np.clip(y, -1.0, 1.0) * 32767.0).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def spectrogram_png(path, y, sr=16000, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    y = np.asarray(y, dtype=np.float64)
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=110)
    ax.specgram(y, NFFT=512, Fs=sr, noverlap=384, cmap="magma",
                vmin=-110, vmax=-30)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("frequency [Hz]")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def psd_db(y, sr=16000, nperseg=4096):
    f, p = welch(np.asarray(y, float), fs=sr, nperseg=nperseg,
                 noverlap=nperseg // 2, window="hann")
    return f, 10.0 * np.log10(p + 1e-30)


def smooth_db(db, f, width_hz=60.0):
    """Moving-average smoothing of the log-PSD over ~width_hz."""
    df = f[1] - f[0]
    w = max(1, int(round(width_hz / df)))
    k = np.ones(w) / w
    return np.convolve(db, k, mode="same")


def spectral_peaks(y, sr=16000, n=3, fmin=250.0, fmax=None,
                   min_sep_hz=250.0, nperseg=4096, smooth_hz=60.0,
                   prominence_db=3.0):
    """Lowest-n spectral peaks of a render, Hz. Welch + smoothing +
    scipy find_peaks (distance + prominence) + parabolic refinement."""
    if fmax is None:
        fmax = sr / 2 - 200
    f, db = psd_db(y, sr, nperseg)
    s = smooth_db(db, f, smooth_hz)
    df = f[1] - f[0]
    sel = (f >= fmin) & (f <= fmax)
    idx0 = np.where(sel)[0][0]
    pk, _ = find_peaks(s[sel], distance=max(1, int(min_sep_hz / df)),
                       prominence=prominence_db)
    out = []
    for p in pk[:n]:
        i = idx0 + p
        if 0 < i < f.size - 1:
            d = s[i - 1] - 2 * s[i] + s[i + 1]
            off = 0.5 * (s[i - 1] - s[i + 1]) / d if d != 0 else 0.0
            out.append(float(f[i] + off * df))
        else:
            out.append(float(f[i]))
    return out


def noise_probe(area_track, velum_track, seconds=3.0, seed=12345,
                gain=0.05):
    """White-noise excitation through the IDENTICAL rendering path.
    Returns (lip16, nose16). Deterministic (own fixed-seed generator,
    separate from the mouth's streams -- this is a measuring stick,
    not part of the organ)."""
    n = int(round(seconds * T.FS_INTERNAL))
    rng = np.random.Generator(np.random.PCG64(seed))
    white = rng.standard_normal(n) * gain
    voiced = np.zeros(n)
    noise_mod = np.full(n, 0.3)          # PT's unvoiced modulator floor
    lip, nose = T.render(area_track, velum_track, voiced, white,
                         noise_mod, seed, __import__("mouth2").NOSE_AREAS)
    return T.decimate_16k(lip), T.decimate_16k(nose)


def track_for(areas_n, seconds):
    """Constant area track of the right block count for `seconds`."""
    n_blocks = int(np.ceil(seconds * T.FS_INTERNAL
                           / (T.BLOCK_S * T.FS_INTERNAL)))
    n_blocks = int(np.ceil(round(seconds * T.FS_INTERNAL)
                           / round(T.BLOCK_S * T.FS_INTERNAL)))
    return np.tile(np.asarray(areas_n, float), (n_blocks, 1)), \
        np.zeros(n_blocks)


def twin_transfer(areas_n, freqs, velum_area=0.0, nasal_areas=None):
    """analytic2's PHYSICAL transfer function computed for the ladder's
    ACTUAL terminations: r_end(f) = r0 * H_hf(f) where H_hf is the
    one-pole low-pass tract_core puts inside each end reflection. This
    is the honest twin of a tract_core render -- same discrete geometry
    (N sections of SECTION_CM), same frequency-dependent end
    reflectances (the source of the measured ~7% end correction; see
    tract_core.END_CORRECTION_SECTIONS). Branched math mirrors
    analytic2.transfer_function line for line.

    Returns dict {f, H_lip, H_nose} like analytic2.transfer_function."""
    import analytic2 as A2
    a = np.asarray(areas_n, dtype=float)
    N = a.size
    sec = np.full(N, T.SECTION_CM)
    f = np.asarray(freqs, dtype=float)
    w = 2 * np.pi * f

    a_hf = float(np.exp(-2.0 * np.pi * T.HF_POLE_HZ / T.FS_INTERNAL))
    H_hf = (1 - a_hf) / (1 - a_hf * np.exp(-2j * np.pi * f / T.FS_INTERNAL))
    r_g = T.GLOTTAL_REFLECT * H_hf
    r_l = T.LIP_REFLECT * H_hf

    zc_g = A2.RHO * A2.C_SOUND / a[0]
    zc_l = A2.RHO * A2.C_SOUND / a[-1]
    z_g = zc_g * (1 + r_g) / (1 - r_g)
    z_l = zc_l * (1 + r_l) / (1 - r_l)

    branched = (velum_area > 0.0 and nasal_areas is not None)
    if not branched:
        A, B, C, D = A2._chain_abcd(a, sec, w)
        H_lip = z_g / (z_g * (C * z_l + D) + (A * z_l + B))
        return {"f": f, "H_lip": H_lip, "H_nose": np.zeros_like(H_lip)}

    jn = int(np.clip(round((17.0 / 44.0) * N), 1, N - 2))
    A1, B1, C1, D1 = A2._chain_abcd(a[:jn], sec[:jn], w)
    A2m, B2m, C2m, D2m = A2._chain_abcd(a[jn:], sec[jn:], w)
    na = np.asarray(nasal_areas, dtype=float).copy()
    na[0] = velum_area
    nsec = np.full(na.size, T.SECTION_CM)
    Y_n, (An, Bn, Cn, Dn, z_nostril) = A2._branch_input_admittance(
        na, nsec, w, term_reflect=r_l)          # complex r works elementwise
    P_j = A2m * z_l + B2m
    U_after = C2m * z_l + D2m
    U_nasal = P_j * Y_n
    U_before = U_after + U_nasal
    P_g = A1 * P_j + B1 * U_before
    U_g = C1 * P_j + D1 * U_before
    U_src = U_g + P_g / z_g
    H_lip = 1.0 / U_src
    H_nose = (U_nasal / (Cn * z_nostril + Dn)) * H_lip
    return {"f": f, "H_lip": H_lip, "H_nose": H_nose}


def rms(y):
    y = np.asarray(y, float)
    return float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0


def db_rel(a, b):
    return 20.0 * np.log10(max(a, 1e-30) / max(b, 1e-30))
