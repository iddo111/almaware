#!/usr/bin/env bash
# ============================================================================
#  dist-linux/build_appimage.sh — optional PyInstaller + AppImage packager
#
#  Builds a redistributable bundle of the Hebrew mic. Two stages:
#    1. PyInstaller onedir build  -> dist-linux/build/hebrew-mic/
#    2. (optional) AppImage        -> dist-linux/HebrewMic-x86_64.AppImage
#       only if `appimagetool` is on PATH (download from
#       https://github.com/AppImage/AppImageKit/releases)
#
#  HONEST CAVEATS (see README_LINUX.md §6):
#    * Bundling faster-whisper/ctranslate2 (esp. CUDA) is fragile and large.
#    * The STT model is NOT bundled — it downloads on first run and caches to
#      ~/.cache/huggingface. Ship offline only after pre-warming that cache.
#    * MUST be built + smoke-tested on the real Linux target (cannot be produced
#      on Windows). This script is the recipe; run it there.
#
#  USAGE
#     ./build_appimage.sh            # PyInstaller onedir (+ AppImage if tool present)
#     ./build_appimage.sh --onefile  # single-file binary (slower start, simpler ship)
#     ./build_appimage.sh --clean     # remove build/ and dist artifacts, then exit
#
#  לזכרה של עלמה ז"ל — ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # .../voice-input/dist-linux
APP="$(cd "$HERE/.." && pwd)"                            # .../voice-input
HEBREW_VOICE="$(cd "$APP/../hebrew-voice" 2>/dev/null && pwd || true)"
VENV="$APP/.venv-linux"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
BUILD="$HERE/build"
DIST="$HERE/dist"
NAME="hebrew-mic"

c_cyan(){ printf '\033[36m%s\033[0m\n' "$*"; }
c_grn(){  printf '\033[32m%s\033[0m\n' "$*"; }
c_ylw(){  printf '\033[33m%s\033[0m\n' "$*"; }
c_red(){  printf '\033[31m%s\033[0m\n' "$*"; }

for a in "$@"; do
  if [ "$a" = "--clean" ]; then
    c_cyan "== cleaning build/ dist/ + AppImage =="
    rm -rf "$BUILD" "$DIST" "$HERE/${NAME}.spec" "$HERE"/*.AppImage
    c_grn "clean done."; exit 0
  fi
done

ONEFILE=false
for a in "$@"; do [ "$a" = "--onefile" ] && ONEFILE=true; done

# ── prerequisites ────────────────────────────────────────────────────────────
if [ ! -x "$PY" ]; then
  c_red "ERROR: venv not found at $VENV. Run ./run.sh --setup first."
  exit 1
fi
c_cyan "== ensuring PyInstaller in venv =="
"$PIP" install -U pyinstaller >/dev/null

# Collect hooks so faster-whisper/ctranslate2/sounddevice data + libs come along.
COLLECT=( --collect-all faster_whisper
          --collect-all ctranslate2
          --collect-all sounddevice
          --collect-all soundfile
          --collect-submodules backends )

# Bring the shared STT engine + the config files in as data.
ADD_DATA=()
[ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ] \
  && ADD_DATA+=( --add-data "$HEBREW_VOICE/hebrew_stt.py:." ) \
  || c_ylw "WARN: hebrew_stt.py not found — STT engine won't be bundled."
for f in config.json config.linux.json; do
  [ -f "$APP/$f" ] && ADD_DATA+=( --add-data "$APP/$f:." )
done

MODE_FLAG="--onedir"
$ONEFILE && MODE_FLAG="--onefile"

c_cyan "== running PyInstaller ($MODE_FLAG) =="
# We point the entrypoint at the existing xplat runtime and add the app dir to
# the path so `import mic`, `import transcribe`, `from backends import ...` resolve.
PYTHONPATH="$APP${HEBREW_VOICE:+:$HEBREW_VOICE}" \
"$PY" -m PyInstaller \
  --name "$NAME" \
  --noconfirm \
  $MODE_FLAG \
  --console \
  --paths "$APP" \
  ${HEBREW_VOICE:+--paths "$HEBREW_VOICE"} \
  "${COLLECT[@]}" \
  ${ADD_DATA[@]+"${ADD_DATA[@]}"} \
  --distpath "$DIST" \
  --workpath "$BUILD" \
  --specpath "$HERE" \
  "$APP/voice_input_xplat.py"

c_grn "== PyInstaller build done -> $DIST/$NAME =="
c_ylw "   NOTE: VOICEINPUT_BACKEND=linux is set by run.sh, not baked into the"
c_ylw "   binary. Launch the bundle with that env set, e.g.:"
echo  "     VOICEINPUT_BACKEND=linux $DIST/$NAME/$NAME"

# ── optional AppImage ─────────────────────────────────────────────────────────
if $ONEFILE; then
  c_ylw "== --onefile build: skipping AppImage (already a single binary) =="
  exit 0
fi
if ! command -v appimagetool >/dev/null 2>&1; then
  c_ylw "== appimagetool not found — skipping AppImage step =="
  c_ylw "   Install from https://github.com/AppImage/AppImageKit/releases to enable it."
  exit 0
fi

c_cyan "== assembling AppDir =="
APPDIR="$BUILD/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST/$NAME/." "$APPDIR/usr/bin/"

cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export VOICEINPUT_BACKEND=linux
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
exec "$HERE/usr/bin/hebrew-mic" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/hebrew-mic.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=Hebrew Mic
GenericName=Hebrew Voice Input
Comment=ALMAWARE always-on Hebrew voice-to-text dictation
Exec=hebrew-mic
Icon=hebrew-mic
Terminal=true
Categories=AudioVideo;Utility;
DESKTOP

# minimal placeholder icon (1x1 PNG) so appimagetool is satisfied; replace with a real one
ICON_SRC="$APP/mic_icon.png"
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$APPDIR/hebrew-mic.png"
else
  printf '\x89PNG\r\n\x1a\n' > "$APPDIR/hebrew-mic.png"   # placeholder; replace before shipping
  c_ylw "   (placeholder icon written — drop a real mic_icon.png in voice-input/ to brand it)"
fi

c_cyan "== building AppImage =="
( cd "$BUILD" && ARCH="${ARCH:-x86_64}" appimagetool "$APPDIR" "$HERE/HebrewMic-${ARCH:-x86_64}.AppImage" )
c_grn "== AppImage -> $HERE/HebrewMic-x86_64.AppImage =="
c_ylw "   Smoke-test it ON THE TARGET: chmod +x HebrewMic-x86_64.AppImage && ./HebrewMic-x86_64.AppImage --doctor"
