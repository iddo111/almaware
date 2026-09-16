> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Vipassana on ESP32 — Stage 1 design (one self-learning chip)

**Approved by Iddo:** approach A 2026-09-15 08:12 ("יא בייבי!"), design 08:16 ("קודם כל תתחיל את התכנון").
**Memory:** `project_vipassana_esp32_20260915`. **Research:** workflow wbx4s53cf (estimates from published ESP32-S3 benchmarks, not measured on Iddo's boards).

## Goal
A language model that feeds on its own output — the eran1 Vipassana loop — running **nonstop on one Heltec V4** (ESP32-S3, 16 MB flash, 2 MB PSRAM, OLED): generate → train on its own text + Rebbe Nachman grounding → checkpoint → repeat, surviving power loss.

## Out of scope (later stages)
Radio / ESP-NOW exchange (stage 2), 10-node tiny cloud (stage 3), drones (stage 4, needs CAAI answer in writing), Hebrew quality.

## Source mind (read-only reference)
eran1 `~/vipassana/vipass.py`, vipass.service: char-level `Embedding(110,96) → GRU(96,256,2 layers) → Linear(256,110)`, 705,454 params. Round = generate 200 chars @ TEMP 1.2 → 3 self steps (BLOCK 32, BATCH 16, Adam 3e-3) → 6 grounding steps on a random 400-char passage of `corpus.txt` (82,615 chars, Likutei Moharan, public domain) → reseed every 50 rounds → atomic checkpoint every 25 rounds. **Never modified by this project.**

## Architecture — three units

### 1. `vipass_mini.py` — reference mind (eran1, `~/vipassana-mini/`, CPU)
- Same loop, chip-sized: `Embedding(V,24) → GRU(24,64,2) → Linear(64,V)`, V = 110 (vocab copied from the live checkpoint's `itos`), 52,030 params.
- BATCH 4 (configurable 4–8), BLOCK 32, Adam 3e-3, 3 self + 6 grounding steps, reseed 50, checkpoint 25 (atomic tmp + `os.replace`, resumes round + optimizer).
- **Change 1 — incremental generation:** carry the GRU hidden state; feed only the newest char (the live code re-runs the last 32 chars per char, ~32× waste).
- **Change 2 — accumulate buffer:** ring buffer of the last 16 generations; self steps sample from buffer + newest instead of newest only (Gerstgrasser et al. 2024, arXiv 2404.01413).
- Deterministic mode (`--seed`, `--dump-golden`) exports: initial weights, one fixed batch, loss, all gradients, weights after one Adam step, and a greedy generation — in a flat binary format the C code reads.
- Runs as its own user unit `vipass-mini.service` only after golden tests pass; nice 19, CPU only, 1 thread.

### 2. `vipass.c` / `vipass.h` — the mind in C (no libraries)
- float32. Structures: `Mind` (weights), `Grads`, `Adam` (m, v, t), `Workspace` (BPTT activations sized for BATCH×BLOCK), `Ring` buffer, `Rng` (xorshift, seedable).
- Functions: `mind_init`, `forward_step` (one char, hidden in/out), `generate` (incremental, temperature sampling), `loss_and_grad` (full BPTT over BLOCK), `adam_step`, `round_run`, `ckpt_write` / `ckpt_read` (versioned header + CRC32).
- Platform shim `plat.h`: time, storage (POSIX file on Linux, LittleFS on ESP32), log, display. Same `vipass.c` compiles on eran1 (gcc, aarch64) and in the PlatformIO build.
- Memory target at BATCH 4: < 1.5 MB total (weights 0.2 MB, grads + Adam 0.6 MB, activations ~0.4 MB).

### 3. `firmware/` — Heltec V4 PlatformIO project (`D:/CLAUDE/vipassana-esp32/firmware`)
- `setup()`: mount LittleFS; `ckpt_read("/mind.ckpt")` → resume, else init from seed; load `corpus.txt` from a flash partition (memory-mapped, not copied to RAM).
- `loop()`: `round_run()`; every 25 rounds `ckpt_write` to `/mind.tmp` then rename to `/mind.ckpt`; OLED shows round, loss, last 2 lines of generated text; serial prints one status line per round.
- Task watchdog (esp_task_wdt) fed each training step; brown-out → reboot → resume.
- Region/radio untouched (no LoRa TX in stage 1).

## Data flow per round
seed/last text → `generate` 200 chars → push to ring → 3 × (`loss_and_grad` on buffer sample, `adam_step`) → 6 × (grounding passage from corpus) → stats (loss, entropy, unique-char ratio) → every 25: checkpoint → every 50: reseed → repeat.

## Error handling
| Failure | Response |
|---|---|
| Power cut / brown-out / crash | Boot resumes from last good checkpoint (round, weights, Adam, ring, rng). |
| Corrupt or partial checkpoint | CRC mismatch → keep previous `/mind.ckpt` (tmp never replaces it unless its CRC verifies after write). |
| NaN / Inf in loss or grads | Skip the update, reload last checkpoint, halve LR (floor 3e-4), log it. |
| Loop stall | Task watchdog reboot → resume. |
| Repetition collapse (unique ratio < 0.08 over 8 rounds, as eran1) | Reseed from mantra + corpus passage. |
| Flash wear | Checkpoint every 25 rounds (~12–20 min estimated); LittleFS wear levelling; estimate > 10 years. |

## Testing / acceptance (each must be shown with real output)
1. **Golden twin (eran1):** C `loss_and_grad` + `adam_step` vs PyTorch on the same weights and batch — loss and every gradient within 1e-4 relative; greedy 200-char generation identical.
2. **Checkpoint round-trip (eran1):** write → kill -9 mid-run → restart resumes the same round with bit-identical weights.
3. **C endurance (eran1):** 1,000 rounds, no NaN, memory flat.
4. **Firmware build (PC, compile only):** `pio run` succeeds; RAM/flash report under budget.
5. **On the chip:** 24 h nonstop; serial shows rounds advancing; OLED shows text.
6. **Power pull:** unplug mid-round → replug → resumes from the last checkpoint round.
7. **Measured speed on the board:** chars/s and min/round replace the research estimates.

## Constraints and laws
- No training on the PC: golden tests and endurance run on eran1; the PC only compiles and flashes.
- eran1 live jobs untouched (vipass, keshev7-kof, gpt-oss, STT fallback): mini runs nice 19, 1 thread, CPU only.
- Autosave Law satisfied on both eran1 mini and the chip.
- Flashing requires the Heltec V4 plugged in by Iddo (COM port, flashes clean per `project_lora_tdeck`).
- RAMCHAT claim before each build step; DONE posts with evidence.

## Open risks
- 52K params may never approach real Hebrew (research: eran1's 705K mind has not either).
- All speed/memory numbers are estimates until test 7.
- f32 gets no SIMD on ESP32-S3; if too slow, a later int16 fixed-point path is the lever.
