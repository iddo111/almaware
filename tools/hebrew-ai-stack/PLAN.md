# Hebrew AI Stack — Plan
2026-05-23. Iddo, RTX 3070 Ti (8 GB VRAM). FOSS-first per [[prefer-open-source]].

## Goal
Excellent Hebrew (and English) voice in / voice out / local LLM, plus A70 bridge so the tablet's mic feeds either local stack OR Anthropic remote sessions.

## Hardware budget
- **GPU:** RTX 3070 Ti, 8 GB VRAM
- **Fits:** Mistral-7B / Dicta-LM Q4_K_M (~5 GB) + Whisper large-v3 turbo (~1 GB on GPU) simultaneously with headroom for TTS
- **Watch:** can't fit 13B + Whisper large simultaneously; if running both, drop to Whisper medium or quantize LLM harder

## Component picks (all FOSS, all on-device)

### 1. Speech → Text (STT)
**`faster-whisper` + `large-v3-turbo`** (already installed via pip).
- Hebrew WER ~10–13% (state-of-art for open-source Hebrew STT).
- Backend: CTranslate2, CUDA accelerated.
- For streaming/real-time: wrap in `whisper-live` or `WhisperFastApi`.
- Model size: 1.5 GB int8.

### 2. Local Hebrew LLM
**`dicta-il/dictalm2.0-instruct`** — Israeli-built, native Hebrew-tuned, 7B.
- Run via **Ollama** (easiest) — quantized Q4_K_M ≈ 4.7 GB.
- Alternative: `meta-llama/Llama-3.1-8B-Instruct` (multilingual, decent Hebrew).
- Alternative: `mistralai/Mistral-Nemo-12B-Instruct` (heavier but excellent Hebrew if you accept slower).
- All callable from any HTTP client via Ollama's REST API at `localhost:11434`.

### 3. Text → Speech (TTS)
**Piper** + Hebrew voice (`he_IL/*`).
- Already downloaded to `D:\CLAUDE\tools\piper\`.
- Voices: download from https://huggingface.co/rhasspy/piper-voices/tree/main/he/he_IL
- Real-time inference (~0.05× realtime on CPU; way faster on GPU).
- Output: WAV at 22 kHz, plays via system audio or streams to A70.

### 4. A70 mic bridge (two modes)
**Mode A: A70 mic → local PC stack**
- A70 captures audio (PWA via Web Audio API, or native app like WhisperTop)
- Streams audio chunks over Tailscale to `<tailnet-ip>:8765/audio`
- Clod-bridge feeds to faster-whisper → Hebrew text
- Text flows into local Dicta LLM OR Claude Code session window

**Mode B: A70 mic → Anthropic remote**
- A70 transcribes locally (WhisperTop / FUTO offline Hebrew model)
- POSTs text to clod-bridge `/type` endpoint
- Bridge pastes into Claude Code window → Claude responds
- (This is the existing clod-bridge flow; just need quality Hebrew STT on the A70 side)

## Build order
1. **CUDA + faster-whisper smoke test** — transcribe a Hebrew sample, measure WER. (~30 min)
2. **Install Ollama** → `ollama pull dictalm:7b-q4_K_M` (~5 GB DL). (~15 min DL)
3. **Download Piper Hebrew voice** (~100 MB). (~5 min)
4. **PoC: voice loop** — record 5s Hebrew → Whisper → Dicta reply → Piper voice out. (~1 hour)
5. **Wire to clod-bridge** — add `/audio` endpoint that accepts uploaded chunks. (~1 hour)
6. **A70 PWA upgrade** — add mic button using MediaRecorder API, sends to `/audio`. (~30 min)
7. **WhisperTop install** as offline fallback on A70 (still needs ADB pair codes from user). (~10 min)

## Latency targets
- A70 mic → text on PC: < 800 ms one-shot (chunk on silence)
- Text → Dicta reply: < 2 s for short prompt
- Text → Piper voice: < 500 ms first chunk

## What's NOT in scope here
- Training a new model from scratch (per user: "not from scratch")
- Fine-tuning Dicta (later, on user's own data, if needed)
- Multi-speaker diarization (later)
- Real-time bidirectional streaming voice call (later, Phase 2)

## Risks
- 8 GB VRAM is tight if running Whisper + Dicta + Piper concurrently. Mitigation: lazy load.
- Hebrew TTS quality varies; if Piper's `he_IL` voice is weak, fallback to Microsoft Asaf (Windows built-in Hebrew SAPI voice, decent but robotic).
- A70 PWA mic needs HTTPS for `getUserMedia` (or self-signed cert + manual trust). May need to expose clod-bridge over `https://<tailnet-ip>` with a local CA.
