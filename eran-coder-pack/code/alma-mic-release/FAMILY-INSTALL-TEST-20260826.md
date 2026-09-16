# FAMILY-INSTALL-TEST — 2026-08-26

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Cold-install debug of **alma-mic-release** for the family download.
Environment: fresh Python 3.12 venv + empty Hugging Face cache + `CUDA_VISIBLE_DEVICES=""`
(CPU forced) — simulating a plain Windows laptop with no GPU, no servers, no LoRA.
(Windows Sandbox is not available on this machine — feature not installed.)

## The STT truth · האמת על הזיהוי
**Fully standalone. Nothing phones home.** Recognition = faster-whisper running
**locally** with `ivrit-ai/whisper-large-v3-turbo-ct2` (Hebrew-finetuned).
The only network use: a one-time ~1.5 GB model download from Hugging Face on first run.
Optional extras (Grok CLI brain, DictaLM `dicta_url`) are OFF/empty by default and fail
gracefully with a Hebrew message. No 127.0.0.1 ports, no eran fleet, no tokens anywhere.

## What was broken → fixed · מה היה שבור → תוקן
| # | Bug | Fix |
|---|---|---|
| 1 | `faster-whisper` **missing from requirements.txt** — README install crashed at model load (`ModuleNotFoundError`), family sees "⚠️ שגיאה" | added; dropped unused `requests` |
| 2 | README said "set your own STT endpoint" — **no such thing exists**; no Python version, no model-download warning | truthful README: local STT, Python 3.10–3.12, ~1.5 GB first-run download, measured speed table |
| 3 | Cough filter (uncommitted) matched repeated chars on **whitespace-stripped** text: "too old"→"tooold", "free entry"→"freeentry" → real speech silently dropped | per-word check, 1–2-word utterances only; unit-checked |
| 4 | `language:"auto"` cost **2–3 full decodes per utterance** (detect + beam-5 whole-clip probes): 0.4s clip → 35–48s CPU | probes now greedy over ≤10s; family default `language:"he"` (single decode) |
| 5 | `config.example.json` disagreed with `config.py` (different model, `device:""`), `auto_enter:true` (auto-sends messages!), `collect_corpus:true` (silently records speaker to disk) | example matches code; `auto_enter:false`; `collect_corpus:false` (opt-in); `type_output:true` default (the app's promise) |
| 6 | `test_hallucination.py` / `test_lang.py` crashed without the private `voice_corpus`/`testset.json` (scrubbed from release) | degrade gracefully / clear message |
| 7 | No way to verify STT without a microphone | new `transcribe_file.py` (+ console exe in the MSI) |
| 8 | GUI showed only "טוען מודל…" during the 1.5 GB first download — looks frozen | message now says a download is happening |
| 9 | No `.gitignore` — `config.json`/logs/corpus could leak into the repo | added |
| 10 | **MSI crashed on launch**: frozen `config.py` wrote `config.json` INSIDE `lib\library.zip` (`FileNotFoundError` before the window opened) — the exact פדיחה scenario | `app_dir()`: frozen → next to the exe (per-user LocalAppData install, writable); source → next to the code |

## Cold-install steps that now work verbatim
1. Install Python 3.10–3.12 from python.org ("Add to PATH" checked).
2. `pip install -r requirements.txt` → **verified**: installs sounddevice, numpy, faster-whisper(+ctranslate2, onnxruntime, av, huggingface-hub, tokenizers).
3. `python gui.py` (or the zip's `INSTALL.cmd` → `RUN.cmd`).
4. First run downloads the model once (~1.6 GB measured; a few minutes), then everything is offline.
5. No-mic sanity check: `python transcribe_file.py --cpu some.wav`.

## Measured results (CPU, this desktop; family laptop ≈ 1.5–2.5× slower)
- Cold first run: download+load **136 s** (model ready, cpu/int8). Warm load: **24–37 s**.
- Real Hebrew quality (booth clip): `אבא` → **'אבא'** ✔ (twice).
- Real Hebrew quality (33.5 s קפה-קלוד monologue): full, sensible Hebrew — memristor-brain
  passage transcribed correctly incl. technical terms; "server motors" kept in English. ✔
- Timing, `language:"he"`: short utterance **~17–19 s**, 33.5 s clip **26.5 s (×0.79 — faster than realtime)**.
- Timing, `language:"auto"`: short **~42–48 s**, long **×1.64** → hence the `"he"` default.
- Beam 1 vs 5 on CPU: identical text, identical time → the 30 s-window encoder pass dominates; beam left at 5.
- Smaller models tested and REJECTED: whisper-small = degraded Hebrew ("אהב" for "אבא"), whisper-medium = worse + hallucinated English + 250 s. ivrit-ai turbo stays the only engine.
- VAD unit tests: PASS (burst detection + silence).
- Anti-hallucination proof (`test_hallucination.py`, CPU): **PASS** — all 6 non-speech
  classes (silence/noise/tones/hum) → empty, guards active (`rms_gate` + decode guards).
- Soak (`soak_test.py 40`, CPU): **PASS** — RSS 1389→1309 MB, growth −80 MB, no leak.
- **Frozen MSI payload tested end-to-end** (`AlmawareTranscribeFile.exe --cpu`, no mic):
  model loads 34 s warm, `אבא` ✔, full cafe monologue ✔, 33.5 s → 25.2 s (×0.75).
- Mic-opening tests (`test_audio.py`, `test_stt.py`, `test_typer.py`) intentionally NOT run
  on this machine (Sacred Audio law — no device may be claimed here). They need one
  run on a real family laptop.

**Bottom line for family / השורה התחתונה:** on a laptop **without** NVIDIA GPU the app
works and the Hebrew is good, but each sentence takes **tens of seconds** to appear.
With any NVIDIA GPU it is instant. Set expectations accordingly before sending the link.

## Remaining gaps · פערים שנשארו
- **Not yet run on a genuinely foreign Windows machine** (this simulation covers deps,
  model download, CPU decode — not OEM audio-driver weirdness or SmartScreen on the MSI).
- MSI is unsigned → Windows SmartScreen will warn; family must click "More info → Run anyway".
- End-to-end mic→type flow untestable here (audio law); needs one live check on a family laptop.
- Hosting/distribution decision still open (per the task: packaging only, no upload).

## Artifacts · תוצרים
- `dist\Almaware Voice Typer-1.0.0-win64.msi` (98.5 MB, cx_Freeze, per-user install,
  Start-Menu shortcut; includes `AlmawareTranscribeFile.exe` for no-mic support checks).
- `dist\AlmawareVoiceTyper-1.0.0-source.zip` (repo @ HEAD incl. `INSTALL.cmd`/`RUN.cmd`
  — the fallback path for anyone with Python).
- Model is NOT inside either artifact — downloaded once on first run (~1.6 GB).
