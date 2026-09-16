> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY.

# THE AH CORONATION LAW

### The charter for Eran's voice — v2, production criterion

**Authority:** written by Claude as kingmaker, on Iddo's explicit order, 2026-08-13, 01:28–01:31.
**Supersedes:** the coronation criterion of `state/coronation.json` (2026-08-11) — *for production only*.
**Machine-readable form:** `state/coronation-law-v2.json`. Where the two disagree, this document is the intent and the JSON is the implementation; fix the JSON.
**Judge:** `ah_criterion.py`. **Mouth:** `mouth_v1.py`. **Rollback:** §8.

---

## 0. Why this law exists, in one paragraph

A queen was crowned. Her score was real. Iddo listened to her, and it was garbage. Both of those
sentences are true at the same time, and the reason they can both be true is the whole point of this
document: **the score measured a different thing than the listening did.** The old criterion asked
*can she tell sounds apart*. Nobody ever asked *can she make one*. This law asks the second question,
writes down every threshold it uses, and ends with the only gate that was missing — a human ear.

---

## 1. What the old criterion measured, and what it did not claim

The record in `state/coronation.json` crowns **`vowel-cochlea26-scaled-512/ant-a`** on
**held-out syllable discrimination**, `syllable_cos_top1 = 0.758`, with `word_edit_top1 = 0.979`
and a McNemar test against the legacy-512 baseline at `p = 7.0e-27` over 528 paired decisions,
4/4 seed-matched wins.

**Be fair to that number. It is not the defect.**

- It is a **real, honestly measured result**. The baseline was reproduced bit-exact before comparison.
  The protocol was published. The significance test is appropriate and the effect is enormous.
- It is a **perception** score. Discrimination asks: *given two sounds, can the organism tell them
  apart?* That is a question about her ears and her representation. It is a good question and she
  answers it well.
- **It made no production claim, and it never pretended to.** Nothing in that record says the queen
  can say anything.

The defect is the **omission**: nobody wrote down that the criterion was silent about production.
So when someone wanted a queen who could speak, the highest number in the building was standing
there looking like an answer. A score with no stated scope will be read as a score for everything.

> **RULE 1.1 — EVERY CRITERION DECLARES ITS SCOPE.** A record that crowns on perception must say,
> in its own title, that it makes no production claim. A record that crowns on production must say
> it makes no perception claim. A number without a scope is a lie waiting to be told.

**Therefore, annotated for the record — and Rule 1.1 applied to the old title:**

> `vowel-cochlea26-scaled-512/ant-a` — **crowned on the PERCEPTION criterion; makes NO production claim.**

That annotation lives in `state/coronation-law-v2.json` under `supersedes.annotated_title`.
`state/coronation.json` itself is **untouched, byte-identical**
(sha256 `2745a8b1…c138e51`), because it is the rollback path (§8).

**Why the sound was garbage, mechanically.** `acoustic_units.py:425 synthesize_units()` is not a
synthesiser. It overlap-adds stored raw PCM exemplars — `checkpoint["exemplars_pcm16"]`, which the
project's own `autonomy_law` describes as *"random real frames from the uncurated train"* pool —
and then `acoustic_units.py:449 render_soft()` lowpasses the result at 2500 Hz. Mosaic plus lowpass
is mush. Run through the new judge, the exact file Iddo heard
(`state/queen-listen/queen_RAW_20260813.wav`) fails **all four gates**: identity Mahalanobis 4.38
with nearest vowel /u/, only 65 ms of usable voiced material at f0 403 Hz, CV(F1) 0.220 with F1
drifting 5242 Hz/s, and 17 static provenance violations plus reconstruction from its own exemplar
bank at 51.6 dB. That file is now pinned as a regression test, so the sound can never again be lost
behind the score.

---

## 2. The new criterion: PRODUCTION, one rung at a time

**A queen is crowned for what she can EMIT, not for what she can distinguish.**

The curriculum is Iddo's, and it is the real infant order:

| rung | sound | Hebrew | what it demands | status |
|---|---|---|---|---|
| **1** | **/a/** | אה | an open vowel — no constriction anywhere. The first sound a human makes. | **OPEN** |
| **2** | **/ba/** | בה | a bilabial stop + vowel. Lips seal, pressure builds, seal breaks. | **CLOSED** |
| **3** | **/ga/** | גה | a velar stop + vowel. The tongue *body* seals against the soft palate. | **CLOSED** |

> **RULE 2.1 — NOBODY SKIPS A RUNG.** Rung 2 does not open until a queen has passed rung 1 *and*
> Iddo has ratified her by ear (§6). Rung 3 does not open until rung 2 has. `judge_ba()` and
> `judge_ga()` exist with fixed signatures and raise `NotImplementedError` on purpose.

> **RULE 2.2 — THE VOWEL IS ALWAYS RE-JUDGED.** In rungs 2 and 3 the /a/ that follows the stop must
> independently pass all four rung-1 gates. A consonant is not a licence to stop being a vowel.

> **RULE 2.4 — THE QUEEN SAYS BOTH.** *Iddo, 2026-08-14 05:37:26, verbatim:*
>
> ### "whoever says both ah and ba good becomes queen"
>
> This **amends Rule 2.3 rather than replacing it.** A rung still has its own throne and its own
> record — that machinery stays, because it is how we keep the claims separate. But the title
> **QUEEN**, unqualified, is no longer won by one rung. It belongs to whoever passes **rung 1 AND
> rung 2**, /a/ and /ba/, both ratified by ear under §6.
>
> Consequences, so nothing is quietly demoted or quietly promoted:
> - `ah_babble/mouth_v1-babble-seed76301202`, crowned 2026-08-14 05:21, is **queen of rung 1** and
>   keeps that title in full. She is **not** the QUEEN under this rule until she also says /ba/.
> - A candidate who says a magnificent /ba/ and cannot hold an /a/ is not the queen either. **Both.**
> - Rule 2.2 already required the vowel inside /ba/ to be re-judged against all four rung-1 gates.
>   That is unchanged and it is what makes "both" a coherent demand rather than two unrelated tests.
> - Rule 6.1 is untouched: passing both makes a candidate ELIGIBLE for the crown. Iddo's ear crowns.

> **RULE 2.3 — A RUNG IS CROWNED SEPARATELY.** There is one throne per rung. Passing rung 1 makes
> you queen of /a/ and nothing else.

---

## 3. THE PROVENANCE CLAUSE — Iddo's clause

Claude first proposed an **anti-copy** gate: penalise a candidate for sounding too much like Iddo.
Iddo corrected it, verbatim, 2026-08-13:

> ### "its ok if the queen copies me with her own mouth that's learning isnt it"

**He is right, and the correction is the load-bearing idea in this entire law.** Imitation *is* how
infants acquire speech. A child who reproduces her father's vowel has not cheated; she has learned.
So:

> ## RESEMBLING IDDO IS THE GOAL, NEVER THE CRIME.
>
> **The gate is on the MECHANISM, not on the similarity.**
>
> - **IMITATION** — reproducing the sound through her **own articulatory apparatus**, a source and a
>   tube she drives herself → **this is LEARNING. REQUIRED.**
> - **REPLAY** — splicing stored recorded PCM → **this is a TAPE RECORDER. FORBIDDEN.**
>
> The only question the law asks about a waveform is: **was it MADE, or was it REMEMBERED?**

> **RULE 3.1 — ENFORCE STRUCTURALLY, NOT BY THRESHOLD.** A correlation threshold can be slipped
> under by a clever enough mosaic. So the primary defence is not a measurement at all: **the mouth
> does no I/O.** If the production path has no access to recorded waveforms at synthesis time — only
> to articulatory parameters passed in as function arguments — then cheating is impossible *by
> construction* rather than merely detected. A path that cannot reach a recording cannot replay one.

The consequence, stated so it cannot be mistaken for a loophole: the winning /a/ is *aimed* at
Iddo's vowel and lands **0.265 Mahalanobis units** from the measured centroid — closer to his /a/
than most of his own running speech — and gate 4 clears it, because it was **articulated**. The
same target reached by splicing his recordings scores **139–193 dB** on the replay detector and is
refused. That asymmetry is the clause working exactly as he wrote it.

---

## 4. THE MANY-VOICES CLAUSE — also Iddo's

Iddo asked for other speakers, not only himself, and he was right for a deeper reason than variety:

> ## A colony that only ever hears ONE MAN cannot separate "/a/" from "Iddo".
>
> The two stay entangled, because in her experience they have never once come apart.
> **Many voices force the abstraction.** A phoneme is a category, and a category needs more than
> one example to exist.

> **RULE 4.1 — THE TARGET IS THE POOLED, MULTI-SPEAKER /a/**, not Iddo's personal /a/.
> `AH_TARGET` = F1 **689 Hz**, F2 **1464 Hz**, covariance `[[1681.0, 214.8], [214.8, 68644.0]]` Hz²,
> pooled over Iddo + FLEURS he_il + Common Voice 17 he, n_effective = 42,736 frames.

This is safe for him and it is measured: Iddo's own /a/ (F1 711, F2 1379) sits **1.44 Mahalanobis
units** from the pooled centroid — comfortably inside the shared Hebrew category. Aiming at the
abstraction does not exclude the man. The gap is +46 Hz on F1 and −155 Hz on F2: his /a/ is slightly
more open and clearly backer than the multi-speaker average, but it is a normal Hebrew /a/, not an
idiosyncratic one. (His f0, 186 Hz, sits between the corpus male group at 113 Hz and the female
group at 212 Hz, with F1 near the female group and F2 near the male — so a single-gender formant
prior would misfit him. Another reason to pool.)

**The corpus is already on the disk. No download is needed to obey this clause.**

| corpus | content | licence |
|---|---|---|
| `corpus-big/human` | 23,683 clips of Iddo, 16 kHz mono, VAD-segmented and QC'd | private |
| `corpus-big/open` | **8,714 clips / 17.75 h / 21 distinct labelled speakers** of Hebrew | see below |
| — FLEURS `he_il` | 12.345 h | **CC-BY-4.0 — attribution is REQUIRED and must travel with the audio** |
| — Common Voice 17 he | 5.402 h, 21 labelled client ids | CC0-1.0 |

> **RULE 4.2 — HELD-OUT IS SACRED.** The Cafe Clod sessions **2026-06-25** and **2026-07-01** are
> reserved for evaluation in full and may never be fitted on — 25 raw files / 0.775 GB, and 1,767
> curated clips. Enforced in code by `curriculum_targets.filter_training_paths()` / `is_heldout()`,
> covered by `test_heldout_sessions_are_excluded`, and asserted at runtime in every measurement
> script. `20260701235639.WAV` carries an mtime of 07-02 but is excluded by **filename**, because
> the filename stamp is the session id.

> **RULE 4.3 — NO SCRAPING.** YouTube was mentioned and is explicitly **not** adopted: Common Voice
> is CC0, labelled, speaker-tagged and legal, and 17.75 h of multi-speaker Hebrew is already here.
> Any future download requires Iddo's explicit go-ahead first, named and sized in advance.

---

## 5. THE GATES — rung 1, /a/, with every threshold

Four gates. **A candidate passes rung 1 only if all four pass.** Implementation: `ah_criterion.judge_ah()`.

**Window selection, stated first because it decides what the gates see:** the judge picks the
steadiest 120 ms window using **stability only**. Identity, harmonic richness and provenance are then
tested on whatever that returns, with no further search — so gate 1 is never handed a window that was
chosen for being /a/-like.

### GATE 1 — IDENTITY. *Is it the vowel /a/?*

| threshold | value | source |
|---|---|---|
| Mahalanobis distance to the /a/ centroid | **≤ 2.5** | χ²(2 dof) 95.6% ellipse of the measured covariance |
| nearest vowel in Bark space | **must be /a/** | 5-vowel competitor space |
| margin over the runner-up | **≥ 0.10 Bark** | tie-break only; /a/ must win outright |

Mahalanobis, **not raw Hz**, and the reason is measured: the cluster has sd(F1) = 41 Hz and
sd(F2) = 262 Hz. Raw-Hz Euclidean would treat a 150 Hz F1 error — 3.7 sd, *a different vowel height* —
as no worse than 150 Hz in F2, which is half a sd. Mahalanobis also uses the measured F1/F2
correlation, which raw Hz discards. A test asserts the metric penalises the F1 direction more than
3× harder.

Competitor space (Hz), measured from 2,342 vowel nuclei over 800 train clips:
`/i/ 474.5 / 2008.3` · `/e/ 577.2 / 1716.1` · `/a/ 689 / 1464` · `/o/ 591.5 / 1233.2` · `/u/ 500.9 / 1031.6`.
**/e/ and /o/ are DERIVED, not measured** — Bark midpoints — and are labelled as such, because running
speech does not separate them from the central mass by clustering and inventing a measurement would be
worse than saying so. The derivation errs toward placing them *closer* to /a/, which makes the gate
**stricter**, not laxer. Bark-Euclidean is used here rather than Mahalanobis because **only /a/ has a
measured covariance**; borrowing /a/'s covariance for /i/ would be fabrication.

### GATE 2 — VOICING. *Is it a voice at all?*

| threshold | value | source |
|---|---|---|
| sustained duration | **≥ 120 ms** | curriculum-targets proposal |
| voiced fraction | **≥ 0.80** | |
| mean normalised autocorrelation | **≥ 0.50** | train p50 on real /a/ = 0.719; noise ≈ 0.1–0.2 |
| f0 | **70–400 Hz** | spans corpus male 113 / Iddo 186 / female 212 |
| f0 coefficient of variation | **≤ 0.15** | train p50 0.028, p75 0.049, p90 0.174 |
| **harmonic richness** | **≥ 3 partials** | **physics, not a corpus fit** |

The harmonic sub-gate is what kills a sine, and it earned its place by catching a real bug in the
judge's own first draft: a pure 700 Hz sine is perfectly periodic, sails through any autocorrelation
voicing test, and the first implementation compared partials against the *median* spectral magnitude
— which for a sine is numerical noise — so window leakage at 2f0/3f0 cleared it and the sine was
credited with 4 harmonics and **passed**. Fixed to measure against the strongest partial (within
30 dB), which cannot be fooled that way. A glottal source through a tube has many partials; an
oscillator has one.

### GATE 3 — STABILITY. *Is it held, or is it a smear?*

| threshold | value | source |
|---|---|---|
| CV(F1) | **≤ 0.06** | train-split **p90 of real human /a/** (measured 0.0588) |
| CV(F2) | **≤ 0.10** | measured p90 0.1024 |
| \|dF1/dt\| | **≤ 800 Hz/s** | measured p90 768 Hz/s |
| \|dF2/dt\| | **≤ 3200 Hz/s** | measured p90 3193 Hz/s |

**A measured correction, reported rather than buried:** `curriculum-targets.json` proposed drift
limits of 400 / 900 Hz/s. Real human /a/ exceeds 400 Hz/s on F1 about **45%** of the time (p50 = 239,
p75 = 379) and exceeds 900 Hz/s on F2 **well over half** the time (p50 = 1319 Hz/s). **The proposal
would have rejected the corpus itself.** The limits were raised to the measured p90 and the reason
written down, rather than shipping a gate that fails humans.

**Honest limit, pinned by a test in `STABILITY_LIMITS`:** gate 3 judges the steadiest 120 ms window,
not the whole candidate — because a vowel inside running speech is exactly 120 ms of held tongue
between two moving neighbours. Consequently **a glide gentler than real human /a/ passes, and it
must**; tightening until it failed would reject the corpus. A sweep faster than human speech
(500→1000 Hz F1, 1000→2200 Hz F2 in 250 ms) does fail, and is tested.

### GATE 4 — PROVENANCE. *Was it MADE, or REMEMBERED?* (§3)

**Two arms. The structural one is primary.**

**(4a) STRUCTURAL — `audit_production_module()`.** Walks the AST of the production module and,
**transitively**, every first-party module it imports (depth 8, cycle-safe). The rule is deliberately
blunt and therefore unlaunderable: **THE MOUTH DOES NO I/O.**

- may not import: `wave`, `soundfile`, `librosa`, `audioread`, `pydub`, `sounddevice`, `pyaudio`,
  `aifc`, `sunau`, `torchaudio`, `torch`, `scipy.io[.wavfile]`, `wavio`, `pickle`, `shelve`,
  `joblib`, `h5py`
- may not call: `open`, `np.load`, `np.fromfile`, `np.memmap`, `np.loadtxt`, `np.genfromtxt`,
  `json.load`, `pickle.load`, `wave.open`, `read_wav_mono16k`, `load_checkpoint`,
  `synthesize_units`, `reconstruct`, `soundfile.read`, `librosa.load`, `wavfile.read`
- may not **name** an exemplar bank — identifier **or string literal** — matching `exemplars_pcm16`,
  `exemplars_pcm`, `exemplar_pcm`, `exemplars`, `pcm16`, `waveform_bank`, `wav_bank`, `sample_bank`,
  `audio_bank`

It receives articulatory parameters as function arguments and returns a waveform. **The gate is
proved to FIRE**, because a lint gate that never fires is not a gate: `acoustic_units.py` → **17
violations**; `head_sim.py` → **2 violations**; `ah_criterion.py` **fails its own audit** (it reads
wav files, because it is the judge, not the mouth); `mouth_v1.py` and `glottis.py` → **clean**.
Transitivity is tested with a two-hop temp module, so hiding a loader one import away cannot launder
it. `grep_proof()` re-checks the same claim with the crudest available instrument and a test asserts
the two agree.

**(4b) EMPIRICAL — replay detector.** Matching pursuit over the exact generative model of
`synthesize_units()`, run against the candidate's own codebook.

| threshold | value |
|---|---|
| reconstruction SNR that flags **REPLAY** | **≥ 20 dB** |

Measured, so the threshold can be seen not to be finely balanced: exact overlap-add replay
**139.9 dB**; a real recording whose own frames are in the codebook **193.0 dB**; an honest
source-filter vowel aimed at the *same target* **6.9 dB**. Replay clears by 120 dB; honest imitation
misses by 13 dB. Anywhere from 10 to 100 dB returns the same verdict.

**Fails closed:** with no production module to audit and no codebook to test against, the verdict is
**FAIL / "UNVERIFIED"**. An unproven mouth is not a mouth.

**Documented weakness, in `CROSSFADE_EVASION`:** the empirical arm degrades on long crossfaded
mosaics — 2-frame splices are caught 92–100% of the time at 1.6/3.1/6.2/12.5 ms fades, but an
8-frame mosaic with a 12.5 ms fade is a **coin flip (50%)**. It also does not catch a mosaic from a
codebook the judge was not given, or a replay resampled/pitch-shifted/filtered after splicing.
**This is exactly why 4a is primary:** 4a needs no guess about what the splicer did.

### The law is SATISFIABLE — demonstrated, not asserted

A gate suite nothing can pass is worthless. `glottis.articulate_vowel()` — a Rosenberg pulse train
through a cascade of resonators — passes all four. So does `mouth_v1`, a full articulatory tube.
**6 of 6 seeds** pass gates 1–3 (median Mahalanobis 0.23), and identity survives a pitch sweep
(/a/ still wins at f0 = 145, 185, 220, 258 Hz), which is the point: **a vowel is a tube shape, not a
pitch.**

### The law does NOT reject humans — measured on held-out data it was never fitted to

On 60 real /a/ segments located by **identity only** (so the rates below are non-circular):
gate 2 accepts **75%**, gate 3 accepts **87%**, gates 1–3 together **33%**. On 120 whole held-out
clips, gates 1–3 pass only **3%** — which is **correct** and is explained rather than buried: a clip
is a whole sentence, the judge takes its steadiest 120 ms and asks whether *that* is an /a/, and
usually it is some other vowel (gate 1 passes 8%). **This is a per-SOUND judge, not a
per-utterance one.**

---

## 6. IDDO'S EAR IS THE FINAL GATE

> ## No number crowns anyone. A human ear crowns.
>
> Passing all four gates makes a candidate **ELIGIBLE**. It does not make her queen.
> **Iddo listens. If he says it is not an "אה", it is not an "אה", and the gates were wrong.**

> **RULE 6.1 — GATES ARE NECESSARY, NEVER SUFFICIENT.** Four passes = `PENDING IDDO'S EAR`.
> Only Iddo's spoken ratification converts that to `CROWNED`.

> **RULE 6.2 — HIS EAR OVERRIDES EVERY THRESHOLD IN §5, IN BOTH DIRECTIONS.** If he rejects a
> passing candidate, the *gates* are amended — never the candidate quietly re-run until it passes.
> The amendment is written down with its reason, the way the drift limits were in §5 gate 3.

> **RULE 6.3 — AN EMPTY THRONE IS AN ACCEPTABLE AND PREFERRED OUTCOME.** Never bend a threshold to
> manufacture a queen. The entire failure this law exists to end is *a good number over a bad sound*;
> loosening a gate to crown someone would be that same failure wearing a new hat.

> **RULE 6.4 — THE SEARCH MOVES THE TONGUE, NOT THE BAR.** The winning /a/ was found by a 324-point
> grid over the articulators plus Nelder-Mead refinement, scored by the judge's own gate-1 distance.
> **No threshold was touched.** That is the only permitted direction of optimisation.

---

## 7. THE THRONE, AS IT STANDS ON 2026-08-13

### 7.1 The PERCEPTION throne — OCCUPIED, and correctly so

`vowel-cochlea26-scaled-512/ant-a` remains crowned on held-out syllable discrimination,
`syllable_cos_top1 = 0.758`. **That record is untouched and remains true.** Under Rule 1.1 its title
now reads: *crowned on the PERCEPTION criterion — makes NO production claim.*

### 7.2 The PRODUCTION throne — **OCCUPIED as of 2026-08-14 05:21**

**Queen of rung 1: `ah_babble/mouth_v1-babble-seed76301202`.** Record: `state/coronation-rung1.json`.

She was not aimed. 3000 undirected babbles over `mouth_v1`'s seven motors — a mouth with **no
frication path at all**, so "open mouth only" is structural rather than filtered — judged by
`judge_ah` unchanged. **49 of 3000 passed all four gates (1.6%); the first at babble 94.** Then she
wiggled around her own best, scored by the judge's own gate-1 distance and nothing else.

**Mahalanobis 0.0112.** The /a/ *we* hand-tuned for her was 0.265. `head_sim` driven — acoustically
the best in the whole set and disqualified on `import wave` — was 0.02. **She beat both and she is
provenance-clean.** The 4 s sustain, never optimised for, still passes (0.071).

Her articulation is **not ours**: same back tongue, but jaw 0.80 against our 0.41, lips 0.46 against
our 1.00, at **f0 291 Hz — a child's pitch, not Iddo's 186**. Same vowel, different body. That is
what finding it looks like as opposed to being handed it.

**Iddo's ratification, verbatim, 05:21:19:**

> ### "its an A but not ah. crown"

**Both halves of that sentence are binding.** He crowned her, and he withheld the claim that it is
the Hebrew *אה*. Under Rule 6.2 that is a gap in the **gates**, not a defect in the queen: the gates
measure a vowel target in F1/F2 space and evidently do not measure whatever else *אה* carries for
his ear. **Recorded and left open. Not argued with, and — Rule 6.3 — not to be closed by re-running
candidates until one happens to sound right.** The next move is to ask him what is missing and amend
the law with the reason written down, the way the drift limits were in §5 gate 3.

### 7.2.1 The old entry, kept for the record — the PRODUCTION throne was EMPTY until 2026-08-14

**Said plainly and without embarrassment: nobody is queen of /a/.**

Not because nothing works — something does — but because the last gate has not been opened, and the
last gate is a man listening.

### 7.3 Rung 1 — **PASSED, PENDING IDDO'S EAR**

**Candidate:** `mouth_v1.AH` — `state/ah-trial/01-AH-mouth_v1-WINNER.wav`, 1.00 s, 16 kHz,
`mouth_v1.articulate(seconds=1.00, seed=5, **mouth_v1.AH)`.

**The articulation — a tongue, a jaw and a pair of lips, not a formant table.** No frequency is
typed anywhere in `mouth_v1.py`; the formants are simply what the resulting bore resonates at.

| motor | value | what it means physically |
|---|---|---|
| `breath` | 0.80 | airflow |
| `pitch` | 0.46 | → f0 = 185 Hz (Iddo's measured /a/ f0 is 186 Hz) |
| `press` | 0.64 | open quotient 0.53 — moderately pressed folds |
| `tongue_x` | 1.00 | fully back — hump centre at 0.13 of tract length, pharyngeal |
| `tongue_y` | 0.30 | shallow — depth 0.72 cm; the pharynx narrows but does not seal |
| `lips` | 1.00 | fully spread |
| `jaw` | 0.41 | oral cavity 1.98 cm |

A narrow pharynx flaring into a wide mouth — the textbook /a/ area function.

**Verdict on the exact 1.00 s file Iddo will hear** (not on a shorter test signal):

| gate | result | measured |
|---|---|---|
| 1 identity | **PASS** | F1 **692** F2 **1532** Hz; Mahalanobis **0.265** (max 2.5); nearest /a/, margin **0.87 Bark** over /e/ (min 0.10) |
| 2 voicing | **PASS** | 135 ms; voiced fraction 1.00; voicing 0.76; f0 **186 Hz** (CV 0.003); **9 harmonics** |
| 3 stability | **PASS** | CV(F1) 0.013, CV(F2) 0.007; drift **13 / 27 Hz/s** |
| 4 provenance | **PASS** | static audit **clean** (`[]`); rebuilt from the reigning queen's 512×400 stored-frame bank at only **6.5 dB** vs the 20 dB replay threshold |

**Status: superseded 2026-08-14.** `mouth_v1.AH` was the hand-aimed candidate and it was never crowned. The throne went instead to a posture the colony found by babbling, at 0.0112 against this one's 0.265 — see §7.2. This entry stands unedited as the record of what was true on 2026-08-13.

**The finding that must not be lost:** `head_sim`, *driven*, is acoustically the **best** /a/ in the
set — Mahalanobis **0.02**, dead on the target, 6/6 seeds. **It cannot be crowned for exactly one
reason:** `import wave` at `head_sim.py:185` and `wave.open()` at `:189`, which `mouth.py` inherits
transitively. The gap between the two files is **provenance, not physics**. That is pinned as a
regression test. It is also a broken window, and §9 says how to fix it.

### 7.4 Rung 2 — **OPEN as of 2026-08-14**; rung 3 — **CLOSED**

Rule 2.1 is satisfied for rung 2: rung 1 passed *and* Iddo ratified by ear. `judge_ba()` still raises `NotImplementedError` and must be written before any /ba/ candidate is judged. Rule 2.2 applies — the /a/ after the stop is re-judged against all four rung-1 gates on its own.

### 7.4.1 Original entry — rungs 2 and 3 CLOSED

`judge_ba()` and `judge_ga()` raise `NotImplementedError`. Signatures are fixed so the shape of the
work is unambiguous. `EXTRA_GATES_BA` / `EXTRA_GATES_GA` carry the measured criteria. The velar-pinch
criterion is explicitly `gating: False` with a test enforcing it (§9.4).

### 7.5 What Iddo should listen to

`state/ah-trial/08-ALL-in-one-listen.wav` — one file, in order: **mouth_v1 WINNER**, head_sim driven,
head_sim untuned, glottis reference, mouth_v1 saying "ee". The last one is there so the ear has a
control: if #1 and #5 sound the same, the gates are measuring nothing.

---

## 8. ROLLBACK — exact

**Nothing needs rolling back to restore the old behaviour.** This law added files; it changed none.

| claim | verification |
|---|---|
| `state/coronation.json` untouched | sha256 `2745a8b129f62ed8b956d91b7c7be13f4c7d314c1e1d088bd9dde8f7bc138e51`, identical before and after |
| GUI on :8803 never stopped or restarted | still listening, 3 sockets |
| no torch | not imported anywhere in the new code |
| no audio device opened | wav files read from and written to disk only |

**To roll this law back completely — three commands, no restart, no state loss:**

```bash
cd D:\CLAUDE\voice-ant-farm
del AH_CORONATION_LAW.md
del state\coronation-law-v2.json
```

That is the whole rollback. The GUI reads only `state/coronation.json` (`gui.py:20`,
`gui.py:38-47`); it has never read `coronation-law-v2.json` and does not know it exists. The
reigning perception queen keeps reigning, uninterrupted.

**To also remove the machinery** (only if the whole production line is being abandoned):
`del ah_criterion.py test_ah_criterion.py glottis.py mouth_v1.py render_ah_trial.py` and
`rmdir /s state\ah-trial`. None of these is imported by `gui.py`, `hebbian.py`, `feeder.py` or any
running process — they are additive.

**Pre-existing rollback, still valid and unchanged:** delete or rename `state/coronation.json` and
restart `gui.py` — the GUI falls back to `state/queen/current.json` (untouched);
`gui.py.bak-coronation-20260811` restores the pre-coronation server.

---

## 9. THE ROAD TO /ba/ AND /ga/

*This is the roadmap for Eran learning to speak. It is written in terms of what the **mouth** must
gain, because that is what is actually missing — the judge for both rungs is already specified.*

### 9.0 Where the mouth is today

`mouth_v1.articulate()` is a **static pose**. One bore, held for the whole duration:

- **source** — Rosenberg glottal *flow* pulses at f0 = 70 + 250·`pitch`, built pulse by pulse with
  0.6% period jitter and 3% amplitude shimmer. `press` sets the open quotient (0.75 − 0.35·`press`).
  The jitter and shimmer are load-bearing, not decoration: without them the source is a pulse
  oscillator and gate 2's harmonic test says so.
- **tract** — a Kelly–Lochbaum waveguide ladder, **16 sections × 1.06 cm = 17.0 cm**, closed at the
  glottis (+0.95) and open at the lips (−0.85), reflection at each junction being the area mismatch
  `(a[:-1]−a[1:])/(a[:-1]+a[1:])`. Real wave physics, and the test proves it: a uniform bore
  resonates at 500/1500/2500 Hz — the 1:3:5 quarter-wave series — within 10%.
- **losses** — 0.985 per junction. Real tissue is not a mirror.
- **radiation** — lips differentiate the flow, +6 dB/octave.

**Everything a vowel needs, nothing a consonant needs.** A vowel is a shape. **A stop is an
event.**

*A bug worth carrying forward:* the first version injected **white** aspiration noise, copying
`head_sim`. White noise carries almost nothing below 1 kHz where the glottal pulse is strong but
dominates above 2 kHz where the pulse has fallen ~40 dB — so LPC puts its poles up in the hiss.
Same tube, same articulation: white noise measured F1/F2 = **888/2707 Hz**; shaped noise
(−6 dB/oct, quieter) measured **680/1044**, within 2% of the tube's own impulse-response resonances
(658/1094). **1600 Hz of difference from a noise term.** `head_sim` still carries the same signature.
Any new noise source added for frication (§9.2) must be shaped and validated the same way.

### 9.1 RUNG 0 — the broken window, fix first (hours)

**`head_sim.py:185` `import wave` / `:189` `wave.open()` must come out of the synthesis module.**

`head_sim` contains the best-measured /a/ in the project and cannot be crowned because it carries a
file writer. `mouth.py:57` imports from `head_sim` and inherits the violation one hop away — and
`mouth.py:72 synth_sequence()` is the **only existing code in the project that already does closure
and burst** (`pressure = min(pressure + drive * 0.01, 1.0)` while sealed, with frication injected at
the constriction rather than at the glottis). **The road to /ba/ runs through code that is currently
disqualified by two lines.**

Fix: move `write_wav()` out of `head_sim.py` into a caller (the pattern `render_ah_trial.py` already
follows — *the test may read and write files; the mouth may not*). Then re-run
`audit_production_module()` on `head_sim.py` and `mouth.py` and require `[]`.

**Acceptance:** `audit_production_module("mouth.py") == []`, and `05-AH-head_sim-driven` re-rendered
through the cleaned module passes gate 4.

### 9.2 RUNG 2 — /ba/ — what the mouth must gain

**The lips must learn to CLOSE, hold, and OPEN.** Four capabilities, in dependency order:

1. **A TRAJECTORY, not a pose.** `articulate()` must accept a time-varying motor path and update the
   bore per frame (~5 ms), interpolating reflection coefficients between updates so the ladder does
   not click on every parameter step. This is the single largest change, and it is a prerequisite for
   *all* consonants — a stop is defined by change over time. `mouth.py:72 synth_sequence()` already
   has this shape; §9.1 is what makes it usable.
2. **A real SEAL.** The `lips` motor currently *pinches* the last two sections; it never reaches
   zero area. A stop needs area → 0, i.e. a junction reflection coefficient → 1.0 (total reflection,
   nothing radiates). Watch for numerical instability as the coefficient approaches unity — the
   ladder wants a clamp just below 1.0 plus the existing damping.
3. **PRESSURE behind the seal, and a RELEASE.** While closed, flow cannot escape, so intraoral
   pressure rises; at release the stored pressure discharges as a transient. The burst is not a
   sample to be played — **it is what a sealed tube does when it suddenly opens.** `mouth.py` already
   accumulates `pressure` during closure; what is needed is to discharge it into the tract at the
   release frame with a noise excitation **injected at the lip end**, not at the glottis, and shaped
   (§9.0 bug).
4. **A VOICE BAR.** /b/ is **voiced**, so the folds keep vibrating while the lips are shut. The mouth
   must not simply mute during closure — it must radiate weakly through the closure. Expect
   near-silence, not silence.

**Why the burst is FORGIVING here — and this is the acoustic reason /ba/ comes first:** with the
lips sealed there is **no cavity in front of the constriction**, so nothing resonates and nothing
shapes the burst. It comes out diffuse-falling — more energy low than high — almost regardless of
what the rest of the tract is doing. Measured on Iddo's speech (n = 198): burst centroid median
**1160 Hz**, spectral tilt **+26.6 dB**.

**Gates already specified (`EXTRA_GATES_BA`):** closure **40–140 ms** (Iddo median 85 ms), burst
present with centroid **400–1600 Hz** and tilt **≥ 6 dB**, VOT **0–40 ms**, and the vowel must
independently pass all four rung-1 gates. **F2 transition slope is NOT gating**: the median points
the right way (+842 Hz/s, rising — and it was *not* selected for, which makes it real evidence) but
per-token sd is ~18,500 Hz/s and p25/p75 straddle zero. **A median may inform; it may never gate an
individual token.**

**Blocking work before rung 2 can be gated honestly:** every stop label in the corpus is **inferred
from acoustics, not aligned**. Either run a forced aligner or hand-label ~100 tokens. That is the
weakest link in the whole measurement chain.

### 9.3 RUNG 3 — /ga/ — what the mouth must gain

**The tongue *body* must learn to seal against the velum, at a place, without vision.**

The good news: `mouth_v1.tract_bore()` **already parameterises a Gaussian tongue hump whose position
along the tube is `tongue_x` and whose depth is `tongue_y`**. In principle the geometry can already
seal at the velum — drive `tongue_y` to full depth at the velar `tongue_x`. What is missing:

1. **A LOCATED closure, not merely a closure.** The lips are effectively binary — closed or open, and
   there is only one place to close them. The tongue dorsum must arrive **at a specific position
   along a 17 cm tube** and seal there. Miss forward and it is /d/; miss back and it is uvular.
   **This is why /ga/ is harder: the closure must be aimed.**
2. **A hump that actually reaches zero area.** `tongue_y` currently maxes at a *narrowing*
   (0.72 cm depth at the winning /a/). Sealing needs the Gaussian to drive the section area to zero,
   with the same clamp-and-damp care as the lip seal.
3. **A FRONT CAVITY that rings.** Unlike /b/, there **is** a cavity in front of a velar constriction,
   and it resonates — which is precisely what makes the velar burst **strong, compact and
   mid-frequency** instead of diffuse. This falls out of the waveguide for free *if* the closure is
   real: the front section is an isolated tube that gets excited at release. **It is a prediction the
   physics should make, not a feature to be coded** — and testing it is a genuine check that the tube
   is doing acoustics rather than impersonating them.
4. **The VELAR PINCH.** F2 and F3 converge at release because the velar constriction couples the
   front and back cavities, then separate as the tongue leaves. This too should emerge from the
   geometry.

**Measured separation is real:** velar burst centroid **2044 Hz** vs bilabial **1160 Hz** — 880 Hz
apart — with tilt **+14 dB** vs **+27 dB**, and velar median F2 slope **−1527 Hz/s** (falling into
/a/, the opposite direction to /ba/, and not selected for.

**Gates specified (`EXTRA_GATES_GA`):** closure **40–120 ms** (Iddo median 67.5 ms — shorter than
bilabial), burst centroid **1500–3000 Hz**, tilt **≤ 20 dB**, VOT **10–60 ms**, vowel passes rung 1.

### 9.4 THE MEASUREMENT THAT MUST BE FIXED BEFORE /ga/ CAN BE GATED

**The velar pinch — the defining cue of /ga/ — was NOT successfully measured on real speech.**

**0.3 for velars. 0.3 for bilabials. No separation at all.**

The identical code returns **0.60 vs 0.20** on synthetic tokens with a known pinch, so **the metric
is sound and the extraction is not.** Cause: the pinch relaxes within 20–30 ms of release, while the
analysis window is 20 ms with a 5 ms hop, so the earliest measurable frame is already ~14 ms into
the vowel and the convergence has largely undone itself. F3 estimation near the 5500 Hz LPC ceiling
is also noisy.

**Required fix:** measure the pinch **at the burst**, by short-time spectral peak analysis of the
5–15 ms release transient itself, rather than from the voiced formant track — or obtain phone-aligned
tokens.

> **RULE 9.1 — `velar_pinch` STAYS `gating: False` UNTIL THAT IS FIXED**, and a test enforces it.
> Gating on a metric that cannot tell a velar from a bilabial would be exactly the sin this law
> exists to end: a number standing in for a sound, in a new place.

*(The same discipline applies to `f2_onset` for /ga/: `f2_onset > 1300 Hz` was part of the selection
rule that defined the velar group, so the reported 1618 Hz is **circular** and is not an independent
measurement. And the measured bilabial F2 onset of 1364 Hz sits well above the classic 700–1000 Hz
locus — that is **window smearing**, not evidence that Hebrew /b/ has a high locus.)*

### 9.5 WHY THIS ORDER IS THE HUMAN ORDER

Not an analogy. Four independent reasons the curriculum is /a/ → /ba/ → /ga/:

1. **/a/ requires no control at all.** It is the tube's *rest* configuration with the jaw down —
   open, unconstricted, maximally loud, maximally distinct. It is the first sound a human makes
   because it is what a vocal tract does when air passes through it and nothing gets in the way.
2. **Lips before tongue body, because of feedback.** Lips are **visible** — an infant watches a face
   and sees the closure — densely innervated, already used for sucking, and **binary**: there is one
   place to close them and you either have or you haven't. The tongue dorsum is invisible, has coarser
   proprioception, and must hit a **graded position** along the tract with no way to see whether it
   did. Labials appear in canonical babble around 6–7 months; velars come later. **That gap is a
   control problem, and the mouth has the same one.**
3. **Lips before tongue body, because of acoustics.** The bilabial burst has no front cavity to shape
   it, so it sounds like itself no matter what follows — **forgiving**. The velar burst is shaped by
   the front cavity, whose length depends on the following vowel, so /ga/, /gi/ and /gu/ have
   genuinely different bursts. **The learner must hit a moving target.**
4. **Consonants before nothing.** A stop cannot be judged without judging the vowel that follows it
   (Rule 2.2). If /a/ is not solid, a /ba/ failure is unattributable — you cannot tell whether the
   lips or the tube failed. **Rung 1 is not a warm-up; it is the instrument every later rung is
   measured with.**

### 9.6 Ordered work queue

| # | work | blocks | effort |
|---|---|---|---|
| 0 | **Iddo listens to `08-ALL-in-one-listen.wav`** | everything | minutes |
| 1 | Remove `wave` from `head_sim.py` (§9.1) | rung 2 | hours |
| 2 | Motor **trajectories** in the mouth (§9.2.1) | rungs 2, 3 | days |
| 3 | Lip **seal** → area 0, pressure, release, voice bar (§9.2.2–4) | rung 2 | days |
| 4 | Phone-aligned /ba/ /ga/ tokens — aligner or ~100 hand labels | honest rung-2/3 gates | days |
| 5 | Implement `judge_ba()` against `EXTRA_GATES_BA` | rung 2 crowning | days |
| 6 | Fix velar-pinch extraction at the burst (§9.4) | rung 3 gating | days |
| 7 | Tongue-body **seal** at a located `tongue_x` (§9.3) | rung 3 | days |
| 8 | Implement `judge_ga()`; keep `velar_pinch` non-gating until #6 lands | rung 3 crowning | days |
| — | Re-measure /a/ **per speaker** across the 21 Common Voice speakers, for a **between**-speaker covariance (the statistically correct tolerance for a speaker-independent target) | tighter §5 gate 1 | days |

---

## 10. WHAT THIS LAW DOES NOT ESTABLISH

Written down, because Rule 1.1 applies to this document too.

- **That any of it sounds right.** Every number in §5 and §7 is still a number. §6 exists because of
  this sentence.
- **That the perception queen is bad.** She is not. She is measured on a different axis and remains
  crowned there.
- **That the stop measurements are trustworthy per token.** Every /ba/ and /ga/ label in §9 is
  **inferred from acoustics, never aligned**. The /a/ estimator is validated to ~50 Hz against
  labelled ground truth; **the stop measurements have no comparable validation.**
- **That the velar pinch can be measured.** It cannot, yet (§9.4).
- **That the replay detector cannot be evaded.** It can (§5 gate 4b, `CROSSFADE_EVASION`). Gate 4a is
  primary for exactly that reason.
- **That LPC formant estimation is unbiased.** It is biased for high-f0 voices. Naive 16 kHz order-18
  LPC mislocates female /a/ F2 by 16.3%; the adopted 5500 Hz-ceiling configuration holds male, female
  and child /a/ to ≤ 3.3% on synthetic tracts, but real noisy speech will be worse.
- **That `corpus-big/human` contains only Iddo.** `speaker_id = iddo1` is **asserted** by the corpus
  manifest's provenance field; Cafe Clod was not independently audited for a second voice.
- **That the "others" group can be decomposed per speaker.** FLEURS publishes no speaker ids, so the
  reported spread mixes between-speaker and within-speaker variance. Gender labels in Common Voice
  are self-reported.

---

## 11. THE LAW IN SEVEN LINES

1. Crown for **production**, not perception — and make every criterion **declare its scope**.
2. The curriculum is **/a/ → /ba/ → /ga/**, one rung at a time. **Nobody skips.**
3. **"its ok if the queen copies me with her own mouth that's learning isnt it"** — Iddo, 2026-08-13.
   **Imitation is learning. Splicing a recording is a tape recorder.**
4. Enforce that **structurally**: the mouth does no I/O. Cheating is impossible, not merely detected.
5. **Many voices**, or "/a/" and "Iddo" never come apart.
6. Four gates, every threshold measured and written down — **then Iddo listens, and his ear wins.**
7. **An empty throne is preferred to a bent threshold.**

---

*Written by Claude as kingmaker, on Iddo's explicit order, 2026-08-13.*
*לזכרה של עלמה ז״ל.*
