# -*- coding: utf-8 -*-
"""simulate_voicebox.py — will the PRINTED throat actually phonate, and how will it sound?

Iddo's question (2026-08-25 10:00): "Once this thing is printed and you run air
through it — how does it sound? Does it work or not?" This answers it BEFORE
plastic and silicone are spent, with the standard physics used in voice science:

  SOURCE — the cast Ecoflex fold, as a Steinecke–Herzel two-mass model
  (the canonical reduced model of flow-induced vocal-fold self-oscillation),
  with mass and stiffness derived from OUR actual part, not from a human:
    * geometry: M5 fold from THROAT-MOLD-A (length 17 mm, medial depth ~9 mm,
      inferior–superior thickness ~8.4 mm; cast volume ≈ 1.15 cm³)
    * material: Ecoflex 00-30 — E ≈ 69 kPa nominal (published 50–125 kPa),
      ρ ≈ 1070 kg/m³. Sweep E ×0.5 / ×1 / ×2 to bracket the uncertainty.
    * k from shear-block estimate k = G·A/h (G ≈ E/3); m from ρ·V split 80/20
      between lower/upper mass, the classic two-mass proportion.
  FILTER — the printed tube: ERAN's own 34 cross-section areas (first keyframe
  of his best structured-abba trajectory = his vowel posture), as a
  Kelly–Lochbaum reflection-line — the same tube math his digital voice uses.

  HONEST LIMITS (say them, always):
   * source-filter is DEcoupled here; real tube loading shifts onset pressure
     and F0 some (usually helps phonation near resonance).
   * E of Ecoflex is a literature estimate, hence the ×0.5/×2 bracket.
   * one fold against a rigid collar wall (hemilarynx) ≈ symmetric two-fold
     model to first order; good enough for a go/no-go verdict.

Outputs: pressure-sweep verdict table (printed), fold-motion + spectrogram PNG,
and a WAV of the predicted sound at the design pressure (+200 hPa, Sawada's
number). Sacred Audio: writes the wav, never plays it.
"""
import numpy as np
import wave as wavemod

# ---------------- our part, in SI ----------------
L   = 17e-3          # fold length (m) — FOLD_LEN in make_real_mold.py
T   = 8.4e-3         # inferior–superior thickness (m) — M5 profile height
DEP = 4e-3           # sheared depth of the rubber block (m)
VOL = 1.15e-6        # cast volume (m^3) — mold cavity
RHO_SIL = 1070.0     # Ecoflex density kg/m^3
RHO_AIR = 1.2
E_NOM = 69e3         # Pa — Ecoflex 00-30 nominal Young's modulus

G0  = 0.5e-3         # rest half-gap to the collar wall (m) — mold/collar design
FS  = 44100

def fold_params(E):
    G = E / 3.0
    k_total = G * (L * T) / DEP          # shear-block stiffness, N/m
    m_total = RHO_SIL * VOL              # kg
    m1, m2 = 0.8 * m_total, 0.2 * m_total
    k1, k2 = 0.75 * k_total, 0.25 * k_total
    kc = 0.3 * k_total                   # inter-mass coupling, classic ratio
    return m1, m2, k1, k2, kc

def simulate_fold(Ps, E, seconds=0.8, fs=FS):
    """Steinecke–Herzel two-mass with collision; returns glottal flow U(t)."""
    m1, m2, k1, k2, kc = fold_params(E)
    z1, z2 = 0.1, 0.6                                  # damping ratios (S-H)
    r1 = 2 * z1 * np.sqrt(m1 * k1)
    r2 = 2 * z2 * np.sqrt(m2 * k2)
    c1, c2 = 3 * k1, 3 * k2                            # collision springs
    d1, d2 = 0.6 * T, 0.4 * T                          # mass heights
    x1 = x2 = v1 = v2 = 0.0
    n = int(seconds * fs); dt = 1.0 / fs
    U = np.zeros(n)
    for i in range(n):
        a1 = 2 * L * (G0 + x1)                         # glottal areas (both lips)
        a2 = 2 * L * (G0 + x2)
        amin = min(a1, a2)
        open_ = amin > 0
        # Bernoulli pressure on the lower mass while the duct is open
        if open_ and a1 > 0:
            P1 = Ps * (1 - (amin / a1) ** 2) if a1 > amin else 0.0
            P1 += Ps * 0.5 * (1 if a1 <= amin else 0)  # jet recovery on min section
        else:
            P1 = Ps                                    # closed: full push below
        F1 = L * d1 * P1
        F2 = 0.0                                       # upper mass: aero force ~0 (S-H)
        col1 = c1 * (-(G0 + x1)) * (1 if (G0 + x1) < 0 else 0)
        col2 = c2 * (-(G0 + x2)) * (1 if (G0 + x2) < 0 else 0)
        a1dd = (F1 - r1 * v1 - k1 * x1 - kc * (x1 - x2) + col1) / m1
        a2dd = (F2 - r2 * v2 - k2 * x2 - kc * (x2 - x1) + col2) / m2
        v1 += a1dd * dt; x1 += v1 * dt
        v2 += a2dd * dt; x2 += v2 * dt
        U[i] = (np.sqrt(2 * Ps / RHO_AIR) * amin) if amin > 0 else 0.0
    return U

def analyze(U, fs=FS):
    """(oscillating?, F0, modulation depth) from the steady half of U."""
    s = U[len(U) // 2:]
    if s.max() <= 0:
        return False, 0.0, 0.0
    ac = s - s.mean()
    depth = (s.max() - s.min()) / (s.max() + 1e-12)
    spec = np.abs(np.fft.rfft(ac * np.hanning(len(ac))))
    freqs = np.fft.rfftfreq(len(ac), 1 / fs)
    band = (freqs > 30) & (freqs < 1200)
    f0 = float(freqs[band][np.argmax(spec[band])]) if band.any() else 0.0
    osc = depth > 0.1 and f0 > 30
    return osc, f0, depth

# ---------------- the printed tube: Kelly–Lochbaum on ERAN's areas ----------
def kl_filter(source, areas, fs=FS, tube_len=0.1715):
    """Classic KL reflection line; areas in cm^2 (ERAN's convention)."""
    A = np.maximum(np.asarray(areas, float), 0.05)
    r = [(A[i + 1] - A[i]) / (A[i + 1] + A[i]) for i in range(len(A) - 1)]
    # section delay: tube_len/len(A) per section; resample source so one sample = one section pass
    c = 343.0
    fs_tube = c * len(A) / (2 * tube_len)              # two passes per section round trip
    n = int(len(source) * fs_tube / fs)
    src = np.interp(np.linspace(0, len(source) - 1, n), np.arange(len(source)), source)
    fwd = np.zeros(len(A)); bwd = np.zeros(len(A))
    out = np.zeros(n)
    r_glottis, r_lips = 0.9, -0.85
    for t in range(n):
        fwd_new = np.empty_like(fwd); bwd_new = np.empty_like(bwd)
        fwd_new[0] = src[t] + r_glottis * bwd[0]
        for j in range(len(A) - 1):
            f_in, b_in = fwd[j], bwd[j + 1]
            fwd_new[j + 1] = (1 + r[j]) * f_in - r[j] * b_in
            bwd_new[j] = r[j] * f_in + (1 - r[j]) * b_in
        bwd_new[-1] = r_lips * fwd[-1]
        out[t] = (1 + r_lips) * fwd[-1]
        fwd, bwd = fwd_new, bwd_new
    y = np.interp(np.linspace(0, n - 1, len(source)), np.arange(n), out)
    return y

def main():
    import json, glob
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("== fold parameters from OUR part ==")
    for tag, E in (("E x0.5", E_NOM / 2), ("E nominal", E_NOM), ("E x2", E_NOM * 2)):
        m1, m2, k1, k2, kc = fold_params(E)
        f_nat = np.sqrt(k1 / m1) / (2 * np.pi)
        print(f"  {tag:9s}: k1={k1:7.1f} N/m  m1={m1*1e3:.2f} g  f_nat≈{f_nat:5.1f} Hz")

    print("\n== pressure sweep (does it phonate?) ==")
    rows = []
    for E, etag in ((E_NOM / 2, "x0.5"), (E_NOM, "x1"), (E_NOM * 2, "x2")):
        for Ps in (500, 1000, 2000, 3000, 5000):
            U = simulate_fold(Ps, E)
            osc, f0, depth = analyze(U)
            rows.append((etag, Ps, osc, f0, depth))
            print(f"  E{etag:5s} Ps={Ps:5d} Pa -> {'OSCILLATES' if osc else 'silent   '} "
                  f"F0={f0:6.1f} Hz  depth={depth:.2f}")

    # design point: Sawada's +200 hPa = 2000 Pa, nominal E
    U = simulate_fold(2000, E_NOM, seconds=1.2)
    osc, f0, depth = analyze(U)
    src = np.diff(U, prepend=U[0])                     # radiated ~ dU/dt
    # ERAN's vowel posture: first keyframe of his best structured-abba trajectory
    bj = sorted(glob.glob(r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE"
                          r"\821d90a4-5eb6-4778-81c7-2d750c86fe02\scratchpad"
                          r"\bestjson\eran2\abba-0\best*.json"))
    areas = json.load(open(bj[0]))["keyframes"][0]["areas"] if bj else [3.0] * 34
    y = kl_filter(src, areas)
    y = y / (np.max(np.abs(y)) + 1e-12) * 0.7
    out = r"D:\CLAUDE\alma-larynx\SIM-voicebox-2kPa.wav"
    with wavemod.open(out, "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(FS)
        f.writeframes((y * 32767).astype(np.int16).tobytes())
    print(f"\ndesign point 2 kPa: {'OSCILLATES' if osc else 'SILENT'} F0={f0:.1f} Hz -> {out}")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4), facecolor="white")
    tt = np.arange(len(U)) / FS
    axes[0].plot(tt[:int(0.08*FS)], U[:int(0.08*FS)] * 1e6, lw=0.8)
    axes[0].set_title("glottal flow, first 80 ms (µL/s-ish)"); axes[0].set_xlabel("s")
    axes[1].specgram(y, NFFT=1024, Fs=FS, noverlap=768, cmap="magma", vmin=-90)
    axes[1].set_ylim(0, 4000); axes[1].set_title("predicted sound through ERAN's tube (0-4 kHz)")
    plt.suptitle(f"SIMULATED VOICEBOX — Ecoflex M5 fold @ 2 kPa: "
                 f"{'phonates' if osc else 'silent'}, F0≈{f0:.0f} Hz")
    plt.tight_layout()
    plt.savefig(r"D:\CLAUDE\alma-larynx\SIM-voicebox-report.png", dpi=110)
    print("saved SIM-voicebox-report.png")

if __name__ == "__main__":
    main()
