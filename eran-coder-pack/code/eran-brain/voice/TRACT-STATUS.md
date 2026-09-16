> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ERAN's vocal tract — status 2026-08-23 16:00. NOT DONE.

Iddo, 14:34: *"אין טעם ללמד אותו הברות בלי פה ואוזן."* He was right; `voice/voice.py` was a
splicer, not a mouth. This file is the attempt at a real one. **It does not work yet.**

## PROVEN

**The delay line is correct.** An impulse fired into the ladder returns at exactly
`4(n-1)` samples for n = 8, 16, 32, 64, 124 — ratio **2.00 at every length, no drift**.
The waveguide propagates and reflects the way a tube must.

## FOUR ANALYSER BUGS FOUND, ALL MINE, ALL FIXED

1. **Spectral tilt.** Lip radiation differentiates (+6 dB/oct), so "the tallest peaks"
   were always the highest FREQUENCIES. Every tract, every vowel: ~3.7 kHz.
2. **No minimum separation.** After de-tilting, the three "formants" came back 15 Hz
   apart — three bins of one hill.
3. **Hand-rolled Levinson-Durbin.** Replaced with a direct Yule-Walker solve. (This one
   turned out NOT to be the cause: identical numbers before and after. Recorded because a
   fix that changes nothing is evidence, not waste.)
4. **The bandwidth gate was 700 Hz.** A real formant is 50–150 Hz wide. At 700 the gate
   passed LPC's junk poles: **pure white noise with no tube at all reported confident
   "formants" at 748 / 1392 / 2006 Hz.** Tightened to 220 Hz plus a pole-radius floor.

## THE MEASUREMENT THAT BROKE THE CASE OPEN

Running the glottal source **alone, with no tube**, through the same pipeline:

```
source only + lip differentiator :  1187 · 1961 · 2714 Hz
"/a/" through the whole tract    :  1202 · 1972 · 2714 Hz   <- the same numbers
```

**The "formants" were the source, not the tract.** Periodic excitation plus LPC returns
harmonics dressed as formants. Every vowel number printed before this was that artefact.
Excitation is now white noise: flat spectrum, so a peak in the output belongs to the filter.

## STILL BROKEN

With noise excitation and the tight gate, a uniform tube still reports F1 ≈ 900–1000 Hz for
n = 8 … 64, and /a/, /i/, /u/ come out within 20 Hz of each other. **Length still does not
move the resonance in the audible band, and shape still does not move it at all.**

One phantom peak survives on bare noise (748 Hz), so the analyser is cleaner but not clean.

## THE NEXT STEP, WRITTEN DOWN SO IT IS NOT RE-DERIVED

With `uniform` areas every reflection coefficient is **zero** — the tube has no internal
scattering at all and is a bare delay line between the glottis and the lips. So the uniform
case cannot show shape sensitivity even in principle, and its comb has equal-height peaks
at every odd multiple, which is exactly the kind of spectrum where LPC picks arbitrarily.

Test order for next session:
1. Compute the transfer function **analytically** from the reflection coefficients — no
   synthesis, no LPC, no source. If the analytic poles track length and shape, the tube is
   right and only the measurement chain is left.
2. Only then compare synthesis against it.

**Nothing here is to be reported to Iddo as "the mouth works" until length moves F1.**
