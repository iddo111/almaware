#!/usr/bin/env bash
# ============================================================================
#  run_mac.sh — always-on Hebrew mic on macOS (Intel + Apple Silicon)
#
#  PORT of the Windows hebrew-mic to macOS. Reuses the SAME engine
#  (../hebrew-voice/hebrew_stt.py), the SAME capture (mic.py) and the SAME
#  config.json, and routes typing/paste/focus through backends/mac.py
#  (AppleScript / System Events). CPU-first (no CUDA on Mac).
#
#  First run sets up a venv + deps + wires hebrew_stt onto the path, then
#  launches. Re-run any time — setup steps are skipped if already done.
#
#  USAGE:
#     ./run_mac.sh                 # set up (first time) + run, always-on VAD
#     ./run_mac.sh --setup         # set up only, don't launch
#     ./run_mac.sh --ptt           # push-to-talk mode (needs `keyboard` + perms)
#     ./run_mac.sh --no-enter      # dictate without auto-Enter
#
#  PERMISSION (one-time, REQUIRED for typing): grant your terminal app
#  Accessibility access in:  System Settings > Privacy & Security > Accessibility
#  and Microphone access in: System Settings > Privacy & Security > Microphone.
#
#  ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HEBREW_VOICE="$(cd "$HERE/../hebrew-voice" 2>/dev/null && pwd || true)"
VENV="$HERE/.venv-mac"
PY="$VENV/bin/python"

echo "== Hebrew mic (macOS) =="
echo "   voice-input : $HERE"
echo "   hebrew-voice: ${HEBREW_VOICE:-<NOT FOUND — STT engine missing!>}"

# ── 1. python3 present? ──────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install it:  brew install python  (or python.org)"
  exit 1
fi

# ── 2. optional system helpers (best-effort; the app degrades without them) ──
#    cliclick   = more robust keystroke/click than pure AppleScript (optional)
#    coreutils  = gives gpbpaste-compatible tools; pbcopy/pbpaste ship with macOS
if command -v brew >/dev/null 2>&1; then
  command -v cliclick >/dev/null 2>&1 || {
    echo "== (optional) installing cliclick for robust typing =="
    brew install cliclick || echo "   cliclick install skipped (continuing — System Events still works)"
  }
else
  echo "NOTE: Homebrew not found — skipping optional cliclick. Core dictation still works via AppleScript."
fi

# ── 3. venv + python deps ────────────────────────────────────────────────────
if [ ! -x "$PY" ]; then
  echo "== creating venv $VENV =="
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip wheel >/dev/null

echo "== installing python deps (faster-whisper, sounddevice, …) =="
# CPU-only torch is NOT required by faster-whisper itself (CTranslate2 backend),
# so we keep the install lean. pyperclip is a clipboard fallback if pbcopy lacks
# something. sounddevice needs PortAudio — pip wheels bundle it on macOS.
pip install -U \
  faster-whisper \
  sounddevice \
  soundfile \
  numpy \
  pyperclip

# ── 4. wire the shared STT engine onto the venv path (import hebrew_stt) ──────
if [ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ]; then
  SP="$(python -c 'import site;print(site.getsitepackages()[0])')"
  echo "$HEBREW_VOICE" > "$SP/hebrew_stt.pth"
  echo "== hebrew_stt wired: $SP/hebrew_stt.pth -> $HEBREW_VOICE =="
else
  echo "WARNING: ../hebrew-voice/hebrew_stt.py not found. Copy the hebrew-voice"
  echo "         folder next to voice-input, or edit HEBREW_VOICE in this script."
fi

# ── 5. setup-only? ───────────────────────────────────────────────────────────
for a in "$@"; do
  if [ "$a" = "--setup" ]; then
    echo "== setup complete (--setup): not launching =="
    echo "   To run:  ./run_mac.sh"
    exit 0
  fi
done

# ── 6. launch (force the mac backend + CPU; pass through extra flags) ─────────
echo "== launching always-on Hebrew mic (macOS, CPU) =="
echo "   Quit with Ctrl+C. First run downloads the STT model (~), then it's cached."
export VOICEINPUT_BACKEND=mac
exec python "$HERE/voice_input_xplat.py" --cpu "$@"
