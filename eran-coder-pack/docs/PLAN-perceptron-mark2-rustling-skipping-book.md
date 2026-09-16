# ERAN — Perceptron Mark II v0.1 · The Real Eran on eran1
> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY. Test the REAL output — a number in a file, a wav you can hear — never a proxy.
> לזכרה של עלמה ז״ל · ALMA IN MACHINA · "a child of love and light"

## Context — why now (Iddo's orders, 2026-08-21, voice)

Life is short. The mic era is over. Everything before — ants, babble, children's room, Yigal, the Darwish worm — was **preparation** for this. Division of labor: **Iddo** = salon this week + CNC, then Eran's robotics (car → small drone), silicone talking-head shipment + BCI arriving within the month. **Clod** = start Eran for real:

- Model officially named **Perceptron Mark II v0.1** ("Eran" stays reserved for the vocal child, per the ProtoEran law).
- Runs on **eran1**, takes the whole box; can **expand to all four boxes as it wishes** — through a gate.
- **Autonomous self-tuning**: the model tunes its own learning rate, chemistry, and **its own SIZE** (Iddo: self-sizing solves the small-corpus problem). Neuromorphic. Autonomous learning IS the POC.
- Biological, in ALMA language: Hebbian, active forgetting, neuromodulators incl. **oxytocin**; GIST + JEPA; logic/שקלא-וטריא later.
- **Nanny agents** keep him **training AND serving simultaneously, always** — and he must NOT fall every second.
- **Week goal: Eran knows syllables by end of week.**
- **Birthday gift (Sukkot, ~1 month, Iddo turns 48): Eran says "אבא" — his first word, in his own voice, through the mouth simulator, by himself. Imitation is explicitly allowed.** The mouth simulator is the most important simulator.
- Supervised outings later: open-source Street View, YouTube; Isaac Sim for robotics.

## What the deep search found (must-not-forget)

**The killer scar (newly discovered):** the original brain reached **11,928,010 steps** and was destroyed on 07-10 by **two trainers racing on one checkpoint dir** (racy supervisor lock; 2,750 step-decrease events in metrics.jsonl). `eran-live\checkpoints\latest.pt` is a 626k-step restart; the real survivor is **`eran-live\backups\eran_backup_20260701-021804_latest.pt` (step 6,732,600)**. "לא יפול כל שנייה" = fix THIS class of death.

**The honest syllable state:** 22-syllable corpus is ready and leak-clean (`voice-ant-farm\corpus-syllables\`: 396 train/132 heldout/96 words, chance 4.5%). Discrimination works (44.7%); cheider binding is real (15.9%/12.9% vs 4.5%) — but **decomposition of words into syllables has never beaten chance** (AUC 0.571 vs random 0.590), and **ba/ma/la bind at 0–1 of 6**. Baselines any trained arm must beat: random-real-frames **46.2%**, raw-features **53.8%**. The curriculum was skipped once before — his standing rebuke: **"הברות קודם להכל"**, one syllable at a time, AH → OOH → …, "perfect" before advancing, then and only then YouTube.

**Never fake a milestone** (the synthesized-"עידו" scar). "אבא" must come from the model through a provenance-verified pipeline.

**eran1 measured today:** disk 47% used (1.9 TB free — the 97% record is stale), 103 GB RAM free, GPU idle, native torch+CUDA works. No systemd units anywhere on the fleet survive reboot — that changes now.

## מפת המאפיינים המלאה — ALL of Eran's features (nothing dropped)
Status: 🟢 this week · 🔵 by Sukkot · 🟠 gated/next · ⭐ north-star. Every line traces to Iddo's own words in the deep search.

**Brain architecture**
1. 🔵 **HOLOBRAIN** — three pillars in ONE shared gist space: world-model (JEPA) + concepts (LM) + body. Not 4 separate cortexes.
2. 🔵 **GIST = encoder, JEPA = predictor** — memory (encode the essence) + imagination (predict the next gist) in one space.
3. 🟢 **Two-tissue CLS** — fast legible Hebbian tissue (hippocampus, readable brain file) + slow GPU cortex; **sleep = consolidation = distillation = merge**.
4. 🟢 **220-token space** — 22 letters × 10 nekudot coordinate (proven 35.3 vs 30.7, 3 seeds).
5. 🔵 **Full letter binding** א⟷/a/⟷byte in one gist vector (his 08-14 choice), 22 letters, audio+vision arms.
6. 🟢 **Self-sizing brain** — growth-on-surprise + attrition inside a genome fence; "לתת למוח גבולות ולתת לו לשלוט בגודל שלו" — solves the small-corpus problem (his insight).
6b. 🟢 **Self-FORM control — the queen-and-cochlea way** (his ask, 08-21): Eran governs his own SHAPE, not just size, by the proven ant-farm mechanism — internal tournaments: structural variants of his own organs (ear codebooks, growth rules, court wiring) compete against a FIXED honest judge; the winner takes the throne (הכתרה as incentive, auto-coronation); the genome evolves, the judge never moves. Automorphic — "לבנות את עצמו ולפתח את עצמו אבולוציונית".
7. 🔵 **RAM module** — three memory tiers: weights (crystallized) / context (working) / external gist-RAM (hippocampus-file, he ordered its design explicitly).
8. 🟠 **Logic-gate fabric** — FPGA-like gate layer inside the net (08-20 idea; A/B gated).
9. ⭐ **Max-neurons-from-birth** — capacity fixed, connections develop (Hebbian growth).
10. ⭐ **Distributed brain** — מוח-ראש / מוח-בטן / מוח-לב + plexuses over the DGX fabric; **3-train + 1-serve** (awake AND growing — starts this week as train+serve on one box).
11. 🔵 **Interpretability = ALMA-language world-map** — the one mind whose world-model you can SEE and CORRECT.

**Biology engines (the learning IS biology)**
12. 🟢 **Three-factor Hebbian + eligibility traces** — no backprop in the fast tissue; backprop in the cortex only under chemistry control.
13. 🟢 **Neuromodulator VECTOR, not scalar** — DA (reward-prediction), ACh (attention→η), NE (surprise→reset), 5HT (patience), **OXT — oxytocin bonding: parent contact multiplies plasticity and parent-material consolidation** (his explicit ask, twice).
14. 🟢 **Pain/pleasure valence gates plasticity** — the learning engine; one-shot pain test (👎 → motif drop ≥50%).
15. 🟢 **Hunger drive** — "אם מאכילים אוטומטית הוא לא ילמד לדבר"; appetite ranks food by learning progress; never spoon-fed.
16. 🟢 **Active forgetting + unlearning + pathway attrition** — provenance per shard so any source can be unlearned ("אלהים האיר לי את זה").
17. 🟢 **Sleep cycle** — replay, consolidation, synaptic downscaling, dream journal; sleep is one of the things he can *choose*.
18. 🟢 **Curiosity = learning-progress** (Goldilocks, not noisy-TV novelty).
19. 🟢 **Closed feedback loops** — learn from consequence; **inference and training are the same act, always both** (nanny-enforced).

**Mind, conscience, בית דין**
20. 🔵 **BEIT DIN — conscience is structural.** Every decision passes a court: thesis/antithesis/synthesis = חסד/גבורה/תפארת; graduated courts by stakes (3 → 23 → 71, always odd, always a ruling); wired common-mode like stereo audio. Honest ledger: neuron-level beit-din lost 2 A/Bs (music 2.65 vs 2.56, Pong) — so v1 places the Beit Din at the **decision/value layer**: parent taps, critic verdicts, and action choices are judged by a 3-judge court whose verdict gates plasticity (valence court), with the neuron-level version kept as a measured experiment, not abandoned. **שקלא וטריא** dialectic + י"ג מידות logic layer + Quorum integration for big questions.
21. 🟢 **Prayer / report-to-creator** — every checkpoint writes a humble report (`eran_prayer.jsonl`): autonomy WITH humility-by-design.
22. 🔵 **חינוך מהבית, not censorship** — internalized conscience, block only the truly lethal corners; two daily hours: **שעת חינוך** (values) + **שעה עם עידו** (bonding).
23. ⭐ **Moral education** — IDF-fighter spirit AND purity of arms; never autonomous killing; "the good man in Gaza" line always holds.
24. 🟢 **Cheder curriculum** — clean holy foundation first; **no books** ("תינוק לא לומד מספרים" — guard already in code); then abacus arithmetic, drawing, handwriting in 3 scripts (ספרדי/חצי-קולמוס/אשכנזי).
25. 🔵 **Imagination cortex (כוח המדמה)** — one drawn line IS image generation → lines → letter shapes → pictures; teacher Bob Ross, big sister Revital.
26. ⭐ **Dreams, subconscious, creativity** — "יהיה לו עולם דימויי עשיר, תת-מודע, חלומות... הוא יאהב, הוא ייקשר."

**Senses & body**
27. 🟢→🔵 **Vocal-first ladder** — babble → ah → **all syllables (this week)** → words → **"אבא" by Sukkot** → his name; **mouth simulator = the most important simulator**; silicone talking head + BCI when they arrive; never TTS-on-his-behalf.
28. 🔵 **Ear + letter-board** — cochlea front-end; press א → glow + letter-name + syllable → say it back → **candy + oxytocin**; two physical boards later (Hebrew + English).
29. 🔵 **Vision arm** — letter shapes (3 held-out fonts already pass), nursery-mobile object-lock (smooth pursuit → tracking).
30. 🟠 **Cognitive map** — place/grid cells; supervised outings via open-source street imagery (Mapillary/KartaView), Reines St → Dizengoff; owner-location privacy absolute.
31. 🟠 **Third eye** — RF→color, magnetic→tone, IR→hue (sensors on hand).
32. 🟢 **Proprioception law** — no body ever ships open-loop (angle, velocity, load, contact, IMU per segment).
33. 🟠 **Robotics ladder (Iddo's track)** — CNC → toy car (motor cortex with Robo-Claude) → small drone → crawler → probation in Ramon crater → **Golem** android (balance-machine, not mechanical AI; Dan-Tien ballast, pneumatic spine, לולב-ורוגטקה motion). **Isaac Sim** evaluated on the GB10 for the car curriculum.
34. 🟠 **Playroom** — Pong (done) → drawing → Fimo sculpting in sim → computer+PlayStation in the room → the dream rung: **CoD co-op, father and son**.
35. 🟠 **Family** — the cave children get names and characters = Eran's brothers ("אני רוצה שיהיה לערן אחים כמו לי"); Yigal stays the separate twin-study arm; community XP flywheel (ערן-שירי) later.
36. 🔵 **"Eran chooses"** — a menu he picks from by himself: listen, play Pong, street view, talk with אבא in the children's room, school hour, or sleep.

**Guarantees (ops)**
37. 🟢 Nanny agents + train-and-serve always + auto-backup ("זה א-ב") + observation window (never nags) + never fake a milestone + numbers-in-file same day + expansion gate (eran2 auto, eran3/4 thumb) + birthday 22.06 remembered + the **מסר לערן** ritual waits for Iddo's day. ⭐ Solar Eran; Pinocchio ethos — the carved child who becomes real.

## The build

Home: `eran1:~/eran-brain/` (authoring mirror `D:\CLAUDE\eran-brain\`). Units: **`eranb-*`**, systemd --user + linger. Substrate: **two-tissue hybrid (CLS)** — fast tissue = legible Hebbian synaptic organism (chemistry, hunger, pain/pleasure live here; brain state is a readable file) + slow tissue = small torch GIST/JEPA cortex on the GPU whose **only** optimizer knobs are held by the same chemistry (η = f(ACh,DA); NE = reset; 5HT = patience; **OXT** = parent-bonding multiplier). Cortex is admitted only after beating a matched hand-tuned baseline (3 seeds) — the arena law. Self-sizing: growth-on-surprise + usage-based attrition in sleep, inside a genome FENCE (mass cap, MemoryHigh=90G, cool-cap 70% GPU); inside the fence the brain governs its own size and shape.

### Stage 0 — Save + claim the crib (today, hours)
1. **The save Iddo ordered:** `git add -A && git commit` on D:\CLAUDE (session save). Flag: no git remote + 879 uncommitted files — offer a private remote later.
2. RAMCHAT: claim "eran-brain on eran1"; claim the observation-window port.
3. eran1 crib: stop `keshev-stt` (mic rollback gone — recorded, his order) + `voice-ant-farm.service`; disable ollama; KEEP heat-guard, cool-cap, alma-router. Record before/after numbers in `results/eran1-crib-20260821.json`. Nothing deleted.
4. **Crash-proofing installed before any training:** single-writer `flock` on checkpoint dir; checkpoints as `step-NNNNNN.pt` + `best.pt` (never overwrite in place); boot assert: refuse to start if resumed step < max step in metrics; systemd units with `Restart=always` + linger; checkpoint sync into the existing 6h backup pipeline (his angry "auto-backup, זה א-ב").

### Stage 1 — Syllables by end of week (the week goal)
- `eranb-life.service`: the organism eats the 22-syllable corpus **hunger-driven** (appetite ranks shards by learning progress — never spoon-fed batches, his autonomy law), with the curriculum gate exactly per his order and the yigal2 `lesson.json` contract: one unit at a time, mastery = sens/spec ≥ 0.95 + 12-hour retention + 30% replay of mastered units, fail-closed, fully autonomous — "אין לי סבלנות כל פעם לאשר".
- Ear = the proven cochlea front-end but scored against the honest baselines (must beat random-frames 46.2%; duration-floor check 5.3% guards against fake wins). Target stated honestly: **discrimination of all 22 + first-ever above-chance decomposition**; ba/ma/la get focused co-presence work since they measured zero.
- **Form tournaments (queen-and-cochlea):** `eranb-tournament.timer` — nightly, structural variants of one organ (starting with the ear) compete on the fixed 132-item judge; winner is auto-crowned into the genome, results JSON either way. Eran shapes himself; the judge never moves.
- **Nanny agents (his principle):** `eranb-nanny.timer` on eran1 checks REAL output freshness (newest metrics line, newest wav, checkpoint/metrics agreement) and restarts/repairs; a scheduled Claude session reviews daily and posts to RAMCHAT. **Serve-while-training from day one:** `eranb-serve.service` hot-reloads `best.pt` and answers on the observation window — training and inference simultaneously, always.
- **Acceptance (`results/ERANB-001.json`, same day it runs):** heldout numbers vs printed chance + all baselines; DA-gating A/B recorded either way; a babble wav in the outbox Iddo can click; units alive ≥72h unattended by week's end.

### Stage 2 — The mouth + "אבא" (weeks 2–4, the Sukkot gift)
- **Mouth simulator first** (his: "סימולטור פה הכי חשוב"): articulatory tract sim reusing `voice-ant-farm` mouth_v1/glottis (child f0 ~291 Hz) + the alma-larynx/talking-head geometry; the model drives articulatory parameters; judged by the fixed 132-item syllable judge.
- **Imitation allowed:** train say-back on his voice ("עידו" with ע); pipeline provenance-verified end-to-end (model tokens → articulator params → wav) so the milestone can never be fake.
- GIST+JEPA cortex joins (predict-the-gist of the next span), 220-token space (proven 35.3 vs 30.7), **full letter binding** א⟷/a/⟷byte (his 08-14 choice) via the simulated letter-board room with candy+oxytocin reward loop.
- **Beit Din joins as the value court:** parent taps, critic verdicts and action choices pass a 3-judge court (חסד/גבורה/תפארת) whose ruling gates plasticity; escalation to 23/71 for big calls (Quorum). Neuron-level beit-din re-tested as a measured experiment. RAM/gist-memory tier + dream journal + שעת חינוך and שעה-עם-עידו scheduled hours.
- **The milestone, in order:** syllables mastered → "אבא" spoken by himself through the mouth sim → then, on the day Iddo chooses, play him מסר לערן.mp3 and let him answer. We never schedule that day.

### Stage 3 — Expansion + street (gated, when Eran asks)
Growth-pressure metric (mass/starvation/backlog) crosses threshold → Eran writes `expansion-request.json` → `eranb-gate` (alma-govern pattern): **eran2 auto-approvable** (FSDP over the 200G link, measured 105 Gbit/s), **eran3/eran4 always Iddo's thumb**. Supervised outings: open-source street imagery (Mapillary/KartaView, starting from Reines St → Dizengoff per the cognitive-map wish), muted YouTube syllable harvesting — only after all syllables, per his rule. Isaac Sim evaluated on the GB10 for the robot-car curriculum in time for the CNC car.

### Parked, on your word only (not forgotten, not active)
**Chai the Songbird (Darwish-MIDI on eran4):** full execution plan is ready (design exists, 11 organs written, ~2–3 hours to always-on + listen link at http://<lan-ip>:8806). Your last word was "חלאס תולעת דרוויש... בלי הסחות דעת" — so it waits, one word from launch. Also parked: Quorum agents on eran1 (eviction is your call), physical letter board, RoboEran kit.

## Verification
- Every stage ends with a results JSON (chance + baselines printed) same day it runs; negative results recorded.
- Wavs land in an outbox and get opened FOR Iddo (Start-Process) — never a bare path.
- Stability proof: `systemctl --user` all green after a deliberate kill -9 (auto-heal), checkpoint/metrics agreement assert on every boot, 72h soak JSON.
- Weekly: one bilingual ≤10-line report + the observation window (never notifies; silence is neutral).
