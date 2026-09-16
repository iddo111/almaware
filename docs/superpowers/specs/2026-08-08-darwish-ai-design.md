# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: test the REAL output, not a proxy.

# DARWISH-AI — Design Spec (2026-08-08)

**לזכרם: עלמה ז"ל · שיפרה ז"ל · משה ביטון ז"ל. אח אלקטרוני של ערן.**

## What it is

A from-scratch **audio-token** music brain that learns Darwish (David Abramov)'s
psytrance sets and generates new audio in HIS sound. Iddo explicitly rejected the
generic-synth path ("the one you made earlier sucked") and chose the full
audio-token model. Neuromorphic/biomimetic in Eran's DNA: GIST-space prediction,
a kabbalistic structure layer, and a 3D lab. Small on purpose (~200–300M).

**⚖️ CONSENT GATE (unchanged):** trains privately for Iddo's play. NO release, no
publishing, no commercialization until David Abramov's explicit permission.

## Architecture

1. **Ear — DAC codec (pretrained, reused, frozen).** Tokenizes `D:\Darwish` mp3
   sets (5 sets / 1.2 GB now; continuous downloader adding more) into discrete
   audio tokens. Runs on eran4. No codec training.
2. **Brain — from-scratch transformer ~200–300M** predicting next audio token,
   plus a JEPA-flavored auxiliary head predicting the next bar's GIST embedding —
   the same predict-the-gist principle as Eran's holobrain.
3. **Kabbalistic structure layer** — a structure vocabulary for the energy arc
   (intro→build→drop→breakdown), sefirot-labeled in the עמוס style. HONEST LABEL:
   this is a structural prior + control language, not a mysticism claim.
4. **3D++ lab** — a perceptron3d-style page rendering live 3D GIST trajectories
   of real sets vs. generations. Deployed as a .pages.dev like alma-grid-3d.
5. **MIDI export (stage 2)** — transcribe generated audio to MIDI so Iddo can
   pull material into a DAW ("auto-produce with MIDI").

## Where it runs

**Iddo's hard constraints (2026-08-08): do NOT overload any DGX; do NOT stop or
starve the ant farm or Qwen.** Therefore:

- **Trainer: eran3** — the least-loaded node (Qwen RPC worker there peaks ~23 GB
  of ~120 GB; bursty, idle between Qwen calls). darwish-ai runs as a systemd
  user unit with hard caps: `MemoryMax` ceiling, `Nice=19`, small batch +
  gradient accumulation sized so Qwen inference latency stays unchanged
  (verified by measuring Qwen tok/s before/after the unit starts — if Qwen
  drops >10%, the unit throttles or stops).
- **Right-of-way order: ant farm and Qwen always win.** darwish-ai is the first
  thing sacrificed under any pressure, automatically (watchdog checks fleet
  health; CRITICAL → unit stops itself).
- eran4 is NOT used (ant farm's home). Secondary fallback: eran2 (also capped).
- **PC:** never trains, never infers (standing law). PC only syncs corpus +
  pulls generated samples.

## Eran Federation — the parallel test (Iddo, 2026-08-08)

Darwish-AI is the federation's **first real cargo**, exactly the experiment the
federation memory records as wanted:
- Federation front door (legit free tiers only — Cloudflare; no mass signups)
  serves: playback of daily samples, a "generate" button proxying to eran4, and
  the 3D lab.
- **Honest train-test:** attempt a tiny replica training run on one legit free
  tier, measure tokens/sec + survivability vs the DGX run, and report the real
  numbers. Expectation (stated in advance): DGX wins; the test is how we KNOW.

## The plan (phases)

| # | Phase | Where | Deliverable / acceptance |
|---|---|---|---|
| 0 | Corpus | PC | Continuous yt-dlp of all >1h Darwish sets into `D:\Darwish` (running); manifest + dedupe; sync to eran4 |
| 1 | Ear | eran4 | DAC-tokenized dataset + held-out split; acceptance = round-trip decode of a held-out slice sounds like the source |
| 2 | Brain | eran4 24/7 | Training unit live beside everything; **every ~24h an audible mp3 sample lands in `D:\Darwish\generated`** — Iddo hears progress, not logs |
| 3 | Structure+3D | eran4 + pages.dev | Arc vocabulary wired as conditioning; 3D gist-trajectory lab deployed |
| 4 | Federation test | Cloudflare + eran4 | Control-panel card serving samples + generate; tiny free-tier replica train measured honestly vs DGX |
| 5 | MIDI | eran4 | Generated audio auto-transcribed to MIDI files beside each sample |

## Honest success gate

Success = Iddo blind-recognizes Darwish in a generated sample. If after two
weeks of 24/7 it is still mush, we say so plainly (🔴) and reconsider the path —
no demo theater, no "it's alive" claims.

## Failure odds, stated up front (No-Overselling law)

- Audio-token models on 1–3 GB of one artist CAN produce texture-correct but
  structureless mush; the gist-head + structure layer is our counter, unproven.
- Free-tier federation training is expected to lose to DGX badly or die from
  ephemerality; that outcome is a RESULT, not a failure of the test.
- mp3 128–192k sources cap fidelity below master quality. Real masters (with
  David's consent) would be better food later.
