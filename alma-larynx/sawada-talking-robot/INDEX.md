> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Sawada Talking Robot — Harvest Index / אינדקס האיסוף על רובוט הדיבור של סאוודה

Everything in this directory about Prof. Hideyuki Sawada's mechanical talking robot (Kagawa Univ. 1996–2017, Waseda 2017–), harvested 2026-08-25 by four parallel agents (lab pages, papers, specs, patents).
כל מה שנאסף על רובוט הדיבור המכני של פרופ' סאוודה — דפי מעבדה, מאמרים, מספרי הנדסה ופטנטים — נאסף ב-2026-08-25 על ידי ארבעה סוכנים במקביל.

**Start here / להתחיל כאן:** `specs-found.md` (every verified engineering number / כל מספר הנדסי מאומת) → `BUILD-NOTES.md` (mapping to ERAN's throat / מיפוי לגרון של ערן).

## The files / הקבצים

### ⭐ Deliverables / תוצרים
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| specs-found.md | Every verified engineering number, each cited to a saved source / כל מספר הנדסי מאומת עם ציטוט למקור | The single most useful file — the robot's full spec sheet / הקובץ השימושי ביותר: דף הנתונים המלא |
| BUILD-NOTES.md | Sawada's design mapped to ERAN's physical-throat plan / מיפוי התכן של סאוודה לתוכנית הגרון הפיזי של ערן | Turns the harvest into build decisions / הופך את האיסוף להחלטות בנייה |
| misses.txt | Honest record of everything NOT obtained / רישום כן של כל מה שלא הושג | Saves the next agent from re-hunting dead ends / חוסך לסוכן הבא ציד חוזר |

### 📄 Papers by Sawada's group / מאמרים של קבוצת סאוודה
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| sawada-2000-jsme-intl-mechanical-model-vocal-system-auditory-feedback.pdf | JSME Int. J. C 43(3):645, 2000 — first full system paper (scanned, no text layer) / מאמר המערכת הראשון | First-prototype numbers: 250×φ30 mm tube, 6000 hPa compressor, pitch loop / מספרי אב-הטיפוס |
| 2001-jsme-robomech-vocal-system-auditory-feedback-abstract.pdf | JSME ROBOMECH 2001 abstract / תקציר | Bridge between the 2000 and 2002 papers / גשר בין המאמרים |
| 2002-jrm-vocalization-control-mechanical-vocal-system-auditory-feedback.pdf | Higashimoto & Sawada, JRM 14(5):453, 2002 (CC BY-ND) / המאמר המכונן | Definitive Fig. 4: 180 mm × φ36 silicone tract, 5 stainless press-bars / השרטוט המכריע של הצינור |
| sawada-2007-intech-talking-robot-vocalization-singing.pdf (+.txt) | IntechOpen chapter, DOI 10.5772/4761, 22 pp / הפרק המקיף ביותר | Fullest single description: two-layer cords, plaster nasal cavity, SONN 20×20 / התיאור השלם ביותר |
| 2007-jaciii-robotic-auditory-system-musical-sounds-human-voices.pdf | Sawada, JACIII 11(9), 2007 / צד השמיעה | The robot's EAR — how it listens to itself / האוזן של הרובוט |
| 2008-robotic-voice-simulator-hearing-impaired-training.pdf (+.txt) | Sawada/Kitani/Hayashi, J. Biomed. Biotech. 2008 / מאמר הדגל | THE lead open paper: 8-motor tract, SOM maps, training use / מאמר הדגל הפתוח |
| 2008-pmc-fig-001.jpg … 008.jpg (8 files) | All 8 figures from the 2008 PMC paper / כל האיורים | Construction photos + SOM maps at full resolution / תמונות בנייה ברזולוציה מלאה |
| 2008-interactive-training-speech-articulation-hearing-impaired-icdvrat.pdf | ICDVRAT 2008 / אימון דיבור לכבדי שמיעה | "10 servomotors in total" count / ספירת המנועים |
| 2010-robotic-vocalization-training-system-auditory-impaired-icdvrat.pdf | ICDVRAT 2010 / הוספת הלשון | Tongue added: string + servo for /l/ / הלשון הראשונה |
| 2012-plosive-sound-vocalization-talking-robot-visual-information-icdvrat.pdf | ICDVRAT 2012, 1 p / פיצוצי + מידע חזותי | Plosives needed VISUAL info, not just audio — a warning for us / אזהרה: פוצצים דרשו עין, לא רק אוזן |
| 2014-japanese-vowel-classification-fuzzy-inference.pdf | J. Korea Convergence Soc. 5(1), 2014 / סיווג תנועות | Vowel classification variant (fuzzy) / וריאנט סיווג |
| 2015-ijae-talking-robot-expressive-speech-communication.pdf (+.txt) | Int. J. Affective Engineering 14(2):95, 2015 / דיבור רגשי | Two 3D-SOMs, expressive speech / SOM תלת-ממדי |
| 2016-automatic-vowel-sequence-reproduction-parcor.pdf | IEIE Trans. SPC 5(3), 2016 / רצפי תנועות | PARCOR template matching — vowel sequences / התאמת תבניות |
| 2016-jcmsi-realtime-interactive-modification.pdf (+.txt) | Vo Nhu & Sawada, SICE JCMSI 9(6):251, 2016 / הרובוט הסופי | Final 12-motor robot, RS-485, formant-Hz-per-mm numbers / רגישויות הפורמנטים למ"מ |
| 2018-cerebellum-snn-timing-talking-robot-connection-science.pdf | Connection Science 30(4), 2018, 22 pp / תזמון עיצורים | Cerebellum-like SNN for consonant TIMING — closest to ERAN's brain style / הכי קרוב לסגנון המוח של ערן |
| sawada-2004-jsme-magazine-talking-singing-robot-JP.pdf | JSME magazine 107(1033), 2004 (Japanese) / סקירה ביפנית | Mid-era review / סקירת אמצע התקופה |
| sawada-2011-jsme-topological-structure-learning-JP.pdf | JSME Trans C 77(775):1062, 2011 (Japanese) / Dual-SOM | Dual-SOM voice acquisition / רכישת קול |

### 📄 Other groups — comparison only / קבוצות אחרות — להשוואה בלבד
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| waseda-talker-WT5-2007-jsme-vocal-cord-model-JP.pdf | Fukui/Takanishi (DIFFERENT group), WT-5 vocal cords / קבוצה אחרת | Septon thermoplastic folds, hollow layered — alternative cord design / תכן מיתרים חלופי |
| waseda-talker-WT7-2008-jrsj-vocal-cord-nn-control-JP.pdf | WT-7 NN cord control (DIFFERENT group) / קבוצה אחרת | NN control of mechanical folds / בקרת NN |
| osuka-1998-jrsj-mechanical-speech-synthesizer-different-group-JP.pdf | Osuka et al. (a different Kenji Sawada!) / קבוצה אחרת | Earlier mechanical speech synthesizer, context / הקשר היסטורי |

### 🏛️ Lab pages — current Waseda / דפי המעבדה בוואסדה (היום)
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| waseda-lab-home.md | Lab About/home page / דף הבית | Current lab does NOT mention the talking robot / המעבדה הנוכחית כבר לא עוסקת ברובוט |
| waseda-sawada-bio-career.md | Full career/bio (b.1967; Kagawa 1999-2017, Waseda 2017-) / קורות חיים | Timeline of the whole program / ציר הזמן |
| waseda-lab-research-intro-ja.md | 研究紹介 current research (Japanese) / מחקר נוכחי | Shows the pivot to tactile/SMA / הפנייה למישוש |
| waseda-lab-projects-en.md | Projects/grants (English) / מענקים | Funding history / היסטוריית מימון |
| waseda-lab-members.md | Lab members / חברי מעבדה | Who to contact / למי לפנות |
| waseda-pubs-before-2016-kagawa-era.md | Kagawa-era publication list / רשימת פרסומי קגאווה | 50+ vocal/singing entries — the densest bibliography / הביבליוגרפיה הצפופה ביותר |
| waseda-pubs-2017-2026.md | Year-by-year pubs 2017-2026 / פרסומים אחרונים | What the robot line became / מה קרה לקו המחקר |
| waseda-rdb-profile-ja.md / -en.md | Waseda researcher-DB full records / רשומות מלאות | Grants + all pubs + misc works, huge / הרשומה המלאה |
| waseda-sawalab-intro-poster-2022.jpg | Lab intro poster, 2752×3893 / פוסטר המעבדה | Visual overview of the lab today / סקירה חזותית |

### 🏛️ Lab pages — Kagawa era via Wayback / דפי קגאווה דרך ארכיון האינטרנט
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| kagawa-lab-home-en-2010-wayback.md | 2010 English home: KTR-ver.3 robot, demo-video index, press / דף הבית 2010 | Names the robot KTR-ver.3; lists all demo videos + media / שם הרובוט ורשימת הדגמות |
| kagawa-lab-laboratory-en-2010-wayback.md | Lab page: Voice & Sound group, address / דף המעבדה | Group structure / מבנה הקבוצה |
| kagawa-voice-group-2006-wayback.md | Voice group projects (Japanese) / קבוצת הקול | Robot + speech-training for articulation disorders / הרובוט + אימון דיבור |
| kagawa-topics-2006-wayback.md | Media coverage + demo-video index / סיקור תקשורתי | What existed as video (mostly lost) / מה היה בווידאו |
| kagawa-paperlist-2006-wayback.md | Publication list as of 2006 / רשימת פרסומים 2006 | Early mechanical-voice papers / המאמרים המוקדמים |
| kagawa-research-2004-wayback.md / -2001-wayback.md | Research pages 2001/2004 / דפי מחקר | The 2000 JSME auditory-feedback citations / ציטוטי 2000 |
| kagawa-sawada-profile-en-2010-wayback.md, kagawa-lab-ja-2006-wayback.md | Profiles / פרופילים | Bio context / רקע |
| kagawa-talking-robot-mechanism-2005.jpg / -2007.jpg | **Verified mechanism photos** / תמונות המנגנון | Silicone tract, ~8 pinch motors, nasal block, feedback mic — SEE the machine / לראות את המכונה |
| kagawa-newscientist-2002-article-scan.jpg | Scan of New Scientist May 2002 article / סריקת הכתבה | Only surviving copy of the article / העותק היחיד ששרד |
| kagawa-lab-view-2007.jpg, sawada-portrait-kagawa.jpg, kagawa-book-cover-takarajima-2004.jpg | Lab view, portrait, book cover / תמונות אווירה | Context / הקשר |

### 📰 Press / עיתונות
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| ieee-spectrum-freaky-robot-mouth-learns-to-sing.md | Full IEEE Spectrum article (Ackerman, 13 Jul 2011) + YouTube links / הכתבה המלאה | Independent description: air-pump lungs, silicone tongue, nasal cavity, self-listening mic / תיאור עצמאי |
| ieee-spectrum-robot-mouth-closeup.jpg | Main article image / תמונת הכתבה | Tract close-up with pinch actuators / תקריב המנגנון |

### 🗃️ Databases / מאגרים
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| researchmap-publications-all.md | All 252 papers, newest-first / כל 252 המאמרים | Complete bibliography via researchmap API / הביבליוגרפיה השלמה |
| researchmap-publications-talking-robot-filtered.md | 43 talking-robot/vocal/singing papers / 43 מאמרי הרובוט | The relevant subset, pre-filtered / התת-קבוצה הרלוונטית |
| researchmap-published-papers.json | Raw API JSON (252 items) / ה-JSON הגולמי | Machine-readable source / מקור לקריאת מכונה |
| researchmap-profile.md | researchmap profile / פרופיל | ORCID-style record / רשומה רשמית |
| jstage-search-results-hideyuki-sawada.xml | Raw J-STAGE API results (174 hits) / תוצאות J-STAGE | Search reproducibility / שחזור החיפוש |

### ⚖️ Patents / פטנטים
**Headline finding: NO patent exists on the talking-robot mechanism itself** — verified 4 independent ways (see misses.txt #29). The drawings live only in the papers. His real portfolio is the SMA tactile line.
**הממצא המרכזי: אין פטנט על מנגנון רובוט הדיבור** — אומת בארבע דרכים בלתי-תלויות. השרטוטים קיימים רק במאמרים.
| file | what / מה | why it matters / למה חשוב |
|---|---|---|
| patent-JP4395572B2-sma-tactile-display-granted.pdf | Granted 2010, SMA vibration tactile display / פטנט מישוש | His actual patent line (NOT the throat) / קו הפטנטים האמיתי שלו |
| patent-JP2007048268A-sma-tactile-display-2005-app.pdf | Earlier 2005-priority family / משפחה מוקדמת | Same SMA line / אותו קו |
| patent-JP2011054079A-info-transmission-method.pdf | Info-transmission via SMA vibration / שיטת העברת מידע | SCA Corp + Kagawa Univ / שיתוף תעשייה |
| patent-JP5292655B2-living-body-info-transmission-granted.pdf | Granted JP, main family / הפטנט הראשי | Granted claims / תביעות שאושרו |
| patent-WO2011052484A1-living-body-info-transmission-PCT.pdf | PCT, 35 pp full drawing set (scanned) / בקשת PCT | Complete drawings / השרטוטים המלאים |
| patent-US20120212442A1-living-body-info-transmission-US-english.pdf | US publication, ENGLISH text + FIGs / הגרסה האמריקאית | The readable English version / הגרסה הקריאה |
| patent-JP5118777B1-peripheral-nerve-exam-granted.pdf | Peripheral-nerve exam device / בדיקת עצבים | SMA actuator application / יישום רפואי |

---

## MISSES — what we honestly do NOT have / מה שבאמת אין לנו
Full detail with URLs and DOIs in `misses.txt` (33 numbered items). Summary / סיכום:

- **~26 paywalled papers** — the entire IEEE/Springer/De Gruyter/Brill conference line 1998–2020 (ICRA, IROS, ICMA, HSI, KES, Advanced Robotics). No bypass attempted. **The single most painful one: ICMA 2017 "Singing performance with newly redesigned artificial vocal cords" — the only paper likely to hold the 2017 vocal-cord dimensions** (misses #17, #28). / כ-26 מאמרים בתשלום; הכואב ביותר: מאמר 2017 עם מידות המיתרים המחודשים.
- **ICMC 1996** (the very first paper) — open-access page but bot-blocked (HTTP 403 to every client) (miss #22). / המאמר הראשון — חסום לבוטים.
- **Demo videos** — not downloaded (out of scope by instruction); most archived .mpg URLs recorded, many never archived at all and the original server is offline (miss #3). / סרטוני ההדגמה — מחוץ לתחום; רבים אבדו לתמיד.
- **Lost forever:** P2.jpg robot photo and several 2010-era Kagawa sub-pages were never archived by the Wayback Machine (misses #1–2). / אבודים לנצח: תמונות ודפים שמעולם לא נשמרו בארכיון.
- **Press:** Wired July 2004 and De Ingenieur June 2002 — citations only (misses #5–6). New Scientist 2002 survives only as our scan. / עיתונות — ציטוטים בלבד.
- **PhD theses** (Kitani ~2012, Vo Nhu Thanh 2017) — in no open repository (miss #27). / עבודות דוקטורט — לא נמצאו.
- **Numbers no open source states** (see specs-found.md UNKNOWN): tube **wall thickness**, silicone **durometer/grade**, exact **motor models/torques**, two-layer **cord layer thicknesses**. / מספרים שאף מקור פתוח לא מוסר: עובי דופן הצינור, קשיות הסיליקון, דגמי המנועים, עוביי שכבות המיתרים.
- **Patents:** none on the voice mechanism (that is a finding, not a miss); a few name-match false positives inspected and discarded (misses #29–33). / פטנטים: אין על המנגנון — ממצא, לא החמצה.

*Compiled 2026-08-25 by claude-cli (Fable) from four agents' harvests. Every claim above points at a file in this directory or a numbered line in misses.txt.*
