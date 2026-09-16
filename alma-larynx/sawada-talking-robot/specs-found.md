# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY.

# Sawada Talking Robot — VERIFIED ENGINEERING NUMBERS
### מספרי הנדסה מאומתים מרובוט הדיבור של פרופ' סאוודה

Every number below was READ in a source saved in this directory. Citation = [tag] → file list at the bottom.
Numbers not found in any source are listed at the end as UNKNOWN — nothing here is invented.

---

## 1. VOCAL TRACT (the ONE soft resonance tube) / קנה התהודה

**Final design (2002 → 2016, unchanged):**
- Material: **silicone rubber**, "molded with the softness of human skin" [JRM2002 p.455; Intech2007]
- Length: **180 mm** [JRM2002 Fig.4; Intech2007; Hindawi2008; JCMSI2016]
- Bore diameter: **φ = 36 mm**, i.e. cross-sectional area **10.2 cm²** [JRM2002 p.455; Intech2007]
- Fig. 4 of [JRM2002] additionally marks a **45 mm** dimension across one press-bar interval of the tube body.
- Fig. 2 of [Intech2007] marks **180 (lip side), 60, 40** on the structural drawing (mm; 60/40 are the intake-side outer dimensions as drawn).
- Deformation: **displacement forces applied from outside the body with stainless bars** pushed/pulled radially [JRM2002 p.455]

**Pinch-point actuators — count grew over the years:**
- 2002: **DC motors at 5 positions** x_j (j = 0–4), intake → outlet [JRM2002 p.455] (same in [JSME2000] prototype and [Intech2007])
- 2007: "six motors equipped in the vocal tract and the nasal cavity" for phoneme NN control [Intech2007 §3.4]
- 2008: **compact servo motors at 8 positions** x_j (j = 1–8) along the tube; NN associates sound with **9 motors** (8 tract + nasal valve); **10 servomotors in total** in the whole robot [Hindawi2008; ICDVRAT2008]
- 2016: **12 motors total** — vocal-tract shape, tongue motion, air intake, nasal cavity; **command-type servo motors on RS-485**, motor data value range −1500…(+1500), **125 motor-value units = 2 mm** of pinch displacement [JCMSI2016]
- 2016 grouping: lip-end section = motors 1–3, middle = 3–6, throat-end = 6–8 [JCMSI2016 §4.3]

**Measured formant sensitivity to a single pinch-motor (2016):**
- Lip-end group: F2 +50 Hz/mm, F3 +40 Hz/mm
- Middle group: F2 +20 Hz/mm, F3 +20 Hz/mm
- Throat-end group: F1 +15 Hz/mm, F2 +10 Hz/mm [JCMSI2016 §4.3]

**First prototype tube (1996–2000, before the silicone tract):**
- rubber flexible tube, **L = 250 mm, D = 30 mm (7.1 cm²)**, **polyurethane coatings inside and outside** to improve resonance; DC motors at 5 positions [JSME2000 p.647]

**Human reference values the design copied:** vocal tract ≈ **170 mm** long, cross-section varies **0–20 cm²**; nasal tract volume **60 cm³** [JSME2000 p.647; JRM2002 p.455]

---

## 2. VOCAL CORDS / מיתרי הקול

**Phase 1 (1996–2002): commercial artificial larynx** (device used by laryngectomy patients):
- vibrating **rubber strip, width 5 mm**, stretched over a plastic body; **sound outlet φ = 5 mm** [JSME2000 Fig.1; JRM2002 Fig.1]
- F0 model: f = (1/2L)·√(S/D) — L strip length, S tension, D material density [JSME2000 eq.(1)]
- Measured F0: **130–320 Hz** [JSME2000 Fig.3] / **110–350 Hz** [JRM2002 Fig.3]
- Tension axis as printed: **0–32 in units of [0.01 gf]**; airflow curves at **10–14 l/min** [JSME2000 Fig.3] and **10–16 l/min** [JRM2002 Fig.3]

**Phase 2 (2005→): custom two-cord silicone vocal cords** (Sawada lab):
- "two vibrating cords molded with silicone rubber with the **softness of human mucous membrane**" [Intech2007 §3.3; Hindawi2008]
- Three hardness variants built: hard / soft / medium; the medium = **two-layered: hard silicone core + soft silicone outer coating** — chosen for best (most human-like) waveform & spectrum [Intech2007 §3.3; Hindawi2008]
- Vocal-cord length scale in the pitch experiment: **10–20 mm** (axis of Fig. 9; 15 mm marked) [Intech2007 Fig.9]
- Pitch control: **one DC motor pulls the cords (tensile force)** [Intech2007 Fig.8]
- F0 range of two-layer cords: **110–250 Hz** [Intech2007]; later rubber-band cords: **110–350 Hz** [JCMSI2016; IJAE2015]
- 2016 wording: "vibration of a thin **rubber band, width 5 mm**, attached to a plastic body" — F0 **110 Hz–350 Hz** by tension + air pressure [JCMSI2016 §2]

(Comparative, DIFFERENT robot: Waseda Talker WT-5 vocal folds are molded of **"Septon" thermoplastic rubber**, hollow layered human-like structure — Fukui/Takanishi group, saved here only for comparison [WT5].)

---

## 3. LUNGS / AIR SUPPLY / הריאות

- Air source: **air compressor**; air compressed to **6000 hPa** [JSME2000 p.647; JRM2002 p.455]; the 2007 chapter says **8000 hPa** (later pump) [Intech2007 §3.1]
- Human reference: lung pressure ≈ **+200 hPa above atmospheric** [JSME2000; JRM2002; Intech2007]
- **Pressure-reduction valve** at compressor outlet drops pressure to ≈ trachea pressure and smooths compressor fluctuation [JSME2000; JRM2002]
- **Airflow control valve** (motor-driven screw) = voice volume control [JSME2000; JRM2002]
- 2007 system adds an **air buffer** between pump and valves (Fig. 1 block diagram) [Intech2007]
- Working airflow in the F0 experiments: **10–16 l/min** [JSME2000 Fig.3; JRM2002 Fig.3]
- Pitch/volume use **2 motors**: motor 1 = cord tension, motor 2 = airflow-valve screw [JSME2000 p.647; JRM2002]

---

## 4. NASAL CAVITY + SOFT PALATE / חלל האף

- Nasal cavity **made of plaster**, attached to the intake part of the resonance tube [Intech2007 §3.2; Hindawi2008]
- Human reference volume copied: **60 cm³** [JSME2000; Intech2007]
- **Sliding valve** (= soft palate) at the tube–nasal junction, motor-controlled: open → /n/, /m/; closed → plosives /p/, /t/ [Intech2007 Fig.4; Hindawi2008]
- 2016: replaced by a **rotary valve** [JCMSI2016 §2]

---

## 5. TONGUE + LIPS / לשון ושפתיים

- Up to 2008: **no tongue** — noted as the reason /r/ and fricatives fail [Intech2007 §conclusions]
- 2010: tongue added, **string + servo motor for up-down motion** to articulate /l/ [ICDVRAT2010]
- 2016: **silicone tongue "made in reference to the shape and size of a human tongue"** [JCMSI2016 §2]
- Human-size head model (2000, pilot): based on a **Koken Co., Ltd. 3D medical-education model**, all tissues (tract, tongue, lips, skin) silicone rubber; **2 jaw motors** (open–close + forward–backward) [JSME2000 §4]

---

## 6. AUDITORY FEEDBACK / LEARNING NUMBERS

- Pitch loop: sampling **1 kHz**, FFT window **1024 points**, resolution ≈ **1 Hz**, pitch-match threshold **0.6 Hz**; pitches assumed < **500 Hz** [JSME2000 p.649; Intech2007]
- Phoneme loop: **10th-order PARCOR**, sampling **8 kHz**, **256 points** [JSME2000 p.649]; later 10th-order **LPC cepstrum** as SONN input [Intech2007; Hindawi2008]
- SONN: SOM array **20×20**; trained on **150 random articulations**; reinforcement with 5 Japanese vowels × **6 speakers** [Intech2007 §3.5]
- 2011: Dual-SOM topological learning (Japanese, kikaic 77-775) [KIKAIC2011]
- 2015: two **3D-SOMs** (3D-Motor_SOM + 3D-Phonetic_SOM), sampling 8 kHz [IJAE2015]
- 2016: PARCOR-based real-time modification; voice recorded at 8 kHz sampling in Matlab; motors driven from Matlab over RS-485 [JCMSI2016]
- Singing range acquired in 2000 experiment: pitches C to G (≈130–200 Hz figure axis) [JSME2000 Fig.7]

---

## UNKNOWN — numbers NOT found in any open source here
- Silicone tube **wall thickness** — never stated in any of the saved papers.
- Exact silicone rubber grade/durometer (only "softness of human skin" / "softness of mucous membrane").
- Exact motor models/torques (only "compact servo motors", "command-type servo motors, RS-485", "DC motors").
- Two-layer vocal-cord layer thicknesses.
- The redesigned-2017 vocal cords dimensions (paper is IEEE-paywalled — see misses.txt #17).

---

## SOURCE FILES (all in this directory)
| tag | file | what it is |
|---|---|---|
| JSME2000 | sawada-2000-jsme-intl-mechanical-model-vocal-system-auditory-feedback.pdf | Sawada & Hashimoto, JSME Int. J. C 43(3):645-652, 2000. SCANNED — numbers read visually from pages 2-4. |
| JRM2002 | 2002-jrm-vocalization-control-mechanical-vocal-system-auditory-feedback.pdf | Higashimoto & Sawada, J. Robotics & Mechatronics 14(5):453, 2002 (CC BY-ND). Text layer garbled; read visually. |
| Intech2007 | sawada-2007-intech-talking-robot-vocalization-singing.pdf | Sawada, IntechOpen chapter, DOI 10.5772/4761 (22 pp, the fullest single description). |
| Hindawi2008 | 2008-robotic-voice-simulator-hearing-impaired-training.pdf | Sawada, Kitani, Hayashi, J. Biomedicine & Biotechnology 2008:768232. |
| ICDVRAT2008 | 2008-interactive-training-speech-articulation-hearing-impaired-icdvrat.pdf | Kitani, Hayashi, Sawada, ICDVRAT 2008 — "10 servomotors in total". |
| ICDVRAT2010 | 2010-robotic-vocalization-training-system-auditory-impaired-icdvrat.pdf | tongue string+servo for /l/. |
| IJAE2015 | 2015-ijae-talking-robot-expressive-speech-communication.pdf | Sawada, Int. J. Affective Engineering 14(2):95, 2015 (J-STAGE). |
| JCMSI2016 | 2016-jcmsi-realtime-interactive-modification.pdf | Vo Nhu & Sawada, SICE JCMSI 9(6):251, 2016 — 12-motor robot, RS-485, formant-per-mm numbers. |
| KIKAIC2011 | sawada-2011-jsme-topological-structure-learning-JP.pdf | Kitani, Hara, Sawada, JSME Trans C 77(775):1062, 2011 (Japanese). |
| WT5 / WT7 | waseda-talker-WT5-2007-jsme-vocal-cord-model-JP.pdf, waseda-talker-WT7-2008-jrsj-vocal-cord-nn-control-JP.pdf | DIFFERENT GROUP (Fukui/Takanishi, Waseda Talker) — comparison only. Septon vocal folds. |
| — | osuka-1998-jrsj-mechanical-speech-synthesizer-different-group-JP.pdf | DIFFERENT GROUP (Osuka et al., Osaka Pref. U., Kenji Sawada) — kept for context. |
| — | sawada-2004-jsme-magazine-talking-singing-robot-JP.pdf | Sawada, JSME magazine 107(1033), 2004 (Japanese review). |

*Compiled 2026-08-25 by claude-cli (Fable) — every number traced to a saved source; misses recorded honestly in misses.txt.*
