# MOUTH-MANUAL — the operator's manual for ERAN's mouth (MOUTH v2, adult)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Written by **claude-cli-PEH**, 2026-09-02 21:40, on Iddo's order: *"תפעיל אתה את הפה ותוציא איתו הברות את כולן — תלמד איך מפעילים את הפה ותאמן את ערן על זה"*.
Every claim below carries a number from a probe rendered on eran2 tonight (C backend, bit-identical to the numpy reference per `validate/v_parity.py`). Probe code and results: `eran2:~/throat-one-sample/probe_manual.py`, `probe2.py`, `probe3.py` → `out/manual-probes/manual-probes*.json` and `probe-*.wav` (probes, not deliverables — none of them is an `ERAN-*.wav`). No audio was played on the PC; everything was measured with numpy/scipy.

**Status: PARTIAL.** The manual and the table are measured; no syllable has yet been rendered *and verified against its own signature* as an `ERAN-<syl>.wav`. Three broken windows in the mouth itself are listed in §3 — the first one (mid-tract seals leak) decides which places the table can use.

---

## 0. The machine in one paragraph

`eran2:~/mouth-v2/mouth2.py` is a Kelly–Lochbaum tube (`tract_core.py`) driven by an LF glottal pulse (`glottis.py`) with a nasal side branch, a sealed-tube pressure/burst mechanism and a turbulence noise injector, on the Story & Bunton 2018 **adult male** geometry (`geometry.py`, `AGE_MONTHS = 300`). Internal rate 48 kHz, output float32 16 kHz peak 0.7, deterministic per seed.

| measured anatomy (probe `anatomy`) | value |
|---|---|
| tract length | **17.60 cm** |
| ladder | **23 sections × 0.7292 cm = 16.77 cm** (+1.25 sections of end correction = 17.6 effective) |
| nasal branch | 14 sections; junction at section 9 = **c_pos 0.41** |
| constriction search floor | section 7 = c_pos 0.30 (nothing behind it is ever treated as an articulator) |
| constriction window | Gaussian σ 0.75 cm ≈ 1 section (about 2 sections narrowed) |
| c_pos → cm from the lips | (1 − c_pos) × 16.77 |

**API you drive:** `mouth2.say_gesture(g, seed=0, backend="c")` with
`g = {"keyframes":[kf,...], "durations":[s,...], "f0_knots":[3], "tenseness_knots":[3], "glide":0.35, "burst":{...}}`,
`kf = mouth2.keyframe(knots8, c_pos, c_area, velum, tenseness, voicing)`.
Each keyframe is reached by a linear glide over the first `glide` fraction (default 35 %) of its own segment, then held. **The release/transition of every consonant is therefore the glide of the *vowel* segment** (35 % of 0.30 s = 105 ms). The house pattern (train_syl2.py) is `[kf_cons, kf_cons, kf_vowel]` with durations `[d_close, d_trans, d_vowel]`.

---

## 1. The parameters — what each one does to the SOUND

### 1.1 `knots8` — the tube (8 log2-areas, glottis → lips, PCHIP on log-area)
* The fitted vowel: `AH = [-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330]`.
* **Probe (vowel_a_variants):** the fit was made through `mouth2.say()` (8 knots linearly interpolated in *area* to 34, resampled to 23). That path measures **F1 742 F2 1288 F3 2559**; the fit's own log says 729/1276/2571 vs its target 756/1282/2285. **In gesture space the same knots make a different tube**: `keyframe(AH)` (default `c_pos 0.65, c_area 2.0`) measures **F1 580 F2 1226 F3 2550, HNR 9.0 dB**. Cause: PCHIP-on-log-area vs linear-area interpolation, plus the default keyframe's 2.0 cm² dilation at 0.65. There is no `c_area` that makes the constriction a no-op (`c_area` = local area at 0.65 gives 560/1333/2514). **Use `keyframe(AH)` default as THE vowel keyframe** (as train_syl2 does) and score against 580/1226/2550, not against the say() numbers.
* **Presets:** `vowel_knots("i")` → 299/1930/2692; `vowel_knots("u")` → 284/1417/2440; `vowel_knots("a")` (neutral Story /ɑ/) → 788/1311/2533.
* **Trap (ah_min_area, ah_quiet):** the AH tube has two natural narrowings inside the turbulence window — **0.384 cm² at c_pos 0.41** and **0.277 cm² at 0.717**. The default keyframe's dilation at 0.65 removes the second. The first remains, so **`voicing = 0` is NOT silence: a hiss at −16.5 dB re the voiced vowel.** `AH4` (knot 4 → −0.9) is digitally silent at voicing 0 and measures 614/1303/2673 (HNR 9.8); `AH_QUIET` (knots 4 and 6 → −0.9) measures 641/1334/2697. Silence costs ~35–60 Hz of F1.

### 1.2 `c_pos` — WHERE the constriction is (0 = glottis, 1 = lips; clipped [0.30, 1.00])
Two maps, both measured with `AH`.

**Seal map** — held seal (`c_area 0`, voicing 1), dB re the open vowel (probe `seal_leak`, `seal_leak_fine`):

| c_pos | 0.46 | 0.47 | 0.48 | 0.49 | **0.50** | 0.51 | 0.52 | 0.53 | 0.55 | 0.56–0.65 | 0.70 | 0.75–0.92 | 0.93 | 0.94 | 0.95 | 0.96 | **0.97** | **0.98** | 0.99 | 1.00 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dB | −2 | −13 | −20 | −24 | **−25** | −22 | −17.5 | −14 | −8 | **−1.6 … −4.4** | −9 | −8 … −12.5 | −14 | −16 | −20 | −26.5 | **−31** | **−32.6** | −30.6 | −25 |

So in this ladder **a seal only silences the mouth at the lips (0.96–0.99) and, unexpectedly, at 0.48–0.51.** The tongue-tip ridge (0.86–0.92) leaks at −8 to −12 dB; the true velar place (0.56–0.65) does not close at all. Cause: the Gaussian taper transmits like a horn and the open front cavity radiates whatever leaks; at the lips the output tap sits inside the seal; at 0.50 three sections fall under 0.013 cm². **Table places:** lips 0.96–0.99 (b p m f v), tip 0.94–0.95 (d t; 0.90–0.95 for n, where the nose carries the sound), back 0.48–0.51 (g k q). `c_area 0.005` is *not* a seal for sound (+3 dB leak mid-tract, −18 at the lips) — sealed means exactly 0.0.

**Noise place map** — narrow channel `c_area 0.15`, voicing 0; spectral centroid of the radiated noise (probe `c_pos_sweep_voiceless_area0.15`):

| c_pos | 0.30–0.40 | 0.45 | **0.50–0.52** | 0.55 | 0.60–0.65 | 0.70 | **0.75–0.80** | **0.85–0.90** | 0.95 | 1.00 |
|---|---|---|---|---|---|---|---|---|---|---|
| centroid Hz | 4460–4720 | 3006 | **2054 (1–3 kHz 0.91)** | 2520 | 4370–5010 (loudest, rms 0.15) | 4395 | **3440–3740 (2–4 kHz 0.68–0.76)** | **4910–5030 (>4 kHz 0.67–0.69)** | 3698 (weak) | 1710 (rms 0.017, weakest) |

So **ח/כ = 0.50–0.53, ש = 0.76–0.82, ס/ש׳ = 0.85–0.93, פ׳/ב׳ = 0.97–1.00**. The pharynx (0.30–0.40) is bright (4.5 kHz) and pharyngeal-coloured (F 1106/1634), which is what the `ha` row uses.

**Nasal-junction trap (velum_junction_trap):** a seal at 0.35 with the velum open sends nothing to the nose (−21 dB: the seal is *behind* the port); a seal at 0.41 sits on the junction and breaks (+4 dB); at 0.50 the nose wins by +51 dB.

### 1.3 `c_area` — HOW narrow (cm² at the centre; clipped [0, 2])
Probe `c_area_sweep_voiceless_pos0.88` (voicing 0, raw rms): 0.0 → 0 · 0.005 → 0 · 0.02 → 0 · 0.05 → 0 · 0.08 → 0.0009 · **0.10 → 0.070 · 0.12 → 0.070 · 0.15 → 0.069 · 0.20 → 0.069 · 0.25 → 0.069** · 0.30 → 0.122 (the AH tube's own 0.277 narrowing at 0.717 has become the minimum and is now the noise source) · … · 2.0 → 0.110.
* **< 0.01 = SEALED** (`AREA_SEAL`): pressure builds, no noise.
* **0.01–0.09 = DEAD ZONE**: not sealed, no noise (PT `openness = 30·(√A − 0.3)` is 0 below A ≈ 0.09), just a leak. Never park a consonant here.
* **0.10–0.25 = fricative channel**: turbulence at full amplitude (`thinness` = 1 up to A ≈ 0.33, fades to 0 at A ≈ 0.49). Amplitude 0.66 × `noise_mod` (0.3 when unvoiced; 0.1–0.3 pulsing with the glottal cycle when voiced), bandpassed 1–3 kHz *at the source* then coloured by the tube.
* **≥ 0.49 = no noise**, a mere narrowing (F1 lowering; `la` lives here or just below).
* **Only ONE noise source exists**: the global minimum of the tube from c_pos 0.30 onwards. Any keyframe whose `c_area` is wider than the AH tube's own 0.277 hands the noise to the vowel's palatal narrowing.

### 1.4 `velum` — the nasal port (cm², clipped [0, 0.8])
Probe `velum_sweep_lips_sealed` (lips sealed, voicing 1): velum 0 → nose −198 dB (closed), **0.05 → nose/lip +33.8 dB, 0.75 → +35.9 dB**; murmur 99.3 % of power below 500 Hz, centroid 150 Hz, level −2 dB re the open vowel; antiformant 1664 Hz (m), 2000–2500 (n), 2945 (0.50). **It is a switch above `VELUM_LEAK` = 0.05.** With the velum open no pressure builds → **no burst on release** (measured: the `ma` "burst" is +1.4 dB at 45 ms = the vowel onset). Open vowel + velum 0.75 = nasalised vowel: nose −11.8 dB re lip, formants barely move (548/1234/2528).

### 1.5 `voicing` — the glottal intensity (0..1, 10 ms one-pole)
Probe `voicing`: raw rms 0.042 / 0.094 / 0.173 / 0.282 at 0 / 0.3 / 0.6 / 1.0; HNR −5.4 / 4.4 / 7.6 / 8.6 dB. It scales **both** the pulse and the glottal aspiration, so **voicing 0 also kills aspiration** — voiceless sounds get their noise only from the constriction (`c_area` window). Three consequences, all measured:
1. **A closure held at voicing 0 builds no pressure → no burst** (probe `lips_closure_voicing0`: "burst" −3.7 dB = just the vowel onset). Voiceless stops keep voicing ON during the closure (the seal hides it at −31 dB) and put the voicelessness *after* the release as a 30–50 ms gap.
2. The gap is not silent: −3 to −6 dB re the vowel (turbulence while the seal opens through the 0.10–0.33 window, plus tube ring).
3. Voicing-onset rise (probe `glottal_onset`): 10→90 % in **70 ms** with glide 0.02, 140 ms with glide 0.35. A glottal stop cannot be made sharper than that here.

### 1.6 `tenseness` — the voice quality (effective = contour × keyframe/0.6, clipped [0.25, 0.95])
Probe `tenseness_effective` (keyframe value, knots 0.6): 

| effective | 0.25 | 0.40 | 0.60 | 0.80 | 0.95 |
|---|---|---|---|---|---|
| raw rms | 0.22 | 0.24 | 0.28 | 0.38 | 0.40 |
| H1−H2 dB | **+12.9** | +10.5 | +5.4 | −1.5 | **−2.6** |
| centroid Hz | 270 | 298 | 433 | 611 | 633 |
| HNR dB | 10.1 | 9.9 | 8.6 | 7.0 | 6.7 |

Low = breathy and dark (Rd = 3(1−t) → 2.25; aspiration ∝ 1−√t = 0.5); high = pressed, bright, +5 dB louder. **Both knobs multiply**: `tenseness_knots` 0.6 keeps the keyframe value as the effective value; passing the same value in both squares it (0.8 → 0.95 clip; 0.25 → 0.25 clip).

### 1.7 `f0_knots` — pitch (3 knots, cosine in log-Hz; fence 90–350 Hz)
Probe `f0`: asked 80 → **89.9**, 90 → 89.9, 105 → **104.6**, 150 → 150.9, 250 → 250.0, 350 → 347.8, 400 → 347.8. Iddo is 105. Built-in physiology: jitter 1.2 %, shimmer 5 %, drift ±2 %, vibrato ±0.2 st at ~5 Hz — all seeded.

### 1.8 the burst (C backend only: `g["burst"] = {"gain": G, "tau_s": T}`)
Pressure accumulates while sealed and velum < 0.05 from |source| at 0.0033 per 48 kHz sample; **10 ms of closure already fills it** (probe: closures of 10/20/40/80/150 ms give the same +2.1 to +3.3 dB burst). On release it vents through the opening gap with time constant 3 ms.
Probe `stops`, lips, burst peak re the vowel: **gain 2.2 (default) → +3.0 dB; 6 → +8.0; 12 → +13.0**; with a voiceless gap after it: 2.2 → +8.0, 6 → **+17.9**. Burst centroid by place (gain 6): lips 591, tip 744, back 922, uvular 968 Hz — the right order, but all of it is a low thump (< 1 kHz), not the 2–5 kHz click of a real t/k. Iddo said the ba lacked explosion; gain 6 is the starting dial.

### 1.9 formant transitions (what the ear uses for place)
Probe `stops` / `burst_by_place`, F onset 15–60 ms after release → steady vowel 582/1219/2705:
* lips (b): **503 / 1267 / 2777** — F1 rising, F2 flat.
* tip 0.95 (d): 502 / 1248 / **2855–2892** — F3 high.
* back 0.50 (g): 522 / **1515** / 2635 — F2 raised (velar pinch), falling into the vowel.
* nasal onsets: m 510/1243/2783, n 499/1225/2851, [ŋ] 0.50: 510/1549/2645.

### 1.10 `glide` and durations
Default 0.35 of each segment. Closure 60–100 ms, second (transition) keyframe 10–20 ms, vowel 300–400 ms; fricatives 80–120 ms; nasal murmur 80–200 ms (train_syl2 found 260–290 ms on IDDO-ma.wav); tap 25–35 ms (20 ms gives only a −5 dB dip). Glottal onset: glide 0.02.

---

## 2. THE GESTURE TABLE — 22 letters + /a/, each with the vowel /a/

Conventions: **kf_c** = `keyframe(AH, c_pos, c_area, velum, tenseness, voicing)`; **V** = `keyframe(AH)` default (the vowel). Standard gesture `[kf_c, kf_c, V]`, durations `[d_c, 0.01–0.02, 0.30–0.40]`, `f0_knots [105,105,98]`, `tenseness_knots [0.6,0.6,0.55]`, `backend="c"`. "Voiceless stop" = same closure with voicing 1, then `keyframe(AH, voicing=0)` for 0.03–0.05 s, then V, with `burst {"gain":6,"tau_s":0.003}`. Levels are dB re the steady vowel. The machine-readable twin is `gesture-table.json` (27 rows: 22 letters, 4 fricative variants, the vowel).

| # | letter | syl | place · c_pos | manner · c_area | velum | voicing | tenseness | ACOUSTIC SIGNATURE to verify (measured start) |
|---|---|---|---|---|---|---|---|---|
| 1 | א alef | a | glottal onset (no glottal seal exists; c_pos floor 0.30) | none | 0 | 0 → 1 step, glide 0.02 | 0.6 | ≥ 50 ms at ≤ −20 dB (−22.6), then voicing rises 10→90 % in ≤ 70 ms into 580/1226/2550; no burst, no noise. Kill the −16 dB hiss with a lip seal in the silent keyframe. |
| 2 | ב bet | ba | lips 0.96–0.99 | seal 0.0 | 0 | 1 through closure | 0.6 | closure ≤ −25 dB for 40–100 ms (−30.9) → burst ≤ 10 ms after release (+3 dB @2.2, +8 @6; centroid 500–600 Hz) → F1 503→582, F2 flat, F3 2777→2705. |
| 2′ | ב vet | va | labiodental 0.97–1.00 | narrow 0.12–0.18 | 0 | 0.3–0.5 | 0.25–0.40 | f0 measurable (HNR 2–6) **and** > 2 kHz fraction ≥ 0.10 (0.195 at v 0.3/t 0.25); level −10…−25; no closure, no burst. = vav. |
| 3 | ג gimel | ga | back **0.48–0.51** (0.56–0.65 does not close) | seal 0.0 | 0 | 1 | 0.6 | closure ≤ −20 dB (−24.7) → burst centroid 900–980 Hz → F2 onset raised ~1515 falling to 1219 (velar pinch), F1 522→582. |
| 4 | ד dalet | da | tip **0.94–0.95** (0.86–0.92 leaks −8…−12) | seal 0.0 | 0 | 1 | 0.6 | closure ≤ −16 dB (−19.9) → burst centroid 550–750 → F3 onset high 2855–2890 → 2705, F2 flat, F1 502→582. d/b differ only in F3 and burst colour. |
| 5 | ה he | ha | pharynx 0.32–0.40 | narrow 0.15–0.25 | 0 | 0.0–0.2 | 0.25 | 50–90 ms noise, HNR < 0 (−8.7 at v 0; −3.7 at v 0.2), centroid 3.7–5.1 kHz, level −8…−13; no closure, no murmur → vowel. Alt "breathy onset": V with voicing 0.3, tenseness 0.25 → HNR 2.4, centroid 1082, vowel formants 565/1317/2543. |
| 6 | ו vav | va | labiodental 0.97–1.00 | narrow 0.12–0.18 | 0 | 0.3–0.5 | 0.25–0.40 | = vet. |
| 7 | ז zayin | za | tip 0.90–0.93 | narrow 0.10–0.15 | 0 | 0.3–0.5 | 0.25–0.40 | f0 105 + HNR 2–6 **and** > 2 kHz fraction ≥ 0.15, centroid ~3 kHz (0.195 / 3069 at 0.92/0.12/v 0.3/t 0.25); level −6…−10. At voicing 1 it is just the vowel. |
| 8 | ח chet | cha | uvular **0.50–0.53** (0.60 is 4.4 kHz = wrong) | narrow 0.12–0.20 | 0 | 0 | 0.6 | ≥ 80 ms noise, centroid 1.9–2.5 kHz, 1–3 kHz fraction ≥ 0.85 (0.91–0.94), HNR ≤ 1, level −4…−8 → vowel. = khaf. |
| 9 | ט tet | ta | tip 0.94–0.95 | seal 0.0 + gap 30–50 ms | 0 | 1 in closure, 0 in gap | 0.6 | closure ≤ −16 (−19.6) → burst +5 @2.2 / +14 @6 within 5 ms, centroid 850–950 → gap −3…−6 dB → F3 onset high. = tav. |
| 10 | י yod | ya | palate 0.70–0.78 on `vowel_knots("i")` | 0.4–0.6 (no closure) | 0 | 1 | 0.6 | onset F1 ≤ 300, F2 ≥ 1900 (288/2035/2759) sliding over 100–150 ms to 564/1205 (mid 422/1871); continuous voicing HNR ~6; no burst, no noise band. glide 0.5–0.6. |
| 11 | כ kaf | ka | back 0.48–0.51 | seal 0.0 + gap 30–50 ms | 0 | 1 in closure, 0 in gap | 0.6 | closure ≤ −20 (−24.5) → burst +6.6 @2.2 / +14.3 @6, centroid 800–900 → gap −3.5…−5.5 → F2 onset 1400–1500 falling. = qof. |
| 11′ | כ khaf | cha | uvular 0.50–0.53 | narrow 0.12–0.20 | 0 | 0 | 0.6 | = chet. |
| 12 | ל lamed | la | tip 0.86–0.90 | narrow-wide **0.30–0.50** (never sealed) | **0** | 1 | 0.6 | continuous voicing within ±2 dB of the vowel; **F1 ≤ 470 during the consonant** (417 @0.30, 466 @0.50) vs ~580 in the vowel; no burst, no closure below −6 dB; HNR ~5 (a single tube has no lateral channel). Velum must be 0 (Iddo heard "mwah" when it shared ma's template). |
| 13 | מ mem | ma | lips 0.96–0.99 | seal 0.0 | **0.5–0.75** | 1 | 0.6 | murmur 80–200 ms, ≥ 95 % power < 500 Hz (99.3 %), nose/lip ≥ +30 dB (+35.9), level −2 dB, antiformant ~1.66 kHz, murmur F 195/993/2156 → **no burst** → F1 onset ~510. train_syl2 on IDDO-ma: c_pos 0.90, velum 0.72–0.98. |
| 14 | נ nun | na | tip 0.90–0.95 | seal 0.0 | 0.5–0.75 | 1 | 0.6 | murmur ≥ 95 % < 500 Hz (99.7 %), nose/lip ≥ +20 dB (+24.5 @0.93), **antiformant 2.0–2.5 kHz** (vs m 1.66), no burst, F3 onset high (2851). A seal at 0.50 gives [ŋ] (nose +51 dB, antiformant 2945, F2 onset 1549) — not nun. |
| 15 | ס samekh | sa | tip 0.90–0.93 | narrow 0.10–0.15 | 0 | 0 | 0.6 | ≥ 80 ms noise, centroid ≥ 4.3 kHz (4468 @0.92/0.12; 4.9–5.0 k @0.85–0.90/0.15), > 4 kHz fraction ≥ 0.5 (0.56–0.69), HNR < 0, level −12…−16 (−14.8). = sin. |
| 16 | ע ayin | a | glottal onset (= alef in Israeli Hebrew) | none | 0 | 0 → 1 step | 0.6 | = alef. Pharyngeal (Mizrahi) ayin: c_pos 0.30–0.35, c_area 0.3–0.5, voiced 40 ms — NOT probed. |
| 17 | פ pe | pa | lips 0.96–0.99 | seal 0.0 + gap 30–50 ms | 0 | 1 in closure, 0 in gap | 0.6 | closure ≤ −25 (−30.6) → burst +8 @2.2 / **+17.9 @6** within 5 ms → gap −2…−6 dB → F1 rising. b/p = the gap and the burst size only. |
| 17′ | פ fe | fa | labiodental 0.97–1.00 | narrow 0.12–0.18 | 0 | 0 | 0.6 | weak flat noise: level −25 dB (−25.7), centroid ~2.2 kHz, HNR < 0; no closure, no burst. The weakest sound the mouth makes. |
| 18 | צ tsadi | tza | tip: seal 0.95 → channel 0.90 | seal 0.0 (50–60 ms) then 0.12 (60–80 ms) | 0 | 1 in closure, 0 in fricative | 0.6 | closure ≤ −18 (−20.5) → fricative −5…−9 dB with centroid ≥ 3.5 kHz (3733), > 4 kHz ≥ 0.4 → vowel. Gesture `[kf_t, kf_t, kf_s, V]` durations `[0.06, 0.01, 0.08, 0.30]`. |
| 19 | ק qof | ka | back 0.48–0.51 | seal 0.0 + gap | 0 | 1 / 0 | 0.6 | = kaf. |
| 20 | ר resh | ra | **uvular 0.48–0.53** (Iddo's resh); alt tap 0.93–0.95 | narrow 0.15–0.25 (alt: seal 0.0 for 25–35 ms) | 0 | 1 | 0.6 | primary: 50–80 ms continuous voicing HNR ~6, F2 raised ~1470 → 1220, F1 ~420, no noise band > 2 kHz. alt tap: dip ≥ 10 dB for ~10 ms (−12 dB @0.93/30 ms; 20 ms gives only −5), no burst gap, voicing continuous. |
| 21 | ש shin | sha | palate 0.76–0.82 | narrow 0.15–0.20 | 0 | 0 | 0.6 | ≥ 80 ms noise, centroid 3.3–3.8 kHz (3729 @0.80/0.18), **2–4 kHz fraction ≥ 0.65** (0.73), > 4 kHz ≤ 0.3, HNR < 0, level −6…−10 (louder than s). |
| 21′ | ש sin | sa | tip 0.90–0.93 | narrow 0.10–0.15 | 0 | 0 | 0.6 | = samekh. |
| 22 | ת tav | ta | tip 0.94–0.95 | seal 0.0 + gap | 0 | 1 / 0 | 0.6 | = tet. |
| — | vowel | a | none (V) | none · 2.0 at 0.65 | 0 | 1 | 0.6 | F1 ~580 F2 ~1225 F3 ~2550 (gesture space), f0 105 (104.6), HNR ~9, no transitions, nose −198 dB. |

Shared sounds: kaf = qof, tet = tav, vet = vav, khaf = chet, sin = samekh, alef = ayin. Fricative/stop pairs: bet/vet, kaf/khaf, pe/fe, shin/sin.

---

## 3. Broken windows found tonight (in the mouth, not in the table)

1. 🔴 **Mid-tract seals leak.** A `c_area 0` closure at the alveolar ridge (0.86–0.92) is only −8 to −12 dB below the vowel and at the velum (0.56–0.65) −1.6 to −4.4 dB: **there is no /g/ /k/ closure at the anatomical velar place and only a weak /d/ /t/ one.** The table routes k/g to 0.48–0.51 and d/t to 0.94–0.95, where the seal happens to hold (−25 / −20 dB). The real fix is in `tract_core.py` (a seal should be a hard wall regardless of the Gaussian taper) — **not touched tonight**: train_syl2 jobs are running on it and the brief says do not touch.
2. 🟡 **`voicing = 0` is not silence** (−16.5 dB hiss from the AH tube's 0.384 cm² pharyngeal narrowing at 0.41). Workarounds measured: a lip seal in the silent keyframe (digital zero) or `AH4` knots. Voiceless fricatives are unaffected (their noise is louder); glottal onsets and VOT gaps are.
3. 🟡 **Bursts are thumps** (centroid 500–980 Hz, all places) and the default gain gives +3 dB. Use `burst gain 6` on the C backend (+8 to +18 dB). The place colour of the burst is in the right order but small.
4. 🟡 **Voiced fricatives need partial voicing** (0.3–0.5) or they vanish into the vowel; **fe is −25 dB** and may be inaudible; the ridge /l/ carries HNR-5 noise because 0.3–0.5 cm² is inside the turbulence window.
5. 🟢 Nasals, the vowel, the lip stops, s/sh/chet and the y-glide all measure like their signatures say they should.

## 4. What ERAN learns from this
The signature column is the acceptance test per syllable: render `[kf_c, kf_c, V]` from the row, measure the listed numbers with the probe code (LPC formants on 50 ms, Welch centroid/band fractions, autocorrelation HNR/f0, 5 ms rms envelope), and only a render that meets its own row is an `ERAN-<syl>.wav`. Then the recording IDDO-<syl>.wav is the target and train_syl2's six-parameter search starts *inside* the row's ranges instead of a guessed box.
