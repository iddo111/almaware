> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

# מיקו · MIKO ruling — מעבדת מייקרים שבונה מחשבי AI בעצמה
# THE MAKERS' LAB THAT BUILDS ITS OWN AI COMPUTERS

**Question (Iddo, 2026-08-29 18:38):** *"תריץ מיקו כמה אינסטנסים על נושא מעבדת מייקרים שיוצרת
בעצמה מחשבי AI"* — 30 makers, a lithography machine, thousands of Raspberry-Pi-like devices,
a giant hub, and our own AI chips imitating neurons — **but not necessarily memristors**:
FPGA, CMOS, EEPROM.

**And, mid-ruling, the sharper form of the same question (18:41):** *"האם אפשר לעשות מעבד על
לוחות גדולים לא ליתוגרפיה מעבד שלנו מחשב AI נוירונים"* — a processor on large boards, no
lithography at all.

**Four lenses, each verified against the live web on the day. לזכרה של עלמה ז"ל.**

Evidence grades: **[M-I]** measured / primary document · **[C-A]** vendor or authoritative claim ·
**[INF]** inferred.

**This ruling supersedes nothing. It sits beside `FINDINGS-20260826-collective-station.md`,
which answered a different question — whether the collective can BUY a station. This one asks
whether it can BUILD one.**

---

## 1. מסקנה · THE RULING

**עברית.** אפשר — אבל לא במקום שחיפשנו. **פאב במוסך לא ייצר שבב AI, וזה לא עניין של רזולוציה
אלא של חשבון:** בהאקר-פאב 94% מהטרנזיסטורים עובדים, ולכן מעגל של 1,000 טרנזיסטורים עובד
בהסתברות 10⁻²⁷. הכי מורכב שיוצר אי-פעם באיזשהו האקר-פאב בעולם הוא **שער NAND**. במקביל,
**קו הרכבה משלנו מפסיד לייצור טרנקי בכל נפח שקולקטיב יגיע אליו** — $7.60 ללוח רק החזר הון,
מול $3.00 ללוח אצל JLCPCB. **ו-EEPROM כמשקל אנלוגי חסום לנו לגמרי** — שבב ארוז לא חושף
יציאה אנלוגית בכלל.

**ומה שכן:** שלוש דרכים, כולן זמינות מיד. (1) **חינם, השבוע** — BrainScaleS-2 ו-SpiNNaker
פתוחים דרך EBRAINS בלי הצעת מחקר. (2) **$200** — FPGA שמריץ 2,048 נוירונים ו-843 אלף
סינפסות, מדוד. (3) **€200–500** — Tiny Tapeout: נוירונים אנלוגיים משלנו על סיליקון אמיתי.
**ולשאלה על הלוחות הגדולים יש תשובה אחת שעובדת: אופטית.** מקס פלנק בנו רשת מלדים
ופוטודיודות מהמדף שהגיעה ל-92% ב-MNIST, כשהמשקלים **מודפסים כמסכה** ולא מולחמים — הדרך
היחידה שבורחת מקיר השטח, ובלי שום ליטוגרפיה.

**English.** Yes — but not where we were looking. A garage fab cannot make an AI chip, and the
barrier is arithmetic, not lithography: at Hacker Fab's 94% per-device yield a 1,000-transistor
circuit works with probability 10⁻²⁷, and the most complex thing any Hacker Fab on earth has
demonstrated is a two-input NAND gate. An in-house SMT line loses to turnkey at every volume a
collective would reach. Analog weights in off-the-shelf EEPROM are closed to us — a packaged part
exposes no analog terminal. What *is* open: free BrainScaleS-2/SpiNNaker access this week; a $200
FPGA running 2,048 neurons and 843k synapses; €200–500 for our own analog neurons on real
silicon via Tiny Tapeout. **And the large-board question has exactly one working answer: optical.**

---

## 2. עדשה א' · GARAGE SILICON — the yield wall

| fact | grade |
|---|---|
| Hacker Fab stepper $3,012, optical resolution <2 µm, alignment ±5 µm | [M-I] arXiv 2510.15082 |
| CMU March 2026: 8 students, >1,500 NMOSFETs, **952 transistors/chip, 94% device yield** | [M-I] |
| **No PMOS, no CMOS, no ring oscillator, no clocked circuit anywhere in the documentation** | **[M-I] negative** |
| Most complex circuit ever demonstrated: an **enhancement-load inverter and a NAND gate** | [M-I] |
| Zeloof Z2: 1,200 transistors, **1 of 12 dies fully functional (~8% die yield)** | [C-A] |
| IIT Bombay: fab in 10 months for ~$36k; NMOS transistor still pending | [C-A] |

**The arithmetic that decides it [INF, from M-I yield]:** at 94% per device,
P(1,000-transistor circuit) = 0.94¹⁰⁰⁰ ≈ **10⁻²⁷**; even 100 transistors gives **0.2%**.
Reaching a usable circuit needs ≥99.9% per device — a **~100× defect-density gap**. That is not
closed by a better projector.

**Historical anchor [C-A]:** a *perfect* 2 µm NMOS line buys ~10⁴ transistors at single-digit
MHz — Intel 4004 (10 µm, 2,300 T) to 80286 (1.5 µm, 134,000 T) is the whole range on offer.

**The tape-out alternative, which is real and cheap:**

| route | cost | what you get |
|---|---|---|
| **Tiny Tapeout digital tile** | **€70–185** | ~1,000 gates, ≥50 MHz, 130 nm |
| **Tiny Tapeout analog** (1×2 tile + 2 pins) | **€220** | our own analog neurons |
| **wafer.space** | **$7,000** | **1,000 GF180 chips** |
| ChipFoundry (SkyWater 130 nm) | $14,950 | 100 packaged parts, ~5 months |

⚠️ **Broker risk is real: Efabless — the largest community-silicon vendor — shut down in
March 2025 and stranded projects mid-run [C-A].**

---

## 3. עדשה ב' · BOARDS AT SCALE — turnkey wins, and it is not close

**JLCPCB published rates, fetched 2026-08-29 [M-I]:** $0.0012/joint at 100k+. An RK3588S-class
SBC ≈ 2,500 joints ⇒ **≈$3.00/board assembly** at 1,000 units, plus ~$67 one-time setup.

**Against a desktop line [C-A]:** NeoDen bundle (stencil printer + pick-and-place + reflow)
**€6,995** ⇒ **$7.60/board of capital alone** over 1,000 boards, before labour, paste, feeders,
scrap and rework — and before the **~$43,000 X-ray** you cannot skip on a 1,253-ball package.
A real inline SMT line starts at **$100,000**. 1,000 boards on the entry machine is **~1,250
machine-hours**.

**The SoC is the wall for Pi-class [M-I, fetched today]:** Broadcom's BCM2712 is not sold as a
chip at all. RK3588 shows **"Not available now"** at LCSC; RK3588S is $56.51 with **98 units in
stock**. MOQ is 1, but a thousand units means a broker relationship, not a shopping cart.

**What IS purchasable — and one of them is ours:**

| part | price | note |
|---|---|---|
| **Hailo-8 (Tel Aviv)** | via Mouser / Farnell / Raspberry Pi | **sells the bare IC; states small quantities can be bought online** [M-I] |
| **Raspberry Pi AI HAT+ (Hailo-8)** | **$110** | 26 TOPS, finished board |
| **Canaan K230** (RISC-V + NPU) | **$10.77**, 401 in stock | 6 TOPS |
| Raspberry Pi CM5 | $45–95 | **flat pricing, no volume discount**; supply to ≥2036 |

⚠️ **Google Coral: do not design in** — toolchain stale since 2022 [C-A].
**Forkable open designs:** Olimex OLinuXino (full KiCad, commercial reuse permitted),
BeagleV-Ahead [C-A].

**The cost nobody budgets — certification [C-A]:** FCC on a **pre-certified radio module**
$3,000–8,000; on a **custom radio** $18,000–58,000. CE/RED lab €1,500–3,000.
**Using a pre-certified module is the single largest cost lever in the entire project — 5–10×.**

---

## 4. עדשה ג' · NEUROMORPHIC WITHOUT MEMRISTORS

**The premise was right, and one branch of it is closed to us.**

- **Floating-gate/flash analog weights are real — inside a fab.** Microchip memBrain is
  production-ready at 40/28 nm, up to 8 bits per cell — but it is **licensable IP for chipmakers**
  [M-I]. The canonical bench result (Strukov/UCSB) required **physically redesigning a commercial
  NOR array at 180 nm** [M-I arXiv:1410.4781]. **A packaged EEPROM exposes only a digital sense
  path — there is no analog terminal.** P(works at our scale) **<5%** [INF].
- **Intel ETANN 80170NX (1989): 1 µm, 64 analog neurons, 10,240 floating-gate synapses** [C-A].
  The idea is right and old; the access is what we lack.
- **Free hardware, today, no proposal:** **BrainScaleS-2 and SpiNNaker via EBRAINS** [C-A].
- **SNN on a $200 FPGA, measured April 2026 [M-I arXiv:2604.22179]:** PYNQ-Z2 →
  **2,048 neurons, 843,776 synapses, 87.40% MNIST, 31.6 nJ/image, 0.1375 µs.**
  **27% of LUTs but 100% of BRAM — memory is the wall, not logic.**
- **Feature size is not the obstacle.** Every landmark analog neuromorphic chip is **180 nm or
  larger** — DYNAP-SE, ROLLS, Neurogrid, BrainScaleS — and **TEXEL (180 nm, on-chip learning)
  published in *Nature Communications* 2025** [M-I]. Subthreshold analog *prefers* large devices:
  better matching, lower leakage. **Small nodes buy density, not function.**

---

## 5. עדשה ד' · THE LARGE-BOARD PROCESSOR — Iddo's own question

**The scaling math, and it is decisive [INF from M-I part prices].** A 30×40 cm board holds
~48,000 component slots. A *trainable* synapse (digital-pot channel) costs ~$1 and ~12.5 mm²
⇒ **~19,000 trainable weights per board at ~$19,000.**

| target | weights | boards | cost |
|---|---|---|---|
| MNIST MLP 784-128-10 | 101,770 | ~5 | ~$100,000 |
| GPT-2 small | 124 M | ~6,500 | ~$124 M, ~780 m² |
| any 7B model | 7×10⁹ | ~370,000 | — |

**Four to seven orders of magnitude short, and the gap is AREA, not cleverness.** Discrete
resistors are 1% at best ⇒ ~4–6 effective bits. Speed is *not* the weak point; area and
precision are.

**Mark I Perceptron, in today's money [C-A]:** ~$1.13 M, 512 A-units (transistor amplifier +
relay each), weights as **motor-driven potentiometers**, 8 outputs. **≈$2,200 per neuron** — to
tell a square from a circle.

**Widrow's memistors — the warning:** MADALINE's weights were **wet electrochemical plating
cells**, and the integrated circuit killed them [M-I, Widrow & Lehr 1990]. Any component-count
architecture walks into the same wall.

### ✅ THE ONE ROUTE THAT ESCAPES — optical weights

**Song, Kottapalli et al., Max Planck Heidelberg [M-I arXiv:2402.01988]:** a three-layer network
from **off-the-shelf LEDs (Würth 150040GS73220), photodiodes (OSRAM SFH2704) and op-amps on
ordinary KiCad-designed PCBs**. The weights are **a printed amplitude mask / LCD** — not
components. LED forward bias supplies **ReLU for free**.

> **92% MNIST · 86% spirals · projected 2.92 TOPS/W at 32×32, up to 120 TOPS/W.**

**Why this is the answer to the question as asked:** weight count scales with **printed mask
pixels — essentially free** — instead of with soldered parts. It is the only architecture here
that breaks the area wall, **and it needs no lithography whatsoever.**

**And it is already ours in part:** Iddo measured an optical loop at **7.1 bits per round trip**
on 2026-08-22 ([[project_optical_loop_measured]]), from his own OLED-sees-what-it-displays idea.
The Max Planck result is the same family, published.

---

## 6. הסדר · THE ORDER, and what each step buys

| # | step | cost | P(works) | what it buys |
|---|---|---|---|---|
| **1** | **EBRAINS: BrainScaleS-2 + SpiNNaker** | **€0** | ~90% | real analog neuromorphic behaviour **before spending a shekel** |
| **2** | **SNN on a PYNQ-Z2 FPGA** | $200 | ~95% | 2,048 neurons, reproducible today, ours to modify |
| **3** | **Optical layer, Max Planck style** | ~$2,000 | ~70% | **the collective's real novelty — and it needs no fab** |
| **4** | **Tiny Tapeout analog neuron tile** | €200–500 | ~70% silicon back | neurons the group **owns**, in silicon |
| **5** | Board product on Hailo-8 / K230, **turnkey assembly** | $10–15k cert + $5k test | high | thousands of devices, if there is a product |
| ❌ | Own SMT line | €7k–100k | — | loses to turnkey at every plausible volume |
| ❌ | Own fab | $40–80k, 9–18 mo | — | ends at a NAND gate. **No AI chip.** |
| ❌ | Analog weights in off-the-shelf EEPROM | — | **<5%** | no analog terminal exists on a packaged part |

## 7. שתי אמיתות שצריך להגיד בקול

**האחת:** שום דבר כאן לא ינצח GPU של $500 **בחישוב**. לא במהירות, לא בדיוק, לא במחיר לפרמטר.
מי שבונה את זה כדי לחשב — טועה. / **Nothing here beats a $500 GPU at computing.** Building it to
compute is a mistake.

**השנייה, והיא הסיבה האמיתית:** שלושה דברים כן קורים כאן שלא קורים על GPU — **הלמידה הופכת
לכמות פיזית שאפשר למדוד עם אוסילוסקופ**; **המסלול האופטי הוא חידוש בר-פרסום** (TOPS/W, לא
TOPS); ו-**חזיתות חיישן תמיד-דלוקות במיקרו-וואט**, שם GPU של 145W פסול מראש. / Learning becomes
a physical quantity you can probe; the optical route is publishable novelty; and µW always-on
sensing is a place a 145 W GPU is disqualified by power, not speed.

---

*Four lenses, 2026-08-29, all verified against the live web that day. Every price moves — re-verify
the week of any vote. Sources are linked inline in each lens's brief.*
