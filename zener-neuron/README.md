> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ZENER NEURON — POC (2026-09-10)

One zener in breakdown → LM358 ×101 → ESP32 GPIO34 → PC keeps every raw sample. An LED blinks from the bit.
Real quantum (tunnelling/avalanche) noise, **no hash, no whitening** — whitening would erase exactly the small bias phase 2 looks for.

- `BUILD.html` — the build sheet (rendered to JPEG+PDF on the Desktop as `ZENER-NEURON-POC-20260910`).
- `firmware/zener_neuron/zener_neuron.ino` — 15 lines, the ESP32 only reads and reports.
- `pc/logger.py` — `python logger.py COM5 --cond test` · `--fake --seconds 3` self-test (verified 19:12: 984 vN bits, ones 0.48).

## Acceptance (POC)
1. Input grounded: std 1–3 LSB (ADC alone).  2. Zener in: std ≥ 20 LSB — that jump is the neuron.
3. Monobit 0.499–0.501 after 1M vN bits.  4. `bits-*.bin` does not zip below 99%.

## Phase 2 — the honest question (NOT before the four checks pass)
Three conditions, not two: **A** Iddo asking · **B** Iddo present, silent · **C** empty room.
A vs B is the claim. B vs C measures what a warm body, a phone and mains do to a zener.
30 × 20-min sessions per condition, files under random IDs, mapping sealed until scoring is done.
Preregistered prediction: A = B = C. Any difference → check temperature first.

## The medium is the message — architecture
`dice-organ`: ONE service serving hardware bits + metadata (source, temperature, health), logging every bit forever.
Fallback to PRNG is **labelled** (`source=prng-fallback`), never silent. ALMA gets a `dice` primitive (real stochastic neuron).
ERAN gets it at the margin: babble targets and tie-breaks. Boltzmann board and Ouija are clients of the organ, not owners.
No port bound yet — claim in RAMCHAT before binding.

## DREAM BOARD — הלוח החולם (built 2026-09-10 20:41, verified live)
`dream/dream_board.py` → **http://127.0.0.1:8864/** (`dream/RUN-DREAM.cmd`, or launch.json `dream-board`). Port 8864 claimed in RAMCHAT.
- 32×32 visible board; hidden = **one-of-22 softmax over Hebrew letters + "dark"** (one-of-K hidden units, a standard Boltzmann construction).
- Weights **prescribed** from thin DavidCLM letter templates (Hebbian). **Not trained — no training on the PC.**
  v→h: `s_k = (2|v∩T_k| − |v|)/|T_k|` (1 on a match, <0 on noise), logit `γ(s−θ)`; h→v: centred template ×α + visible bias (board stays dark with no letter).
- In darkness a spontaneous spike lights one letter, and **the bit source picks which letter**. The dice choose. Nothing else does.
- Every coin is labelled: `zener` (ESP32 serial) / `prng` / `file`; hardware short → `prng-fallback`, shown in red. Never silent.
- Every sweep → `dream/logs/dream-<stamp>.csv` (time, source, temp, best letter, score). This is the phase-2 data: zener vs PRNG letter statistics, scored blind.
- `python dream_board.py --selftest` — hold 20/20 for א מ ש, 9 distinct letters dreamed from noise in 1500 sweeps, fallback verified loud.
- The RTX is **not** used: torch on this PC is CPU-only, and a 1024×22 board needs no GPU. The bottleneck is bits (zener ≈ 2.5 kbit/s ≈ one sweep per 3 s).
