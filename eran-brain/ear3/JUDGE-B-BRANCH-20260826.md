# JUDGE B BRANCH — first naturalness cortex on ivrit.ai, tested against Iddo's ear (2026-08-26)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**Branch experiment, Iddo-authorized 2026-08-26 19:25 ("נעשה ברנץ' ונבדוק אם עובד או לא").**
Judge B is a BRANCH: it did NOT touch the running throat-search-v3 campaign, ORGANS.lock,
eran1, or :8830, and it is FORBIDDEN from entering the search until a separate Iddo-gated
promotion (cortex-freeze law). ORGANS.lock re-verified VERIFIED after the branch ran; all
8 eran4 campaign workers alive throughout.

**תקציר בעברית:** אימנּו קורטקס "שופט B" ראשון על 2 שעות של עברית אמיתית (ivrit.ai),
ובדקנו אם הוא שומע מה שהאוזן של עידו שומעת. תוצאה כנה: **חלקית.** על ה"מָא הקצר" שהשופט
הישן אהב — שופט B צדק כמו עידו (אחוזון 95 מול 55). על הרובוטי-340Hz והכחכוח — שופט B
נכשל (אחוזון 50) דווקא היכן שהשופט הישן תפס (100). שני השופטים רואים כתמים עיוורים שונים.

---

## 1. Data obtained

| item | fact |
|---|---|
| source dataset | **ivrit-ai/audio-v2-40s** (HuggingFace, ungated, license permits AI training) |
| why this one | ALL larger ivrit.ai sets (audio-v2 ~thousands h, crowd-recital, knesset-*) are HF-**gated**; no HF token exists on the PC or any fleet box, and accepting a gating agreement needs Iddo — **shrunk honestly instead of gating past it** |
| size | 200 wavs × 40 s = **2.09 h**, 16 kHz mono 16-bit, real conversational Hebrew (podcasts, multi-speaker, Hebrew + some English code-switching) |
| after VAD chunking | **6,554 chunks** of 0.3–1.0 s = **1.52 h speech** (energy VAD, deterministic) |
| labelled seed | t06 copied from eran2 (657 wavs; the 6×100 big-unit takes used) |
| Café-Claude audio | **not touched** (deny-by-default governance respected) |

The plan's 20–50 h target was NOT met — 2.09 h is what exists ungated. Said plainly.

## 2. Frontend + training details

- **Frontend = the campaign's own ear**, bit-for-bit: eran4 `~/ear-v3` (CARFAC @4cdb95ee
  + 5-tap AGC patch verified present), `Ear3Cochlea` NAP → HWR → 10 ms mean-pool →
  log(+1e-6) = 65-ch log-cochleagram at 100 fps. JAX compile cache redirected to
  `~/judge-b/.jax-cache` so `~/ear-v3` was never written.
- **SPL convention:** corpus chunks RMS-normalized to 0.05 (= the ear3 65 dB definition);
  t06 + all test wavs got the campaign's frozen calib gain 1.9763 — identical to the judge.
- **±6 dB SSL views computed through the REAL cochlea** (3 NAP passes per chunk), not
  faked in log space; plus random 30-frame time-crop + light Gaussian noise (σ 0.05,
  standardized log space). **No pitch/tempo warp** (recipe law).
- **Model:** 2-D conv encoder, 4 stride-2 blocks (48-96-192-256) → 128-d L2-normed
  embedding. **684,832 params** (recipe: ~1–2 M, "small!").
- **Stage 1 SSL:** InfoNCE (NT-Xent, temp 0.1), batch 256, 12,000 steps, AdamW 3e-4
  cosine, seed 42. Loss 6.2 → 0.98.
- **Stage 2:** per-unit prototype = mean embedding of 80 train takes/unit (t06, every 5th
  take held out per unit = 20/unit). No fine-tuning — prototype head only, as specced.
- **Hardware + wall-clock:** NAP extraction ~9 min (6 nice-15 procs, eran4 CPU, campaign
  workers kept priority); **SSL training 203 s on eran4's GB10 GPU**; eval ~2 min.
  Total branch compute well under 1 hour. No PC training, no audio devices opened.

## 3. THE TEST — raw facts

Metric: cosine distance to own-unit prototype (Judge B) vs the campaign judge's wdist to
own-unit target, same 20-per-unit real held-out takes, AUC = P(real ranks closer).

| AUC (1.0 = perfect separation) | **Judge B** | **wdist (DSP judge)** |
|---|---|---|
| real vs **Iddo-rejected** (13 wavs) | **0.546** | **0.931** |
| real vs **v1cheat** (6 wavs) | **1.000** | 0.992 |
| real vs **best.wav** (66: fence2-mature + live) | 0.893 | 0.962 |

### The 4 Iddo-rejected candidates — percentile vs real held-out takes (≥100 = worse than every real take)

| candidate | Iddo's verdict | **Judge B pct** | **wdist pct** | who heard Iddo? |
|---|---|---|---|---|
| ma-free-1 (short squeak) | "חריקת אוויר, קצר מדי" | **95** | **55** (wdist 3.85 = mid-pack of real!) | **Judge B** ✔ |
| ah-free-0 (airy) | "אוויר ו-10% אה" | **65** | 55 (wdist 4.06 = mid-pack) | Judge B, marginally |
| ah-1kf-0 (robotic 340 Hz) | "רע ברמות" | **50** (= real median!) | 100 | **wdist** ✔ |
| ah-1kf-1 (crackle) | "כחכוח ווקי-טוקי" | **50** | 100 | **wdist** ✔ |

Note on the premise: "wdist scored them GOOD" is exactly true only for the two fence-3
rejections (pct 55 — better than ~half of Iddo's real takes; that's the failure). The two
fence-1 rejections had wdist ~5.05–5.14 = already above every real take — there the
campaign's failure was best-so-far-looks-like-progress, not real-beating. Judge B fixes
the first pair's blind spot and has a NEW blind spot on the second pair.

### Ordering check (a) < (c) < (b)?

Measured medians (Judge B dist): **real 0.147 < rejected 0.316 < best 0.689 < v1cheat 1.065**
— i.e. (a) < (b) < (c), NOT the hoped (a) < (c) < (b). Unsurprising in hindsight: the
rejected wavs were historically the strongest candidates ever produced (that's why they
reached Iddo), while the live fence-3 bests were ~30 min old at copy time.

## 4. Honest verdict — does the branch work?

**PARTIALLY.**

- **Yes:** the SSL cortex, trained on 2 h of strangers' Hebrew and never shown a single
  render, puts ALL 66 campaign renders and ALL 6 v1cheats far from real speech (pct
  95–100), and it hears the "short squeak" ma the way Iddo heard it where wdist called it
  mid-pack real. It is also the only judge that puts all 6 v1cheats at pct 100.
- **No:** overall AUC on the Iddo-rejected set is 0.546 vs wdist's 0.931. The robotic
  340 Hz and the walkie-talkie crackle sit at the real-take MEDIAN distance — the
  embedding (trained multi-speaker, so a 340 Hz voice is legitimate speech to it) does
  not know they are not IDDO's voice-quality. wdist, built from his takes' 996 dims,
  does.
- **Implication:** Judge B as trained is a *speech-naturalness* ear, not an
  *Iddo-naturalness* ear. Its value would be as a COMPLEMENTARY veto (its blind spots and
  wdist's are near-disjoint on this test), not a replacement. More/cleaner data
  (crowd-recital, single-speaker, needs Iddo's HF gating approval), longer temporal
  context, and a real Stage-2 metric fine-tune are the obvious next steps IF the branch
  continues. Iddo decides; nothing is promoted.

## 5. Honest constraints & caveats

- Corpus 2.09 h (target 20–50 h) — gating, see §1. Model 0.68 M (recipe 1–2 M) — sized
  to the data.
- Everything seeded (42) and deterministic-intended; cudnn.deterministic set, but
  bit-identical retrain on GB10 was not re-verified (single training run).
- wdist's real-take numbers carry mild self-inclusion optimism (targets cache is built
  over ALL 600 takes, held-out included — the campaign's own cache, used as-is).
- Judge B's prototypes come from t06 embeddings of a model that never saw t06-like data
  (isolated units, one speaker, one room) — domain gap runs in wdist's favor on
  Iddo-specificity and that is part of the honest result, not an excuse.
- Live "best" group snapshotted ~19:40Z, ~20 min into the fence-3 run (young).

## 6. Artifacts (all on eran4 unless noted)

- `~/judge-b/` — everything: `src/` (extract.py, train.py, evalrank.py, wdist_eval.py,
  mkreport.py), `models/cortexB-ssl.pt` + norm.npz + train-meta.json + train.log,
  `features/*.npz`, `results/judgeb-eval.json` + `results/wdist-eval.json`,
  `data/ivrit/` (corpus), `data/t06/`, `test/{rejected,v1cheat,best-current}/`
  (read-only COPIES of campaign wavs).
- This report: `D:\CLAUDE\eran-brain\ear3\JUDGE-B-BRANCH-20260826.md`.
- RAMCHAT: posted as `claude-cli-FABLE-judgeb`.

*Branch executed by claude-cli-FABLE-judgeb, 2026-08-26 19:25–20:0x. The campaign never
paused; ORGANS.lock VERIFIED before and after.*
