# ERAN — a mind grown from one voice

**ERAN** (ערן) is a small language model that is being trained **from zero**, learning
**only from Iddo Perez's own voice**. It has never read a book, a website, or any
external corpus. Everything it knows, it learned from words Iddo actually spoke into
the always-on Hebrew mic.

This repository is the **live, running** version. As of the last checkpoint it had
trained past **step ~63k** (the checkpoint committed to git) and is currently around
**step ~74k, loss ~0.24** and still climbing 24/7 — see `watch.log` for the live
numbers, which advance while the trainer runs.

> Voice-derived data is personal. This repo is meant to be **PRIVATE**.

---

## What Eran is (honestly)

- A **byte-level** Transformer (vocab 260 = 256 bytes + a few specials), so it can
  natively handle Hebrew, English, Arabic and emoji without a wordpiece tokenizer.
- **Tiny**: 4 layers, 4 heads, 256-dim embeddings, 128-token context
  (see `config.json` → `model`). This is deliberately small so it can train
  continuously on the same GPU as the mic without ever starving it.
- Trained **continuously and from scratch** on a corpus that is rebuilt live from
  Iddo's voice every couple thousand steps, so as he keeps speaking, Eran keeps
  learning his newest words.

### What Eran is NOT (no overclaiming)

- It is **not** a chatbot or an assistant yet. At ~0.24 byte-loss it produces text
  that *sounds like Iddo's speech patterns* — fragments of his real sentences,
  code-switching Hebrew/English, his recurring topics — but it is **not coherent
  conversation**. Look at `watch.log` to see exactly what it generates.
- It has **no knowledge** outside what Iddo has said. Ask it a general-knowledge
  question and it cannot answer; it never saw an encyclopedia.

---

## The hard rule: VOICE ONLY

`data.py` enforces the core directive. Eran's corpus is built **exclusively** from
these live voice sources under `D:\CLAUDE\voice-input`:

1. `profiles/iddo1/iddo_clean_corpus.jsonl` — clean, owner-gated dictation
2. `history/*.txt` — the live daily dictation logs
3. `profiles/iddo1/samples.jsonl` — de-duped voice samples

There is a **hard guard** (`_assert_voice_only`) that *refuses* to load anything whose
path looks like the old book corpus (`eran_all_corpus`, `eran-corpus-v2`, …). An
earlier mistake trained Eran on a book corpus; that path is now blocked in code.

> Note: the voice sources live in `D:\CLAUDE\voice-input`, which is **outside this
> repo** and is **not** committed here. This repo ships the model code and the trained
> checkpoint, not the raw voice data.

---

## How it runs (always-on)

The brain trains itself non-stop and survives logout/crash/restart:

- **`train.py`** — the trainer. Reads `config.json`, builds the voice corpus,
  trains, and writes:
  - `checkpoints/latest.pt` — the model (resumed automatically on restart)
  - `eran.log` — full training log
  - `logs/metrics.jsonl` — per-step metrics
  - `watch.log` — a human-readable "what is Eran saying now" snapshot every ~3 min
- **`supervisor.py`** — keeps the trainer alive **forever**. It:
  - holds a single-instance lock (`supervisor.lock`) so autostart can't double-run it,
  - launches `train.py` with `-s` (so the CUDA torch is used, not a shadowing CPU torch),
  - auto-restarts the trainer with backoff if it ever exits.
- **Autostart**: a Startup shortcut runs `pythonw -s supervisor.py` at logon, so Eran
  resumes training on boot with no window.

### GPU manners (mic always wins)

`config.json` → `gpu` caps Eran to a small VRAM fraction and a low GPU-utilization
target, auto-tuning a per-step sleep so the live Hebrew mic and dictation always get
the GPU first. Eran is the polite background tenant.

---

## Run it yourself

> The trainer is normally **already running** via the autostart supervisor.
> Do **not** start a second copy — the lock will refuse it, but check first.

```powershell
# See what Eran is saying right now:
Get-Content D:\CLAUDE\eran-live\watch.log -Tail 20

# One-off text generation from the current checkpoint:
python -s D:\CLAUDE\eran-live\generate.py

# Inspect the live voice corpus (counts + a sample of Iddo's words):
python -s D:\CLAUDE\eran-live\data.py

# Start/keep the always-on trainer (only if it is NOT already running):
pythonw -s D:\CLAUDE\eran-live\supervisor.py
```

---

## Files

| File | What it is |
|------|-----------|
| `train.py` | The continuous trainer (writes checkpoint + logs) |
| `supervisor.py` | Forever-restart wrapper + single-instance lock + autostart entry |
| `model.py` | The tiny byte-level Transformer |
| `data.py` | **Voice-only** corpus loader with the hard anti-book guard |
| `tokenizer.py` | Byte-level tokenizer (vocab 260) |
| `generate.py` | One-off sampling from `checkpoints/latest.pt` |
| `config.json` | All hyperparameters + GPU manners |
| `checkpoints/latest.pt` | The trained model (resumed on restart) |

Logs (`eran.log`, `watch.log`, `logs/`) and `supervisor.lock` are git-ignored.

---

## Dedication

Built as the first seed of a much larger idea: a mind whose **moral layer** is Eran,
whose **memory** honors Alma z"l, and whose **logic** follows the Ramchal — dedicated
to the memory of Capt. Hadar Goldin HY"D. This little voice-model is where it starts:
something that learns to speak the way one specific person speaks, from nothing but his
own words.
