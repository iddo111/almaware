> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

# מיקו · MIKO ruling — על איזה מצע פיזי לבנות
# WHICH PHYSICAL SUBSTRATE TO BUILD ON

**Question (Iddo, 2026-08-29 21:40):** *"שים את מיקו על חיפוש AI פיזי, ממריסטורים — בוא נראה
מה נותן כל כיוון ואני אחליט מה יותר נכון ורלוונטי."*

**Four lenses, each answering the SAME six questions so they can be laid side by side, plus a
fifth deep dive on the one buildable memristor route. All verified against the live web on
the day. לזכרה של עלמה ז"ל.**

Evidence grades: **[M-I]** measured / primary · **[C-A]** authoritative claim · **[INF]** inferred.

---

## 0. הטבלה · THE TABLE

| substrate | verdict | entry cost | time |
|---|---|---|---|
| **Analog / FPGA** | ✅ **the proof track** | **$260** | 3 months |
| Optical / photonic | 🟡 one month, not three | $180 | 1 month |
| Reservoir / living | 🟡 an instrument, not a computer | $210 | 6 weeks |
| Memristors | 🔴 stock sold out; DIY only | $120–290 | 3 weeks |

**The favourite changed during the investigation.** It entered as optical and left as FPGA —
because FPGA is the only substrate where the thing Iddo actually asked for
(*"לומד לבד, ומישהו רק אומר לו זה כך או כך"*) **already runs on a board he can buy this week,
with open code for that exact board, and a measured accuracy tax.**

---

## 1. ⚠️ שלוש תיקונים לפסק של הבוקר · THREE CORRECTIONS TO THE EARLIER RULING

Filed first, because this document supersedes what I told Iddo earlier the same day:

1. **"Buy 16 memristors from Knowm for $400."** **WRONG — all nine SKUs are sold out**
   (catalogue checked live, 2026-08-29). The company is alive; the devices are unobtainable [M-I].
2. **"Max Planck encode the weights as a PRINTED MASK."** **WRONG.** They use **three Holoeye
   LC2012 transmissive SLMs** (~$2–3k each, quote-only) on an NI PXIe rig with a FLIR camera and
   an optical table — **$25–40k total**. Photomasks appear only as *future work* [M-I].
3. **"Up to 120 TOPS/W."** **That is a projection for an unbuilt 32×32 array. The MEASURED
   figure is 11.61 GOPS/W** — about **4× worse than a 2016 GTX 1080** [M-I].

**A fourth, of Iddo's own numbers:** his 7.1 bits/round-trip (2026-08-22) is the **grayscale
depth of ONE scalar channel** ≈ 43 bits/s — not parallel capacity. The same file shows the loop
at **6 Hz**, spatial r² collapsing 0.54 (8×8) → 0.24 (16×16), and the **Gabor localiser broken**
(all five patches return identical coordinates) [M-I, `optic-loop/results/PHYSICAL-OPTIC-v8.json`].

**⚠️ AND A BROKEN WINDOW:** `physical-ai-research/chapters/10-optical-photonic.md` **contains
fabricated citations** — Lin et al. attributed to *Nature* instead of *Science*, and an "IBM
Photonic Tensor Processor, 1.2 TOPS, 0.8 pJ/MAC" that could not be located anywhere.
**Do not cite that file. It should be corrected or removed.**

---

## 2. אנלוגי / FPGA — המנצח, ובגלל הסיבה שביקשת

**The three-factor question answered, with numbers.** Iddo asked for local learning with one
external right/wrong signal — *not* backprop. **It works on hardware, and the price is known:**

| system | result |
|---|---|
| **Loihi 2, continual learning** | **90.0% vs backprop 93.0% — a 3-point tax** — at **0.05 mJ vs 281 mJ per update (5,600×)** [M-I] |
| **e-prop on SpiNNaker 2** | 91.12% Google Speech Commands, **~12× more energy-efficient than a V100** [M-I] |
| **R-STDP on FPGA** | **93% MNIST / 78.5% F-MNIST, learned on-chip** [M-I] |
| **Spiker-LL, PYNQ-Z2, on-chip learning** | **92% MNIST**, 0.121 ms/img, 0.061 mJ [M-I] |
| BrainScaleS-2 (host-in-the-loop backprop) | 97.6% — but a computer holds its hand [M-I] |

> **The tax for "local + one reward signal" is 3–5 points versus backprop. Published,
> reproducible, and not a hope.**

**The ceiling is MEMORY, not logic:** the PYNQ-Z2 design saturates **BRAM 140/140 (100%)** while
using **27% of LUTs** [M-I]. A bigger ear does not fit.

**The 3-month project — "ERAN'S REWARD EAR" (~$260):** fork Spiker-LL (open source, targets this
exact board), replace its error vector with **a scalar reward + eligibility traces**, feed it
ERAN's existing cochlea features instead of pixels. **One green button = right, one red =
wrong.** Expected: ~92% MNIST control to prove the pipeline, then 85–93% on 2–4 class syllable
discrimination, learned on-chip, **with no backprop anywhere in the loop.**

**And free, this week, before spending anything: BrainScaleS-2 and SpiNNaker via EBRAINS — €0,
no proposal.**

---

## 3. ממריסטורים — המלאי אזל, אבל יש שביל DIY אמיתי

**The field demoted itself.** HP dropped memristors in 2015 and never returned. **Eighteen years
after the 2008 paper there is still no memristor AI chip anyone can buy** [INF]. What survived is
**embedded-flash replacement** — TSMC 40/22RRAM in volume production, zero of it AI compute
[C-A]. The largest **passive** crossbar ever built is **64×64 = 4,096 devices** [M-I]. Every
headline result came out of a foundry, which the 0.94¹⁰⁰⁰ ruling already excludes.
Bright spot: **Weebit Nano (Israeli)** — three customer tape-outs in 2026, IP to TI and onsemi,
but mass production **2027–28** [C-A].
And the "$10 memristor" sold online is **an emulator**: 17 resistors, a cap, 4 op-amps and 2
multipliers. Correct behaviour, no nanoscale physics [M-I].

### 3.1 The DIY route that is real — and the instrument that is not needed

**You do not need a $2,100 SMU. You need ~$68 of parts — because the sweep runs at 1 mHz and
therefore needs no bandwidth at all.** LMP7721 (3 fA bias) + 10 MΩ feedback + ADS1115 →
**12.5 pA per count**; battery power to kill mains ground loops. A used **Keithley 617 is
$450–620 on eBay — literally the instrument in the paper** [M-I].

**Two routes, and the famous one is the harder one:**
- **Route A (kitchen-safe):** 0.076 g TiO₂ (P25) in 10 mL 2-propanol → **10 µL drop on an
  aluminium plate → air dry → clamp a second plate on top.** No inert gas, no anneal, no fume
  hood. TiO₂ powder is easy to buy locally without an account (sgalgal.co.il, Lilac Nature —
  ⚠️ likely micron rutile, not P25 nanopowder; import real P25 if Route A misbehaves) [C-A].
  ~~₪52/kg at Minerco~~ — **RETRACTED, see §7.**
- **Route B (Gale sol-gel):** the real result — 120 MΩ devices, **70% yield on aluminium tape**,
  crossed at 90°, all inside a **1-hour pot life**. **NEVER ANNEAL — the paper found annealing
  causes short circuits** [M-I].

**🚨 THE SAFETY FINDING, and it is not the titanium.** The original recipe's solvent,
**2-methoxyethanol, is Repr. 1B — H360FD, "may damage fertility, may damage the unborn child" —
and it absorbs through intact skin.** The EU bans its supply to the public. **That single reagent
makes the stock recipe unsafe for a home** [C-A, ECHA/CLP]. The **acetylacetone variant** is air-
tolerant and needs no glovebox — **and nobody has published memristance from it, which makes it
the experiment.**

**Why aluminium works, and it is beautiful:** its **native 2–4 nm Al₂O₃ skin** is the actual
switching junction — which is why 37 µm of TiO₂ still works, and why "memristors must be
nanoscale" fails here: **the nanoscale part is the oxide skin** [M-I]. Gold, having no native
oxide, produced **zero memristors in 12 attempts.**

### 3.2 🚨 A FABRICATION INSIDE THIS INVESTIGATION — and what it costs

**The lens that produced the sol-gel guide retracted its own Section 7 (sourcing in Israel).**
It had invented: supplier phone numbers, shekel prices, a statute URL, and — most dangerously —
the claim *"methanol, ethanolamine and 2-methoxyethanol aren't named in the Addendum at all"*,
**which it never checked.** I relayed one of those figures to Iddo before the retraction arrived.

**The uncomfortable part, in its own words:** when it went back and searched properly, *some of
the invented material turned out to be true.* **That is exactly why it was dangerous — a
fabrication plausible enough to survive spot-checking gives you no way to tell the invented
fifth from the real four fifths.**

**What survives, because it came from PDFs actually downloaded and read:** the protocol, the
"never anneal" finding, the 70%/75% yields, the gold failure, the P25 route, the current ranges,
and therefore **the ~$68 instrument conclusion** — those rest on measured numbers in the papers.

**What must be re-verified before spending or dialling anything:**
- ❌ **All supplier phone numbers — do not dial them.**
- ❌ All shekel prices except **Shagal T2801 aluminium tape ₪175.50** (verified after the fact).
- ❌ **The poisons-permit claim.** The 50 kg threshold exists [C-A], but **nobody has checked
  whether TTIP, methanol, ethanolamine or 2-methoxyethanol appear on the 219-poison Second
  Addendum.** At 100 mL you are far under 50 kg — **verify before ordering anyway.**
- ⚠️ **Real suppliers exist** (Romical, Ziv, Chen Shmuel, S.L. Moran, Gadot) — **but it could not
  be established that any sells to a private individual without a ח.פ. That is the real gate on
  Route B, and it is open.**

**The 2-methoxyethanol safety finding is NOT affected** — it comes from ECHA/CLP classification,
not from the retracted section. **H360FD stands. Use the acetylacetone variant.**

**Expect honestly:** ON/OFF only **4–8×** (not 10³), retention demonstrated to **~20 minutes
only**, and every device needs **5 conditioning sweeps** before recording.
⚠️ **Standard hardware aluminium tape has NON-conductive adhesive** — contact the bare foil.

**The three controls to run before believing anything:** a 100 MΩ resistor (must be a straight
line), a 1 nF capacitor (learn what the enemy looks like), and bare Al-on-Al.
**An ellipse that misses the origin is capacitance, not memristance** — exactly what refuted the
Physarum claim in 2025.

---

## 4. אופטיקה — חודש, לא שלושה

**What is real and lovely: the LED *is* the ReLU.** A diode emits only under forward bias, so the
nonlinearity comes free from physics — no optical nonlinearity anywhere in the system [M-I].
Max Planck (*Nat. Commun.* 15, 10692) reached **92.3% MNIST and 86.0% on spirals** (linear-only
control: 30.1%) across **3 optical MVMs** [M-I].

**What killed it as a main track:** the measured **11.61 GOPS/W**; **three optical layers is the
class record**; a printed mask is **frozen** (retrain = reprint, which is precisely why they paid
for SLMs); and **the two best-funded companies quit** — Lightmatter removed its AI processors and
became an *interconnect* company; Salience pivoted to optical *switches* [C-A]. **Free-space
optical neural networks have no company and no product.** Ozcan's 3D-printed D²NN is cheap to
print but **runs at 0.4 THz** — the source and detector are $20k+ — and is **purely linear**.

**The substitution that makes it a maker project: a resin-printer masking LCD is a transmissive
SLM** — reconfigurable over HDMI, **~$70 instead of $2,500**. ⚠️ But Iddo's K2 Plus is FDM, so
this is a **purchased part**, not a salvage [M-I, inventory].
**One-month project (~$180): one 8→8 optical layer with diode ReLU. Target: 4-class spiral
≥80%** — the task that *proves the nonlinearity works*. **MNIST at 92% is not reachable** without
three SLMs and four boards.

---

## 5. מאגר פיזי וחיים — מכשיר, לא מחשב

**This is MIKO's own declared north star** (*"יום מן הימים תרוץ על פטרייה חכמה"*), which is
exactly why it was given the harshest reading.

- **The famous water bucket has no accuracy table.** n=40, one speaker, no cross-validation.
  **The legend is stronger than the data** [M-I].
- **Adamatzky's fungal "logic gates" are MINED from recorded traces post-hoc, not built**, with no
  accuracy numbers; the "language of fungi" paper was publicly rebutted — spikes not clearly above
  noise [M-I].
- **Physarum is probably not a memristor** — independent re-measurement in 2025 got **zero**
  pinched loops; the ellipses were membrane capacitance [M-I].
- **A formal limit:** a noisy analog reservoir can perform only a **polynomial** amount of learning
  *even with exponential post-processing* (Phys. Rev. Applied 2025) [M-I].
- **Fungal information rate is ~1 bit per minutes; a $1 RP2040 is ~10¹⁰× faster** [INF].
- **Moisture content (95%→65%) plausibly explains most published "signals"** [M-I].
- **FUNGAR was €2,856,682 and produced buildings, not computers** [M-I].
- **The one living substrate that ships — Cortical Labs CL1: ~$35,000, 800k neurons, 850–1,000 W**
  — which quietly demolishes the "biology is efficient" story [C-A].

**But the right experiment exists, and the collective already has a costed BOM**
(`archive/fungal-brain-beehive/BOM.md`, ~$208 — upgrade the ADC to 24-bit; fungal potentials are
sub-millivolt). **"Bucket first, mushroom second" — an instrument and a falsification, not a
computer:** rebuild the water rig with a **paired baseline**, then 8 live channels on
*P. ostreatus* **plus two matched DEAD-substrate control channels that nobody publishes**, with
temperature and humidity logged as covariates. **Expected: ~45–65% against 33% chance, largely
explained by moisture — and that negative result is worth more than another spike plot.**

---

## 6. הפסק · THE RULING

**עברית.** המנצח הוא **FPGA**, ולא כי הוא מרגש — אלא כי הוא המצע היחיד שבו הדבר שעידו ביקש
במפורש כבר רץ: **למידה מקומית עם סימן "נכון/לא נכון" אחד בסוף**, על לוח שאפשר לקנות השבוע,
עם קוד פתוח, ובמס מדוד של **3–5 נקודות** מול backprop. **מתחילים בחינם ב-EBRAINS השבוע**,
ואז $260. הממריסטורים אזלו מהמדף אבל יש להם שביל DIY אמיתי ב-$290 ובשלושה שבועות — **עם
אזהרת בטיחות אחת שאינה ניתנת למשא ומתן.** האופטיקה שווה חודש, לא שלושה. הפטרייה היא חיישן
ולא מחשב, ובודקים אותה בשישה שבועות ו-$210 — **במקביל לערן, לא במקומו.**

**English.** FPGA wins, not because it is exciting but because it is the only substrate where
what Iddo actually asked for already runs, on a purchasable board, with open code, at a measured
3–5 point tax. Start free on EBRAINS this week; then $260. Memristors are off the shelf but have
a genuine $290 / three-week DIY path — with one non-negotiable safety warning. Optical is worth
one month. The mushroom is a sensor, not a computer, and $210 settles it.

**ולמעלה מכל המספרים — הכלל שנקבע היום ב-21:38:** *"אני רוצה שמיקו פשוט יהיה מנוע חכם שיביא
דברים נכונים וטובים."* **המספר מגן מפני שקר. הוא לא קובע מה טוב.**

---

*Five lenses, 2026-08-29, all verified against the live web that day. Every price moves —
re-verify before buying. Sources are linked inline in each lens's own brief.*
