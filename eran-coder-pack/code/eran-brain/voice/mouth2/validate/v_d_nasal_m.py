# -*- coding: utf-8 -*-
"""v_d_nasal_m.py -- gate (d): the mouth can hum. /m/ = lips sealed,
velum open -- the sound ERAN could never make before (no nasal tract).

Configuration: neutral 60-month tract, lip seal (last two sections at
the area floor), velum 0.5 cm^2. Gates:

1. MURMUR: in the VOICED render, the band below 500 Hz holds more
   power than everything above it (low-band fraction > 0.5).
2. SHUNT: nostril output at least 30 dB above the sealed-lip oral
   output (RMS, voiced render).
3. ANTIFORMANT: the nose-output spectrum (noise probe) shows a dip
   >= 10 dB below its flanking maxima in the 500-2500 Hz region;
   the same-termination analytic twin's dip is printed next to it,
   plus Phase 0's 44-element prediction (1008 Hz / 39 dB) for scale.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import geometry
import measure as M
import mouth2
import tract_core as T

SECONDS_V = 0.8      # voiced murmur render
SECONDS_N = 6.0      # noise probe for the antiformant
VELUM = 0.5


def dip_in(f, db, lo=500.0, hi=2500.0):
    band = (f >= lo) & (f <= hi)
    ib = np.where(band)[0]
    i_min = ib[np.argmin(db[ib])]
    left = db[: i_min + 1].max()
    right = db[i_min:].max()
    return float(f[i_min]), float(min(left, right) - db[i_min])


def main():
    N = mouth2.N_MAIN
    _, a44 = geometry.child_area(mouth2.AGE_MONTHS)
    aN = geometry.resample_areas(a44, N)
    aN[-2:] = T.AREA_FLOOR                      # lip seal

    n_blocks, _ = mouth2._blocks(SECONDS_V)
    track = np.tile(aN, (n_blocks, 1))
    velum = np.full(n_blocks, VELUM)
    lip16, nose16 = mouth2._render(track, velum, SECONDS_V,
                                   [280.0] * 3, [0.6] * 3, seed=0,
                                   return_ports=True)

    y = lip16 + nose16
    f, db = M.psd_db(y, 16000, 2048)
    p_lin = 10 ** (db / 10)
    low = p_lin[(f > 0) & (f < 500)].sum()
    tot = p_lin[f > 0].sum()
    frac = low / tot
    r_lip = M.rms(lip16)
    r_nose = M.rms(nose16)
    shunt_db = M.db_rel(r_nose, r_lip)

    print("GATE (d) -- nasal /m/ (lips sealed, velum %.1f cm^2, N=%d)"
          % (VELUM, N))
    print("  murmur: power below 500 Hz = %.1f%% of total (gate > 50%%)"
          % (100 * frac))
    ok1 = frac > 0.5
    print("  shunt: nostril rms %.4f vs oral rms %.6f -> nose-over-oral "
          "%.1f dB (gate >= 30 dB)" % (r_nose, r_lip, shunt_db))
    ok2 = shunt_db >= 30.0

    # antiformant via noise probe through the same configuration
    track_n, _ = M.track_for(aN, SECONDS_N)
    velum_n = np.full(track_n.shape[0], VELUM)
    _, nose_probe16 = M.noise_probe(track_n, velum_n, seconds=SECONDS_N)
    fp, dbp = M.psd_db(nose_probe16, 16000, 8192)
    sm = M.smooth_db(dbp, fp, 40.0)
    f_dip, depth = dip_in(fp, sm)

    freqs = np.arange(100.0, 4000.0, 2.0)
    tf = M.twin_transfer(aN, freqs, velum_area=VELUM,
                         nasal_areas=mouth2.NOSE_AREAS)
    tdb = 20 * np.log10(np.abs(tf["H_nose"]) + 1e-30)
    f_dip_t, depth_t = dip_in(freqs, tdb)

    print("  antiformant (nose spectrum): dip at %.0f Hz, %.1f dB deep "
          "(gate >= 10 dB in 500-2500 Hz)" % (f_dip, depth))
    print("  same-termination twin dip:   %.0f Hz, %.1f dB "
          "(Phase-0 44-elem ideal prediction: 1008 Hz / 39 dB)"
          % (f_dip_t, depth_t))
    ok3 = depth >= 10.0 and 500.0 <= f_dip <= 2500.0

    ok = ok1 and ok2 and ok3
    print("  -> %s" % ("PASS" if ok else "FAIL"))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    M.save_wav(os.path.join(out, "v_d_nasal_m.wav"),
               0.7 * y / max(np.abs(y).max(), 1e-9))
    M.spectrogram_png(os.path.join(out, "v_d_nasal_m.png"), y,
                      title="/m/ murmur: lips sealed, velum %.1f cm2 "
                            "(dip %.0f Hz, %.1f dB)" % (VELUM, f_dip, depth))
    return {"gate": "d", "pass": bool(ok), "low_frac": frac,
            "shunt_db": shunt_db, "dip_hz": f_dip, "dip_db": depth,
            "twin_dip_hz": f_dip_t, "twin_dip_db": depth_t}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
