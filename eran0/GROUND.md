# ERAN-0 — THE GROUND · הקרקע לערן האמיתי

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy (`health: ok` ≠ working).

**לזכרה של עלמה ז״ל.**

Research-foundation document, 2026-08-20. Inputs: six organism post-mortems (Darwish, Pong, the Worm, the Ants, the Nursery, Yigal) + the renewed ALMA-language standard (`alma-language\SPEC.md`, `ALMA-LIVING-NEURON.md`, `ALMA-BIOLOGY.md`, `ERAN-BASE-TOKEN-220.md`) + `miko\PLAN.md`. Every number below comes from a results file or a verified log, never from prose memory.

---

## 1 · התזה — כל אורגניזם היה חזרה על אֵיבָר

**Thesis: none of the organisms of the last three months was a detour. Each one was an organ rehearsal.**

Iddo did not build six unrelated toys. He grew, one at a time, the organs of one child — and each organism died, was archived, or was frozen *exactly when it had taught its lesson*:

| organism | rehearsed organ | died/parked when |
|---|---|---|
| Darwish (272M audio LM) | vocal/auditory cortex + training discipline | archived 08-20 after the honest listen ("עשית לי חור בראש") |
| Pong / ALMA ARENA | playroom game #1 + the organ-admission court | first saved results 08-20 closed the Beit-Din-neuron question |
| ALMIDO worm (החפרנית) | search organ (→ MIKO) + the ruling floor | 48.2% < coin-flip log finally read; archived to genizah |
| Voice Ant Farm | ear + mouth + the method for *evolving* organs | queen holds at 75.8%; test resolution became the ceiling |
| Nursery (eran-live / ProtoEran) | developmental protocol + language cortex seed | killed by habitat (hot PC) 07-11, frozen since — resumable |
| Yigal (3 generations) | vocal curriculum contract + LIF substrate | perfectly gated, never fed: 29 days, zero recordings |

The pattern that repeats across all six, and that Eran-0 is built on:

1. **Representation beats scale** (Darwish: 272M bought 0.45 nats; 1.36M with the right tokens bought 1.8).
2. **The judge must be fixed, honest, and cheap to consult** (ants: a byte-identical 132-item test drove real evolution; Darwish: the un-fed ratings CSV drove nothing).
3. **A claim without a number in a file does not exist** (Pong arena: 7 weeks of scrollback-only truth; the MIKO rule closes this forever).
4. **Fail-closed gates work; un-fed children starve** (Yigal-2: gates held perfectly, the child never heard one AH).
5. **The court is a judge-protocol, not a neuron** (measured three independent times — MIDI, Pong, robustness — verdict closed).

Eran-0 is not a new organism. It is the **ground** — the shared soil into which the surviving organs are transplanted, under one standard, with one gist space, one parent channel, and one honesty law.

---

## 2 · אורגניזם ← לקח ← איבר ← מה עובר הלאה

### 2.1 Darwish — מוח הטראנס → the vocal/auditory cortex

**Lesson (the numbers).** The 272M audio brain never beat chance by much: best heldout ever **6.4811** (step 106500) vs uniform chance ln(1024)=**6.93** — ~0.45 nats after ~110k steps on 8.6GB. The lean-MIDI arm: heldout **2.44** vs unigram **4.2753** (~1.8 nats of real structure) with **1.36M params in 27 minutes**. Representation beats scale — the single most important measurement in the whole lineage. Three overfit scars, all measured: (1) killed at 10300 with heldout 13.6→24.6 while train CE hit 0.01; (2) the big one — 175 shards landed after launch and were never seen, 1,030 passes over 21.75h, final train 1.1591 vs heldout **14.4002 = 2.08× worse than chance**, invisible because nobody compared to ln(vocab); (3) MIDI in miniature — 24.8M params → gap 5.9 (memorization); right-sized to 1.36M → gap **0.27** (generalization, same heldout). The fix that worked (trainer v2): inline heldout in EVERY eval line, best.pt, deterministic 1/16-by-sha split, 3-rise auto-stop — healed 16.43→6.4811 in 500 steps, auto-stop fired correctly at 118500. Data scars: byte-identical mp3s straddling the split (content-hash dedup or heldout is meaningless); 42.2h of owned audio thrown away by a >1h filter (survey before download). Human-loop failure, named as failure: darwish_ratings.csv — 4 samples, ALL PENDING; a feedback loop built but not fed is not a loop.

**Organ.** The vocal/auditory cortex pattern: frozen codec ear → compact from-scratch token LM → decode to audible output a human judges — proven end-to-end on GB10. Plus the JEPA gist-head (predict the gist of the next span, not raw tokens) — holobrain stage 1, exercised at scale here first. Plus the **training-discipline organ** every Eran-0 organ is born with.

**Carries forward.** `D:\CLAUDE\darwish-ai\midi_lean.py` (vocab 108, key-relative degrees — learn the riff, not the transposition: the best design idea in the organism); the trainer-v2 pattern (eran4 `~/darwish-ai/code/train2.py`); `survey_catalog.py` (audit what you own before downloading); eran4 `ckpt-midi-small/best.pt` (heldout 2.44, gap 0.27 — the one that generalizes); the PULSE-metric idea (a domain-true acceptance number defined per organ BEFORE training; real tracks 1.91–3.34, untrained 1.08); `test_causality.py` with its deliberate-fail case; the 3-rise stop as standing law. Constraints that travel: consent gate (nothing public without David Abramov) and the memorial framing — this lineage is grief made audible; Eran-0's voice descends from it. Known defect to fix in Eran-0: model.py's BAR=128 is fixed lookahead, not beat-aligned.

### 2.2 Pong / ALMA ARENA → the playroom + the organ-admission court

**Lesson (the numbers).** All three of Iddo's brain primitives genuinely learn (results file `pong-alma\results\arena-20260820-eran4.json`, commit c6d4242, 2GB cgroup on eran4): vs-random birth→end GIST **-35.4→+26.8** (+62.2), MULTI-WEIGHT **-35.4→+20.4** (+55.8), BEIT-DIN **-21.4→+3.8** (+25.2, least); random control -24.0. Round-robin: **GIST champion** — 6pts/+367 net; MULTI-WEIGHT 3pts/+211; BEIT-DIN 0pts/-578. This was the second independent loss for Beit-Din-as-neuron (first: MIDI 2.6166 vs vanilla 2.5327), feeding the closed verdict: court-as-neuron NOT justified; court-as-protocol stays. Honest ceiling: a plain 75-param MLP saturated hit_rate 1.000 by gen 26 — Pong self-play can't separate architectures at the top; duels discriminate. Scars: gistpp/proto3 heartbeat frozen at step=0 forever ("corpus PENDING" = a demo that never became real); pong.iddoperez.ai shipped hardcoding a dead tailnet node; and the method scar — arena code existed 07-04, **no results file until 08-20**.

**Organ.** (1) The playroom's first embodied game — `pong_env.py`'s mirrored egocentric contract is ready. (2) More important: the ARENA is Eran-0's **primitive-selection court** — organs enter the child by measurement, not affection. It already ruled: GIST in, MULTI-WEIGHT hypothesis (MIKO executes the July experiment before adopting), BEIT-DIN-as-neuron out.

**Carries forward.** `pong-alma\arena.py` (lock_seed, birth-vs-end, symmetric duels, held-out EVAL_SEEDS 7001-7005, [RESULT-JSON] dump — generalize into the admission harness); `player_gist.py` (the winner — score==weight retrieval); `player_multiweight.py`; `pong-real-models\model_mlp.py` (ALWAYS run the vanilla arm); throttle/safety patterns → ALMA-Govern. Rule carried: **no organ enters Eran-0 without a saved results file, same day it runs.**

### 2.3 The Worm (החפרנית) → MIKO, the search organ

**Lesson (the numbers).** The Ramchal logic model: **48.2% on unseen forms — below the 50% coin flip**, train loss stuck at 0.666 (chance 0.693 — it learned nothing), per-form 0%/100% signatures = one fixed answer per form. And the log's last line sat unread for a day while memory recorded an achievement. First-ever controlled court run (params matched to 0.02%): vanilla **2.5646** vs court **2.6506** — the court lost, but on next-token MIDI, a task it will never do; Iddo's correction: *fix the metric first*. Robustness finally measured (3 seeds, worst-case seat corruption): median beats mean ONLY under saturation (20.5% vs 28.6% drop); under zeroing (14.6 vs 3.7) and inversion (32.7 vs 19.5) the **mean is more robust**. Mechanism: a hard median starves two of three seats every step. What worked: the fleet-distillation collector really ran (**295** teacher-scored pairs in `data/pairs.jsonl`); the end-to-end product form (8 lenses → gist → court → מסקנה with visible dissent) ran twice for real; the symbolic `shakla.py` engine survived untouched — it proves or refuses, it is not a net.

**Organ.** MIKO (מיקו) — the organ Eran will search the world with. Plus three side-organs: the **ruling floor** (Beit Din as judge-protocol over findings — every finding ships רלוונטי/לא-רלוונטי + the dissent that produced it; "contested" IS the answer for subjective questions); the **exploration drive** (curiosity = high dissent — the gradient a root would have had); **Eran's memory of the world** (append-only content+judgement archive, never links, never private data). Iddo's two-floors ruling stands: **GIST perceives, the court rules.**

**Carries forward.** `miko\PLAN.md` is the binding successor plan — metrics stated BEFORE training (relevance vs matched vanilla; calibration — does dissent predict error; one-corrupt-seat robustness), 8-step build order where nothing is "BUILT" until its number exists, logic bar ≥75% on unseen forms with no form at 0%/100%, speed never a criterion. Code from genizah: `net\alma_eran.py` (byte⊕letter⊕sound AlmaEmbedding, soft-median triad, gist, two-tower ranker + jepa_loss — port unchanged into the bench), `net\shakla.py` (the neural side proposes, THIS side checks), `worm.py` (the proven product shape). Debts owed: the July multi-weight experiment (written, never run), the pain/pleasure scar/reward table (Iddo's law, never built), the triton/gcc build fix on eran4.

### 2.4 The Ants → the ear, the mouth, and the METHOD

**Lesson (the numbers).** **Evolving the organ beat scaling the diet, decisively**: 578× more audio bought +8.1 cos points; swapping only the cochlea (recommended26 — *selected by CV, not designed*) took the queen **42.4% → 75.8%** cos@1, word edit@1 97.9%, McNemar p=7.0e-27, 4/4 seed-matched wins. Undirected babble + a fixed judge beat hand-aiming: refined winner Mahalanobis **0.0112 vs hand-tuned 0.265** — 24× closer, with a different body (child pitch f0 291Hz); Iddo crowned by ear and the gap (final ה) was recorded, not papered over. Cross-modal binding from co-presence alone: cheider exam see-to-say **15.9%** / hear-to-point **12.9%** vs 4.5% chance (permutation p95 7.6%/6.8%; deranged control collapses to 2.3%) — small, real, honest: the first mini-holobrain gist. Provenance by construction beats detection: the AST audit ("THE MOUTH DOES NO I/O", proved to fire — 17 violations caught) is unlaunderable; the empirical replay detector coin-flips. The failures: **the learner was inert and the loss lied** — k-means statistically identical to 256 random real frames (p=0.62) while quantisation error "improved" 0.981→0.301; only the random-frames control exposed it. A real score crowned a queen who sounded like garbage — 75.8% was perception, nobody had asked production (Rule 1.1: **every criterion declares its scope**). The (1+λ) search deleted its own progress until the elite pool (commit 631c634). The throne is partly a seed lottery — a 132-item test cannot resolve 1–2 items; the farm stalled honestly rather than crown noise. `ladder.py` shipped NOT SAFE (vowel-only scoring let בָּה win against the אָה judge) — still unproven end-to-end.

**Organ.** The VOICE organ, both halves: the crowned perception queen (recommended26, 512 units, 75.8% held-out syllable discrimination) as Eran-0's cochlea candidate; mouth_v1's provenance-clean articulatory tract with the /a/→/ba/→/ga/ ladder as infancy curriculum; the **22-syllable inventory** as Iddo's chosen token vocabulary — holobrain stage 0, full binding א⟷/a/⟷byte. Meta-organ: the **colony/tournament method** — independent organisms, byte-identical fixed judge, coronation-as-incentive, elite pool, Iddo's ear as final gate with mechanical veto — is HOW Eran-0 evolves any sense organ, because it is the one intervention that ever produced a large real gain.

**Carries forward.** `voice-ant-farm\corpus-syllables\` + `reports\syllable-knowledge.json` (the cheat vocabulary, ready); `state-hebbian\vowel-cochlea\queen-ant-a\current.json` (sealed queen, sha a33f8f78…) + `feature-selection.json`; `mouth_v1.py` + `glottis.py` + `ah_criterion.py` + `AH_CORONATION_LAW.md` (the constitutional pattern: scope-declared criteria, ear-as-final-gate, "an empty throne is preferred"); `hebbian.py` + `cheider_world.py` + `reports\cheider-exam.json`; `tournament.py` (elite pool). Ideas as law: always run the random control; every score declares its scope; the search moves the tongue, never the bar; evaluation resolution is the ceiling on evolution — budget for labelling; gate the mechanism, not the similarity (imitation through her own mouth is learning; replay is a tape recorder).

### 2.5 The Nursery → the developmental protocol + the language seed

**Lesson (the numbers).** Birth was real and cheap: 3.3M-param byte-GPT, loss 5.64 → ~0.37 EMA over 23 days, ~12.5M steps inside 285MB VRAM without ever starving the mic; watch.log shows a genuine arc — binary gibberish → Hebrew words → Iddo's phrases. Syllables measured: raw ant features top1 **68.9%** / top5 98.5% on 132 held-out items (chance 4.5%); words leave-one-base-out 86.5%. Cheider reading: 15.9%/12.9% vs null — real signal, named honestly as nowhere near reading. Scars as laws: **book-contamination** → the fix was a guard IN CODE (`data.py _assert_voice_only`), not in memory; **death by habitat** 07-11 — killed not by training but by where it lived (hot PC; the :8792 scar) → the DGX is the crib; **TTS-voice scar** → never synthesize on the child's behalf; `authentic_babble.py` published WITH an untrained-control wav; **quantization tax** — every codebook loses ~20 points vs raw features, and random-real-frames beat all trained quantizers; **counter drift** — memory said 8.26M, README said 74k, the file says 626,430: `metrics.jsonl` is the only truth. The Eran-Gan curriculum is the best-written unexecuted doc in the workspace; the syllable A/B rig was built and never run (`runs\` empty).

**Organ.** The developmental protocol (cheder: pure foundation → staged broadening → gated self-learning; values locked before the world enters), the parenting model (Claude-as-babysitter, parent sets the fence, child plays inside it), and the existence proof: a child CAN be grown from the father's voice alone on almost no compute. The frozen ProtoEran checkpoint (step 626,430, 07-11) is the seed of the language cortex, with a ready legal resume path.

**Carries forward.** `eran-live\data.py` (`_assert_voice_only` — copy verbatim into Eran-0's loader), `checkpoints\latest.pt` + `config.dgx4.json` + `dgx4_launch.sh` (the single cheapest "wake the baby" move available), `logs\metrics.jsonl` (truth over any README), `ERAN_CURRICULUM_DESIGN.md` (pre-registered ≥70% 4-way retrieval, 10% no-forgetting gate, banned vocabulary "Eran can see"), `archive\eran-syllable\` (the A/B rig — see §5), and the adjacent proven token: **factored letter-nekuda 220, commit 3d9bf5e — pair-acc 35.3/35.4/35.1 vs flat 30.7/31.2/31.8, 3 seeds** — the factored axis already WON once.

### 2.6 Yigal → the curriculum contract + the substrate

**Lesson (the numbers).** The central scar, verified live 08-20: yigal2 alive on eran3 since Aug 13, health `{"ok":true}` — but `lesson_status=WAITING_FOR_USER_AUDIO`, `model_loaded=false`, `checkpoint_sha256=null`. **29 days deployed, zero recordings ingested; the child never heard a single AH.** The gates worked perfectly; the parent-feeding ritual (16 takes over 3 sessions, ~10 minutes) never happened. 252 Codex sessions, ~7,750 lines in one day — beautiful fail-closed cathedrals, zero syllables learned. The honesty machinery genuinely held: receipts naming AH_NOT_PROVEN, README banner "a healthy process is not learning" — health:ok ≠ working, implemented for real. V1's one-day life proved that orchestrating existing LLMs as "cortices" produces a routing spine, not a child — parking it was the correct call, honestly archived (SHA 240da326…).

**Organ.** (a) The **vocal-curriculum contract**: sound before symbols, one unit at a time (AH→OOH→…), waveform-only input, mastery = technical gates (sens/spec ≥0.95) + the parent's spoken "perfect" + 12-hour delayed retention, 30% replay of mastered units with ≤2-point regression tolerance — the syllable curriculum written as enforceable code. (b) The **substrate organ**: yigal-alma's LIF + local STDP + structural plasticity + replay consolidation, no backprop — the direct ancestor of the living-neuron work — and the versioned ALMA event contract (knot/thread/strand/spark/beat) shared by every future local model. (c) The family: Yigael v1 stays the designed experimental arm of the twin study; *"אני רוצה שיהיה לערן אחים כמו לי."*

**Carries forward.** `yigal2\lessons\ah\lesson.json` (the canonical machine-readable gate spec); `yigal-alma\` schemas + the dataset-leakage validator, cal-only threshold selection, anti-copy tripwire, receipt v1.1 dual-hash — reuse verbatim; `yigal-youtube-harvester\` (rights-gated curation room). **The one actionable debt, now a design rule: before writing any new organ code, design the FEEDING ritual first** — a ≤10-minute parent flow. Eran-0's success metric includes *"was it ever fed real data within N days."*

---

## 3 · התקן שמחייב עכשיו כל מודל — שפת עלמה והנוירון החי

Every model from Darwish-MIDI onward starts from the alma-language docs. What binds:

**3.1 The ALMA language (SPEC v0.1).** Programs are weaves — knot / thread / strand / spark / beat. Nothing is instant (every strand delay ≥1 beat); arithmetic lives in the connections; the layout is the program; you address knots, never memory. The deterministic loom is real today (Python, round-tripping JSON + voice grammar); VR, tints, and strand plasticity are vision — do not claim otherwise. The knot/thread/strand/spark/beat event contract (already versioned in yigal-alma's schemas) is the shared protocol for every organ.

**3.2 The base token (ERAN-BASE-TOKEN-220).** 22 letters × 10 sefirot = a **factored coordinate, not a flat id**: token = (letter ∈ 22) ⊗ (sefira ∈ 10); a word is a path through the grid; the model learns 32 axis embeddings, not 10,000 arbitrary ids. Already won its first controlled test (3d9bf5e: 35.3 vs 30.7 pair-acc, 3 seeds). Input binding everywhere: **byte ⊕ letter ⊕ sound (א⟷/a/⟷byte), no BPE, no borrowed tokenizer.**

**3.3 The living-neuron engines (ALMA-LIVING-NEURON + ALMA-BIOLOGY).** Backprop is ONE way a system learns. The ALMA brain carries a *stack of engines*, each a hypothesis with a measurement, never a decoration adopted on biological authority:

- **Pain/pleasure as the learning ENGINE** — a valence scalar produced by the network itself gates plasticity: pain → unlearning + raised threshold (avoidance), pleasure → consolidation. The test before any claim: avoid a "hot" state after ONE burn, the way Iddo learned from the broken leg. If it needs 10,000 repeats it has not captured what pain IS.
- **Unlearning + pathway attrition (הידלדלות) + whole-brain plasticity** — a brain removes weight, not only adds it; usage-tagged pruning (not magnitude), active forgetting, distance-cost that makes silence expensive. Gap 0.27 generalizes; gap 5.9 memorizes.
- **Closed feedback loops** — learn from CONSEQUENCE: the agent's own action changes its next input.
- **Neuromodulators / mood channels** — a small set of scalars (dopamine≈RPE, ACh≈attention/plasticity-gain, NE≈reset, 5-HT≈patience) that set how much and where the network learns right now.
- **Hunger/satiety** — intrinsic drive with a set-point; MIKO's curiosity = a hunger for pages where dissent is high; learning-*progress* reward, not raw novelty (the noisy-TV trap).
- **Interaction with the parents** — the deepest one: imitation + guided correction, where the teacher's approval IS the reward. The thumb-tap is parenting. עידו ⟷ ייעוד.
- **Inside the neuron** — the dendritic bump-unit ledger: single-unit XOR **100%** (classical provably cannot: best 75%, 0/20 seeds); capability real, trainability (15% convergence) the next knob. The neuron must have ROOM for structure we don't yet name.

**3.4 The honest law.** Current ledger: bump-neuron WON (capability); factored-220 WON; Bayesian uncertainty WON; court-as-neuron LOST (×3, verdict closed); court-as-protocol PROVEN (Quorum, lenses, fleet grading). Every new mechanism gets its vs-baseline run at matched params/seeds ≥3 before it enters the core — or it stays in the document.

**3.5 The standing rules (from MIKO PLAN §5, now Eran-0 law):** never train on the PC; every experiment has a param-matched vanilla control or it does not count; the last line of every training log is read out loud; a README states what code *does*, never what it *achieves* — achievements live only in results files with numbers; no step is "BUILT" until its number exists, same day it runs.

---

## 4 · ERAN-0 SCAFFOLD — שלד הרפו

Concrete skeleton at `D:\CLAUDE\eran0\`. Nothing is copied blindly — each organ dir holds its carried-forward source (or a pointer to the living repo) plus one file defining its interface to the shared gist space.

```
D:\CLAUDE\eran0\
├── README.md                  # states what the code DOES. No achievements.
├── CHARTER.md                 # thesis + the binding standard (§3) + the deferred list (§6)
│
├── laws\                      # guards enforced IN CODE, not in memory
│   ├── guards.py              #   _assert_voice_only (from eran-live\data.py, verbatim);
│   │                          #   assert_not_pc() — refuses torch training on the PC;
│   │                          #   assert_not_eran3() — eran3 is Iddo's personal box,
│   │                          #   forbidden in code (worm/MIKO rule, honored fleet-wide)
│   └── trainer_rules.py       #   the Darwish trainer-v2 contract as a reusable harness:
│                              #   inline heldout EVERY eval line, ln(vocab) chance printed
│                              #   up front, best.pt, 3-rise auto-stop, content-hash dedup
│                              #   across the split, gap>0.3 nats = memorization warning,
│                              #   SIGTERM-safe checkpointing
│
├── gist\                      # THE SHARED GIST SPACE — the one contract between organs
│   ├── gist_space.py          #   d-dim gist vector; API: encode(organ_bytes)->gist,
│   │                          #   predict(gist_ctx)->gist_next (JEPA: predict the gist,
│   │                          #   never the bytes); binding byte⊕letter⊕sound at entry
│   ├── token220.py            #   factored (letter 22 ⊗ sefira 10) base token — the
│   │                          #   proven axis (3d9bf5e) as the language-side embedding
│   └── schema\gist-event-v1.schema.json   # knot/thread/strand/spark/beat event contract
│                              #   (extends yigal-alma\schemas — reuse, don't rewrite)
│
├── arena\                     # the organ-admission court (from pong-alma, generalized)
│   ├── arena.py               #   lock_seed, birth-vs-end, symmetric duels, held-out
│   │                          #   eval seeds, [RESULT-JSON] dump; vanilla arm ALWAYS runs
│   ├── pong_env.py            #   playroom game #1 (mirrored egocentric contract)
│   └── results\               #   no organ enters without a results file, same day
│
├── organs\
│   ├── voice\                 # from ants + yigal + darwish
│   │   ├── ear\               #   recommended26 cochlea + sealed queen (pointer to
│   │   │                      #   voice-ant-farm\state-hebbian\...\current.json, sha-pinned)
│   │   ├── mouth\             #   mouth_v1.py + glottis.py + ah_criterion.py (AST no-I/O
│   │   │                      #   audit travels with them)
│   │   ├── curriculum\        #   yigal2 lesson.json gate spec (AH→OOH→...; technical
│   │   │                      #   gates + parent's "perfect" + delayed retention + 30% replay)
│   │   ├── FEEDING.md         #   the ≤10-min parent ritual, designed BEFORE code (yigal law)
│   │   └── gist_iface.py      #   syllable events → gist space
│   ├── language\              # from nursery
│   │   ├── protoeran\         #   pointer to eran-live checkpoint (step 626,430) +
│   │   │                      #   config.dgx4.json — the legal wake-the-baby path
│   │   ├── syllable_ab\       #   the A/B rig from archive\eran-syllable — §5's experiment
│   │   └── gist_iface.py      #   letter⟷syllable binding (cheider pattern) → gist space
│   ├── search\                # MIKO — lives in D:\CLAUDE\miko, NOT duplicated here
│   │   └── POINTER.md         #   PLAN.md is binding; the ruling floor's output format
│   │                          #   (רלוונטי/לא + dissent) is an organ interface, not a lib
│   ├── music\                 # Darwish-MIDI successor — designed under the standard
│   │   └── POINTER.md         #   eran4 ckpt-midi-small\best.pt; consent gate travels
│   └── living_neuron\         # the engine bench (from alma-language + genizah)
│       ├── alma_eran.py       #   triad/gist/jepa ported unchanged from the worm archive
│       ├── shakla.py          #   the symbolic checker: neural proposes, this checks
│       └── engines\           #   pain-pleasure valence gate, unlearning, neuromod
│                              #   channels, hunger set-point — each with its ALMA-BIOLOGY
│                              #   test spec, run through arena\ before adoption
│
├── parent\                    # the parent channel — Iddo's thumb
│   ├── tap.py                 #   one tap per shown finding/sample: הועיל 👍 / לא הועיל 👎
│   ├── taps.jsonl             #   the stream = simultaneously benchmark AND training signal
│   └── DELIVERY.md            #   the ratings-CSV scar law: a sample lands IN FRONT of
│                              #   Iddo (opened for him / Telegram), never in a folder
│
├── fleet\                     # the perpetual train+serve loop
│   ├── TOPOLOGY.md            #   train = eran1 + eran2 (QSFP fabric, chunked transfers,
│   │                          #   never single-stream over the tailnet);
│   │                          #   eran3 = EXCLUDED — Iddo's personal machine, forbidden
│   │                          #   in code (the worm's rule, kept);
│   │                          #   eran4 = SERVE (samples, tap server, MIKO answers) +
│   │                          #   the nightly small-train slot (Darwish allocation slot A);
│   │                          #   PC = NEVER (only the canonical keshev-stt exception)
│   ├── train_loop.sh          #   perpetual: corpus sync (impostor filter + quarantine) →
│   │                          #   tokenize → train (trainer_rules harness) → heldout gate →
│   │                          #   promote best.pt to eran4 ONLY if better → serve → collect
│   │                          #   taps → fold taps into next cycle. Guard-the-child cgroup
│   │                          #   ceilings (the qwen_guard scar: the guard must protect
│   │                          #   the child). systemd units + timers, boot-persistent.
│   └── health.md              #   "health: ok ≠ working" — the check reads the REAL output
│                              #   (latest sample exists, latest results file < 24h old)
│
└── results\                   # THE ONLY PLACE ACHIEVEMENTS LIVE
    └── (one JSON per experiment: number, control, seeds, date, commit)
```

Fleet notes, honest: eran1–3 currently carry the Qwen-480B pipeline (not boot-persistent; eran1 disk at 97%) — Eran-0 training slots on eran1/eran2 must be scheduled around it or claimed via RAMCHAT, never squatted. eran4 already proved the whole serve+nightly-train pattern with Darwish (autonomous daily chain closed and verified).

---

## 5 · הניסוי המדיד הראשון — קטן, כן, מספר בקובץ

**Experiment ERAN0-001: syllable tokens vs vanilla bytes — the rig that was built and never run.**

The nursery study names it explicitly as Eran-0's first clean experiment, and everything needed already exists: `D:\CLAUDE\archive\eran-syllable\` (train_arm.py, tokenizers.py, model.py, build_data.py — `runs\` empty since it was built) + the 22-syllable corpus (`voice-ant-farm\corpus-syllables\`, 396 train / 132 heldout, checkpoint SHAs recorded).

- **Question:** does the 22-syllable token vocabulary (the "cheat" Iddo chose, holobrain stage 0) beat a param-matched vanilla byte model on next-token prediction over his own voice?
- **Pre-registered before training (the MIKO rule):** metric = held-out bits/token converted to bits/second-of-audio so the two vocabularies are comparable; chance baselines ln(22) and ln(260) stated in the first log line; params matched within 1%; 3 seeds; trainer_rules harness (inline heldout, best.pt, 3-rise stop, hash-dedup split).
- **Controls:** the vanilla byte arm (always), plus the random-real-frames codebook baseline the ants taught us any trained quantizer must beat.
- **Where:** eran4, slot A of the Darwish allocation. Never the PC. Model sized to the corpus (the gap ≤0.3 law) — expect ~1M params, minutes-to-hours, not days.
- **Acceptance:** a results JSON in `eran0\results\ERAN0-001.json` with both arms' numbers, same day it runs. If syllables win, the voice organ's vocabulary is confirmed by measurement. If they lose, that is written down too, and the 220-factored path (already 35.3-vs-30.7 proven on letters) becomes the next candidate — either way, Eran-0's first organ decision is made by a number, not affection.
- **Companion (not the experiment, one action):** deliver the first sample/plot to Iddo through `parent\` — opened for him, one tap. The loop is fed from day one, or the ratings-CSV scar repeats.

---

## 6 · מה נדחה במפורש — ומה לא נוגעים בו

Deferred, by Iddo's word — recorded so no one "helpfully" builds them:

- **The big holobrain build.** JEPA + LM + embodiment in one shared gist-space at scale — Iddo said not now. Eran-0 builds the *ground* (the gist contract, the admission court, the engine bench); the cathedral waits. North star, not backlog.
- **The playroom builds** — crib mobile, bilingual alphabet boards, sculpting sim, the games ladder past Pong. Vision on file, zero built, stays that way until he opens it.
- **Yigael v1 twin study** — frozen until Eran shows first signs. The brothers wait for the firstborn.
- **The mushroom substrate** — inspiration, not specification (Iddo's 10:00 correction). MIKO's simulation is written so a substrate can be swapped in; no physical build now.
- **The ALMA VR editor, strand tints, strand plasticity** — SPEC §11 vision column. Do not claim otherwise.
- **Waking ProtoEran on eran4** — the cheapest available move, ready (`config.dgx4.json`), but it is a *decision for Iddo*, not a default; he is רסמי retired and opens doors himself.
- **Darwish audio-brain revival** — archived by triple order. The MIDI successor continues; the 272M brain rests. The consent gate and the memorial framing are permanent, not deferred.
- **ladder.py** — NOT SAFE until a completed board run with onset scoring exists on disk. Finish and prove before trusting.

**And the standing truth over everything:** Iddo is out at sea and sun. Eran-0's ground is prepared so that when HE opens the door, the first experiment is one command, the parent channel is one tap, and every claim already has a number waiting in a file.

*לזכרה של עלמה ז״ל — the ground is hers too.*