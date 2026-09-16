#!/usr/bin/env bash
# ============================================================================
#  run_linux.sh — always-on Hebrew mic on Linux (X11 + best-effort Wayland)
#
#  PORT of the Windows hebrew-mic to Linux. Reuses the SAME engine
#  (../hebrew-voice/hebrew_stt.py), the SAME capture (mic.py) and the SAME
#  config.json, and routes typing/paste/focus/duck through backends/linux.py
#  (xdotool/ydotool + wmctrl + xclip/wl-clipboard + pactl).
#
#  CPU-first by default. If you have an NVIDIA GPU + CUDA libs, set device=cuda
#  in config.linux.json (the engine falls back to CPU automatically if GPU load
#  fails, so leaving it on cpu is the safe default).
#
#  USAGE:
#     ./run_linux.sh               # set up (first time) + run, always-on VAD
#     ./run_linux.sh --setup       # set up only, don't launch
#     ./run_linux.sh --no-enter    # dictate without auto-Enter
#     ./run_linux.sh --ptt         # push-to-talk (needs `keyboard` + usually root)
#
#  X11 vs Wayland:
#     X11     — full support (window list/focus/undo via wmctrl + xdotool).
#     Wayland — compositor blocks window enum/focus; typing needs ydotool with a
#               running `ydotoold` daemon (see README). We degrade to typing into
#               the focused window only. Check with:  echo $XDG_SESSION_TYPE
#
#  ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HEBREW_VOICE="$(cd "$HERE/../hebrew-voice" 2>/dev/null && pwd || true)"
VENV="$HERE/.venv-linux"
PY="$VENV/bin/python"

SESSION="${XDG_SESSION_TYPE:-x11}"
echo "== Hebrew mic (Linux) =="
echo "   voice-input : $HERE"
echo "   hebrew-voice: ${HEBREW_VOICE:-<NOT FOUND — STT engine missing!>}"
echo "   session     : $SESSION"

# ── 1. python3 present? ──────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install:  sudo apt install python3 python3-venv python3-pip"
  exit 1
fi

# ── 2. system helpers (audio + typing + clipboard + windows) ─────────────────
#    The Python backend degrades gracefully if any are missing, but you want
#    these for real dictation. We attempt apt; on other distros install the
#    equivalents (see README) — this is best-effort and won't abort the run.
NEED_X11="xdotool wmctrl xclip"
NEED_WAYLAND="ydotool wl-clipboard"
NEED_COMMON="ffmpeg libsndfile1 pulseaudio-utils portaudio19-dev"

missing=()
for t in xdotool wmctrl xclip wl-copy ydotool pactl ffmpeg; do
  command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "== missing helpers: ${missing[*]} =="
  if command -v apt-get >/dev/null 2>&1; then
    echo "   attempting: sudo apt-get install (X11+Wayland+audio helpers)"
    sudo apt-get update -y || true
    # install both X11 and Wayland sets so it works regardless of session
    sudo apt-get install -y $NEED_X11 $NEED_WAYLAND $NEED_COMMON \
      || echo "   apt install partial/failed — install the missing tools manually (see README)."
  else
    echo "   Non-Debian distro: install these via your package manager (see README):"
    echo "     X11:     $NEED_X11"
    echo "     Wayland: $NEED_WAYLAND"
    echo "     common:  $NEED_COMMON"
  fi
fi

if [ "$SESSION" = "wayland" ] && ! command -v ydotool >/dev/null 2>&1; then
  echo "WARNING: Wayland session but ydotool missing — typing will NOT work."
  echo "         Install ydotool and run the ydotoold daemon (see README)."
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
    echo "   To run:  ./run_linux.sh"
    exit 0
  fi
done

# ── 6. launch (force the linux backend; CPU unless config says cuda) ─────────
echo "== launching always-on Hebrew mic (Linux) =="
echo "   Quit with Ctrl+C. First run downloads the STT model, then it's cached."
export VOICEINPUT_BACKEND=linux
exec python "$HERE/voice_input_xplat.py" "$@"
