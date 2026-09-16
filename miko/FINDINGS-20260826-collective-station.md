> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

# מיקו · MIKO ruling — תחנת הבינה של הקולקטיב / THE COLLECTIVE BLACKWELL STATION

**Question (Iddo, 2026-08-26 14:26):** a full founding ruling — can his collective ("קפה קלוד",
up to 150 makers, owners not customers, solar-powered, at floor prices, the seed of an urban
kibbutz with its own AI) build a Blackwell station bigger than his DGX fleet?
**Two lenses verified against the live web (hardware/market · organization/legal/precedents).
This is the ruling seat. לזכרה של עלמה ז"ל.**

Evidence grades: [M-I] measured/primary-document · [C-A] vendor/authoritative claim · [INF] inferred.

---

## 1. מסקנה · THE RULING

**עברית — כן, וזה בנוי משלושה מספרים שנסגרים זה על זה:**
(1) **התחנה:** 4× RTX PRO 6000 Max-Q במגדל Threadripper — **~₪243K לשנה ראשונה כולל הכל** (מכס 0%,
מע"מ 18%, חשמל, קו ייעודי). כרטיס אחד כזה מהיר פי 4-7 מ-DGX Spark ⇒ התחנה ≈ **פי ~20 מכל צי
ה-Sparks** של עידו, עם 384GB ECC ו-16 פרוסות MIG ל-150 חברים. תחנת 8 הכרטיסים **מתה** — אנבידיה
הכפילה את המחיר ב-2026 (מחסור GDDR7).
(2) **הכסף:** מניית-חבר חד-פעמית ₪1,500-3,000 × 150 = ₪225-450K. **התקדים הישראלי קיים ומוכח:
אופק** — אגודה שיתופית שגייסה 15,000+ חברים ב-₪3,000 מניה. דמי תפעול: ₪30-50 לחודש.
(3) **הצורה:** **אגודה שיתופית** (7 מייסדים, חבר=קול, מניות ללא-דיבידנד במסלול אופק — בלי
תשקיף; לאמת עם עו"ד), עמותה-אחות בהמשך למענקים. רישום — רק אחרי שיש 50 חברים משלמים אונליין.

**English —** Yes, on three mutually closing numbers: a 4× RTX PRO 6000 Max-Q tower at ~₪243K
year-1 all-in (≈20× the Spark fleet; the 8-card build died with NVIDIA's 2026 price-doubling);
150 member shares at ₪1,500-3,000 (the Ofek credit-union precedent proved ₪3,000/member works in
Israel at 15,000-member scale); the אגודה שיתופית form with non-dividend shares (no prospectus,
verify with counsel). Register only after 50 paying members exist online.

## 2. The hardware verdict [full tables in the lens report]

| option | year-1 all-in | what it is | verdict |
|---|---|---|---|
| **4× PRO 6000 Max-Q, WRX90 tower** | **≈₪243K** | 384GB @1.79TB/s, ~30K+ tok/s serving, 16 MIG slices, ONE 16A circuit | **THE RULING FAVORITE** |
| 2× PRO 6000 + 2× RTX 5090 (₪15K local) | ≈₪150K | 256GB, best tok/s-per-shekel | the budget-flex runner-up |
| 6× used A100 80GB | ≈₪160K | most VRAM/shekel, no warranty, no FP8 | a labeled gamble |
| 14× DGX Spark | ≈₪251K | 1.8TB "VRAM" behind the 273GB/s wall | Iddo already knows this wall personally |
| 8× PRO 6000 | ≈₪490K | — | dead — 2026 price doubling |

Key measured facts: PRO 6000 street $14-16K (was $8.5K MSRP — re-verify the week of the vote,
prices move monthly) [C-A]; one PRO 6000 = 4-7 Sparks at inference [M-I benchmarks]; Max-Q variant
(300W blower) is the only stackable one [C-A]; Israel: 0% duty + 18% VAT, **VAT reclaimable as
עוסק ≈ ₪35-70K back** [C-A/INF]; local PRO 6000 retail does not exist — direct import [INF];
4-card power = 1.7kW = one dedicated 16A line (~₪1K) [C-A].

## 3. ☀️ Solar (Iddo's requirement)

1.7kW continuous ≈ a ~10kWp rooftop + storage — standard Israeli residential scale. **Ruling:
grid-first, solar lands WITH the physical space** (a roof you own/rent is a prerequisite; the
online stage has no roof). The kibbutz stage makes the station sun-powered — "בינה לכולם בחשמל
של אף אחד". Note: no verified operating Israeli energy community exists yet [C-A negative] — the
collective would also be a solar pioneer, which fits its story.

## 4. The organization verdict

- **Form:** אגודה שיתופית — the law literally contemplates member dues, at-cost services, and
  co-owned assets [M-I, registrar's 2025 FAQ read in full]. 7 founders register; 60-day answer;
  model-bylaws route ≈ free + lawyer ₪5-20K. Annual: assembly by 30/09, audited report.
- **Shares:** non-dividend (access-at-cost is the benefit) → the Ofek no-prospectus path;
  refunded at nominal value on exit (Ofek template; exit law: Malkiya/Afgin) [C-A].
- **Governance:** 1 member = 1 vote → elected ועד + ועדת ביקורת (mandatory) [M-I]; machine
  fairness = LiteLLM per-member keys + MIG slices + AI-Horde-style earned credits or plain
  fair-share; access gated on a short certification (hackerspace best practice) [C-A].
- **Big upgrades:** London-Hackspace pledge drives — the CO-OP owns what pledges buy [C-A].
- **Grants:** מפעל הפיס/רשות החדשנות do not fund equipment clubs [C-A negative] — the sister
  עמותה (AI education) is the grant door later [INF].
- **The magnet:** weekly public "floor-price AI" demos running on Iddo's EXISTING fleet — the
  ERAN story draws the 150 [INF; MDLI's 20K-member precedent shows the channel: Telegram+FB].

## 5. First 90 days (the playbook, from 4 Israeli precedents)

1. Open the flagship channel (Telegram/WhatsApp) + FB group. Name: קפה קלוד.
2. Weekly ritual: an online demo — ERAN, the fleet, floor-price AI answers (Hamakor/MDLI pattern).
3. Public member counter. **At 50 signed founding members → register the אגודה → open the
   share drive** (Hamakor law: incorporate only when money must move).
4. Buy the station (re-verify GPU prices that week). 5. Physical space last — rent, never buy first.

## 6. במחלוקת · DISSENT — kept visible

1. **4×PRO6000 vs 2+2-flex:** full seat says buy the end-state once; flex seat says ₪93K cheaper,
   proves demand first, adds cards later (prices may fall as GDDR7 eases — or rise further).
   **Ruling: let the founding assembly vote with that-week prices on the table.** Dissent stands.
2. **Co-op vs amuta:** amuta seat cites TAMI (it works, donor-friendly); co-op seat answers that
   150 OWNERS at floor prices is the whole point, and amutot cannot return shares. **Ruling:
   co-op + sister-amuta later.** Dissent stands.
3. **Buy now vs wait out the GDDR7 crunch:** prices doubled in a year and move monthly — both
   directions argued. **Ruling: the 50-member gate IS the waiting period; re-price at the vote.**
4. **Solar-first vs grid-first:** resolved by physics — no roof, no solar; solar arrives with
   the kibbutz stage. No standing dissent.

## 7. Could not verify (honesty)

Used-GPU price bands (±30%) · Israeli PRO 6000 local pricing (no listing exists) · Israeli GPU
colocation (quote-only) · ISA's Ofek no-action applying to a compute co-op (needs counsel/pre-ruling)
· Israeli makerspace insurance terms (nothing published) · all 2026 GPU prices beyond the week
they were read.

## 8. הניסוי הזול / The one cheap experiment

**Costs ₪0 and starts tomorrow:** open the Telegram channel, announce the weekly demo, put up
the counter. If 50 Israelis sign as founding members within ~90 days — the station is real and
funded. If they don't — the ruling saved ₪243K, and the demos continue anyway.

**Ruling: רלוונטי — והפעם גם בַּשל. The numbers close from three directions.**
