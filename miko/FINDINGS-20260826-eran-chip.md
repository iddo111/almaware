> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

# מיקו · MIKO ruling — שבב ערן / THE ERAN CHIP

**Question (Iddo, 2026-08-26 12:06):** a full ruling on an ERAN chip — taking into account that
the target is **a BIG ERAN on 4 DGX minimum** (the holobrain), inspired by Google making their own
computers. **Two lenses searched (2026 fab-access · neuromorphic-silicon landscape), both verified
against the live web. This is the ruling seat. לזכרה של עלמה ז"ל.**

Evidence grades: **[M-I]** MEASURED-INDEPENDENT · **[C-A]** CLAIMED-BY-AUTHOR · **[INF]** INFERRED.

---

## 1. מסקנה · THE RULING

**עברית — לשבב ערן יש שתי קומות, ואסור לבלבל ביניהן:**

**קומת המוח הגדול (4 DGX ומעלה):** קונים ברזל, כמו גוגל. גם גוגל לא מייצרת את ה-TPU —
היא מתכננת ו-TSMC מייצרת; גם לאנבידיה אין פאב. שבב שמחליף DGX = מיזם בסדר גודל של Habana:
**150+ מהנדסים, מאות מיליוני דולר, שנים** — לא מסלול לצוות קטן, לא השנה ולא בחמש הקרובות.
הריבונות בקומה הזאת היא **בתכנון של מה שרץ על הברזל** (ערן עצמו), לא בבעלות על המכונות.

**קומת האיברים והערנים-הקטנים — וכאן יש בשורה אמיתית:** ערן האורגניזם רץ על **ליבה אחת,
0.155ms לפעימה** — הוא זעיר, וכל הקאנון הנוירומורפי העולמי נבנה בנודים ותיקים (180-350nm).
**סיליקון משלו הוא בר-השגה לצוות של 1-3 אנשים, החל מ-300 דולר, השנה.** הסולם המדורג בסעיף 3.

**English —** The ERAN chip has two floors. **Big-brain floor (4+ DGX):** buy iron — even Google
and NVIDIA own no fabs; replacing a DGX is a Habana-scale venture (150+ engineers, $100M+), not a
small-team path; sovereignty there lives in the design of what runs. **Organs-and-small-ERANs
floor:** the organism is one-core tiny, the entire neuromorphic canon was built at legacy nodes —
**his own silicon is reachable by 1-3 people starting at ~$300, this year.**

## 2. The facts that decide it

| fact | number | grade |
|---|---|---|
| ERAN organism compute | 1 CPU core, 0.155 ms/beat, ≤4096 protos × 192-996 dims ≈ ≤4 GMAC/s | [M-I — our own measurements] |
| Neuromorphic canon node | DYNAP-SE/Neurogrid 180nm, early Indiveri 350nm — old nodes suffice | [M-I] |
| CARFAC ear in logic | 70-section real-time = 18% of a Cyclone V FPGA (van Schaik 2018) | [M-I] |
| efabless | **DEAD (Mar 2025)**; successor **ChipFoundry** acquired the assets (Sep 2025) | [M-I] |
| Tiny Tapeout | ALIVE; SKY130 shuttle **closes 2026-09-07**, IHP closes 09-21; ~€70/tile, chips ~1 yr | [C-A + M-I user silicon reports] |
| wafer.space GF180 | **$7-8K → 1,000 bare dies of 19.67 mm²**; Run 3 GDS Dec 2026 → dies Q2 2027 | [C-A — no end-user silicon report yet] |
| ChipFoundry chipIgnite | $14,950 → 10 mm² SKY130, 100 packaged chips, ~5-month shuttle | [C-A — no post-efabless delivery report yet] |
| Open digital flow | LibreLane (ex-OpenLane2): production-proven on hundreds of TT chips | [M-I] |
| Open SNN silicon to reuse | ODIN (on-chip SDSP plasticity!) + ReckOn (Frenkel, HDL open, silicon-proven); OpenSpike taped out on SKY130 with 100% open tools | [M-I / C-A] |
| Buyable neuromorphic | Akida M.2 **$249** (learning = last-layer binary only); SynSense **Xylo-Audio** = µW ear+SNN chip (price gated); Loihi 2 = institutions only | [C-A] |
| Israel | Europractice-eligible (academic ~€1,100/yr + €4-6K/run X-FAB 180nm); BIU EnICS tapes out routinely; Tower Migdal-HaEmek runs sales-gated MPW | [M-I / C-A] |

## 3. The ladder (organs floor) — ranked

1. **NOW, ~$100-250, 1 person, weeks: FPGA "soft silicon" (ECP5-85F, open toolchain).**
   CARFAC-lite ear + the prototype-matching brain in ERAN's OWN logic architecture. Precedented on
   every axis; the RTL written here IS the future chip's RTL. *The honest first step.*
2. **NOW, $249: BrainChip Akida M.2** — the "many-ERANs on commercial neuromorphic" data point.
   Honesty: its on-chip learning is last-layer-binary — ERAN's Hebbian spawn/prune does NOT map
   onto it without mutilation. A teacher, not a body.
3. **⏰ By 2026-09-07 (SKY130) or 09-21 (IHP), ~€140-300: Tiny Tapeout tile —
   ERAN's first PERMANENT silicon.** One prototype-distance neuron or a 2-4-channel cochlear
   section. A few thousand gates, symbolic + real, chips in hand ~mid-2027. A 2-person team already
   has a LIF+STDP tile on this exact shuttle line.
4. **Later (after the FPGA freezes the architecture), $7-15K, 2-3 people, ~12-18 months:
   the whole-organism chip** — wafer.space GF180 (most silicon per dollar, bare-die burden) or
   chipIgnite (packaged, dearer), skeleton from ODIN/OpenSpike + OpenRAM for prototype memory.
5. **University lane:** BIU EnICS / Europractice unlocks X-FAB 180nm at €4-6K/run — worth one
   phone call if an academic partnership ever forms.

## 4. במחלוקת · DISSENT — kept visible

1. **FPGA-first vs chip-first.** The purist seat: an FPGA is configurable rented logic, not "his
   own fixed silicon" — only a tape-out is a body. The engineer seat: a chip you can't patch, from
   an architecture that changed twice THIS WEEK (ear v3, mouth v2), is money burned. **Ruling: both
   — FPGA as the living RTL truth now, one Tiny Tapeout tile in parallel as the first permanent
   cell.** Dissent stands.
2. **The big-brain chip dream.** One seat says: Habana was Israeli, 150 people, $2B exit — it can
   be done here. The other: they burned ~$250M getting there, and ERAN's holobrain isn't even
   architecturally frozen. **Ruling: dream recorded, not funded — revisit when ERAN's big
   architecture is stable and proven on rented iron.** Dissent stands.
3. **Xylo temptation.** A µW spiking AUDIO chip is the most ERAN-shaped silicon on earth — but
   inference-only and price-gated. **Ruling: inquire the price; buy only if sane; it teaches, it
   does not embody.**

## 5. What MIKO could not verify (honesty)

TT exact 2026 sticker per shuttle · any post-efabless chipIgnite delivery report · wafer.space
Run-1 "dies work" reports · IHP free-tier eligibility for an Israeli non-university team ·
Xylo/Innatera pricing · Tower MPW pricing · Minimal-Fab (Japan) foreign access.

## 6. הניסוי הזול / The one cheap experiment

**Before 2026-09-07** (12 days): decide on one Tiny Tapeout SKY130 tile (~€140-300) — a single
ERAN prototype-distance neuron in Verilog through LibreLane. One person, one week of evenings,
and ERAN's first permanent cell exists in physical silicon by mid-2027. If the deadline slips,
the IHP shuttle (09-21) or the next SKY shuttle catches it — nothing is lost but months.

**Ruling: רלוונטי.** Two floors, two verdicts: big brain = buy iron and own the design;
organs = climb the ladder, starting this month for the price of a pair of boots (und Bomberjacken).
