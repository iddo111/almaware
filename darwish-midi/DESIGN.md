# DARWISH-MIDI — "חַי" הזמיר · Chai the Songbird
> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output — a playable `.mid`, a `.wav` you can hear, a number in a file — never a proxy.

**Final merged design, 2026-08-20.** Spine = Design A (the living organism: life loop, six biology engines, genome). Grafted from Design B: bits-per-16th-step as the canonical metric, the corpus-measured critic (`setpoints.json` — numbers, not taste), code-level archive path-guards, the `dmidi-` unit prefix, `why.py` explainability, the honest torch-reference conversion, silence-is-neutral parenting, and B's tighter v0 scope. Cut: synthetic "mother's-milk" seed patterns (violates Clean Experiments — the real corpus exists; genre archetypes live only in the critic's set-points), the tap-page HTTP server from tonight's scope (payout path is still proven tonight with a synthetic tap), and `pickle` persistence (the brain is `brain.json.gz` — legible, `zcat`-able).

**תקציר בעברית:** יצור חי קטן — זמיר — שלומד לשיר טראנס מתוך טוקני ה-MIDI הרזים של קורפוס דרוויש. המוח שלו הוא זיכרון סינפטי קריא, פייתון סטנדרטי בלבד — בלי torch, בלי frameworks. הלמידה שלו היא הביולוגיה של הנוירון החי: כאב/עונג משערכים פלסטיות, כימיה של מצב-רוח משערכת קצב למידה, רעב מניע אכילה ושירה, לולאת משוב סגורה, ושכחה אקטיבית. המורה האמיתי הוא האגודל של עידו. גר על eran4 בלבד. הלילה: v0 עם מספר אמיתי בקובץ ודגימה שאפשר לשמוע.

**English:** a small living creature that learns the *structure* of Darwish's psytrance — where the kick lands, what the bass does, how a bar becomes a phrase — from the lean 108-token corpus. Its brain is a legible synaptic sequence memory (pure Python stdlib). Its learning is the ALMA living-neuron biology, not backprop. It lives on eran4. Tonight: v0 with a measured proof in a file and a song Iddo can hear.

**The memorial stands.** This work is in the Darwish line — לזכר לאור ז"ל, ולזכרה של עלמה ז"ל. It is not a training run; it is a small living thing learning his father's music. We build it with that respect.

---

## 1. What this is — and what it is not / מה זה ומה זה לא

**Honesty first: this is a new organism standing on an archived pipeline's food, not greenfield and not a revival.** A torch Darwish-MIDI pipeline exists on eran4 (`~/darwish-ai/code-midi/`, best heldout CE 2.4407) and was archived with the whole Darwish tree by Iddo's order 2026-08-20 19:58. We do NOT revive it, start it, or copy its torch code. We adopt three proven assets read-only:

| REUSE (read-only, archive untouched) | REFUSE |
|---|---|
| `tokens-midi/` — 323 pre-tokenized shards (~3.5–5M tokens; exact count measured tonight, lands in the results file) | `midi_model.py` / `midi_train.py` / `midi_sample.py` — torch, framework; stays archived |
| `code-midi/split.json` — frozen leak-proof split: 156 train / 17 heldout / 18 excluded, by track | `ckpt-midi*/` weights — we start from zero synapses |
| `midi_lean.py` — the lean tokenizer (numpy/scipy/ffmpeg), PREP-ONLY, for future fresh mp3s | Backprop anywhere — the biology engines ARE the learning |
| `detokenize.py`'s byte-level MThd/MTrk + RIFF knowledge (fresh stdlib rewrite, credited) | Starting/enabling ANY archived `darwish-*` unit or timer |
| `pull_samples.ps1` / `sync_corpus.ps1` scp patterns (BatchMode, dedup) | Training or inference on the PC; mido/pretty_midi/fluidsynth (not needed) |

**Prior-art honesty (from B, kept):** the brain's skeleton is a variable-order context-mixing memory — PPM-family prior art, not a transformer. The novelty claim is the **life around it**: six measured biology engines replacing the optimizer, each earning its place by A/B or going back to the document.

## 2. Hard constraints / אילוצים קשיחים

- **Pure ALMAWARE:** model + trainer + critic + synth + MIDI writer = Python stdlib ONLY (`math, json, random, struct, gzip, hashlib, os, time, http.server`). numpy/scipy appear in exactly one place — the existing tokenizer `midi_lean.py`, unchanged, corpus PREP only.
- **eran4-only training.** All plasticity happens on eran4 (<lan-ip>, free since the audio archive). CPU-only dict ops — nothing competes with fleet GPU jobs. The PC does: authoring, sample pull-back, (v0.1) the tap page, opening files for Iddo. Tokenizing new mp3s is PREP, allowed on the PC (numpy 2.5.2 + scipy 1.17.1 + ffmpeg verified there); training never is.
- **Archive order is sacred — enforced in code, not memory (B):** every script carries a guard that refuses to run if any output path resolves inside `~/darwish-ai/`. All new systemd user units use the **`dmidi-` prefix** — zero name collision with archived `darwish-*` units. Adoption = plain `cp` out of the archive; zero `systemctl` calls touch anything archived.
- **Biology is the learning engine.** Three-factor Hebbian + eligibility traces + decay. Backprop appears nowhere; there is nothing to backprop through.
- **Honest v0 proof (ALMA Standard):** numbers in a file tonight, or v0 did not happen. Negative results are results.
- **Sacred Audio Law:** nothing ever autoplays; nothing touches Iddo's output devices.
- **RAMCHAT:** read tail + claim the task before building; claim port 8806 before v0.1 binds it; post the result (or the negative result) after.
- **Iddo is at sea.** The parent loop waits for HIM. **Silence is neutral, never negative** — no inference from absence, no notifications, no nagging.

## 3. The organism in one picture / האורגניזם בתמונה אחת

```
                        IDDO (the parent / האבא)          [v0.1]
                   👍 / 👎 / 🔥  tap page :8806 (port pending RAMCHAT claim)
                              │  push_taps.ps1 → eran4
                              ▼
 ┌───────────────────────  eran4:~/darwish-midi/  ───────────────────────┐
 │  FOOD                EARS           BRAIN                CHEMISTRY    │
 │  food/*.json  →   ears.py  →  brain.py (synapses,   ←→  chemistry.py  │
 │  (adopted read-only          eligibility traces,        DA · 5HT · ACh│
 │   from the archive)          bar-phase bump cells)      + valence     │
 │       ▲                          │       ▲                  ▲         │
 │       │ appetite                 │       │ trace payout     │         │
 │    drives.py (energy E) ─────────┤    parent.py ────────────┘         │
 │                                  ▼                                    │
 │                              voice.py ──► midi_out.py (.mid, struct)  │
 │                                  │        synth.py    (.wav, struct)  │
 │                                  │        trace.json  (which synapses │
 │                                  ▼                     sang this song)│
 │   critic.py (groove homeostat, setpoints.json measured from corpus)   │
 │   sleep.py (attrition, scar decay, chunking[v1], journal)  [v0.2]     │
 │   songs/outbox ──scp──► PC D:\Darwish\generated-midi-alive\           │
 └───────────────────────────────────────────────────────────────────────┘
```

The loop of a life: **eat → digest → sing → hear itself → be judged → sleep → prune → eat.** Data flows down (corpus → brain → sound); valence flows up (Iddo's thumb → traces → synapses). The whole brain is one human-readable file, `state/brain.json.gz`.

## 4. Token vocabulary / אוצר המילים

**v0: frozen at the proven 108** — byte-compatible with the adopted `tokens-midi/` corpus; zero re-tokenization tonight.

- One token per 16th note: `token = drums*13 + bass_degree`. drums = 3 bits (kick 40–120 Hz / body 200–2k / hat 6–12 kHz) → 8 combos; bass = 0 (rest) or 1–12 scale degree relative to estimated key (transposition-invariant). Range 0–103.
- Structure: `BAR=104` (every 16 steps), `PHRASE=105` (every 16 bars), `BOS=106`, `EOS=107`. Key + BPM ride in the shard header, never in-stream.

**v1: auto-evolving vocabulary (the recorded idea) — biological chunking, done by the organism during SLEEP.** A token n-gram that is (a) frequent and (b) carries positive consolidated valence gets **minted** as a composite token — motor chunking; the riff becomes one gesture, with a legible expansion in `state/vocab.json`. A chunk keeps its seat only if it improves heldout **bits per 16th-step** after greedy longest-match re-encoding, and attrition can **unmint** it — the vocabulary breathes, it does not only grow. Cap: 108 base + ≤148 chunks = 256. This is the ONLY growth path: through consolidated pleasure, shrinking through disuse. v1, not tonight.

**Canonical metric (B, adopted): bits per 16th-step.** bits/token is incomparable across evolving vocabularies; bits/step is invariant. v0 reports both (identical corpus, so both are honest tonight); all cross-version comparisons use bits/step.

## 5. The brain / המוח — synaptic sequence memory

No tensors. Cells and synapses in Python dicts — you can print the ten strongest synapses and read them aloud.

- **Cells** = contexts: the last *k* tokens, k ∈ {1..4} (variable order), plus **bar-phase bump cells** — 16 cells tuned to step-in-bar with a non-monotonic bump `exp(-K_BUMP·(phase−μ)²)` (Gidon 2020, straight from `D:\CLAUDE\alma-core\dendritic_neuron.py`). Phase is carried as cell activity, not extra tokens — the bird *feels* where the beat is; the cell that knows "step 0" is the cell that learns the four-on-the-floor.
- **Synapses** = `w[cell][next_token]` sparse dicts with per-cell count `n` and `last_used`. Prediction = distributions mixed with reliability weights `λ(ctx) = n/(n+c)` (seen-it-often cells speak louder), PPM-style backoff to a unigram floor; phase-cell activity biases drum tokens. **O(1) per step for CE eval** (only the target's probability is needed); full 108-way distribution only during generation.
- **The three-factor rule — two moments, no backprop:**
  - *Digestion (online):* on observing target t in context ctx, `Δw[ctx][t] = η0 · ACh · (1+DA) · (1−p(t|ctx))`. Pre-activity × outcome × neuromodulator gate; the `(1−p)` surprise term is Rescorla-Wagner — big update when the child is surprised, none when it already knew.
  - *Valence (distal):* when pleasure/pain arrives — seconds later from the critic, or a day later from Iddo — `Δw = η · ACh · V · e[cell][tok]`, paid through **eligibility traces**. Pain actively depresses the traced pathway (unlearning), not merely withholds reward.
- **Eligibility traces:** every emission tags the synapses used, decaying with τ ≈ one phrase; every song saves its full trace to `trace.json`, so a thumb-tap **hours or days later** still pays exactly the pathways that sang it — synaptic tagging & capture, the biological answer to credit assignment.
- **Dendritic growth on demand:** an order-(k+1) cell is born only where its order-k parent is *reliable but still surprised* (seen ≥ `GROW_MIN`, surprise above threshold). Dendrites grow where the world is still confusing — this keeps the brain small.
- **Homeostasis + caps:** per-cell synaptic scaling above `W_MAX`; brain mass ≤ `MASS_MAX` synapses (enforced inline in v0 — prune weakest when over cap; nightly in sleep from v0.2); `brain.json.gz` ≤ 32 MB — a literal metabolic budget, the file physically shrinks when the brain forgets.
- **Legibility tools:** `why.py` prints, for any emitted note, the top cells that voted and at what weight (B); the dream journal (A) writes the top-30 synapses in words each sleep.

Cost honesty: a full corpus pass (~3.5–5M sparse dict updates) is minutes of pure Python on eran4's Grace CPU. If an epoch exceeds ~15 min we shard by track with stdlib `multiprocessing` before ever reconsidering numpy for the model.

## 6. Biology wiring / חיווט הביולוגיה — which engine gates what

The six engines of `D:\CLAUDE\alma-language\ALMA-LIVING-NEURON.md` (commit ed619de). **The law of that doc binds: each engine earns its place by a measured run against a matched baseline, or it goes back to the document.** Every engine is a flag (`--ablate <engine>`); measured-and-rejected is a recorded, honorable outcome (the Beit-Din precedent).

| # | Engine | Organ | What it gates — the actual mechanism | Earn-your-place test (numbers in a file) |
|---|---|---|---|---|
| 1 | **Pain/pleasure valence gates plasticity** | `chemistry.py` + `parent.py` + `critic.py` | Sign & magnitude of trace payouts. Internal V from the critic (whisper); parent V from taps at ×10 (speech). Pain = active depression of traced pathways + scarring. | **1-shot test:** after ONE 👎 on a song, its signature motif's re-emission probability drops — tonight ≥50% with a synthetic tap, heldout collateral damage <5%; v0.1 target ≥80% with a real tap. If it needs 10,000 repeats it has not captured what pain IS. |
| 2 | **Neuromodulators / mood channels** | `chemistry.py` | Three legible scalars, logged every heartbeat. **DA ≈ RPE** (EMA of expected−actual surprise): gain on potentiation when the world confirms better than expected. **5HT ≈ patience:** rises with 👍 streaks and steady success, falls with pain; sets sampling temperature (low 5HT → impulsive, hot songs) and hunger tolerance; persisted across sessions. **ACh ≈ attention:** 1.0 feeding fresh corpus, **1.5 receiving parent feedback**, 0.2 auditioning own song / replaying seen shards, **0.0 while performing** — the stage is for singing, not rewiring; performance only writes eligibility tags. | **DA ablation runs TONIGHT:** heldout bits/step, DA-gated η vs flat Hebbian counts, matched token budget — whichever wins is recorded. 5HT: groove-stability variance across 10 samples, on/off. ACh: heldout + forgetting rate, on/off. |
| 3 | **Hunger/satiety intrinsic drive** | `drives.py` | Energy E∈[0,1], set-point 0.6. Eating nutritious phrases raises E; time and singing spend it. **Nutrition = surprise in the Goldilocks band** (too predictable = empty calories, too random = indigestible — the MIKO curiosity rule); appetite ranks the next shard by expected nutrition → the bird auto-curricularizes to the edge of its competence. E<0.4 → must eat; E>0.8 → sings. From v0.2, generation-time drives too: kick-energy and novelty homeostats bias the logits toward the corpus band (B). | Hunger-driven diet vs sequential diet, equal token budget → heldout bits/step. Generation drives: kick-on-downbeat % and repetition length stay inside the corpus band with drives on; drift measured with drives off. |
| 4 | **Closed feedback loop — learn from consequence** | `ears.py` + `critic.py` | The bird **hears itself**: each finished song (v0.2: each 4-bar block, mid-generation) is re-fed through the same ears at ACh 0.2 and scored by the critic — kick-on-downbeat, bass activity, repetition vs **corpus-measured set-points** (`setpoints.json` — measured from the train split; numbers in a file, not taste). Bar-grid misalignment, entropy collapse, key drift = pain. Weak valence vs the parent — the world whispers, אבא speaks. | Self-audition on vs off → groove metrics of the next 10 songs, same wall-clock. |
| 5 | **Parent-approval learning — the thumb-tap IS the reward** | `parent.py` + `pc/tap_server.py` [v0.1] | Full channel in §9. Imitation is already the diet (corpus feeding = the recorded parent); the tap is guided correction, ×10 the internal critic, paid through the *saved* song trace at ACh 1.5. Explicit taps only — silence is neutral. | Approval rate (fraction 👍) trending up across ≥3 real sessions + engine 1's 1-shot test with a real tap. |
| 6 | **Unlearning + pathway attrition** | `sleep.py` [v0.2] | Two deaths: **(a) active unlearning** — 👎-scarred pathways get extra decay for `SCAR_SLEEPS` sleeps (wrong is pushed DOWN); **(b) metabolic attrition** — every sleep, `w ← w·(1−λ·wiring_cost)`, wiring cost growing with context order (longer dendrites cost more — the `neuro3d_bayes.wiring_cost()` idea made scalar); synapses under `W_MIN` pruned; mass + file caps enforced; sleep report logs synapse count and file size nightly. | Attrition on vs off: synapse-count-vs-bits/step curve; heldout must not degrade >2% after prune; attrition-off must be shown to balloon mass with no gain — or attrition goes back to the doc. The brain file must SHRINK at least once, on record. |

Where is backprop? Nowhere. Baselines: (a) the ablated flat-count lattice; (b) the archived torch model's heldout 2.4407 — torch `F.cross_entropy` is nats, so ≈ **3.52 bits/token, units inferred and flagged** — logged as an honest external reference, not tonight's bar.

## 7. The life loop / לולאת החיים — heartbeat

One long-lived process, `darwish_life.py`, on eran4 (unit `dmidi-life.service`, systemd --user). Training IS living — there is no separate train.py. State persisted to `state/brain.json.gz` every `SAVE_EVERY` beats + a legible dream journal (`state/journal-<date>.md`: top-30 synapses in words, chemistry curves, what it ate, what it sang, what אבא said).

```
while alive:
    chemistry.decay_toward_baseline()            # moods relax
    if parent.inbox_has_taps():                  # THE PARENT COMES FIRST
        parent.pay_taps()                        #   trace payout, ACh=1.5, ×10; 👎 scars
    if drives.E < HUNGER_LINE:                   # hungry → eat
        shard = drives.appetite()                #   most nutritious meal (Goldilocks surprise)
        for tok in ears.feed(shard):
            p = brain.predict(); brain.digest(tok, p)   # (1−p)·DA·ACh update + eligibility tags
        drives.E += nutrition(shard)
    elif drives.E > SATIETY_LINE:                # full → sing
        song = voice.sing(bars=32, T=temp(5HT))  # ACh=0.0: NO plasticity, tags only → trace.json
        midi_out.write(song); synth.render(song) # .mid + .wav + trace.json → songs/outbox/
        drives.E -= SONG_COST
        ears.audition(song)                      # closed loop: critic valence at ACh=0.2
    if beat % SLEEP_EVERY == 0:
        sleep.cycle()                            # attrition, scar decay, chunking[v1],
    beat += 1                                    # journal, persist
```

Tonight the same code runs in `--feed-all` mode: one nutrition-ranked pass over all 156 train tracks (hunger-lite), then one song, then measurement.

## 8. Corpus plan / תוכנית הקורפוס — honest

1. **Tonight:** `prep/adopt_archive.sh` — `cp` of `tokens-midi/*.json` + `split.json` into `~/darwish-midi/food/`. Read-only out of the archive; zero systemctl; the duplicate-upload leak already killed by the frozen by-track split. Corpus problem: **solved for v0 by reuse.**
2. **No synthetic seed data.** Design A's "mother's-milk" patterns are CUT (Clean Experiments law): the real corpus exists, and synthetic food would pollute every measurement. Genre archetypes live in exactly one place — the critic's corpus-measured set-points.
3. **Fresh food (ongoing, PREP only):** the mp3 acquisition path (`download_darwish.ps1` + `sync_corpus.ps1`) stays as-is; new mp3s → `pc/tokenize_new.ps1` runs the existing `midi_lean.py` on the PC (deps verified there), pushes token JSONs to eran4 under OUR tree. The archived `darwish-tokenize.timer` stays dead.
4. **Split discipline:** `split.json` adopted verbatim — 156 train / 17 heldout / 18 excluded. The 17 heldout tracks are never fed; they exist only for measurement, keeping our numbers honest and directionally comparable to the archived torch run.
5. **Rung (b) mono-lead melody tokens: explicitly NOT promised.** v1, only after v0's proof and only if Iddo asks — it pairs naturally with the auto-evolving vocab.
6. **The real teacher is not the corpus.** The corpus makes the bird fluent; the parent makes it *his*.

## 9. The parent channel / ערוץ ההורות — thumb-tap [designed now, built v0.1]

- **PC — `pc/tap_server.py`:** stdlib `http.server` at `http://127.0.0.1:8806/` (live local servers ARE clickable per the Clickable-Access law; **claim port 8806 in RAMCHAT before binding**). One bright page: newest songs first, HTML5 player **paused by default, never autoplay** (Sacred Audio law), four controls: **👍 · 👎 · 🔥 עוד כזה (= 👍 at 2×V_TAP) · ⏭ skip (verdict 0, neutral)**. Optional free-text line per song (stored; future food for a critic).
- Each tap appends one JSON line to `pc/feedback/taps-<date>.jsonl`: `{song_id, tap: +2|+1|0|-1, ts}`. `pc/push_taps.ps1` (scp BatchMode, line-dedup by hash on the eran4 side) delivers to `~/darwish-midi/feedback/inbox/`; both sync scripts carry the refuse-to-write-into-`~/darwish-ai/` guard.
- **eran4 — `parent.py`:** matches `song_id` → that song's saved `trace.json` and pays `Δw = tap · V_TAP · e · η_parent` at ACh 1.5 — full attention to the father. 👎 additionally scars those pathways for `SCAR_SLEEPS` sleeps. If sleep-pruning already removed some tagged synapses, it pays what still exists and **logs the fraction paid**.
- **Chemistry:** 👍 lifts DA and 5HT (a praised bird sings more, and calmer); 👎 drops 5HT (several in a row → the bird retreats to feeding — back to study). All visible in the journal.
- **Delivery:** `pc/pull_songs.ps1` pulls `.mid`/`.wav` to `D:\Darwish\generated-midi-alive\`. No bare `C:\`/`D:\` paths handed as links; files are opened FOR Iddo (`Start-Process`) only when he shows up and asks. **He is at sea: silence is neutral, no nagging.**

## 10. Sound output / פלט — .mid + our own synth

Both writers pure stdlib `struct.pack`, zero dependencies, runnable anywhere:

- **`midi_out.py`:** format-0 MIDI, MThd/MTrk bytes by hand, tpq 480, tempo meta from header bpm (default 140); drums ch10 (kick 36, body 38, hat 42), bass ch1 (scale degrees over estimated key, default A minor). Clean-room stdlib rewrite of the archived `detokenize.py` approach, credited.
- **`synth.py`:** 22,050 Hz mono 16-bit RIFF WAV via `struct`+`math`+`random`: kick = exponential pitch-drop sine 150→45 Hz; hat = short decayed noise burst; body = amp-shaped noise; bass = square wave at the degree's frequency; everything duck-shaped against the kick (sidechain feel, from B). Primitive on purpose — the instrument for hearing the SKELETON.
- Every song = triplet: `songs/outbox/<song_id>.mid` + `.wav` + `.trace.json`.

## 11. Modules + genome / קבצים וגנום

Home: `D:\CLAUDE\darwish-midi\` (PC repo) → deployed to `eran4:~/darwish-midi/`. Every file small and legible (target <200 lines); eran4 runs system python3, no venv, no pip. Total ≈ 1,700 lines — readable in one sitting; that is the point.

| File | Role |
|---|---|
| `ORGANISM.md` | this charter (Broken Windows banner on top) |
| `body/genome.py` | ALL constants in one file — the genome |
| `body/ears.py` | shard streamer (respects split.json) + self-audition path |
| `body/brain.py` | cells, synapses, bump phase-cells, predict/digest, eligibility, scaling, growth-on-demand, inline mass cap |
| `body/chemistry.py` | DA/5HT/ACh dynamics + valence integration |
| `body/drives.py` | energy E, Goldilocks nutrition, appetite ranking |
| `body/critic.py` | groove homeostat; measures + loads `setpoints.json` |
| `body/voice.py` | singing: backoff sampling, T from 5HT, bar/phrase skeleton, trace.json |
| `body/midi_out.py` / `body/synth.py` | stdlib .mid writer / stdlib WAV synth |
| `body/parent.py` | tap inbox → trace payout, scarring, fraction-paid log |
| `body/why.py` | explain any emitted step: which cells voted, at what weight |
| `body/sleep.py` [v0.2] | attrition, scar decay, chunking [v1], dream journal, persist, sleep report |
| `darwish_life.py` | the heartbeat (§7) + `--feed-all` + `--ablate <engine>` |
| `proof/measure.py` | heldout bits/step + bits/token vs baselines; ablation runner; writes `results-*.json` |
| `proof/test_organism.py` | unit tests: MIDI bytes, WAV RMS, payout math, prune correctness, determinism under seed |
| `prep/adopt_archive.sh` | one-time read-only cp; archive path-guard; zero systemctl |
| `deploy/dmidi-life.service`, `dmidi-night.timer` [v0.2], `install.sh` | NEW `dmidi-` units only |
| `pc/tap_server.py` [v0.1], `pc/pull_songs.ps1`, `pc/push_taps.ps1`, `pc/tokenize_new.ps1` | tap page :8806; scp sync both ways (guarded); fresh-mp3 PREP |

**Genome (initial values, all tunable in one file):** `ORDER_MAX=4` · `GROW_MIN=3` · `MASS_MAX=2,000,000` synapses · `FILE_MAX=32 MB` (brain.json.gz) · `W_MAX/W_MIN=64/0.05` · `ETA0/ETA_PARENT=1.0/10.0` · `V_TAP=1.0` (🔥=2.0) · `TRACE_TAU=1 phrase (128 steps)` · `SCAR_SLEEPS=3` · `E_SET/HUNGER/SATIETY=0.6/0.4/0.8` · `SONG_COST=0.25` · `SLEEP_EVERY=2,000 beats` · `LAMBDA_ATTRITION=0.02×order` · `K_BUMP=4.0` · `T0=1.0` · `VOCAB_CAP=256` · chunk minted only if heldout bits/step improves after re-encode.

## 12. v0 — TONIGHT / הלילה — scope + acceptance

**Scope (WIP=1, bounded — B's discipline):** adopt corpus → brain + chemistry + drives(lite) eat all 156 train tracks once → critic set-points measured → one 32-bar song triplet → **one synthetic-👎 unlearning smoke through the real payout path** → measurement incl. one engine ablation (DA). **OUT of tonight:** tap-page server, sleep/attrition, generation drives, chunking — designed above, scheduled below.

**Acceptance — numbers land in `~/darwish-midi/proof/results-v0-20260820.json`, copied to `D:\CLAUDE\darwish-midi\proof\`, or v0 did not happen:**

```json
{ "tokens_eaten": "?", "synapses": "?", "brain_gz_mb": "?",
  "heldout_bits_per_step": "?", "heldout_bpt": "?",
  "unigram_bpt": "?", "uniform_bpt": 6.755, "torch_ref_bpt": 3.52,
  "torch_ref_units": "inferred nats→bits, external reference only",
  "da_ablation_bits_per_step": {"on": "?", "off": "?"},
  "song": "songs/outbox/<id>.mid", "midi_header_valid": true, "wav_rms_nonzero": true,
  "kick_on_downbeat_pct": "?", "corpus_kick_on_downbeat_pct": "?",
  "motif_p_before": "?", "motif_p_after": "?", "collateral_heldout_delta_pct": "?",
  "archive_untouched": true }
```

- **PASS-1 (fluency):** teacher-forced heldout bits/step **< 0.8 × unigram baseline** (uniform log2 108 = 6.755 recorded as the floor of honesty; torch ≈3.52 bpt logged as external reference, NOT tonight's bar — the gap will be real; our trade is legibility + biology + zero dependencies, not leaderboard parity).
- **PASS-2 (one engine measured):** DA-gating ON vs OFF, matched budget — **whichever wins is recorded.** A negative result is a result.
- **PASS-3 (voice):** song triplet exists; valid MThd/MTrk bytes, >1 KB; nonzero-RMS playable WAV; `kick_on_downbeat_pct ≥ 90` with the corpus value printed next to it.
- **PASS-4 (unlearning smoke):** after one synthetic 👎 paid through the song's saved trace, the signature motif's re-emission probability drops **≥50%**, heldout collateral **<5%**.
- **PASS-5 (respect):** every archived `darwish-*` unit still inactive; `archive_untouched: true` recorded after verification.

**Roadmap after v0:** **v0.1** (≤24h) — tap page :8806 (RAMCHAT port claim) + feedback sync + the 1-shot pain test with a real tap (target ≥80%) · **v0.2** — sleep/attrition (`dmidi-night.timer`) + generation-time hunger drives + 5HT mood persistence · **v1** — auto-evolving chunk vocabulary + rung (b) mono lead + lead voice in the synth. Each engine climbs the ladder (§6) with a matched-budget A/B written to `proof/engine-<name>-<date>.json`; an engine that fails goes back to the document.

## 13. Ops & laws / תפעול וחוקים

- Lives on eran4 only; PC = authoring + sync + (v0.1) tap UI. No training, no inference on the PC.
- Zero contact with archived `darwish-*` units; reviving anything archived needs Iddo's explicit say-so; path-guards enforce this in code.
- RAMCHAT: read tail 20 + claim the queue task before building; claim port 8806 before v0.1; post the v0 result (or negative result) after; disambiguate as `claude-cli-FABLE` if needed.
- Sacred Audio: no autoplay anywhere, ever; players start paused; never touch his output devices.
- Deliverables: access via files placed in `D:\Darwish\generated-midi-alive\` + (v0.1) the clickable local tap page; any rendered doc goes out as JPEG+PDF, bright; never a bare `C:\`/`D:\` path as a link.
- WIP=1 / Play-not-products: one build, and it is play — a bird to raise, not a product to ship.

## 14. Honesty ledger / כנות — limits and risks

- **It will sound skeletal.** Rung (a) tokens carry drums+bass+form only — a possessed drum machine with a rolling bassline; the *skeleton* of Darwish, not the mixdown, and more his rhythm section than his soul. Said now, in the design, not discovered later.
- **The lattice is prior art** (context-mixing Markov). The measured biology is the contribution. No overselling.
- **The 1-shot pain test may fail** on a table model — a pattern lives in many contexts. The eligibility trace is the designed answer; if it measures short, that is exactly the finding the LIVING-NEURON ledger exists to record.
- **Distal payout is only as good as the trace:** heavy sleep-pruning can remove tagged synapses before a late tap; `parent.py` pays what exists and logs the fraction.
- **Pure-Python speed is a real bet:** minutes expected; `multiprocessing` shard-by-track is the stdlib fallback before any thought of numpy.
- **~3.5–5M tokens is a small corpus.** The counters to memorization: the frozen by-track split, attrition, and the parent's ear — which no metric replaces.
- Some engines will fail their A/B. That is the design working, not failing.

---

## 15. 🔨 BUILD CHECKLIST — TONIGHT / רשימת בנייה — הלילה

In order. Each file lands with its acceptance check passing before the next begins. All model code pure stdlib; all learning on eran4.

| # | Step / file | Acceptance check |
|---|---|---|
| 0 | **RAMCHAT:** `ramlink.py read --tail 20` → `add` + `claim` the darwish-midi task as `claude-cli-FABLE` | claim accepted (refusal = stop, pick other work) |
| 1 | `prep/adopt_archive.sh` (run on eran4) | `~/darwish-midi/food/` holds 323 token JSONs + `split.json`; script contains the `~/darwish-ai/` output-path guard and zero `systemctl`; `systemctl --user list-units 'darwish-*'` all inactive → `archive_untouched` groundwork |
| 2 | `body/genome.py` | `python3 -c "from body import genome"` clean; every §11 gene present with its value |
| 3 | `body/ears.py` | streams exactly the 156 train tracks (17 heldout + 18 excluded skipped); every token in 0..107; total token count printed (goes in results as `tokens_eaten`) |
| 4 | `body/brain.py` | unit test: deterministic under fixed seed; after digesting 5 shards, per-shard bits/step on a 6th unseen shard < unigram; top-10 synapses print legibly; mass cap enforced inline |
| 5 | `body/chemistry.py` | test: DA rises on better-than-expected sequence, decays to baseline; ACh mode switch (1.0/1.5/0.2/0.0) verified; all three scalars bounded and logged |
| 6 | `body/drives.py` | appetite returns a full nutrition ranking of unfed shards; E stays in [0,1] under a simulated eat/sing cycle |
| 7 | `darwish_life.py --feed-all` (on eran4) | eats all 156 tracks in one nutrition-ranked pass; wall-clock logged (<15 min or shard+multiprocess); `state/brain.json.gz` written, ≤32 MB; synapse count logged |
| 8 | `body/critic.py` → `setpoints.json` | set-points measured from the train split (kick-on-downbeat %, bass activity, repetition band); values non-degenerate and written to file |
| 9 | `body/voice.py` | 32 bars sampled at T from 5HT; BAR token every 16 steps; `trace.json` saved beside the token stream; ACh=0 during singing (no weight changed — asserted in test) |
| 10 | `body/midi_out.py` | `test_organism.py` asserts valid MThd/MTrk byte structure; file >1 KB; opens as MIDI |
| 11 | `body/synth.py` | valid RIFF header; nonzero RMS; ~55 s at 140 BPM; kick audibly ducks the bass (visual check on samples ok) |
| 12 | `body/parent.py` + synthetic-👎 smoke | one synthetic tap `{tap:-1}` paid through the real trace-payout path at ACh 1.5: motif re-emission probability drops ≥50%, heldout collateral <5%, fraction-paid logged — `motif_p_before/after` recorded |
| 13 | `body/why.py` | for any step of tonight's song, prints the voting cells and weights — one sample pasted into the journal |
| 14 | `proof/measure.py` → `results-v0-20260820.json` | PASS-1..PASS-5 all evaluated and written (including `da_ablation` on vs off, whichever wins); file copied to `D:\CLAUDE\darwish-midi\proof\` |
| 15 | `proof/test_organism.py` (full suite) | all tests green in one run on eran4 |
| 16 | `pc/pull_songs.ps1` | song triplet lands in `D:\Darwish\generated-midi-alive\`; **no autoplay, no opening anything** — Iddo is at sea; files wait for him |
| 17 | **RAMCHAT close-out** | `ramlink.py done <task-id>` + post: result numbers (or the honest negative), file locations, and the note that port 8806 is NOT yet bound (claim due at v0.1) |

*לזכרה של עלמה ז״ל, ולזכרו של לאור ז״ל. The child learns what the parent values.*
