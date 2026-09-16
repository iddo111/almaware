> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# BUILD NOTES — Sawada's Talking Robot → ERAN's Physical Throat
# הערות בנייה — מרובוט הדיבור של סאוודה אל הגרון הפיזי של ערן

Sawada built, over ~20 years, exactly the machine we are starting: air source → vibrating soft cords → deformable soft tube → motors → microphone → learning loop that listens to itself. He got vowels, nasals, pitch and singing. **Every Sawada fact below is cited to a file in this directory** (tags = the SOURCE FILES table in `specs-found.md`). Our-side facts cite our own files in `D:\CLAUDE\alma-larynx`.

סאוודה בנה במשך כ-20 שנה בדיוק את המכונה שאנחנו מתחילים: מקור אוויר ← מיתרים רכים רוטטים ← צינור רך מתעוות ← מנועים ← מיקרופון ← לולאת למידה שמקשיבה לעצמה. הוא השיג תנועות, אנפוף, גובה צליל ושירה. כל עובדה מצוטטת לקובץ בתיקייה הזאת.

---

## 1. LUNGS — his compressor vs. our plenum / ריאות — המדחס שלו מול הפלנום שלנו

**Sawada:** air compressor at **6000 hPa** [JSME2000 p.647; JRM2002 p.455], later **8000 hPa** [Intech2007 §3.1] → **pressure-reduction valve** dropping to ≈ trachea pressure and *smoothing compressor fluctuation* → motor-driven **airflow screw valve** = volume control; the 2007 system inserts an **air buffer** between pump and valves [Intech2007 Fig.1]. Human reference he designed to: lung pressure ≈ **+200 hPa** above atmospheric; working airflow in the F0 experiments **10–16 l/min** [JSME2000 Fig.3; JRM2002 Fig.3].

**Us:** the plenum plays his reduction-valve + buffer role. ⚠️ **CORRECTED 2026-08-29:** this paragraph used to say "the fold needs only ~+200 hPa". That was wrong, and it propagated into a diagram handed to Iddo. **200 hPa = 20 kPa.** That is *Sawada's* lung pressure driving *his* two-layer silicone cords. **Cast M5 synthetic folds phonate at an onset of 0.27–1.7 kPa** (Murray & Thomson 2012: M5-UNI 0.84, MRI 1.68, EPI+fibre 0.27; human 0.29–0.49) — i.e. **12 to 70 times lower**. Driving an M5 fold at 20 kPa would blow it open, not make it sing. Our design point, if we cast M5 folds, is **~0.3–2 kPa at roughly 70–340 mL/s** — well inside aquarium-pump territory, with the regulator doing real work. Sawada's 10–16 l/min belongs to his rig, not ours. His lesson: raw pump pulsation reaches the voice; the buffer volume between source and cords is what he added by 2007, so our plenum is not optional plumbing, it is the anti-flutter element.

**אצלנו:** הפלנום ממלא את תפקיד שסתום ההפחתה והבאפר שלו. ⚠️ **תוקן 2026-08-29:** קודם כתוב היה "הקפל צריך רק ~200 hPa" — טעות. **200 hPa = 20 kPa**, וזה לחץ הריאות של *סאוודה* עבור *המיתרים שלו*. קפלי M5 יצוקים מתנדים בסף של **0.27–1.7 kPa** — פי 12 עד 70 פחות. 20 kPa על קפל M5 יפוצץ אותו, לא ישיר אותו. הלקח: פעימות המשאבה מגיעות לקול; הפלנום הוא רכיב מניעת-הרפרוף, לא סתם צנרת.

## 2. VOCAL CORDS — his two-cord silicone vs. our Ecoflex M5 fold / מיתרי הקול

**Sawada:** Phase 1 (1996–2002) a commercial artificial larynx: vibrating **rubber strip, width 5 mm**, outlet φ5 mm, F0 **110–350 Hz** by tension (F0 model f = (1/2L)·√(S/D)) [JSME2000 Fig.1, eq.(1); JRM2002 Fig.1, Fig.3]. Phase 2 (2005→): custom **two vibrating cords molded of silicone rubber "with the softness of human mucous membrane"**; of three hardness variants the winner was **two-layered — hard silicone core + soft outer coating** — chosen for the most human-like waveform and spectrum; cord length scale 10–20 mm; **one DC motor pulls the cords** for pitch; F0 110–250 Hz [Intech2007 §3.3, Fig.8–9; Hindawi2008]. In 2016 he was back to describing a "thin rubber band, width 5 mm" at 110–350 Hz [JCMSI2016 §2]. (Comparison, different group: Waseda Talker WT-5 uses hollow layered **Septon** thermoplastic folds [WT5].)

**Us:** our fold is cast in **Ecoflex** from **THROAT-MOLD-A** — an open-top pour mold whose core is the published **M5 (Titze/Scherer) synthetic-fold cross-section**, fold length **17 mm**, cast block clamping into the buzz-collar with the M5 face toward the airway [make_real_mold.py; THROAT-MOLD-A-real.stl; THROAT-MOLD-print-ready.stl]. Convergences to trust: his winning cord is *layered* (stiff body + soft cover) — exactly the philosophy of the M5 synthetic-fold literature; his cord length (10–20 mm) brackets our 17 mm; his F0 physics says **tension control is the pitch knob** — he spent one dedicated DC motor on it [Intech2007 Fig.8]. Divergence to note honestly: he vibrates a strip/two cords over an orifice; we cast a single M5 half-fold — see open question Q3.

**אצלנו:** הקפל נוצק באקופלקס מהתבנית THROAT-MOLD-A עם חתך M5 (טיצה/שרר), אורך 17 מ"מ, נכנס לקולר. ההצלבות: המיתר המנצח שלו שכבתי (ליבה קשה + ציפוי רך) — בדיוק פילוסופיית ה-M5; האורך שלו (10–20 מ"מ) עוטף את 17 שלנו; פיזיקת ה-F0 שלו אומרת שמתיחה היא כפתור הגובה — הוא הקדיש לה מנוע. הבדל כן: אצלו שני מיתרים/רצועה, אצלנו קפל M5 יחיד — שאלה פתוחה 3.

## 3. THE TUBE — his 180 mm silicone tract vs. our soft tube / הצינור

**Sawada:** one soft **silicone-rubber resonance tube, length 180 mm, bore φ36 mm (10.2 cm²)**, "molded with the softness of human skin", deformed by **stainless press-bars pushed/pulled radially from outside** [JRM2002 p.455 Fig.4; Intech2007; Hindawi2008]. He copied the human reference: tract ≈170 mm, cross-section varying 0–20 cm² [JSME2000 p.647]. His very first tube (250 mm × φ30, rubber with **polyurethane coating inside and out** to improve resonance) was replaced by the plain silicone one [JSME2000 p.647]. Wall thickness and durometer were **never published** [specs-found.md UNKNOWN].

**Us:** our soft tube should copy his final numbers as the starting point — **~180 mm working length, ~φ36 bore** — because that pair is proven to put F1/F2 of the five vowels within reach of external pinching. His coating experiment says surface finish audibly matters; the wall thickness we must find by experiment (Q1).

**אצלנו:** צינור רך — נקודת פתיחה 180 מ"מ אורך, קוטר פנימי ~36 מ"מ, כי הזוג הזה הוכח כמכניס את הפורמנטים של חמש התנועות לטווח צביטה חיצונית. ניסוי הציפוי שלו אומר שגימור הפנים נשמע; את עובי הדופן נמצא בניסוי (שאלה 1).

## 4. MOTORS — his pinch actuators vs. our servos / מנועים

**Sawada's count grew: 5 → 6 → 8 → 12.** 2002: DC motors at **5 positions** along the tube (vowels achieved) [JRM2002 p.455]. 2007: six motors incl. nasal [Intech2007 §3.4]. 2008: **compact servos at 8 positions**, 10 servos in the whole robot [Hindawi2008; ICDVRAT2008]. 2016: **12 motors total** (tract shape, tongue, air intake, nasal), **command-type servos on RS-485**, motor units −1500…+1500 where **125 units = 2 mm** of pinch [JCMSI2016 §2, §4.3]. Measured single-motor formant sensitivity [JCMSI2016 §4.3]:

| tube section / אזור | effect / השפעה |
|---|---|
| lip-end (motors 1–3) | F2 +50 Hz/mm, F3 +40 Hz/mm |
| middle (3–6) | F2 +20 Hz/mm, F3 +20 Hz/mm |
| throat-end (6–8) | F1 +15 Hz/mm, F2 +10 Hz/mm |

**Us:** the sensitivity table is the gold nugget — it says (a) **5 pinch points suffice for vowels** (that is all he had in 2002), start there, not at 12; (b) resolution needed is *sub-millimeter-ish* (his 125 units per 2 mm ⇒ 16 µm command steps) but the *audible* scale is tens of Hz per mm — hobby servos with ~0.5 mm repeatability through a lever are plausibly enough for vowel-level work; (c) put the servos where they pay: lip-end moves F2/F3, throat-end moves F1.

**אצלנו:** הטבלה היא הזהב — (א) 5 נקודות צביטה מספיקות לתנועות (זה כל מה שהיה לו ב-2002), נתחיל שם ולא ב-12; (ב) הסקאלה הנשמעת היא עשרות הרץ למ"מ — סרוו תחביבי דרך מנוף כנראה מספיק לתנועות; (ג) לשים סרוו איפה שמשלם: קצה-שפתיים ל-F2/F3, קצה-גרון ל-F1.

## 5. NASAL CAVITY + TONGUE — what he needed for consonants / אף ולשון

**Sawada:** **plaster nasal cavity (~60 cm³ human reference)** on the intake side, with a motor-driven **sliding valve** as soft palate — open → /n/, /m/; closed → plosives /p/, /t/ [Intech2007 §3.2, Fig.4; Hindawi2008]; a rotary valve by 2016 [JCMSI2016 §2]. **No tongue until 2010** — explicitly named as why /r/ and fricatives failed [Intech2007 conclusions]; then a string+servo tongue for /l/ [ICDVRAT2010], a shaped silicone tongue by 2016 [JCMSI2016 §2]. Plosive learning needed **visual information**, not audio alone [ICDVRAT2012]. Consonant *timing* eventually needed a dedicated **cerebellum-like SNN** [ConnSci2018 = 2018-cerebellum-snn-timing-talking-robot-connection-science.pdf].

**Us:** phase-1 ERAN throat has no nasal branch and no tongue — which by Sawada's own record means: **vowels, pitch and singing are reachable; /m/ /n/ plosives and fricatives are NOT.** That is fine and should be said out loud in every demo claim. His 20-year consonant ladder (nasal valve → tongue → vision → SNN timing) is our future roadmap, pre-validated.

**אצלנו:** שלב 1 בלי אף ובלי לשון — ולפי הרישום של סאוודה עצמו זה אומר: תנועות, גובה ושירה בהישג יד; אנפוף, פוצצים וחוככים — לא. לומר זאת בקול בכל הדגמה. סולם העיצורים שלו (שסתום אף ← לשון ← ראייה ← SNN לתזמון) הוא מפת הדרכים העתידית שלנו, מאומתת מראש.

## 6. THE LEARNING LOOP — his SOM vs. ERAN's frozen-cochlea judge / לולאת הלמידה

**Sawada:** a microphone listens to the robot itself; pitch loop: 1 kHz sampling, 1024-pt FFT, ≈1 Hz resolution, 0.6 Hz match threshold [JSME2000 p.649; Intech2007]. Phoneme loop: 10th-order PARCOR (8 kHz, 256 pt) [JSME2000 p.649], later 10th-order LPC cepstrum feeding a **SONN with a 20×20 SOM**, trained on only **150 random articulations** ("motor babbling"), then reinforced with 5 Japanese vowels × 6 speakers [Intech2007 §3.5; Hindawi2008]; Dual-SOM (2011) and two 3D-SOMs (2015) refined the map [KIKAIC2011; IJAE2015]; PARCOR template matching for vowel sequences in 2016 [JCMSI2016; 2016-automatic-vowel-sequence-reproduction-parcor.pdf].

**Us:** ERAN's judge is his **frozen cochlea** — the same organ that already found /ah/ in the digital tract. Structurally identical loop: articulate → listen to yourself → map motor-space to sound-space → climb toward a target. The encouraging number is **150**: random articulations were enough to organize Sawada's whole motor-to-vowel map. That is an afternoon of babbling for a physical throat, not a corpus. Caveats from our own scars: the cochlea is a vowel judge, not a consonant judge (it can't hear consonants — consistent with Sawada needing vision + SNN for exactly those), and only real acoustics move ERAN (synthetic-corpus scar) — which is the whole argument for building the physical throat at all.

**אצלנו:** השופט של ערן הוא השבלול הקפוא — אותו איבר שכבר מצא /ah/ בצינור הדיגיטלי. אותה לולאה בדיוק: הגה ← הקשב לעצמך ← מפה ממרחב-מנוע למרחב-צליל ← טפס אל מטרה. המספר המעודד: 150 הגיות אקראיות הספיקו לארגן את כל המפה של סאוודה — צהריים של מלמול, לא קורפוס. הסתייגות מהצלקות שלנו: השבלול שופט תנועות ולא עיצורים — עקבי עם זה שסאוודה נזקק לראייה ו-SNN בדיוק שם.

---

## OPEN ENGINEERING QUESTIONS / שאלות הנדסה פתוחות

1. **Tube wall thickness + durometer / עובי דופן וקשיות** — never published anywhere open [specs-found.md UNKNOWN; misses.txt #17 #28]. Must be found by experiment: thin enough for a servo to pinch ~5–10 mm deep at hobby torque, thick enough to spring back and hold resonance. Which Ecoflex/Dragon Skin grade plays the role of "softness of human skin"?
2. **Servo force budget / תקציב כוח** — Sawada never published motor models or torques. What force closes our tube by 2 mm... 10 mm, through what lever geometry, and is a standard hobby servo's resolution really ≤0.5 mm at the pinch point?
3. **One M5 fold vs. his two cords / קפל אחד מול שני מיתרים** — his winner is *two* vibrating cords [Intech2007 §3.3]; our mold casts a single M5 fold against a collar. Does a hemilarynx (fold against rigid wall) buzz well enough at +200 hPa, or do we need to cast and oppose two?
4. **Pitch tension mechanism / מנגנון מתיחה** — he dedicated one DC motor to pulling the cords for F0 110–350 Hz [Intech2007 Fig.8; JCMSI2016]. Our clamp-in-collar design has no tensioner yet. Add one, or accept fixed F0 in phase 1?
5. **Plenum sizing / מידות הפלנום** — ✅ **PARTLY ANSWERED 2026-08-29, and the answer reverses our assumption.** We assumed a bigger buffer is safer. The von Kempelen replica work at Saarland [Brackhane & Trouvain 2008/2009; Brackhane HSCR 2017] reports the opposite as a **measured failure**: a windchest built at **1.5× Kempelen's inner volume caused resonance vibrations and DAMPED the reed**, and had to be scrapped. The historically correct chamber is **40 × 92 × 66 mm ≈ 244 cm³** (their first, oversized attempt was 85 × 140 × 80 mm ≈ 952 cm³). So the plenum is a **tuned** element, not "as big as convenient" — oversize it and you kill the source. Start near 250 cm³ and measure. Sawada's own buffer volume is still unpublished.
   **בעברית:** הנחנו שבאפר גדול יותר בטוח יותר — **הפוך**. שכפול של מכונת פון קמפלן עם נפח פי 1.5 **דיכא את הלשונית** והושלך. הנפח ההיסטורי הנכון: 40×92×66 מ"מ ≈ 244 סמ"ק. הפלנום הוא רכיב **מכוון**, לא "כמה שנוח".
6. **Pinch-point count and placement / מספר ומיקום צביטות** — 5 gave him vowels (2002), 8 gave training-grade articulation (2008), 12 the final robot (2016). Where on our tube do 5 servos land, scaled from his 180 mm layout [JRM2002 Fig.4; JCMSI2016 §4.3]?
7. **Coupling fold → tube / חיבור קפל לצינור** — his cords sat in a plastic body screwed to the tube intake [JRM2002 Fig.1]. How does our buzz-collar + cast block mate to the soft tube without leaks at 200 hPa?
8. **The judge's deafness to consonants / חירשות השופט לעיצורים** — Sawada needed visual feedback for plosives [ICDVRAT2012] and an SNN for timing [ConnSci2018]. When ERAN's cochlea-judge plateaus on vowels, which of those two ladders do we climb first?
9. **The 2017 redesigned cords / המיתרים המחודשים של 2017** — the one paper likely holding improved cord dimensions is IEEE-paywalled [misses.txt #17, #28]. Worth an inter-library request before we iterate cords blind.

---
*Compiled 2026-08-25 by claude-cli (Fable). Sawada-side facts: only what the harvested files in this directory state, tags per `specs-found.md`. ERAN-side facts: the physical-throat plan + `make_real_mold.py` / THROAT-MOLD-A in `D:\CLAUDE\alma-larynx`. Where a number is unknown, it says unknown.*
