> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# מיקו · MIKO ruling — the world's best digital EAR and MOUTH for ERAN

**Question (Iddo, 2026-08-25 21:16):** build, from all the research of everyone — Germans, Americans,
Japanese, and MIKO — the best human mouth simulator; and (21:3x) the ear exactly like a human ear with
a human auditory cortex, leaving room for bat-range hearing. All digital.
**Four lenses searched (PC code archaeology · fleet live-state · mouth literature · ear literature).
This is the ruling seat. לזכרה של עלמה ז"ל.**

---

## 1. מסקנה · THE RULING

**עברית —** לאוזן: **CARFAC של גוגל** (Apache-2.0, מתוחזק, אוגוסט 2026) הוא הקוכליאה היחידה שהיא
בו-זמנית נאמנה לאוזן האנושית (דחיסה, מיסוך, אדפטציה, phase-locking), דטרמיניסטית, מהירה מספיק
ללולאת חיפוש, ומתרחבת לתדרי עטלפים בשינוי פרמטר אחד (fs). מעליה: SAI לגובה-צליל, בנק אפנון
לקורטקס, וקורטקס קטן שמאומן פעם אחת על קולו של עידו ומוקפא. לפה: **הפיזיקה של Pink Trombone**
(MIT — מקור LF אמיתי לכל מחזור, אף, רעש-חיכוך במיצר, פיצוצי סגר) בגיאומטריית ילד של
**Story & Bunton 2018**, כשה-**VocalTractLab** הגרמני משמש אורקל-אימות בלבד (GPL, איטי, אנטומיית
ילד לפי גיל). שום דבר שנמצא לא מכה את הצירוף הזה על שלושת הצירים יחד: נאמנות, מהירות, רישיון.

**English —** Ear: **Google CARFAC** is the only cochlea that is simultaneously human-faithful,
deterministic, search-loop-fast, and bat-extensible by one parameter. Above it: SAI (pitch),
modulation bank (cortex), and a small train-once-freeze-forever cortex on Iddo's voice. Mouth:
**Pink Trombone physics** (MIT) in **Story & Bunton 2018** child geometry, with German
**VocalTractLab** as validation oracle only. Nothing found beats this combination on fidelity,
speed, and license at once.

**Already MEASURED during execution (2026-08-26 05:00):** CARFAC vendored on eran2
(SHA 4cdb95ee), 65 channels at 16 kHz, JAX steady-state ~25 ms per 0.5 s clip — at the speed gate —
**and a real vendor bug caught:** at fs=16000 the JAX backend silently applies a 3-tap AGC spatial
FIR where the design demands 5-tap (NumPy-vs-JAX correlation 0.41 on a real clip). NumPy is the
truth; the vendored JAX is being patched. Upstream's own equivalence test only runs at 22050 Hz and
never sees it.

## 2. The lenses and what each brought

| lens | winner | evidence grade | key fact |
|---|---|---|---|
| Germany (mouth) | VocalTractLab 2.4 | CLAIMED-BY-AUTHOR + headers read | `vtlSetAnatomyFromAge(months)` — the only anatomical child model with code; GPL; speed unpublished → oracle only |
| USA (mouth) | Pink Trombone physics / Story & Bunton child tables | source code read / published tables | real per-period LF + nasal + turbulence + bursts, MIT; child area functions birth→12y from 132 CT studies |
| Japan (mouth) | Maeda 7-param, Sawada loop concept | papers only | no code; the 7-dim control idea informs the gesture space |
| Cochlea (ear) | CARFAC v2 | MEASURED here | see ruling; C++ port is v1-era (two-cap IHC differs — verified in cpp/ihc.h) |
| Cortex (ear) | NSL rate-scale (port) + modulation bank | literature | no maintained Python port exists — ~200-line port owed |
| Bat headroom | CARFAC fs-derived channel map | INFERRED, unverified numerics | 384 kHz → CF≈163 kHz; nobody has published CARFAC above 48 kHz — must be probed, not promised |
| PC archaeology | voice-ant-farm/mouth.py burst mechanism | code read | the only local plosive/frication code ever written; gets ported |

## 3. במחלוקת · DISSENT — kept visible, as the law requires

1. **Ear backend (JAX vs C++):** JAX seat says patched-JAX meets the 25 ms gate with one code path
   for training and search. C++ seat says the Eigen core is 2× faster and JAX just proved it can
   silently diverge. **Ruling: JAX-patched now, C++ port stays a named contingency.** Dissent stands.
2. **Mouth fidelity:** PT-physics seat accepts known formant error (F1 ~18.6%, F2 ~24.2% in
   literature) buying 100× speed; VTL seat says a child's vowels deserve the anatomical model.
   **Ruling: PT-physics with REAL child areas (Story) + Dresden-MRI validation gate — if gate (b)
   fails at 15%, the dissent reopens.**
3. **Trained cortex:** the purist seat holds any learned weights in a judge invite bias
   (single-session corpus can teach "2026-08-23" instead of syllables). **Ruling (Iddo's word):
   train once on the fleet, freeze forever, keep the pure-DSP judge as permanent A/B.** Dissent
   recorded, mitigations mandatory.

## 4. What MIKO could not verify (honesty section)

- CARFAC numerics at 192/384 kHz — untested anywhere in the literature.
- VTL synthesis real-time factor — no published number; measure before ever moving it into a loop.
- Story & Bunton table completeness in the open-access text — being verified during Mouth Phase 0.

**Ruling: רלוונטי.** Sources and full details: the four survey reports in this session +
`D:\CLAUDE\eran-brain\ear3\VENDORED.md` + plan `C:\Users\<user>\.claude\plans\lazy-knitting-crown.md`.
