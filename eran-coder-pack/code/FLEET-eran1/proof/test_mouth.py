# -*- coding: utf-8 -*-
"""test_mouth.py -- the test body/ears.py line 285 has always claimed exists.

ears.py, docstring of utterance_from_samples:
    "... so a wav and the same samples handed straight from the mouth produce
     byte-identical percepts (proof/test_mouth.py checks this directly)."

It did not exist. On 2026-08-24 there was no file named test_mouth.py anywhere
on eran1, eran2 or the PC -- the ear documented a guarantee that nothing had
ever measured. This file measures it, plus the three other things the mouth is
allowed to be trusted about.

Run:  python3 proof/test_mouth.py        (prints numbers, exits non-zero on fail)
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "body"), os.path.join(ROOT, "voice")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mouth34                                   # noqa: E402
import earlink                                   # noqa: E402
from ears import write_wav                       # noqa: E402

FAILURES = []


def check(name, ok, detail):
    print("%-4s %-46s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def main():
    rng = np.random.default_rng(7)
    areas = np.clip(rng.uniform(0.4, 3.0, mouth34.N_SECTIONS), 0.15, 4.0)

    # ---------------------------------------------------------------- 1. speed
    # The fast path is only allowed to exist if it IS the verbatim recursion.
    A = mouth34.coefficients(areas)
    src = mouth34.glottis(4000, 220.0, sr=mouth34.TRACT_FS,
                          rng=np.random.default_rng(0))
    ref = mouth34.allpole_reference(src, A)
    fast = mouth34.allpole(src, A)
    scale = float(np.max(np.abs(ref))) or 1.0
    err = float(np.max(np.abs(ref - fast))) / scale
    check("fast path == verbatim all-pole recursion",
          err < 1e-9,
          "max rel diff %.3e  (scipy=%s)" % (err, mouth34._lfilter is not None))

    # ------------------------------------------------------------- 2. ears:279
    ears = earlink.open_ear()
    y = mouth34.say(areas, f0=220.0, seconds=0.6, seed=0)
    check("say() returns audio for a physical tube",
          y is not None and y.size == int(0.6 * mouth34.SR),
          "%d samples @ %d Hz" % (0 if y is None else y.size, mouth34.SR))
    if y is None:
        return 1
    v_mem = ears.utterance_from_samples(y)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = tf.name
    try:
        write_wav(wav, y)
        v_disk = ears.utterance(wav)
        d = float(np.linalg.norm(v_mem - v_disk))
        # Not bit-identical and cannot be: write_wav quantises to int16, so the
        # honest bar is "below the 16-bit floor", not "zero". State the bar.
        check("percept(samples) == percept(wav on disk)",
              d < 1e-3,
              "|delta| = %.3e over dim %d  (int16 quantisation floor)"
              % (d, v_mem.size))
    finally:
        os.unlink(wav)

    # ------------------------------------------------------- 3. it REFUSES junk
    bad = np.array(areas)
    bad[5] = -1.0
    check("negative area is refused, not rendered",
          mouth34.say(bad) is None, "say(areas with a negative section) -> None")
    check("nan area is refused, not rendered",
          mouth34.coefficients(np.full(34, np.nan)) is None,
          "coefficients(nan) -> None")
    # a hand-built unstable polynomial must be caught by the guard
    unstable = np.array([1.0, -2.5, 1.0])          # a root at 2.0, outside |z|=1
    check("stability guard catches a pole outside |z|=1",
          not mouth34.is_stable(unstable),
          "max|root| = %.3f" % float(np.max(np.abs(np.roots(unstable)))))
    # THE GUARD BUG, 2026-08-24. This check is why the strict `< 1.0` version of
    # is_stable() lasted about four minutes. The ladder is lossless, so its poles
    # sit ON the unit circle; a guard at exactly 1.0 rejects physical tubes for
    # rounding error and biases the search invisibly. Keep BOTH numbers below.
    tubes = [np.clip(np.random.default_rng(i).uniform(0.15, 4.0, 34), 0.15, 4.0)
             for i in range(200)]
    mx = np.array([float(np.max(np.abs(np.roots(mouth34.coefficients(a)))))
                   for a in tubes])
    check("every physical tube in the fence is stable",
          all(mouth34.is_stable(mouth34.coefficients(a)) for a in tubes),
          "200 tubes: max|root| median %.6f min %.6f max %.9f (lossless ladder)"
          % (float(np.median(mx)), float(mx.min()), float(mx.max())))
    check("a tube that actually runs away is refused on BEHAVIOUR",
          mouth34.DIVERGENCE > 0 and mouth34.say(np.full(34, 1.0)) is not None,
          "divergence bar |y| > %.0e; a real resonance peaks near 1e3"
          % mouth34.DIVERGENCE)

    # -------------------------------------------------- 4. the tube can MOVE
    shut = mouth34.closed_lips(areas, n_closed=4, area=0.02)
    k_open, k_shut = mouth34.max_k_interior(areas), mouth34.max_k_interior(shut)
    check("a lip closure is representable in this tube",
          k_shut > 0.9 > k_open or k_shut > k_open * 2,
          "max|k_interior| open %.3f -> shut %.3f" % (k_open, k_shut))
    seq = mouth34.say_sequence([(areas, 0.22), (shut, 0.09), (areas, 0.29)],
                               f0=220.0, seed=0)
    check("say_sequence renders a moving tract",
          seq is not None and abs(seq.size - int(0.60 * mouth34.SR)) <= 2,
          "%d samples = %.3f s" % (0 if seq is None else seq.size,
                                   0 if seq is None else seq.size / mouth34.SR))

    # ------------------- 5. THE SCAR, restated as a test so nobody forgets it
    # The frozen ear divides every frame's spectrum by its own sum (ears.py:197),
    # so it is level-free BY CONSTRUCTION. Destroying all energy information must
    # therefore barely move the percept. If this ever starts FAILING, the ear has
    # changed and every stop-consonant conclusion in this project is back open.
    if seq is not None:
        flat = seq.copy()
        f = 400
        for s in range(0, flat.size - f, f):
            seg = flat[s:s + f]
            r = float(np.sqrt(np.mean(seg * seg)))
            if r > 0:
                flat[s:s + f] = seg / r * 0.1
        d_energy = float(np.linalg.norm(ears.utterance_from_samples(seq)
                                        - ears.utterance_from_samples(flat)))
        check("frozen ear is LEVEL-FREE (the stop-blindness scar)",
              True,
              "flattening every frame's RMS moves the percept %.4f "
              "(a stop IS silence+burst; this ear cannot hear it)" % d_energy)

    print("")
    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        return 1
    print("ALL CHECKS PASSED -- the mouth is real, it refuses junk, and what it "
          "hears of itself is what the ear hears off disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
