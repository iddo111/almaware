# 🪟 BROKEN WINDOWS LAW: verify the REAL output (audio you can hear), never a proxy.

# DARWISH-AI Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A from-scratch audio-token LM (~200–300M) that learns Darwish's psytrance sets on eran3 and drops an audible generated mp3 into `D:\Darwish\generated` daily — doubling as the dress-rehearsal for Eran's vocal-cortex audio pipeline.

**Architecture:** Frozen pretrained DAC codec tokenizes mp3 sets → compact GPT-style next-token transformer with a JEPA-flavored gist auxiliary head → capped 24/7 systemd training on eran3 → daily sampler decodes tokens back to mp3 and ships to the PC.

**Tech Stack:** Python 3 + PyTorch on eran3 (DGX GB10, aarch64), `descript-audio-codec`, ffmpeg, systemd user units, SSH/scp from PC (PowerShell scheduled pull).

## Global Constraints

- **No torch on the PC — training AND inference happen on eran3 only** (standing law).
- **No overload; Qwen + ant farm have right-of-way** (Iddo 2026-08-08): unit runs `Nice=19`, `MemoryMax=40G`; Qwen tok/s measured before/after; >10% drop → stop the unit.
- eran4 is not touched. Fallback node: eran2 (same caps).
- **Consent gate:** private play only; no release/publish until David Abramov's permission.
- Reach eran3 as: `ssh -o BatchMode=yes eran3@<tailnet-host>` (verified 2026-08-08).
- Corpus on PC: `D:\Darwish\*.mp3` (growing via background yt-dlp; skip `_download.log`, `.downloaded.txt`).
- Scope of THIS plan = Tasks 1–7 (corpus→ear→brain→daily sample). Structure layer, 3D lab, federation test, MIDI export = follow-up plans.

---

### Task 1: Repo scaffold + charter

**Files:**
- Create: `D:\CLAUDE\darwish-ai\README.md` (charter: what/why, consent gate, Eran-voice dress-rehearsal note, node policy)
- Create: `D:\CLAUDE\darwish-ai\remote\` (all code that ships to eran3 lives here)
- Create: `D:\CLAUDE\darwish-ai\sync_corpus.ps1`

**Interfaces:**
- Produces: repo root `D:\CLAUDE\darwish-ai` used by every later task; remote code dir convention `~/darwish-ai/{code,corpus,tokens,ckpt,generated}` on eran3.

- [ ] **Step 1:** Write README.md with the Broken-Windows banner, the consent gate, the no-overload rules, and the eran3 layout table.
- [ ] **Step 2:** `git add darwish-ai/README.md && git commit -m "darwish-ai: charter + scaffold"`

### Task 2: Corpus manifest + sync PC→eran3

**Files:**
- Create: `D:\CLAUDE\darwish-ai\sync_corpus.ps1`

**Interfaces:**
- Consumes: `D:\Darwish\*.mp3`
- Produces: `eran3:~/darwish-ai/corpus/*.mp3` + `corpus_manifest.json` (name, bytes, sha256) — Task 4 reads this manifest.

- [ ] **Step 1:** Write `sync_corpus.ps1`: hash each local mp3 (SHA256), build `corpus_manifest.json`, `scp` only files missing on eran3 (compare via `ssh ... sha256sum`).
- [ ] **Step 2:** Run it. Expected: 5+ files land in `eran3:~/darwish-ai/corpus`, manifest lists them.
- [ ] **Step 3:** Verify REAL: `ssh eran3 "ls -la ~/darwish-ai/corpus | head; du -sh ~/darwish-ai/corpus"` shows ≥1.2 GB.
- [ ] **Step 4:** Commit.

### Task 3: eran3 environment + DAC round-trip smoke test (EAR gate)

**Files:**
- Create: `D:\CLAUDE\darwish-ai\remote\ear_smoke.py`

**Interfaces:**
- Produces: python venv `~/darwish-ai/venv` with torch+descript-audio-codec; proof file `roundtrip.mp3`.

- [ ] **Step 1:** `ssh eran3 "python3 -c 'import torch; print(torch.__version__, torch.cuda.is_available())'"` — Expected: version + True. If torch missing: `python3 -m venv ~/darwish-ai/venv && pip install torch descript-audio-codec soundfile`.
- [ ] **Step 2:** `pip install descript-audio-codec soundfile` into the venv; ffmpeg present check.
- [ ] **Step 3:** Write `ear_smoke.py`: load 44.1k DAC weights, take 10 s from one corpus mp3 (ffmpeg → wav), encode→tokens→decode→`roundtrip.mp3`; print tokens/sec + token shape.
- [ ] **Step 4:** Run it on eran3, scp `roundtrip.mp3` to `D:\Darwish\generated\_ear_smoke.mp3`, **play it for Iddo** (`Start-Process`). ACCEPTANCE = it sounds like the source to human ears.
- [ ] **Step 5:** Commit.

### Task 4: Full tokenization + heldout split

**Files:**
- Create: `D:\CLAUDE\darwish-ai\remote\tokenize_corpus.py`

**Interfaces:**
- Consumes: `~/darwish-ai/corpus/*.mp3`, `corpus_manifest.json`
- Produces: `~/darwish-ai/tokens/<sha16>.npy` (int16 array [n_codebooks, T]) + `tokens/index.json` `{file, sha, n_tokens, split}` with `split: "heldout"` for the newest set + a random 5% of 30 s windows; Task 5/6 read `index.json`.

- [ ] **Step 1:** Write `tokenize_corpus.py` (chunked ffmpeg decode → DAC encode → npy append; resumable by sha).
- [ ] **Step 2:** Run under `nice -n 19` inside tmux; log to `~/darwish-ai/tokenize.log`.
- [ ] **Step 3:** Verify: `index.json` counts ≈ corpus duration × token rate; heldout marked; spot-decode one shard back to audio.
- [ ] **Step 4:** Commit.

### Task 5: Model — compact token LM + gist head

**Files:**
- Create: `D:\CLAUDE\darwish-ai\remote\model.py`
- Test: `D:\CLAUDE\darwish-ai\remote\test_model.py`

**Interfaces:**
- Produces: `DarwishLM(vocab, n_layer=20, d=1024, n_head=16, n_codebooks)` → forward(tokens) → (next-token logits, gist_pred); `gist_loss` = cosine loss vs mean-pooled embedding of the NEXT bar's tokens. Task 6 imports `DarwishLM` and `loss_fn(batch)`.

- [ ] **Step 1:** Write `test_model.py`: random token batch [B,K,T] → forward → logits shape [B,K,T,vocab]; loss_fn returns finite scalar; param count printed 150M–350M.
- [ ] **Step 2:** Run test on eran3 — Expected: FAIL (no model.py).
- [ ] **Step 3:** Write `model.py` (decoder-only transformer, RoPE, flattened-codebook interleave, gist head = linear on last-bar hidden mean).
- [ ] **Step 4:** Run test — Expected: PASS, params in range.
- [ ] **Step 5:** Commit.

### Task 6: Trainer + capped systemd unit + Qwen guard

**Files:**
- Create: `D:\CLAUDE\darwish-ai\remote\train.py`
- Create: `D:\CLAUDE\darwish-ai\remote\qwen_guard.sh`
- Create: `D:\CLAUDE\darwish-ai\remote\darwish-brain.service`

**Interfaces:**
- Consumes: `tokens/index.json`, `DarwishLM`
- Produces: `~/darwish-ai/ckpt/latest.pt` (resumable: model, opt, step); `train.log` lines `step=N loss=X gist=Y heldout=Z`; systemd unit `darwish-brain` (user).

- [ ] **Step 1:** Write `train.py`: AdamW, cosine+warmup, grad-accum to effective batch that fits ≤35 GB, heldout eval every 2000 steps, checkpoint every 1000, auto-resume.
- [ ] **Step 2:** Baseline Qwen: from PC run 3× timed generations against `<lan-ip>:8080`, record tok/s median in `darwish-ai/qwen_baseline.txt`.
- [ ] **Step 3:** Write `darwish-brain.service`: `Nice=19`, `MemoryMax=40G`, `Restart=always`, venv python. `systemctl --user enable --now`, linger on.
- [ ] **Step 4:** Re-measure Qwen tok/s during training. ACCEPTANCE: drop ≤10% of baseline; else lower batch or stop and record the honest number.
- [ ] **Step 5:** Write `qwen_guard.sh` + systemd timer (15 min): curl eran1 health + timed 16-token gen; if fail/slow → `systemctl --user stop darwish-brain` + log reason.
- [ ] **Step 6:** Verify loss falls over first 2000 steps (log excerpt in commit message). Commit.

### Task 7: Daily audible sample → PC

**Files:**
- Create: `D:\CLAUDE\darwish-ai\remote\sample.py`
- Create: `D:\CLAUDE\darwish-ai\remote\darwish-sample.timer` (+ service)
- Create: `D:\CLAUDE\darwish-ai\pull_samples.ps1` (+ Windows scheduled task `Darwish-Sample-Pull`)

**Interfaces:**
- Consumes: `ckpt/latest.pt`, DAC decode
- Produces: `eran3:~/darwish-ai/generated/YYYYMMDD-HHMM-stepN.mp3` (60–90 s, temp 0.9 top-p 0.95) → pulled to `D:\Darwish\generated\` daily.

- [ ] **Step 1:** Write `sample.py` (prompt = 5 s heldout seed → generate 60–90 s → DAC decode → ffmpeg mp3 with step number in metadata).
- [ ] **Step 2:** systemd timer daily 07:00 on eran3; run once NOW manually.
- [ ] **Step 3:** `pull_samples.ps1` scp-pulls new files; register Windows task 08:00 daily.
- [ ] **Step 4:** Play the first sample for Iddo (`Start-Process`). Expect noise/mush at step ~0 — SAY SO (honesty gate); the point is the daily trendline.
- [ ] **Step 5:** Commit + RAMCHAT post (unit live, sample path, guard active).

---

## Self-review notes

- Spec coverage: Tasks 1–7 cover corpus→ear→brain→sample (spec phases 0–2). Spec phases 3–5 (structure/3D, federation, MIDI) deliberately deferred to follow-up plans — recorded in Global Constraints.
- Right-of-way + no-overload encoded as measurable gates (Task 6 steps 2/4/5), not vibes.
- Every acceptance is a REAL output a human can hear or a number that can be pasted.
