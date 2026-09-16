# ALMA-MIC — the foundation-stone PC microphone (ALMAWARE-pure)

**LAW (2026-06-28):** 100% ours. **Every line written by our fleet, from scratch.**
ZERO external app/project code. ZERO collage. ZERO patch-on-patch. Models (recognition)
are the model-not-app category (like Eran) and are allowed; *application code is all ours.*

This replaces the old `voice-input` collage entirely. The old one is archived, not patched.

## Why (the failure we're ending)
The old mic = a glued collage (mic + hebrew_stt + transcribe + supervisor + iqbrainz +
corrector + learner + ducking + a pile of patches) → crashed every ~2 days, unreliable,
"not serious." A foundation stone cannot be a collage.

## Clean architecture — small, single-responsibility, each unit TESTED
- `audio.py`   — OS microphone capture (our code over the OS audio API; no third-party app).
- `vad.py`     — our voice-activity detection (speech onset/offset).
- `stt.py`     — thin adapter that calls a RECOGNITION MODEL (ours: Eran-audio; or a model like
                 faster-whisper — a *model*, not external app code). One clear interface.
- `router.py`  — resolve the target window (our code).
- `typer.py`   — type into the window (our SendInput via ctypes).
- `app.py`     — the one clear pipeline: capture → VAD → STT → route → type. No fallback spaghetti.
- `config.py`  — one small config.
- `tests/`     — a test per module; the pipeline is provable, not "seems to work."

## Reliability principles (the whole point)
1. ONE clear pipeline. No hidden fallback layers.
2. We OWN every resource lifecycle (open/close audio, free buffers) → **no memory leaks by design.**
3. Graceful shutdown (clean stop, no orphan GPU/audio handles).
4. Tested before trusted (verify-3x).
5. The mic ALWAYS wins (alma-govern integration is OURS too).

## Build stages — ALL DONE & VERIFIED (2026-06-28, autonomous overnight run)
1. ✅ `audio.py` + `test_audio.py` — host-API-aware live-device pick (BRIO on WDM-KS/DirectSound), real RMS.
2. ✅ `vad.py` + `test_vad.py` — our energy VAD; detects 1 burst, no false positives on silence.
3. ✅ `stt.py` + `test_stt.py` — ivrit-ai Hebrew Whisper on **GPU** (load ~12s, transcribe ~0.2–0.6s).
4. ✅ `typer.py` + `test_typer.py` — our SendInput; Hebrew Unicode types into the focused window (round-trip proven).
5. ✅ `pipeline.py` (the one pipeline) + `gui.py` (window + ⚙ settings) + `app.py` (headless).
6. ✅ `soak_test.py` — **300 inferences, RSS flat at 878MB, +0MB growth, no crash** → the old leak is dead.

## Settings (config.py / ⚙ panel): mic · language · translate-to-English · wake-word (arm) / auto · type-into-window · model/LoRA/device
## Our Hebrew LoRA: `train_lora.py` scaffold (needs `pip install peft` + his voice data + DGX GPU; then merge→ct2→set lora_dir).

## Resolved purity decision
**Our app code (capture/VAD/pipeline/typer/GUI/config) + a recognition MODEL (ivrit-ai Whisper, model-not-app
category like Eran) + OS-audio primitive.** GPU enabled via `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` wheels
(our loader `_enable_cuda_dlls` adds them to the DLL path); first inference JITs cuDNN ~50s once, then cached.
Falls back to CPU cleanly if no GPU. Launch: Desktop `ALMA-MIC.lnk` or `pythonw gui.py`.
