#!/usr/bin/env bash
# ============================================================================
#  dist-mac/run.sh — macOS launcher for the ALMAWARE Hebrew mic
#
#  This is the macOS distribution entry point. It REUSES the same engine and
#  loop as Windows/Linux — it does NOT fork the codebase:
#     ../voice_input_xplat.py   the cross-platform always-on dictation loop
#     ../mic.py                 capture + VAD (pure sounddevice, cross-platform)
#     ../transcribe.py          STT shim -> shared ../../hebrew-voice/hebrew_stt.py
#     ../backends/mac.py        typing / paste / focus / undo via AppleScript
#     ../config.json (+ ../config.mac.json override)
#
#  It sets up a self-contained venv under ./.venv-mac, installs CPU deps,
#  wires the shared hebrew_stt engine onto the venv path, forces the mac
#  backend + CPU, then launches. Re-run any time; setup steps are idempotent.
#
#  USAGE
#     ./run.sh                 first-run setup + launch (always-on VAD)
#     ./run.sh --setup         set up the venv + deps only, do not launch
#     ./run.sh --no-enter      dictate without auto-pressing Return
#     ./run.sh --ptt           push-to-talk (needs `keyboard` + extra perms)
#     ./run.sh --config <p>    use an explicit config override file
#     extra flags are passed straight through to voice_input_xplat.py
#
#  ONE-TIME macOS PERMISSIONS (REQUIRED — typing/mic are blocked without them):
#     System Settings > Privacy & Security > Microphone     -> enable your Terminal
#     System Settings > Privacy & Security > Accessibility  -> enable your Terminal
#     (or the packaged .app, if you build one — see README_MAC.md)
#
#  לזכרה של עלמה ז״ל · ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

# ── locate myself + the voice-input core (one dir up) ────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$(cd "$HERE/.." && pwd)"
HEBREW_VOICE="$(cd "$CORE/../hebrew-voice" 2>/dev/null && pwd || true)"
VENV="$HERE/.venv-mac"
PY="$VENV/bin/python"
ENTRY="$CORE/voice_input_xplat.py"

echo "== ALMAWARE Hebrew mic — macOS =="
echo "   dist        : $HERE"
echo "   core        : $CORE"
echo "   hebrew-voice: ${HEBREW_VOICE:-<NOT FOUND — STT engine missing!>}"

if [ ! -f "$ENTRY" ]; then
  echo "ERROR: cross-platform entry not found at $ENTRY"
  echo "       This launcher expects to live in voice-input/dist-mac/ next to the core."
  exit 1
fi

# ── 1. python3 present? ──────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found.  Install with:  brew install python   (or python.org)"
  exit 1
fi
echo "   python      : $(command -v python3)  ($(python3 -V 2>&1))"

# ── 2. optional native helpers (best-effort; the app degrades without them) ──
#    cliclick = more robust keystrokes than pure AppleScript (optional)
#    pbcopy/pbpaste ship with macOS already; coreutils is NOT required.
if command -v brew >/dev/null 2>&1; then
  if ! command -v cliclick >/dev/null 2>&1; then
    echo "== (optional) installing cliclick for more robust typing =="
    brew install cliclick || echo "   cliclick install skipped (System Events still works)"
  fi
else
  echo "NOTE: Homebrew not found — skipping optional cliclick. Core dictation still works via AppleScript/System Events."
fi

# ── 3. venv + python deps (CPU-only; faster-whisper uses the CTranslate2 CPU wheel) ──
if [ ! -x "$PY" ]; then
  echo "== creating venv $VENV =="
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip wheel >/dev/null

if [ -f "$HERE/requirements-mac.txt" ]; then
  echo "== installing python deps from requirements-mac.txt =="
  pip install -U -r "$HERE/requirements-mac.txt"
else
  echo "== installing python deps (faster-whisper, sounddevice, …) =="
  pip install -U faster-whisper sounddevice soundfile numpy pyperclip
fi

# ── 4. wire the shared STT engine onto the venv path (so `import hebrew_stt` works) ──
if [ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ]; then
  SP="$(python -c 'import site;print(site.getsitepackages()[0])')"
  echo "$HEBREW_VOICE" > "$SP/hebrew_stt.pth"
  echo "== hebrew_stt wired: $SP/hebrew_stt.pth -> $HEBREW_VOICE =="
else
  echo "WARNING: ../../hebrew-voice/hebrew_stt.py not found."
  echo "         Copy the hebrew-voice folder so it sits next to voice-input,"
  echo "         or export HEBREW_VOICE=/path/to/hebrew-voice before running."
fi

# ── 5. setup-only? ───────────────────────────────────────────────────────────
for a in "$@"; do
  if [ "$a" = "--setup" ]; then
    echo "== setup complete (--setup): not launching =="
    echo "   To run:  ./run.sh"
    exit 0
  fi
done

# ── 6. launch (force mac backend + CPU; per-OS config.mac.json auto-applies) ──
echo "== launching always-on Hebrew mic (macOS, CPU) =="
echo "   First run downloads the STT model, then it is cached under ~/.cache/huggingface."
echo "   Quit with Ctrl+C."
export VOICEINPUT_BACKEND=mac
exec python "$ENTRY" --cpu "$@"
