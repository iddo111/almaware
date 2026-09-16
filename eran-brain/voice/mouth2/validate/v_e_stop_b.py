# -*- coding: utf-8 -*-
"""v_e_stop_b.py -- gate (e): a stop consonant is a SILENCE and a BURST.

The 192-d cochlea could never hear one (mouth34's say_sequence warning);
the mouth could barely make one. This gate proves MOUTH v2 makes a real
/aba/: seal forms -> pressure builds (velum closed) -> release bursts at
the constriction -> voicing returns. Gates, on the rendered waveform:

1. CLOSURE: a contiguous stretch >= 30 ms with envelope <= -40 dB
   relative to the steady-vowel RMS.
2. BURST TIMING: the release transient leads the return of voicing by
   5-15 ms (a voiced stop's short VOT).

Artifacts saved next to this script: v_e_stop_aba.wav + spectrogram PNG.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import measure as M
import mouth2

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000


def envelope(y, sr=SR, win_s=0.005, hop_s=0.001):
    win = int(win_s * sr)
    hop = int(hop_s * sr)
    n = 1 + max(0, (y.size - win) // hop)
    t = np.arange(n) * hop_s + win_s / 2
    e = np.array([np.sqrt(np.mean(y[i * hop:i * hop + win] ** 2))
                  for i in range(n)])
    return t, e


def bandpass_fft(y, sr, lo, hi):
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(y.size, 1.0 / sr)
    Y[(f < lo) | (f > hi)] = 0.0
    return np.fft.irfft(Y, y.size)


def aba_gesture():
    """/aba/ with a short devoiced release phase: seal (voice bar 0.25)
    -> lips open while voicing stays low for ~10 ms -> voicing returns.
    A fully-voiced /b/ has VOT ~0 (measured: burst and voicing 3 ms
    apart); the gate asks for the 5-15 ms English-style timing, so the
    gesture holds voicing down through the release moment -- gesture
    TIMING, not mouth physics."""
    ka = mouth2.vowel_knots("a")
    return {
        "keyframes": [
            mouth2.keyframe(ka),                                    # /a/
            mouth2.keyframe(ka, c_pos=0.97, c_area=0.0, voicing=0.25),  # seal
            mouth2.keyframe(ka, voicing=0.25),                      # open, devoiced
            mouth2.keyframe(ka),                                    # voicing returns
            mouth2.keyframe(ka),                                    # hold
        ],
        "durations": [0.22, 0.09, 0.004, 0.024, 0.28],
        "f0_knots": [300.0, 285.0, 250.0],
        "tenseness_knots": [0.6, 0.6, 0.55],
    }


def main():
    g = aba_gesture()
    y = mouth2.say_gesture(g, seed=0)
    assert y is not None
    y = y.astype(np.float64)
    total = y.size / SR

    t, e = envelope(y)
    vow_sel = (t > total - 0.20) & (t < total - 0.05)
    vowel_rms = float(np.median(e[vow_sel]))
    thresh = vowel_rms * 10 ** (-40.0 / 20.0)

    # closure: longest sub-threshold stretch inside the utterance body
    body = (t > 0.10) & (t < total - 0.10)
    quiet = (e <= thresh) & body
    best_len, best_i0, cur = 0, -1, 0
    for i, q in enumerate(quiet):
        cur = cur + 1 if q else 0
        if cur > best_len:
            best_len, best_i0 = cur, i - cur + 1
    closure_ms = best_len * 1.0            # 1 ms hop
    t_close0 = t[best_i0] if best_i0 >= 0 else float("nan")
    t_close1 = t_close0 + closure_ms / 1000.0

    # burst: the FULL-BAND transient right after the closure. A first
    # version looked for a >1 kHz click and failed honestly: a bilabial
    # release radiates through a still-narrow lip opening into an
    # F1-dominated tract, so /b/ bursts are LOW-frequency-heavy
    # (classic labial acoustics) -- the transient shows as an envelope
    # spike-then-dip at closure offset, not as a high-band click.
    after = (t >= t_close1 - 0.002) & (t <= t_close1 + 0.015)
    t_burst = float(t[after][np.argmax(e[after])])

    # voicing onset: low-band envelope back above half its vowel level,
    # sustained 20 ms
    lo = bandpass_fft(y, SR, 60.0, 700.0)
    tl, el = envelope(lo)
    vow_lo = float(np.median(el[(tl > total - 0.20) & (tl < total - 0.05)]))
    onset = None
    need = 20
    run = 0
    for i in range(tl.size):
        if tl[i] <= t_burst:
            continue
        run = run + 1 if el[i] >= 0.5 * vow_lo else 0
        if run >= need:
            onset = tl[i - need + 1]
            break
    vot_ms = (onset - t_burst) * 1000.0 if onset is not None else float("nan")

    print("GATE (e) -- stop /b/ in /aba/ (gesture space, seed 0)")
    print("  vowel rms %.4f; closure threshold (-40 dB) %.6f" % (vowel_rms, thresh))
    print("  closure: %.0f ms at <= -40 dB (gate >= 30 ms), t = %.3f-%.3f s"
          % (closure_ms, t_close0, t_close1))
    ok1 = closure_ms >= 30.0
    print("  burst at %.3f s; voicing onset at %s; burst leads voicing by "
          "%.1f ms (gate 5-15 ms)"
          % (t_burst, "%.3f s" % onset if onset else "NOT FOUND", vot_ms))
    ok2 = onset is not None and 5.0 <= vot_ms <= 15.0
    ok = ok1 and ok2
    print("  -> %s" % ("PASS" if ok else "FAIL"))

    M.save_wav(os.path.join(HERE, "v_e_stop_aba.wav"), y)
    M.spectrogram_png(os.path.join(HERE, "v_e_stop_aba.png"), y,
                      title="/aba/: closure %.0f ms, burst->voicing %.1f ms"
                            % (closure_ms, vot_ms))
    return {"gate": "e", "pass": bool(ok), "closure_ms": closure_ms,
            "vot_ms": vot_ms}


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["pass"] else 1)
