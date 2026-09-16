#!/usr/bin/env bash
# ============================================================================
#  dist-linux/run.sh — self-contained Linux launcher for the ALMAWARE Hebrew mic
#
#  This is the packaged Linux RUN path. It lives in  voice-input/dist-linux/  and
#  resolves the app root one level up (../, i.e. voice-input/). It reuses the
#  SAME engine (../../hebrew-voice/hebrew_stt.py), the SAME capture (../mic.py),
#  the SAME cross-platform runtime (../voice_input_xplat.py) and the SAME
#  config.json, routing typing/paste/focus/duck through ../backends/linux.py
#  (xdotool/ydotool + wmctrl + xclip/wl-clipboard + pactl).
#
#  It does NOT touch or duplicate any core .py file — it only sets up a venv and
#  launches the existing runtime with VOICEINPUT_BACKEND=linux.
#
#  USAGE
#     ./run.sh               # first run: install deps + setup, then launch (VAD)
#     ./run.sh --setup       # set up only (venv + deps + STT wiring), don't launch
#     ./run.sh --no-enter    # dictate without auto-Enter
#     ./run.sh --ptt         # push-to-talk (needs `keyboard` + usually root; VAD recommended)
#     ./run.sh --gpu         # install ctranslate2 CUDA path hint (still falls back to CPU)
#     ./run.sh --doctor      # print an environment / helper-tool diagnosis and exit
#
#  X11 vs WAYLAND (typing injector — read this)
#     X11      full support: typing via xdotool, window list/focus/undo via
#              wmctrl + xdotool, clipboard via xclip/xsel.   echo $XDG_SESSION_TYPE -> x11
#     Wayland  the compositor BLOCKS arbitrary window enumeration/focus for
#              security. Typing works ONLY through ydotool, which needs its
#              background daemon `ydotoold` running with /dev/uinput access
#              (see README_LINUX.md "Wayland setup"). We degrade to typing into
#              the FOCUSED window only.            echo $XDG_SESSION_TYPE -> wayland
#
#  CPU-first by default. Set "device":"cuda" in ../config.linux.json only if you
#  have an NVIDIA GPU + CUDA libs (the engine auto-falls back to CPU on failure).
#
#  לזכרה של עלמה ז"ל — ALMAWARE · iddoperez.ai
# ============================================================================
set -euo pipefail

# ── resolve paths (dist-linux/ -> voice-input/ -> repo) ──────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # .../voice-input/dist-linux
APP="$(cd "$HERE/.." && pwd)"                             # .../voice-input
HEBREW_VOICE="$(cd "$APP/../hebrew-voice" 2>/dev/null && pwd || true)"
VENV="$APP/.venv-linux"                                   # shared with run_linux.sh
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
RUNTIME="$APP/voice_input_xplat.py"
SESSION="${XDG_SESSION_TYPE:-${WAYLAND_DISPLAY:+wayland}}"
SESSION="${SESSION:-x11}"

c_cyan(){ printf '\033[36m%s\033[0m\n' "$*"; }
c_grn(){  printf '\033[32m%s\033[0m\n' "$*"; }
c_ylw(){  printf '\033[33m%s\033[0m\n' "$*"; }
c_red(){  printf '\033[31m%s\033[0m\n' "$*"; }

c_cyan "== ALMAWARE Hebrew mic — Linux (dist-linux) =="
echo   "   app root    : $APP"
echo   "   hebrew-voice: ${HEBREW_VOICE:-<NOT FOUND — STT engine missing!>}"
echo   "   session     : $SESSION"
echo   "   venv        : $VENV"

# ── --doctor : diagnose and exit (no install, no launch) ─────────────────────
have(){ command -v "$1" >/dev/null 2>&1; }
doctor(){
  c_cyan "-- environment doctor --"
  printf '   %-14s %s\n' "session"  "$SESSION (XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-unset}, WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset}, DISPLAY=${DISPLAY:-unset})"
  for t in python3 xdotool ydotool wmctrl xclip xsel wl-copy wl-paste pactl ffmpeg ydotoold xdg-open; do
    if have "$t"; then printf '   %-14s \033[32mfound\033[0m   (%s)\n' "$t" "$(command -v "$t")";
    else               printf '   %-14s \033[31mMISSING\033[0m\n' "$t"; fi
  done
  if [ "$SESSION" = "wayland" ]; then
    have ydotool || c_red   "   Wayland + no ydotool  -> typing WILL NOT work."
    if have ydotool && ! pgrep -x ydotoold >/dev/null 2>&1; then
      c_ylw "   ydotoold daemon not running -> start it: ydotoold &  (see README_LINUX.md)"
    fi
  else
    have xdotool || c_red   "   X11 + no xdotool      -> typing WILL NOT work."
  fi
  [ -x "$PY" ] && c_grn "   venv python present: $PY" || c_ylw "   venv not created yet (run ./run.sh)"
  [ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ] \
    && c_grn "   STT engine present: $HEBREW_VOICE/hebrew_stt.py" \
    || c_red "   STT engine MISSING — hebrew-voice/hebrew_stt.py not found next to voice-input/"
}
for a in "$@"; do [ "$a" = "--doctor" ] && { doctor; exit 0; }; done

# ── 1. python3 ───────────────────────────────────────────────────────────────
if ! have python3; then
  c_red "ERROR: python3 not found. Install:  sudo apt install python3 python3-venv python3-pip"
  exit 1
fi

# ── 2. system helpers (typing / clipboard / windows / audio) ─────────────────
#    The python backend degrades gracefully if any are missing, but you want
#    them for real dictation. Best-effort apt; on other distros see README_LINUX.md.
NEED_X11="xdotool wmctrl xclip xsel"
NEED_WAYLAND="ydotool wl-clipboard"
NEED_COMMON="ffmpeg libsndfile1 pulseaudio-utils portaudio19-dev"
missing=()
for t in xdotool wmctrl xclip wl-copy ydotool pactl ffmpeg; do
  have "$t" || missing+=("$t")
done
if [ "${#missing[@]}" -gt 0 ]; then
  c_ylw "== missing helpers: ${missing[*]} =="
  if have apt-get; then
    c_cyan "   attempting: sudo apt-get install (X11 + Wayland + audio helpers)"
    sudo apt-get update -y || true
    sudo apt-get install -y $NEED_X11 $NEED_WAYLAND $NEED_COMMON \
      python3-venv python3-pip \
      || c_ylw "   apt install partial/failed — install missing tools manually (README_LINUX.md)."
  elif have dnf; then
    c_cyan "   Fedora detected — try:"
    echo   "     sudo dnf install xdotool wmctrl xclip xsel ydotool wl-clipboard ffmpeg-free libsndfile pulseaudio-utils portaudio-devel"
  elif have pacman; then
    c_cyan "   Arch detected — try:"
    echo   "     sudo pacman -S xdotool wmctrl xclip xsel ydotool wl-clipboard ffmpeg libsndfile libpulse portaudio"
  else
    c_ylw "   Unknown distro — install via your package manager (README_LINUX.md):"
    echo   "     X11:     $NEED_X11"
    echo   "     Wayland: $NEED_WAYLAND"
    echo   "     common:  $NEED_COMMON"
  fi
fi

# Wayland-specific typing warning
if [ "$SESSION" = "wayland" ]; then
  if ! have ydotool; then
    c_red "WARNING: Wayland session but ydotool MISSING — typing will NOT work."
    c_red "         Install ydotool + run the ydotoold daemon (see README_LINUX.md)."
  elif ! pgrep -x ydotoold >/dev/null 2>&1; then
    c_ylw "NOTE: Wayland session — ydotoold daemon not detected. Typing needs it:"
    c_ylw "      run 'ydotoold &' (one-time uinput setup in README_LINUX.md)."
  fi
fi

# ── 3. venv + python deps ────────────────────────────────────────────────────
if [ ! -x "$PY" ]; then
  c_cyan "== creating venv $VENV =="
  python3 -m venv "$VENV"
fi
"$PY" -m pip install -U pip wheel >/dev/null

WANT_GPU=false
for a in "$@"; do [ "$a" = "--gpu" ] && WANT_GPU=true; done

c_cyan "== installing python deps (faster-whisper, sounddevice, …) =="
REQ="$APP/packaging/requirements.txt"
$WANT_GPU && REQ="$APP/packaging/requirements-gpu.txt"
if [ -f "$REQ" ]; then
  "$PIP" install -r "$REQ"
else
  # fallback if the packaging reqs file isn't present
  "$PIP" install -U faster-whisper sounddevice soundfile numpy pyperclip
fi
# soundfile isn't in requirements.txt but mic/STT can use it; ensure present
"$PIP" install -U soundfile >/dev/null 2>&1 || true

# ── 4. wire the shared STT engine onto the venv path (import hebrew_stt) ──────
if [ -n "${HEBREW_VOICE:-}" ] && [ -f "$HEBREW_VOICE/hebrew_stt.py" ]; then
  SP="$("$PY" -c 'import site;print(site.getsitepackages()[0])')"
  echo "$HEBREW_VOICE" > "$SP/hebrew_stt.pth"
  c_grn "== hebrew_stt wired: $SP/hebrew_stt.pth -> $HEBREW_VOICE =="
else
  c_red "WARNING: ../../hebrew-voice/hebrew_stt.py not found. Place the hebrew-voice"
  c_red "         folder next to voice-input/, then re-run ./run.sh --setup."
fi

# ── 5. setup-only? ───────────────────────────────────────────────────────────
for a in "$@"; do
  if [ "$a" = "--setup" ]; then
    c_grn "== setup complete (--setup): not launching =="
    echo  "   To run:  ./run.sh        (diagnose: ./run.sh --doctor)"
    exit 0
  fi
done

# ── 6. launch (force the linux backend; CPU unless config says cuda) ─────────
if [ ! -f "$RUNTIME" ]; then
  c_red "ERROR: runtime not found: $RUNTIME"
  exit 1
fi
c_cyan "== launching always-on Hebrew mic (Linux) =="
echo   "   Quit with Ctrl+C. First run downloads the STT model, then it's cached."
export VOICEINPUT_BACKEND=linux
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
# strip our own --gpu/--doctor flags before handing argv to the runtime
ARGS=()
for a in "$@"; do
  case "$a" in --gpu|--doctor) ;; *) ARGS+=("$a") ;; esac
done
cd "$APP"
exec "$PY" "$RUNTIME" "${ARGS[@]+"${ARGS[@]}"}"
