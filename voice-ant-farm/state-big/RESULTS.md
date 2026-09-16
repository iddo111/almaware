# Can they say /a/ now?

**Trained on 40.575 hours instead of 252.7 seconds — 578x more audio, all of it human,
none of it synthetic. On the headline test the answer is: no. It went from two of four
to zero of four.**

But the headline test turns out to be measuring the wrong thing, and once that is
corrected the answer flips to **four of four**. Both numbers are below, and the reason
they disagree is the most useful thing this run produced.

---

## 1. The headline table

Each ant's most vowel-like exemplar, selected by periodicity x low-band-energy ratio,
then F1/F2 by 12th-order LPC. `all-256` colony, 40.575 h.

| ant | before F1/F2 | before | after F1/F2 | after | unit | periodicity |
|---|---|---|---|---|---|---|
| ant-a | 660 / 1064 | **/a/** | 341 / 1759 | not /a/ — /i/ | 53 | 0.86 |
| ant-b | 392 / 1948 | not /a/ | 307 / 2234 | not /a/ — /i/ | 158 | 0.83 |
| ant-c | 348 / 1332 | not /a/ | 236 / 1324 | not /a/ — /u/ | 52 | 0.83 |
| ant-d | 660 / 1064 | **/a/** | 517 / 1030 | not /a/ — /o/ | 169 | 0.85 |

**2/4 → 0/4.** Target is F1 650-850, F2 1000-1400.

### The measurement is calibrated, so this is not a methodology artefact

Run on `state/` — the BEFORE ants — the identical code selects units 8/40/49/12 and
returns 660/1064, 392/1948, 348/1332, 660/1064: **all four brief values reproduce
exactly.** (The original estimator takes the two lowest LPC poles with no bandwidth
gate; a bandwidth gate would have discarded ant-a's 1064 Hz pole, which has a 447 Hz
bandwidth, and returned 2995 instead. That is documented in `scripts/exemplar_formants.py`.)

---

## 2. Why the headline says "no" — the selection rule steers away from /a/

`periodicity x low-band-energy ratio` is not an /a/ detector. It is a *close-vowel*
detector. /a/ has the highest F1 of any vowel, so it has the **least** energy
concentrated below 1 kHz — exactly what the score penalises. Across all 5 120 units
trained here:

| statistic | value |
|---|---|
| corr(low-band-energy ratio, F1) | **-0.585** |
| corr(selection score, F1) | **-0.526** |
| median F1 of the top 100 units by selection score | **435 Hz** |
| median F1 across all units | **870 Hz** |
| share of top-100-by-score in the /a/ band | **8.0 %** |
| share of *all* units in the /a/ band | **13.9 %** |

Selecting by "most vowel-like" makes you **less** likely to land on /a/ than picking a
unit at random. At 64 units the codebook was coarse enough that two ants got lucky; at
256 units there are far more high-scoring candidates and the bias dominates.

So "2/4 → 0/4" is not four ants getting worse. It is a fragile one-out-of-N argmax
being resolved differently in a bigger candidate pool by a rule that was never pointed
at /a/.

---

## 3. The corrected question: does the codebook *contain* an /a/?

Of the units that are clearly voiced (periodicity > 0.45), is there one inside the /a/
window, and where is the closest one?

| colony | hours | speakers | ants with a real /a/ unit | best /a/ candidate per ant (F1/F2) | /a/ units of 256 |
|---|---|---|---|---|---|
| **BEFORE (253 s, 64 units)** | 0.07 | 1 | **2/4** | 699/1265 ✓, 637/1368 ✗, 722/1419 ✗, 660/1064 ✓ | 2 / 0 / 1 / 1 |
| **all-256 (40.6 h)** | 40.58 | 16 | **4/4** | 843/1232 ✓, 843/1232 ✓, 727/1185 ✓, 756/1333 ✓ | 3 / 3 / 3 / 7 |
| iddo-13.8h-256 | 13.80 | 1 | 4/4 | 737/1328 ✓, 748/1299 ✓, 697/1322 ✓, 725/1282 ✓ | 10 / 5 / 4 / 4 |
| multi-13.8h-256 | 13.80 | 15 | 2/4 | 694/1177 ✓, 722/1400 ✓, 642/1289 ✗, 677/1412 ✗ | 2 / 2 / 0 / 1 |
| orig-253s-256 | 0.03 | 1 | 4/4 | 688/1264 ✓, 699/1265 ✓, 732/1266 ✓, 719/1216 ✓ | 4 / 5 / 5 / 9 |
| random-frames-256 | 40.58 | 16 | 4/4 | 692/1345 ✓, 731/1303 ✓, 802/1245 ✓, 711/1268 ✓ | 1 / 3 / 5 / 7 |

**Before, two of four ants had no /a/ anywhere in the codebook at all. Now all four do.**
That is a genuine change and it is the honest positive result of this run.

Note the last two rows before you get excited: `orig-253s-256` reaches 4/4 on the
**original 253 seconds**, and `random-frames-256` reaches 4/4 with **k-means never run**.
Going from 64 to 256 units is doing most of this work, not the 40 hours.

---

## 4. Their vowel space

Regions hit by the 12 most periodic exemplars, and — a stabler measure — the average
number of voiced units landing in each Hebrew vowel box across the four ants.

| colony | voiced units | /a/ | /e/ | /i/ | /o/ | /u/ | boxes covered |
|---|---|---|---|---|---|---|---|
| BEFORE (253 s, 64 units) | 23.5 | 1.8 | 5.2 | 0.5 | 2.8 | 0.0 | **3/5** |
| all-256 (40.6 h) | 120.5 | 6.2 | 15.5 | 7.5 | 3.8 | 0.8 | **4/5** |
| multi-13.8h-256 | 138.2 | 4.8 | 20.5 | **12.2** | 2.5 | 0.2 | 4/5 |
| iddo-13.8h-256 | 118.0 | **8.8** | 17.5 | 4.8 | **6.5** | 0.5 | 4/5 |
| orig-253s-256 | 87.0 | 8.5 | 15.5 | 5.8 | 8.0 | 1.2 | 5/5 |
| random-frames-256 | 131.8 | 9.8 | 18.0 | 9.0 | 3.2 | 1.2 | 5/5 |

Top-12 coverage per ant, before and after:

| | ant-a | ant-b | ant-c | ant-d |
|---|---|---|---|---|
| BEFORE | a,e,i,o (4/5) | e,o (2/5) | e,o (2/5) | a,e,o (3/5) |
| all-256 | e,i,u (3/5) | i,o (2/5) | a,e,i (3/5) | **a,e,i,o,u (5/5)** |

Chart: [`vowel-space.svg`](vowel-space.svg) — F1/F2 in phonetician orientation, diamonds
before, discs after.

**Reading it straight.** The vowel space is genuinely wider than before: /i/ went from
0.5 units per ant to 7.5, and `all-256/ant-d` is the first ant in this project to place
a voiced unit in all five Hebrew vowel boxes. But no colony has more than a token /u/,
and the codebook is heavily skewed to /e/ — which is what Hebrew read speech actually
contains most of. **The codebook allocates capacity by frequency in the corpus, not by
phonological importance.** More audio buys more of the same distribution.

The matched-hours pair is the clearest signal in this table: **the multi-speaker arm has
2.5x the /i/ units and half the /o/ units of the Iddo arm.** That is not an accident —
it is in the input (section 6).

---

## 5. Syllable discrimination — does more data break the 44.7 % ceiling?

**No.** 132 held-out VITS syllable tokens, 22 classes, chance 4.5 %, harness unmodified
(`run_knowledge_tests.score_codebook`). References reproduce the previous run exactly.

| colony | k | cos@1 | cos@5 | edit@1 | best single ant |
|---|---|---|---|---|---|
| BEFORE-253s-64 | 64 | 23.7 | 52.3 | 15.9 | 27.3 |
| **big/all-256 (40.6 h)** | 256 | **31.8** | 68.9 | 33.1 | 37.1 |
| big/multi-13.8h-256 | 256 | 32.6 | 67.6 | 35.2 | 36.4 |
| big/iddo-13.8h-256 | 256 | 31.2 | 64.6 | 30.5 | 35.6 |
| big/random-frames-256 | 256 | 30.5 | 65.3 | 33.3 | 36.4 |
| big/orig-253s-256 | 256 | 25.8 | 59.1 | 23.1 | 30.3 |
| prev syllable curriculum | 256 | **41.9** | 75.2 | 37.3 | 43.9 |
| prev syllable curriculum | 512 | 42.0 | 79.4 | 42.6 | **44.7** |
| _ceiling: raw features, no codebook_ | – | 53.8 | 87.9 | – | – |
| _floor: duration only_ | – | 5.3 | 28.0 | – | – |

Exact McNemar on the same 132 items, matched by seed:

| comparison | metric | left | right | delta | p | ants |
|---|---|---|---|---|---|---|
| **E** 40.6 h vs BEFORE 253 s / 64 u | cos | 31.8 | 23.7 | **+8.1** | **0.0004** | 4/4 |
| | edit | 33.1 | 15.9 | **+17.2** | **<0.0001** | 4/4 |
| **F** 40.6 h vs synthetic curriculum 256 | cos | 31.8 | 41.9 | **-10.0** | **<0.0001** | 0/4 |
| | edit | 33.1 | 37.3 | -4.2 | 0.0945 | 1/4 |
| **G** k-means vs 256 random real frames, same 40.6 h | cos | 31.8 | 30.5 | +1.3 | 0.616 | 2/4 |
| | edit | 33.1 | 33.3 | -0.2 | 1.000 | 3/4 |
| **H** matched 13.8 h: 15 speakers vs 1 speaker | cos | 32.6 | 31.2 | +1.3 | 0.603 | 3/4 |
| | edit | 35.2 | 30.5 | +4.7 | 0.052 | 4/4 |
| **I** 40.6 h vs 253 s, both at 256 units | cos | 31.8 | 25.8 | +6.1 | 0.011 | 3/4 |
| | edit | 33.1 | 23.1 | **+10.0** | **<0.0001** | 4/4 |

Real speech beats the original corpus decisively (E, I). It **loses** to the synthetic
syllable curriculum (F) — unsurprising, since the test set *is* that curriculum's
domain, and it is the honest reading: 40 hours of continuous Hebrew is worse preparation
for "which of 22 vocoder-rendered syllables is this" than 400 vocoder-rendered syllables.
**The 44.7 % ceiling was not broken; the big corpus tops out at 37.1 % on a single ant.**

---

## 6. More data or more speakers?

They can be separated here, because the two matched arms differ by 0.09 % in frame count
(4 949 203 vs 4 953 831 frames) — as clean a match as this corpus allows.

**On syllable discrimination: speakers, weakly.** +1.3 points cosine (p = 0.60) and
+4.7 points edit (p = 0.052, all four ants in the same direction). Directionally in
favour of many voices, not significant at 0.05 on either metric. I would not bank on it.

**On the vowel space: speakers, clearly, and in a specific way.** The input-side scan
shows why:

| pool | hours | F1 med | /a/ rate of voiced frames | vowel boxes hit a/e/i/o/u |
|---|---|---|---|---|
| original 253 s | 0.03 | 518 | **7.81 %** | 9 / 10 / **0** / 3 / 1 |
| Iddo big (26.75 h) | 26.75 | 614 | 4.78 % | 337 / 518 / 107 / 102 / 16 |
| open multi-speaker | 13.80 | 541 | 2.94 % | 217 / 480 / **360** / 83 / 26 |

The open corpora are **less** /a/-dense than Iddo's own recordings (2.94 % vs 4.78 %) —
his are deliberate vowel-heavy training takes, theirs are continuous read speech. But
they carry **3.4x more /i/**, and that difference propagates straight into the codebook
(12.2 /i/ units per ant vs 4.8). **Multi-speaker material does not buy you /a/. It buys
you the rest of the vowel triangle.**

**On absolute quality: neither, much.** Comparison G is the one that matters. On the
full 40.6 h, k-means and 256 randomly chosen real frames are statistically identical
(+1.3 / -0.2 points, p = 0.62 and p = 1.00), and the random-frames control reaches 4/4
on the /a/ test. **The prior finding that the learner is inert survives a 578x increase
in data.** Held-out quantisation error fell from 0.981 to 0.301, which is exactly the
kind of number the earlier work established is not evidence of a better representation.

---

## 7. What is still broken

1. **The learner has to be replaced.** This was the pre-registered prediction and it
   held: at 253 seconds k-means was inert, and at 40.6 hours it is still inert
   (p = 0.62 / p = 1.00 against random real frames). The corpus was a real bottleneck —
   comparisons E and I are strongly significant — but it was **not the only one**, and it
   is no longer the binding one. Nothing in a Lloyd iteration on 14-dimensional
   log-spectral frames can learn phonology. What would: a model with temporal context
   (the features are 25 ms, memoryless — a vowel and a fricative are one frame each), and
   a training signal that is not "minimise reconstruction distance", where the prior
   result already proved distance does not rank ants.

2. **The features are the ceiling, not the codebook.** Raw 14-dim features with no
   codebook at all score 53.8 %; the best big-corpus ant scores 37.1 %. There is a
   17-point gap the quantiser is throwing away — but even 53.8 % is the roof of this
   feature spec. 12 log spectral bands cannot represent a formant; the fact that F1/F2
   have to be recovered by LPC *from the exemplar waveform*, and never enter the feature
   vector, means **the ants do not learn in a space where /a/ is a describable thing.**
   They store waveforms that happen to be /a/. That is a lookup table, not a vowel.

3. **The headline test needs retiring.** `periodicity x low-band-energy ratio` is
   anti-correlated with F1 at r = -0.53. It cannot answer "can they say /a/" and it never
   could. Replace it with the section-3 measure (is there a voiced unit in the /a/
   window) — that one shows a real 2/4 → 4/4 improvement.

4. **Capacity was doing more than data.** `orig-253s-256` — the *original* 253 seconds at
   256 units — already reaches 4/4 on the /a/ test and 4/5 vowel boxes. Most of the
   vowel-coverage gain is the 64→256 jump, not the corpus. The corpus's contribution
   shows up in discrimination (comparison I, +10.0 edit points, p < 0.0001), not in
   whether an /a/ exists somewhere in the codebook.

5. **/u/ is essentially absent** — under 1.3 units per ant in every colony. Hebrew /u/ is
   low-frequency in read speech and no amount of read speech will fix it.

6. **Common Voice Hebrew is barely multi-speaker** (one speaker owns most of it, ~95 %
   male), and FLEURS publishes no speaker IDs at all, so the "15 speaker ids" in the
   matched arm is an overstatement of real vocal-tract diversity. The speaker comparison
   in section 6 is weaker evidence than the clean frame-count match makes it look.
   **`ivrit-ai` remains the biggest unclaimed unlock** — genuinely multi-speaker, gated
   `auto`, needs Iddo to accept the terms and drop an HF token on this machine.

7. **Licensing, unchanged and worth restating.** Spotify is impossible — DRM, no path.
   Bulk YouTube scraping violates their Terms and no tool for it was built; a
   `downloads\youtube\` folder was found in the corpus survey and excluded. Everything
   trained on here is Iddo's own recordings plus CC-0 / CC-BY open corpora. FLEURS is
   CC-BY, so `corpus-big/open/ATTRIBUTION.txt` must travel with the audio.

---

## 8. What was run

* **Corpus** 40.575 h train / 7.518 h held-out / 3.349 h evaluation, 16 kHz mono PCM16.
  Human only. `fire/`, all ant-generated audio, `corpus-syllables/` (the test set) and
  the 16 `_unverified_provenance` segments were excluded by path.
  Before: 252.7 s. **578x.**
* **Colonies** five, four ants each, seeds 7007/7019/7039/7057, 256 units, no codebook
  or weight shared between any two ants (verified after training). Identical held-out
  set for every colony.
* **Queen** selected one ant per colony on held-out syllable discrimination and merged
  nothing (`queen/current.json`). For `all-256` she picked **ant-a** (37.1 % cos@1).
* **Not touched** `state/`, `recordings/`, `corpus-big/`. The fleet services keep running
  off `state/`.

Verification performed is listed in [README.md](README.md): the batched featuriser is
bit-identical to `acoustic_units.features` (max abs diff 0.0); the chunked k-means
reproduces the held-out errors recorded in `state/` (0.9685 / 0.9615 / 0.9948 / 0.9980);
the formant estimator reproduces all four BEFORE values exactly; no PCM appears in two
splits; `acoustic_units.load_checkpoint` accepts all 20 new checkpoints.

---

## Coronation — 2026-08-11 (crowned by Iddo, order: "תחליף מלכה")

**New queen: `vowel-cochlea26-scaled-512/ant-a`** — sealed checkpoint
`state-hebbian/vowel-cochlea/queen-ant-a/current.json`
(sha256 `a33f8f78af150da8a7a547387d6752a9284147c8c8f93516ad907c3c2b1a51cb`),
served live on :8803 via `state/coronation.json` (state/queen/current.json untouched — the
hybrid POC validates it as sealed).

Record, on the published held-out protocol with the legacy baseline reproduced bit-exact
first (reports/vowel-cochlea-knowledge.json + reports/vowel-cochlea-paired.json):

| metric | previous queen (iddo-fresh-256/ant-c) | new queen |
|---|---|---|
| syllable cos@1 | 42.4 % | **75.8 %** |
| syllable edit@1 | — | **68.9 %** |
| word edit@1 | — | **97.9 %** |
| ah, cosine, pooled 4 ants | 7/24 | **21/24** |
| aa, edit, pooled 4 ants | 2/24 | **13/24** |

Exact McNemar vs seed-matched legacy-512, 528 paired decisions: cosine p = 7.0e-27,
edit p = 1.1e-15, 4/4 seed-matched wins. za/ya/na: no regression (23-24/24).

What changed: only the organism's ear — `recommended26` (selected earlier by train-only
CV, feature-selection.json; held-out never read by the selection) with the ant's own
per-dimension scaler. Diet untouched, no label ever entered a feature, a codebook, or a
sampling decision. Codebook kind is random-real-frames: the same physical frames as the
legacy arm, re-heard through the new cochlea.

Previous queen `iddo-fresh-256/ant-c` honorably retired; her record stays in
`queen/current.json` here. Rollback: delete `state/coronation.json`, restore
`gui.py.bak-coronation-20260811`, restart gui.py.
