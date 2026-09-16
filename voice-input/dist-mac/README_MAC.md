# Hebrew Mic — macOS build (`dist-mac/`)

Always-on Hebrew (+ multilingual) dictation for macOS. This is the **macOS
distribution** of the ALMAWARE Hebrew mic. It does **not** fork the codebase —
it reuses the same engine and dictation loop as Windows/Linux and only swaps the
OS input layer (typing/paste/focus) for a macOS one.

> לזכרה של עלמה ז״ל · ALMAWARE · iddoperez.ai

---

## TL;DR — run it

```bash
cd voice-input/dist-mac
chmod +x run.sh           # first time only
./run.sh                  # sets up a venv + deps, then launches (always-on VAD)
```

Then grant two one-time macOS permissions (see **Permissions** below) and start
talking. Quit with `Ctrl+C`.

---

## What's in this folder

| File | Purpose |
|------|---------|
| `run.sh` | **The launcher.** Self-locating; sets up `./.venv-mac`, installs deps, wires the shared STT engine, forces the mac backend + CPU, launches. |
| `requirements-mac.txt` | CPU Python deps (faster-whisper, sounddevice, …). |
| `setup_py2app.py` | Build a double-clickable **`HebrewMic.app`** (recommended packaging). |
| `build_pyinstaller.sh` | Alternative packaging into a CLI binary. |
| `mac_appkit_backend.py` | **Optional** native pyobjc/Quartz typing backend (scaffold; see below). Not active by default. |
| `README_MAC.md` | This file. |

### What it reuses from the core (treated as read-only)

```
voice-input/voice_input_xplat.py   cross-platform always-on loop (mode logic, commands, history)
voice-input/mic.py                 capture + VAD (pure sounddevice — already cross-platform)
voice-input/transcribe.py          STT shim -> shared engine
voice-input/backends/mac.py        ACTIVE mac input backend (AppleScript / System Events)
voice-input/backends/__init__.py   selects MacBackend when sys.platform == "darwin"
voice-input/config.json            base config
voice-input/config.mac.json        macOS overrides (CPU, model=small, duck off)
hebrew-voice/hebrew_stt.py         the shared faster-whisper STT engine (one dir up from voice-input)
```

---

## Dependencies

### System
- **Python 3.10+** — `brew install python` (or python.org). Python 3.12 is what
  the Windows side is pinned to and is a safe choice here too.
- **PortAudio** — usually **not** a separate install: the `sounddevice` pip wheel
  bundles PortAudio on both Intel and Apple Silicon. Only if `import sounddevice`
  fails do: `brew install portaudio && pip install --force-reinstall sounddevice`.
- **pbcopy / pbpaste** — ship with macOS; used for clipboard paste. No install.
- **cliclick** *(optional)* — `brew install cliclick` for more robust keystrokes;
  the app works without it (falls back to AppleScript System Events). `run.sh`
  offers to install it if Homebrew is present.

### Python (installed by `run.sh` into `./.venv-mac`)
From `requirements-mac.txt`:
```
faster-whisper>=1.0.3     # CTranslate2 backend — CPU wheels for Intel + arm64
sounddevice>=0.4.6        # mic capture (bundles PortAudio)
soundfile>=0.12.1
numpy>=1.26.0
pyperclip>=1.8.2          # clipboard fallback if pbcopy/pbpaste is unavailable
```
Optional extras (commented in the requirements file): `pyobjc-framework-Cocoa` +
`pyobjc-framework-Quartz` (for the native backend), `keyboard` (for `--ptt`),
`anthropic` (for the IQBrainz correction / translate layer).

### The model — `ivrit-ai`
The shared engine (`hebrew-voice/hebrew_stt.py`) is dual-model:
- **GPU path → `ivrit-ai/whisper-large-v3-turbo-ct2`** — the Hebrew fine-tune
  (~5–10% WER vs ~25% generic). There is **no CUDA on Mac**, so this path is not
  taken automatically here.
- **CPU path → `cpu_model`** — a generic faster-whisper model. `config.mac.json`
  sets `cpu_model: "small"`. The model auto-downloads from Hugging Face on first
  run and is cached under `~/.cache/huggingface/`.

To use the **ivrit-ai Hebrew model on Mac** anyway (slower on CPU, but best
Hebrew accuracy), set `cpu_model` to it in `config.mac.json`:
```json
"cpu_model": "ivrit-ai/whisper-large-v3-turbo-ct2"
```
> ⚠️ Honest caveat: `hebrew_stt.py` has a hard-coded **Windows** local snapshot
> path (`D:\CLAUDE\models\ivrit-ai\...`). On Mac that path simply doesn't exist,
> so the engine falls back to downloading from the Hugging Face id over the
> network on first load — fine, just not offline. If you want offline on Mac,
> pre-download the model and point `cpu_model` at the local snapshot dir.

---

## How to run

```bash
./run.sh                 # setup (first time) + launch, always-on VAD dictation
./run.sh --setup         # set up the venv + deps only, don't launch
./run.sh --no-enter      # dictate without auto-pressing Return
./run.sh --ptt           # push-to-talk (needs `keyboard` + extra perms — VAD is recommended on Mac)
./run.sh --config <path> # use a specific config override
```
Any extra flags pass straight through to `voice_input_xplat.py`.

`run.sh` forces `VOICEINPUT_BACKEND=mac` and `--cpu`, and `voice_input_xplat.py`
auto-merges `config.mac.json` on top of `config.json` when `sys.platform ==
"darwin"`.

### Mic selection
`config.mac.json` leaves `input_device: null` (system default) with a fallback
chain (`MacBook`, `Built-in`, `USB`, `BRIO`, `Yeti`, `Scarlett`) and a
never-use list (AirPods / Bluetooth — the BT SCO mic is historically flaky).
List devices: `python ../mic.py`. To pin a mic, set `input_device` to a substring
of its name.

### Voice commands (OS-portable subset)
Same Hebrew triggers as Windows for the portable controls: `שירי פרומפט` /
`פרומפט סוף` (prompt buffer), `שירי מהיר` / `שירי שלח` (fast buffer),
`שירי קליפבורד` (clipboard-only), `שירי בטל` (undo), `שירי סוף` / `מיקרופון`
(pause/resume), `שירי <language>` (switch language), `עבור` / "over" (force Enter).
> Window **routing by app name** (`שירי קלוד` → a specific app) is Windows-only.
> On macOS the mic types into whatever window is **focused** — which is the LKG
> Windows default behavior anyway.

---

## Permissions (one-time, REQUIRED)

macOS gates microphone and synthetic keystrokes. Without these, capture or typing
silently no-ops:

1. **System Settings → Privacy & Security → Microphone** → enable the app that
   launches the mic (your **Terminal** / **iTerm**, or `HebrewMic.app` if packaged).
2. **System Settings → Privacy & Security → Accessibility** → enable the same app.
   (Typing/paste via System Events is an "Apple Events / Accessibility" action.)

If typing does nothing, this is almost always the cause — re-check Accessibility.
You may also see a one-time "Terminal wants to control System Events" prompt;
allow it.

---

## Packaging (build a standalone app)

> Run these **on a real Mac** — you cannot cross-build a macOS app from Windows.

### Recommended: `py2app` → `HebrewMic.app`
A proper `.app` is the right shape for an always-on agent: its `Info.plist`
declares the Microphone + Accessibility usage strings, and the **bundle** (not
your Terminal) becomes the entity you grant Privacy permissions to.
```bash
cd voice-input/dist-mac
python3 -m venv .venv-build && source .venv-build/bin/activate
pip install -r requirements-mac.txt py2app
python setup_py2app.py py2app          # -> dist/HebrewMic.app
open dist/HebrewMic.app                 # first launch prompts for Mic + Accessibility
```

### Alternative: PyInstaller → CLI binary
```bash
pip install -r requirements-mac.txt pyinstaller
./build_pyinstaller.sh                  # -> dist/HebrewMic/HebrewMic
```
Simpler, but the binary requests permissions under the launching terminal's
identity rather than its own — prefer `py2app` for the always-on use case.

> Code-signing / notarization is **out of scope** here. An unsigned app runs but
> triggers Gatekeeper ("unidentified developer" → right-click → Open). For
> distribution you'd sign with a Developer ID and notarize — that needs an Apple
> Developer account and a Mac.

---

## Native pyobjc backend (optional scaffold)

`mac_appkit_backend.py` is a **scaffold** for a native typing backend using
Quartz `CGEvent` + AppKit `NSPasteboard` (mirrors the structure of
`backends/win.py` / `backends/linux.py`). It is **not active by default** — the
shipping backend is `backends/mac.py` (AppleScript), which needs no extra deps
and is what `run.sh` uses.

The native path can be sturdier for some apps and avoids spawning `osascript`
per keystroke, at the cost of a `pyobjc` dependency. Its window-list / focus /
duck methods are honest stubs that defer to the AppleScript backend; the
typing/paste/undo via CGEvent are written but **unverified on hardware**. To
make it selectable you'd add a one-line branch in `backends/__init__.py` keyed
on an env var (e.g. `VOICEINPUT_MAC_NATIVE=1`) — deliberately left undone until
it's validated on a Mac.

---

## What genuinely needs a real Mac to finish

This artifact was authored on **Windows**. The architecture, scripts, config, and
backend are complete and internally consistent, but the following can only be
**verified / finished on macOS hardware**:

1. **End-to-end smoke test** — `./run.sh` actually creating the venv, installing
   the CTranslate2/PortAudio wheels for the host arch (Intel vs Apple Silicon),
   downloading the model, capturing audio, and typing Hebrew into a focused app.
2. **AppleScript typing fidelity** — System Events `keystroke` of Hebrew/RTL text
   into real targets (Notes, Pages, browser fields, terminals) and the Cmd+V
   paste-restore dance. Quoting/escaping edge cases surface only on the OS.
3. **Permissions flow** — confirming the Microphone + Accessibility grants behave
   as documented, and the `.app` Info.plist usage strings trigger the right prompts.
4. **Native pyobjc backend** — `CGEventKeyboardSetUnicodeString` Unicode injection
   for Hebrew across apps is the main unknown; window enumeration via the
   Accessibility (AX) API is unimplemented (stubbed to AppleScript).
5. **Packaging** — `py2app` / `pyinstaller` bundling of the loose core modules
   (`mic.py`, `transcribe.py`, `backends/`) and the shared `hebrew_stt.py`, plus
   the native `ctranslate2` dylibs, almost always needs a tweak pass on the target.
6. **The `--ptt` path** — the `keyboard` library's global hotkey on macOS typically
   needs elevated permissions; VAD (always-on) is the recommended mode here.

Everything above is wired to **degrade, not crash**: missing tools/permissions log
a clear warning and the always-on loop keeps running.
