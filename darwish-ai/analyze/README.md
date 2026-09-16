> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# darwish-ai/analyze — המתמטיקה של דרוויש / the math of Darwish

לזכרו של לָאוֹר ז״ל. 2026-09-15.

## מה שבור קודם / Broken first

**עברית**
1. **ציון "נשמע טוב" v0 הוא השערה, והוא מצביע לכיוון הלא נכון.** על 11 הדירוגים שלך הוא שם את היחיד שאהבת (step112000) מתחת ל-9 מתוך 10 שלא אהבת.
2. **המרחק מדרוויש לא מבדיל היטב בין דרוויש אמיתי לשלנו.** דקה אמיתית מקבלת ציון גבוה מרינדור שלנו רק ב-73% מההשוואות.
3. **81 מתוך 314 הקבצים ב-D:\Darwish הם לא דרוויש** (סקווש, קריקט, ראפ, אמנים אחרים). האימון על eran3 עדיין לומד מהם. לא נגעתי בו.
4. **תוויות הסולם חלשות.** מלודיה, אקורדים מאודיו והבס המתגלגל לא נמדדים טוב על מיקס אמיתי.

**English**
1. **The v0 "sounds good" score is a hypothesis, and on your taps it points the wrong way.** It ranks your one "good" clip below 9 of your 10 "bad" ones.
2. **Distance to Darwish only partly tells real Darwish from ours.** A real minute outscores one of our renders in 73% of comparisons.
3. **81 of the 314 files in D:\Darwish are not Darwish** (squash, cricket, rap, other artists). darwish-poly-train on eran3 still trains on them. I did not touch it.
4. **Mode labels are weak.** Melody, audio chord changes and the rolling-bass index barely work on real mixes.

## המתמטיקה של דרוויש, במילים פשוטות (MEASURED)

נמדד על 182 טרקים נקיים, 68 שעות, 850 דקות.

- **קצב:** 142 BPM, רוב הדקות בין 128 ל-147. בתוך טרק הטמפו כמעט לא זז (0.06 BPM). כ-7 מכות צליל בשנייה.
- **סולם:** 81% מהתווים בתוך סולם אחד. הטוניקה היא התו הכבד ביותר (24%), אחריה הקווינטה (16%), ואז הטרצה הקטנה (8%). הנפוצים: מינור טבעי, דוריאני, מז'ור, פריגיש.
- **הרמוניה:** בכל רגע נשמעים בערך 2 תווים יחד. בערך שליש מהמרווחים צורמים. זה דרוויש, לא טעות.
- **אנרגיה וצורה:** עוצמה -9.5 LUFS. 84% מהאנרגיה מתחת ל-250 הרץ, כלומר הקיק והבס הם המוזיקה. דרופ כל כשתי דקות, קטע חדש כל 38 שניות.

## The math of Darwish, in plain words (MEASURED)

Measured on 182 clean tracks, 68 h, 850 one-minute windows.

- **Rhythm:** 142 BPM, most minutes between 128 and 147. Inside a track the tempo barely moves (0.06 BPM). About 7 onsets per second.
- **Scale:** 81% of notes sit in one scale. The tonic is the heaviest note (24%), then the fifth (16%), then the minor third (8%). Most common: natural minor, Dorian, major, Freygish.
- **Harmony:** about 2 notes sound at once. About a third of the intervals are dissonant. That is Darwish, not an error.
- **Energy and form:** -9.5 LUFS. 84% of the energy is under 250 Hz: kick and bass are the music. A drop about every 2 minutes, a new section every 38 s.

## What was measured

- `darwish_math.py` v1.2 ran on eran2 (nice 19): 233 corpus files (84 h) plus 46 of ours.
  - The 46 are 43 renders and 3 real-Darwish control clips.
  - 0 errors.
- Estimator checks on synthetic loops: root 21/21, mode 20/21, BPM 21/21.
- On renders whose filename names a scale, the estimated mode matched only 2/9.

## sounds_good_v0 — the score (HYPOTHESIS v0)

- **What it is:** a 0–100 blend of five parts. Every weight and anchor is a named constant with a one-line reason in `sounds_good_v0.py`.

  | part | weight |
  |---|---|
  | distance to the Darwish profile | 0.35 |
  | scale fit and tonal hierarchy | 0.20 |
  | groove | 0.20 |
  | consonance | 0.15 |
  | energy/form sanity | 0.10 |

- **Fairness:** it reads JSON only.
  - Each Darwish track is scored against the *other half* of the corpus.
  - Each track is scored on one random 60 s window, the same unit as a render.
  - The profile it rebuilds matches `corpus_profile.json` exactly (182 tracks, max p50 difference 0).

| group | n | median | p5–p95 | mean |
|---|---|---|---|---|
| Darwish, held-out, one window per track | 182 | **91.1** | 78.6–97.5 | 89.9 |
| Darwish, in-sample (circular, for comparison) | 182 | 91.4 | 78.6–97.8 | 90.2 |
| real-Darwish control clips human1–3 | 3 | 94.5 | (84.2, 94.5, 97.0) | 91.9 |
| **our renders, all** | 43 | **83.6** | 70.9–94.1 | 83.5 |
| Chai / psy_render / other renders | 18 | 92.8 | 79.4–94.4 | 89.0 |
| mode / rescale previews | 12 | 84.4 | 75.8–88.8 | 83.7 |
| transformer checkpoints | 13 | 78.6 | 62.0–83.6 | 75.8 |

- **Sanity (MEASURED):**
  - Darwish scores high and renders lower.
  - Real vs ours AUC is 0.73. 10 of 43 renders score above the Darwish median.
  - The lowest renders are `step96000` (59.8, dropouts) and `step41000` (63.5).
- **Against his ear (NOT evidence, the numbers are tiny):**
  - **Taps:** AUC 0.10. All 7 "bad" mode previews score 82–89: in scale, with a locked beat. The one "good" checkpoint, step112000, scores 80.8: it loses on scale (0.49) and pulse (0.28). What v0 rewards is not what he tapped "good".
  - **Blind ranking 2026-09-05 (v4 > v3 > v2):** v0 agrees on 1 of 3 pairs at 65 s, where the three scores sit within 1.6 points, and 3 of 3 on the 24 s cuts of the same renders.
  - The Chai renders score as high as real Darwish. His blind note on v4 was, in short, "you can still hear it's a model — no right melody, no right harmony, but there is rhythm". v0 has no ear for melody quality.

## What is HYPOTHESIS

- That closer to the Darwish profile sounds better.
- Every weight and anchor in `sounds_good_v0.py`.
- The tempo prior centred on 138 BPM.
- The tension weights per interval.
- The 0.5 bass bonus in the key estimate.
- Filename-based curation of the corpus (a human-style judgement from titles).

## Next step

1. **Blind test:** run `BLIND-EAR-PROTOCOL.md`.
   - 20 blind render-vs-render pairs, 20 s, loudness-matched, about 15 minutes for Iddo.
   - It needs a small pair-picker script, plus a `/pairs` page added to the existing `taste_server.py`, agreed with its owner.
   - Freeze the pairs and v0's predictions before he listens.
2. **Until then,** v0 does not steer training, and neither does judge.py (BENCHED).
3. **Iddo decides:** whether to clean the 81 non-Darwish files out of the training corpus.

## Files

- `darwish_math.py` — the analyser (MEASURES)
- `sounds_good_v0.py` — the HYPOTHESIS score, which writes `out/sounds_good_v0.json`
- `BLIND-EAR-PROTOCOL.md` — how v0 gets validated or benched
- Results in `out/`:
  - `corpus_profile.json`, `ours_vs_darwish.json`
  - `_curation_darwish.json`, `_mode_validation_synthetic.json`
  - `darwish__*.json`, `ours__*.json`
- Agent: `D:\CLAUDE\.claude\agents\darwish.md`
