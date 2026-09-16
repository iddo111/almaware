# eran-mouth-v0 — ERAN learns LETTER -> MOUTH MOVEMENT (2026-09-03, claude-cli-MORE)

> BROKEN WINDOWS LAW: the numbers below are measured on rendered audio by the family checkers, not on file names.

**What it maps.** Input = a Hebrew letter (one-hot over the 21 taught syllables) + the four facts a child hears:
place {lips, tip, palate, back, glottal}, manner {vowel, stop, fricative, nasal, approximant, tap}, nasal 0/1, voiced 0/1.
Output = the 16-dim gesture vector for `mouth2.say_gesture` (order in `dataset.json` -> `feature_order`):
c_pos, c_area, velum, tenseness, voicing, d_pre, d_cons, d_trans, d_gap, gap_area, d_bridge, d_vowel, glide, burst_gain, knots_i, knots_ah4.
The vowel is always the shared /ah/ FIT knots; f0 knots [105,105,97.65]; tenseness knots [.6,.6,.55]; backend c, seed 0.
`teach.py: to_gesture(vector)` turns the vector into the gesture; `clean()` clips it into the renderer's legal space.

**Training data.** The 21 independently verified hand-made syllables in this folder (dataset.json, 21 rows).
Template fidelity: vector -> gesture -> render passes its own family checker for 21/21 (loo/selfcheck.json); the
tip/back/glottal renders are sample-identical to the hand-made wavs, lips/a/aya differ only by the f0-knot tail (98 vs 97.65 Hz).

**Contents of eran-mouth-v0.npz.**
- `mlp_*`  : 5-seed ensemble, numpy MLP 34->24(tanh)->16 on one-hot letter + class facts (standardised targets `mu`,`sd`)
- `mlpc_*` : the same MLP on the 13 class facts only (no letter)  <-- the best leave-one-out model
- `ridge_W`: additive ridge (lam 0.1) on the 13 class facts + bias
- `nn_table`: the 21 target vectors (nearest-neighbour baseline in class space; place 2, manner 2, nasal 1, voiced 1)
All fitted on all 21 syllables. Full model with the letter known reproduces 17/21 of its own lessons.

**LEAVE-ONE-SYLLABLE-OUT SCORE (hold one out, fit on 20, predict, RENDER with mouth2, judge with that syllable's own family checker):**

| model | passes |
|---|---|
| class-only MLP (`mlpc`) | **3 / 21** (ma, kha, cha) |
| ridge on class facts | 2 / 21 (ma, la) |
| nearest neighbour | 2 / 21 (kha<-cha, cha<-kha: the same gesture) |
| MLP letter+class (letter zeroed at test) | 0 / 21 |

**Why it fails (the finding).** Regression to the mean does not seal a mouth: a held-out stop is predicted with
c_area 0.2 (needs 0), a nasal with velum 0.52 (needs 0.75), plus a spurious 13 ms voiceless gap and a half-strength burst.
Twenty examples, one per class-combination, cannot teach the manner x place interaction; the physics needs exact points,
not averages. Nearest neighbour copies its neighbour's sound (ba<-pa, da<-ta, sa<-za), which the checker rightly refuses.
Per-syllable vectors, fails and measurements: loo/loo-results.json. Rendered predictions: loo/ERAN-<syl>-loo-{mlpc,mlp,ridge,nn}.wav.

Nothing here was played on any speaker. No abba/ima anywhere.
