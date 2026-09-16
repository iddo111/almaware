#!/usr/bin/env bash
# ============================================================================
#  build_pyinstaller.sh — alternative macOS packaging via PyInstaller
#
#  Produces dist/HebrewMic (a CLI-style onedir/onefile binary). Simpler than
#  py2app but the resulting binary asks for Microphone/Accessibility under the
#  *launching terminal's* identity rather than its own — so for an always-on
#  agent, prefer setup_py2app.py (proper .app + Info.plist usage strings).
#
#  RUN ON A REAL MAC:
#     python3 -m venv .venv-build && source .venv-build/bin/activate
#     pip install -r requirements-mac.txt pyinstaller
#     ./build_pyinstaller.sh
#
#  HONEST: authored on Windows, UNVERIFIED on macOS. The --collect-all flags for
#  ctranslate2 / faster_whisper native dylibs almost always need a tweak pass on
#  the target machine. See README_MAC.md "What needs a real Mac".
#
#  לזכרה של עלמה ז״ל · ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$(cd "$HERE/.." && pwd)"
HEBREW_VOICE="$(cd "$CORE/../hebrew-voice" 2>/dev/null && pwd || true)"
ENTRY="$CORE/voice_input_xplat.py"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "ERROR: pyinstaller not found.  pip install pyinstaller"
  exit 1
fi

# Make the core dir + the hebrew-voice engine importable, and bundle config.
PATHS=(--paths "$CORE")
ADD_DATA=(--add-data "$CORE/config.json:.")
[ -f "$CORE/config.mac.json" ] && ADD_DATA+=(--add-data "$CORE/config.mac.json:.")
if [ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ]; then
  PATHS+=(--paths "$HEBREW_VOICE")
  ADD_DATA+=(--add-data "$HEBREW_VOICE/hebrew_stt.py:.")
else
  echo "WARNING: hebrew_stt.py not found — the binary will fail to import the STT engine."
fi

echo "== building HebrewMic with PyInstaller =="
pyinstaller \
  --name HebrewMic \
  --onedir \
  --noconfirm \
  --console \
  "${PATHS[@]}" \
  "${ADD_DATA[@]}" \
  --collect-all faster_whisper \
  --collect-all ctranslate2 \
  --collect-all sounddevice \
  --hidden-import backends \
  --hidden-import backends.mac \
  --hidden-import mic \
  --hidden-import transcribe \
  --hidden-import hebrew_stt \
  "$ENTRY"

echo "== done.  Binary: $HERE/dist/HebrewMic/HebrewMic =="
echo "   Set VOICEINPUT_BACKEND=mac when running it."
