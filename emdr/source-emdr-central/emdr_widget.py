r"""
EMDR Therapy Widget v4 - music-swing edition
============================================
Hard red line compliance (unchanged):
- NO full-screen overlay. Sweep strip = 56px top strip, transparent-for-input,
  no-focus. User can click/type/scroll normally (no_hijack_rule).
- No dimming, no focus steal, no window auto-pop.
- music_daemon respected: paused via `pause` CLI at sweep start, `resume` at end.
  Never brute-kills ffplay (one_music_rule, one_audio_rule).
- CPU-light: single mixer channel, single 60 Hz Qt timer (cpu_temp_rule).

v4 new:
- Built-in music player (pygame.mixer) inside Settings -> Music tab:
    * pick files, scan folder, playlist (reorder, remove, dbl-click-to-play)
    * play/pause/stop/next/prev/shuffle, volume, seek
    * "Quick sources" (Last music_daemon track / File...)
    * Test Pan button (5 sec L<->R demo)
    * persists to D:\NEWCLAUDE\EMDR\playlist.json
- EMDR sweep pans the actual loaded track in stereo following orb X.
  Falls back to v3 synth pan-tone if no track loaded.
"""

from __future__ import annotations

import math
import os
import sys
import struct
import wave
import json
import random
import tempfile
import threading
import subprocess
import datetime
import time
import traceback
from pathlib import Path

import numpy as np

# These import blocks run BEFORE log() exists, so failures are parked here
# and flushed to the log file the moment logging is available.
_BOOT_NOTES: list[str] = []

try:
    import sounddevice as sd
    _SD_OK = True
except Exception as _e:
    sd = None
    _SD_OK = False
    _BOOT_NOTES.append(f"sounddevice unavailable: {_e!r}")

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame  # pygame-ce drop-in
    _PG_OK = True
except Exception as _e:
    pygame = None
    _PG_OK = False
    _BOOT_NOTES.append(f"pygame unavailable: {_e!r}")

try:
    # Source runs only. In a PyInstaller build soundcard_pan is bundled and
    # FrozenImporter wins regardless. append(), NEVER insert(0, ...): putting
    # a user-writable folder at the FRONT of sys.path lets any stray json.py /
    # math.py dropped there shadow the stdlib and break the whole app.
    if not getattr(sys, "frozen", False):
        _SCP_DIR = r"D:\NEWCLAUDE\EMDR"
        if _SCP_DIR not in sys.path:
            sys.path.append(_SCP_DIR)
    import soundcard_pan  # type: ignore
    _SCP_OK = True
except Exception as _e:
    soundcard_pan = None
    _SCP_OK = False
    _BOOT_NOTES.append(f"soundcard_pan unavailable: {_e!r}")

from PyQt6.QtCore import Qt, QTimer, QPointF, QUrl
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QBrush, QPen, QMouseEvent,
    QIcon, QPixmap, QAction, QImage,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QComboBox, QSpinBox, QCheckBox, QPushButton,
    QSystemTrayIcon, QDialogButtonBox, QFormLayout, QTabWidget,
    QListWidget, QListWidgetItem, QFileDialog, QAbstractItemView,
)
from PyQt6.QtMultimedia import QSoundEffect


# ------------- paths / config -------------
def _resolve_base_dir() -> Path:
    r"""Pick the first WRITABLE app-data dir.

    D:\NEWCLAUDE\EMDR normally; %LOCALAPPDATA%\EMDR_Widget, then %TEMP%, if
    that disk is missing or read-only. The old code ran a bare
    ``LOG_DIR.mkdir(...)`` at import time -- if D: were gone the app died
    before log() even existed to record why, with console=False swallowing
    the traceback. Path setup must never be able to kill the process.
    """
    candidates = [Path(r"D:\NEWCLAUDE\EMDR")]
    localapp = os.environ.get("LOCALAPPDATA")
    if localapp:
        candidates.append(Path(localapp) / "EMDR_Widget")
    candidates.append(Path(tempfile.gettempdir()) / "EMDR_Widget")
    for cand in candidates:
        try:
            logs = cand / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            probe = logs / ".writetest"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return cand
        except Exception:
            continue
    return candidates[-1]


BASE_DIR = _resolve_base_dir()
LOG_DIR = BASE_DIR / "logs"
SETTINGS_PATH = BASE_DIR / "settings.json"
PLAYLIST_PATH = BASE_DIR / "playlist.json"
SOUNDCARD_RESIDUE = BASE_DIR / "soundcard_residue.json"

MUSIC_DAEMON = Path(r"D:\NEWCLAUDE\music_daemon.py")
MUSIC_DAEMON_STATE = Path(r"D:\NEWCLAUDE\music_daemon_state.json")

BUTTON_SIZE = 44
STRIP_H = 56
STRIP_Y = 0
EDGE_MARGIN = 40
FPS = 60
BEEP_MS = 100
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus", ".aac", ".wma"}

SAMPLE_RATE = 44100
AUDIO_BLOCKSIZE = 512

SOUND_FREQS = {"Click": 1200, "Beep": 660, "Tick": 1800, "Bell": 880, "Woodblock": 520}
PAN_MODES = ["Sine", "Whoosh", "Off"]

# --- where the bilateral sound comes OUT ---------------------------------
# EMDR_TONE is the default and the only lawful-by-construction option: the
# widget generates its own stereo stream and pans THAT. SYSTEM reaches into
# the Windows default render endpoint's per-channel volumes and swings every
# app on the machine -- it is opt-in only, never a default. See SACRED AUDIO.
PAN_OUT_TONE = "EMDR tone (own stereo, recommended)"
PAN_OUT_MUSIC = "Music track (in-widget)"
PAN_OUT_SYSTEM = "System audio - ALL apps (advanced)"
PAN_OUT_OFF = "Off (visual only)"
PAN_OUT_MODES = [PAN_OUT_TONE, PAN_OUT_MUSIC, PAN_OUT_SYSTEM, PAN_OUT_OFF]

# v4 settings.json files hold the old three-value vocabulary. Map them so an
# existing file still loads. "Soundcard" deliberately does NOT map to the
# system mode: that mode must be re-chosen deliberately, with the opt-in.
LEGACY_PAN_OUT = {
    "Soundcard": PAN_OUT_TONE,
    "In-widget": PAN_OUT_MUSIC,
    "Off": PAN_OUT_OFF,
}

# Smoothing time-constant for the equal-power pan gains. ~10 ms kills the
# zipper/stair-stepping without smearing the image.
PAN_SMOOTH_MS_DEFAULT = 10

DEFAULT_SETTINGS = {
    "duration_sec": 90,
    "sweep_hz": 1.0,
    "edge_sound": "Beep",
    "seed": 42,
    "orb_size": 22,
    "amplitude_pct": 95,
    "auto_color": True,
    "pan_mode": "Sine",
    "pan_volume_pct": 30,
    "music_volume_pct": 70,
    "shuffle": False,
    "pan_output_mode": PAN_OUT_TONE,
    # System-wide pan is a loaded gun: it modulates the master render
    # endpoint. It only ever engages when the user has ticked this box.
    "soundcard_optin": False,
    "pan_smooth_ms": PAN_SMOOTH_MS_DEFAULT,
}

# type / range contract for every key. A settings.json holding a string where
# a number belongs used to kill the process from inside the Settings dialog
# (int("1.0" * 10) -> ValueError) or on Start (1000 / 0 -> ZeroDivisionError).
# Everything is coerced and clamped on load, so the UI and the sweep can only
# ever see values they can survive.
SETTINGS_SPEC = {
    "duration_sec": ("int", 30, 300),
    "sweep_hz": ("float", 0.5, 2.0),
    "edge_sound": ("choice", list(SOUND_FREQS.keys())),
    "seed": ("int", 0, 999999),
    "orb_size": ("int", 12, 40),
    "amplitude_pct": ("int", 50, 100),
    "auto_color": ("bool",),
    "pan_mode": ("choice", PAN_MODES),
    "pan_volume_pct": ("int", 0, 100),
    "music_volume_pct": ("int", 0, 100),
    "shuffle": ("bool",),
    "pan_output_mode": ("choice", PAN_OUT_MODES),
    "soundcard_optin": ("bool",),
    "pan_smooth_ms": ("int", 1, 200),
}


def _as_int(val, default: int, lo: int, hi: int) -> int:
    """Never raises. int('1.0') and int(None) used to kill the process from
    inside the Settings dialog builder, with no console to report it."""
    try:
        return max(lo, min(hi, int(round(float(val)))))
    except Exception:
        return default


def _as_float(val, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except Exception:
        return default


def coerce_settings(raw: dict) -> dict:
    """Force every setting to its declared type and range. Never raises."""
    out = dict(DEFAULT_SETTINGS)
    for key, spec in SETTINGS_SPEC.items():
        if key not in raw:
            continue
        val = raw[key]
        kind = spec[0]
        try:
            if kind == "int":
                out[key] = max(spec[1], min(spec[2], int(round(float(val)))))
            elif kind == "float":
                out[key] = max(spec[1], min(spec[2], float(val)))
            elif kind == "bool":
                out[key] = bool(val)
            elif kind == "choice":
                out[key] = val if val in spec[1] else DEFAULT_SETTINGS[key]
        except Exception:
            log(f"settings: bad value for {key!r} ({val!r}) -> default "
                f"{DEFAULT_SETTINGS[key]!r}")
    return out


def log(msg: str) -> None:
    """Write one line to today's log file. NEVER raises.

    This app ships as a windowed (console=False) PyInstaller build, where
    ``sys.stderr`` and ``sys.stdout`` are None. The log FILE is therefore the
    only place anything can ever be recorded -- so log() must survive a
    vanished or read-only log directory rather than throw from inside a Qt
    slot. No sys.stderr / sys.stdout writes anywhere in this app, ever.
    """
    try:
        ts = datetime.datetime.now()
        fn = LOG_DIR / f"{ts.strftime('%Y%m%d')}.log"
        line = f"[{ts.strftime('%H:%M:%S')}] {msg}\n"
        try:
            with open(fn, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            # dir deleted mid-run / transient lock: try once to recreate
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(fn, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


# ------------- crash net: never die silently again -------------
# In a WINDOWED build PyQt6 aborts the process (exit 0xC0000409) on an
# unhandled exception raised inside a slot -- but ONLY while sys.excepthook is
# the DEFAULT one. Installing our own hook both (a) records the full traceback
# in the log file and (b) keeps the process alive. Armed at import time, so it
# is in place before QApplication and before any dialog can be built.
# This is a NET, not a cure: a slot that dies mid-way leaves half-built state.
# The real fixes are elsewhere; this guarantees we always SEE the next one.
def _log_exception(kind: str, exc_type, exc_value, exc_tb) -> None:
    try:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        text = f"{exc_type!r}: {exc_value!r}"
    log(f"UNHANDLED ({kind}):\n{text.rstrip()}")


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    _log_exception("main", exc_type, exc_value, exc_tb)


def _thread_excepthook(args) -> None:
    _log_exception(f"thread {getattr(args, 'thread', None)!r}",
                   args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _excepthook
try:
    threading.excepthook = _thread_excepthook  # py3.8+
except Exception:
    pass

for _note in _BOOT_NOTES:
    log(_note)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            s = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(s, dict):
                raise ValueError(f"settings.json is {type(s).__name__}, not an object")
            s.pop("dim_pct", None)
            # migrate the v4 three-value pan vocabulary
            old_mode = s.get("pan_output_mode")
            if isinstance(old_mode, str) and old_mode in LEGACY_PAN_OUT:
                s["pan_output_mode"] = LEGACY_PAN_OUT[old_mode]
                if old_mode == "Soundcard":
                    # A v4 file asking for the system-wide endpoint duck.
                    # Migrated to EMDR's own stereo tone -- it is not a pan,
                    # it modulates his master output device, and the SACRED
                    # AUDIO LAW forbids that. Re-selectable, but only with
                    # the explicit opt-in tick.
                    s["soundcard_optin"] = False
                log(f"settings: migrated pan_output_mode {old_mode!r} -> "
                    f"{s['pan_output_mode']!r}")
            return coerce_settings(s)
        except Exception as e:
            log(f"load_settings error ({e!r}); using defaults")
    return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    try:
        s = {k: v for k, v in s.items() if k in DEFAULT_SETTINGS}
        SETTINGS_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"save_settings error: {e}")


def load_playlist() -> list[str]:
    if PLAYLIST_PATH.exists():
        try:
            data = json.loads(PLAYLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(p) for p in data if isinstance(p, str)]
        except Exception:
            pass
    return []


def save_playlist(items: list[str]) -> None:
    try:
        PLAYLIST_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"save_playlist error: {e}")


# ------------- music daemon bridge (pause/resume via CLI) -------------
def music_daemon_state_mode() -> str | None:
    try:
        if MUSIC_DAEMON_STATE.exists():
            d = json.loads(MUSIC_DAEMON_STATE.read_text(encoding="utf-8"))
            return d.get("mode")
    except Exception:
        pass
    return None


def music_daemon_last_query() -> str | None:
    try:
        if MUSIC_DAEMON_STATE.exists():
            d = json.loads(MUSIC_DAEMON_STATE.read_text(encoding="utf-8"))
            q = d.get("current_query")
            return q if isinstance(q, str) else None
    except Exception:
        pass
    return None


def music_daemon_call(cmd: str) -> bool:
    if not MUSIC_DAEMON.exists():
        return False
    if getattr(sys, "frozen", False):
        # LATENT BOMB, defused: in a PyInstaller onefile build sys.executable
        # IS EMDR_Widget.exe, so this Popen would launch a SECOND copy of the
        # widget (second tray icon, second audio owner) instead of python.
        log(f"music_daemon {cmd} skipped: frozen build has no python interpreter")
        return False
    try:
        subprocess.Popen(
            [sys.executable, str(MUSIC_DAEMON), cmd],
            cwd=str(MUSIC_DAEMON.parent),
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        log(f"music_daemon {cmd} dispatched")
        return True
    except Exception as e:
        log(f"music_daemon {cmd} failed: {e}")
        return False


# ------------- beep generation (edge clicks) -------------
def build_beep_wav(path: Path, freq_hz: int, ms: int = BEEP_MS) -> None:
    sample_rate = 44100
    n = int(sample_rate * ms / 1000)
    fade = int(sample_rate * 0.015)
    amp = 0.35 * 32767
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n):
            env = 1.0
            if i < fade: env = i / fade
            elif i > n - fade: env = (n - i) / fade
            s = int(amp * env * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
            frames += struct.pack("<h", s)
        w.writeframes(bytes(frames))


def ensure_beep_files() -> dict:
    out_dir = Path(tempfile.gettempdir()) / "emdr_widget"
    out_dir.mkdir(exist_ok=True)
    paths = {}
    for name, freq in SOUND_FREQS.items():
        p = out_dir / f"edge_{name.lower()}.wav"
        if not p.exists():
            build_beep_wav(p, freq)
        paths[name] = p
    return paths


# ------------- pygame music engine -------------
class MusicEngine:
    """
    pygame.mixer-based music player with stereo panning via Channel.set_volume.
    One Channel, one Sound active at a time. Stop/next managed by parent.
    """

    def __init__(self) -> None:
        # Lazy pygame.mixer init — pygame.mixer.init() can block 2-5s on some
        # systems, so we defer it until the user actually presses Play / Test Pan
        # / starts a sweep. Keeps EMDR widget launch and Music-tab open snappy.
        self._ok = False
        self._inited = False
        self._channel = None
        self._sound = None
        self._current_path: str | None = None
        self._volume = 0.7
        self._pan = 0.0  # -1..+1, smoothed
        self._pan_applied = 0.0
        self._pan_t = 0.0
        self._smooth_ms = float(PAN_SMOOTH_MS_DEFAULT)

    def _ensure_init(self) -> bool:
        if self._inited:
            return self._ok
        self._inited = True
        if not _PG_OK:
            self._ok = False
            return False
        import time as _t
        t0 = _t.perf_counter()
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(4)
            self._channel = pygame.mixer.Channel(0)
            self._ok = True
            log(f"pygame.mixer.init took {_t.perf_counter()-t0:.2f}s")
        except Exception as e:
            log(f"MusicEngine init error: {e}")
            self._ok = False
        return self._ok

    def available(self) -> bool:
        # Report availability based on pygame being importable; actual mixer
        # init is deferred. UI can still offer music without paying the init
        # cost up front. status_text() is the honest version for display.
        return bool(_PG_OK) and (self._ok or not self._inited)

    def status_text(self) -> str:
        """What the Music tab shows. The old label claimed "pygame OK" for an
        engine whose mixer had never been initialised and might still fail."""
        if not _PG_OK:
            return "pygame NOT INSTALLED - in-widget music is unavailable"
        if not self._inited:
            return "pygame present (mixer initialises on first Play)"
        return "mixer ready" if self._ok else "mixer init FAILED - see log"

    def is_playing(self) -> bool:
        return bool(self._inited and self._ok and self._channel and self._channel.get_busy())

    def current_path(self) -> str | None:
        return self._current_path

    def play(self, path: str) -> bool:
        if not self._ensure_init():
            return False
        try:
            # pygame Sound loads whole file into memory — fine for single track.
            # For mp3/m4a large files it still works; no streaming seek though.
            snd = pygame.mixer.Sound(path)
            self._sound = snd
            self._current_path = path
            self._channel.stop()
            self._channel.play(snd)
            self._apply_volume()
            log(f"music play: {path}")
            return True
        except Exception as e:
            log(f"music play error for {path}: {e}")
            return False

    def pause(self) -> None:
        if self._ok and self._channel:
            try: self._channel.pause()
            except Exception: pass

    def unpause(self) -> None:
        if self._ok and self._channel:
            try: self._channel.unpause()
            except Exception: pass

    def stop(self) -> None:
        if self._ok and self._channel:
            try: self._channel.stop()
            except Exception: pass
        self._sound = None

    def set_volume_pct(self, pct: int) -> None:
        self._volume = max(0, min(100, int(pct))) / 100.0
        self._apply_volume()

    def set_smooth_ms(self, ms: float) -> None:
        self._smooth_ms = max(1.0, float(ms))

    def reset_pan(self) -> None:
        self._pan = 0.0
        self._pan_applied = 0.0
        self._pan_t = 0.0

    def set_pan(self, pan: float) -> None:
        """One-pole-smoothed equal-power balance for the loaded track.

        HONEST LIMIT: pygame's Channel.set_volume(l, r) is a BALANCE control
        applied at buffer boundaries (1024 frames = 23 ms here). It attenuates
        the file's existing L and R -- it cannot move a stereo image the way a
        true pan does, and it cannot update mid-buffer. Smoothing the pan
        before handing it over shrinks the per-buffer gain step (which was up
        to 0.78 dB, i.e. audible stair-stepping) but cannot remove the
        quantisation. EMDR's OWN tone -- BilateralEngine -- is the path that
        pans genuinely smoothly, per sample.
        """
        target = max(-1.0, min(1.0, float(pan)))
        now = time.perf_counter()
        dt = (now - self._pan_t) if self._pan_t else 0.0
        self._pan_t = now
        if dt <= 0.0 or dt > 0.5:
            self._pan = target           # first call, or a long stall
        else:
            tau = max(0.001, self._smooth_ms / 1000.0)
            self._pan += (target - self._pan) * (1.0 - math.exp(-dt / tau))
        # Skip inaudible updates: the mixer can only act per buffer anyway.
        if abs(self._pan - self._pan_applied) >= 0.004:
            self._pan_applied = self._pan
            self._apply_volume()

    def _apply_volume(self) -> None:
        if not (self._ok and self._channel):
            return
        ang = (self._pan + 1.0) * math.pi / 4.0
        gL = math.cos(ang) * self._volume
        gR = math.sin(ang) * self._volume
        try:
            self._channel.set_volume(gL, gR)
        except Exception:
            pass


# ------------- EMDR's own bilateral stereo engine -------------
class BilateralEngine:
    r"""ONE stereo stream that owns EVERY sound the EMDR sweep makes.

    * the continuous pan tone (Sine / Whoosh)
    * the edge click, panned hard to the ear the orb has just reached

    PAN LAW -- equal power (constant power):

        theta  = (pan + 1) * pi / 4        pan in [-1, +1]
        gain_L = cos(theta)
        gain_R = sin(theta)

    cos^2 + sin^2 == 1, so total power is CONSTANT across the entire sweep --
    no loudness pumping. Centre sits 3 dB below each edge, which is exactly
    what a correct pan law does. The old scheme instead held the near channel
    at 1.0 and ducked the far channel to 0.15: that pumped +2.91 dB per
    sweep, gave LESS directional cue mid-stroke (4.81 dB vs 7.66 dB here),
    and was a duck, not a pan.

    SMOOTHING -- the GAINS are ramped PER SAMPLE toward the new target with a
    one-pole of time constant ``pan_smooth_ms``. Because the target is
    constant within a block, the recursion has an exact closed form

        g[n] = target + (g_prev - target) * alpha ** (n + 1)

    so it is one cached power-vector multiply: no Python loop on the audio
    thread, and no per-block gain STEP -- that step (up to 0.78 dB) was the
    zipper artefact.

    TRAVEL is full. At pan = -1, gain_R = sin(0) = 0.0. The quiet side really
    goes quiet. There is no floor; the old 0.15 floor is what kept the
    "silent" side always audible.

    SACRED AUDIO LAW: this engine opens ONE output stream and writes its own
    samples into it. It never reads or writes a master volume, an endpoint
    channel volume, or any other system mixer setting, and never opens an
    input device. It can only make EMDR's own sound quieter or louder --
    never his.
    """

    #: master fade applied at start/stop so the tone never clicks in or out
    ENV_TAU_S = 0.008
    #: length of the pre-rendered Whoosh noise loop, seconds
    NOISE_SECONDS = 8
    MAX_CLICK_VOICES = 8

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pan = 0.0
        self._mode = "Sine"
        self._vol = 0.1
        self._click_vol = 0.55
        self._smooth_ms = float(PAN_SMOOTH_MS_DEFAULT)
        self._phase_sine = 0.0
        self._phase_over = 0.0
        # smoothed gain state, carried across blocks. Start centred.
        self._gL = math.cos(math.pi / 4.0)
        self._gR = math.sin(math.pi / 4.0)
        self._env = 0.0
        self._env_target = 1.0
        self._alpha_cache: dict = {}
        self._noise = None
        self._noise_i = 0
        self._click = None
        self._click_name = None
        self._pending_clicks: list = []
        self._voices: list = []
        self._stream = None
        self._active = False
        self._cb_error: str | None = None
        self.set_click_sound("Beep")

    # ---------- settings (all called from the Qt thread) ----------
    def set_pan(self, pan: float) -> None:
        with self._lock:
            self._pan = max(-1.0, min(1.0, float(pan)))

    def set_mode(self, mode: str) -> None:
        mode = mode if mode in PAN_MODES else "Sine"
        if mode == "Whoosh":
            self._ensure_noise()      # build OFF the audio thread
        with self._lock:
            self._mode = mode

    def set_volume_pct(self, pct: int) -> None:
        lin = 0.1 * max(0, min(100, int(pct))) / 100.0
        with self._lock:
            self._vol = lin

    def set_smooth_ms(self, ms: float) -> None:
        with self._lock:
            self._smooth_ms = max(1.0, min(200.0, float(ms)))
            self._alpha_cache.clear()

    def set_click_volume(self, v: float) -> None:
        with self._lock:
            self._click_vol = max(0.0, min(1.0, float(v)))

    def set_click_sound(self, name: str) -> None:
        if name == self._click_name and self._click is not None:
            return
        freq = float(SOUND_FREQS.get(name, SOUND_FREQS["Beep"]))
        n = int(SAMPLE_RATE * BEEP_MS / 1000)
        fade = max(1, int(SAMPLE_RATE * 0.015))
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        env = np.ones(n, dtype=np.float64)
        env[:fade] = np.linspace(0.0, 1.0, fade, endpoint=False)
        env[n - fade:] = np.linspace(1.0, 0.0, fade)
        wave_ = 0.35 * env * np.sin(2.0 * math.pi * freq * t)
        with self._lock:
            self._click = wave_
            self._click_name = name

    def trigger_click(self, side: str) -> None:
        """Queue an edge click, hard-panned to the side the orb reached.

        This is the bilateral cue -- the whole point of the instrument -- and
        it used to be a MONO QSoundEffect sitting dead centre. It only ever
        seemed to move because the system-wide duck was swinging the entire
        output device underneath it.
        """
        with self._lock:
            if len(self._pending_clicks) < self.MAX_CLICK_VOICES:
                self._pending_clicks.append("R" if side == "R" else "L")

    # ---------- lifecycle ----------
    def start(self) -> bool:
        if self._active:
            return True
        if not _SD_OK:
            log("BilateralEngine: sounddevice unavailable -- no EMDR tone")
            return False
        with self._lock:
            need_noise = (self._mode == "Whoosh") and (self._noise is None)
        if need_noise:
            self._ensure_noise()
        with self._lock:
            self._gL = math.cos(math.pi / 4.0)
            self._gR = math.sin(math.pi / 4.0)
            self._pan = 0.0
            self._env = 0.0
            self._env_target = 1.0
            self._voices = []
            self._pending_clicks = []
            self._cb_error = None
        try:
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=2,
                blocksize=AUDIO_BLOCKSIZE, dtype="float32",
                latency="low", callback=self._callback,
            )
            self._stream.start()
            self._active = True
            log(f"BilateralEngine started: equal-power pan, "
                f"{self._smooth_ms:.0f} ms smoothing, tone={self._mode}")
            return True
        except Exception as e:
            log(f"BilateralEngine start error: {e!r}")
            self._stream = None
            self._active = False
            return False

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                with self._lock:
                    self._env_target = 0.0
                time.sleep(0.06)      # let the 8 ms fade reach the device
            except Exception:
                pass
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._active = False
        with self._lock:
            err, self._cb_error = self._cb_error, None
            self._voices = []
            self._pending_clicks = []
        if err:
            # sounddevice normally prints callback tracebacks to sys.stderr,
            # which is None in this windowed build -- they used to vanish.
            # Now they are captured on the audio thread and logged from here.
            log(f"BilateralEngine callback error:\n{err}")

    def is_active(self) -> bool:
        return self._active

    # ---------- DSP ----------
    def _ensure_noise(self) -> None:
        """Pre-render the Whoosh noise loop ONCE, off the audio thread.

        The old code ran a 512-iteration Python for-loop plus a
        standard_normal() allocation INSIDE the sounddevice callback -- about
        44 000 interpreted iterations per second on the real-time thread,
        with dropout risk. A one-pole lowpass y[n] = y[n-1] + a(x[n] - y[n-1])
        has impulse response a*(1-a)^k, so the whole thing is one convolution
        computed up front; the callback then just reads a slice.
        """
        if self._noise is not None:
            return
        t0 = time.perf_counter()
        try:
            a = 0.08
            k_len = 192                   # 0.92**192 ~ 1e-7: fully decayed
            n = int(SAMPLE_RATE * self.NOISE_SECONDS)
            rng = np.random.default_rng(1)
            white = rng.standard_normal(n + k_len - 1)
            kern = a * (1.0 - a) ** np.arange(k_len, dtype=np.float64)
            noise = np.convolve(white, kern, mode="valid")[:n] * 1.5
            with self._lock:
                self._noise = noise
                self._noise_i = int(rng.integers(0, n))
            log(f"Whoosh noise loop built ({self.NOISE_SECONDS}s) in "
                f"{time.perf_counter() - t0:.2f}s")
        except Exception as e:
            log(f"Whoosh noise build failed: {e!r} -- tone falls back to Sine")
            with self._lock:
                self._mode = "Sine"

    def _alpha_curve(self, frames: int, smooth_ms: float) -> np.ndarray:
        """alpha ** (1..frames) for the one-pole gain ramp. Cached."""
        key = (frames, round(smooth_ms, 3))
        curve = self._alpha_cache.get(key)
        if curve is None:
            tau = max(0.001, smooth_ms / 1000.0)
            alpha = math.exp(-1.0 / (tau * SAMPLE_RATE))
            curve = alpha ** np.arange(1, frames + 1, dtype=np.float64)
            if len(self._alpha_cache) > 8:
                self._alpha_cache.clear()
            self._alpha_cache[key] = curve
        return curve

    def _env_curve(self, frames: int) -> np.ndarray:
        key = ("env", frames)
        curve = self._alpha_cache.get(key)
        if curve is None:
            alpha = math.exp(-1.0 / (self.ENV_TAU_S * SAMPLE_RATE))
            curve = alpha ** np.arange(1, frames + 1, dtype=np.float64)
            self._alpha_cache[key] = curve
        return curve

    def render(self, frames: int) -> np.ndarray:
        """Produce one stereo block. PURE numpy -- no device, no I/O.

        Deliberately separate from the callback so the pan law can be
        rendered to a WAV file and measured offline, without ever opening an
        audio device.
        """
        with self._lock:
            pan = self._pan
            mode = self._mode
            vol = self._vol
            smooth_ms = self._smooth_ms
            click_vol = self._click_vol
            click = self._click
            pending = self._pending_clicks
            self._pending_clicks = []
            noise = self._noise
            env_target = self._env_target

        # --- equal-power target gains, ramped per sample ---
        theta = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
        tgt_l = math.cos(theta)
        tgt_r = math.sin(theta)
        apow = self._alpha_curve(frames, smooth_ms)
        gl = tgt_l + (self._gL - tgt_l) * apow
        gr = tgt_r + (self._gR - tgt_r) * apow
        self._gL = float(gl[-1])
        self._gR = float(gr[-1])

        # --- continuous tone ---
        if mode == "Off" or vol <= 1e-6:
            mono = np.zeros(frames, dtype=np.float64)
        elif mode == "Sine" or noise is None:
            t_step = 1.0 / SAMPLE_RATE
            f1, f2 = 220.0, 440.0
            idx = np.arange(frames, dtype=np.float64)
            ph1 = self._phase_sine + 2.0 * math.pi * f1 * idx * t_step
            ph2 = self._phase_over + 2.0 * math.pi * f2 * idx * t_step
            mono = (0.85 * np.sin(ph1) + 0.25 * np.sin(ph2)) * vol
            self._phase_sine = (self._phase_sine
                                + 2.0 * math.pi * f1 * frames * t_step) % (2.0 * math.pi)
            self._phase_over = (self._phase_over
                                + 2.0 * math.pi * f2 * frames * t_step) % (2.0 * math.pi)
        else:
            n = noise.size
            i = self._noise_i % n
            if i + frames <= n:
                mono = noise[i:i + frames] * vol
                self._noise_i = i + frames
            else:
                tail = n - i
                mono = np.concatenate((noise[i:], noise[:frames - tail])) * vol
                self._noise_i = frames - tail

        stereo = np.empty((frames, 2), dtype=np.float64)
        stereo[:, 0] = mono * gl
        stereo[:, 1] = mono * gr

        # --- edge clicks: hard-panned to the side that fired ---
        if click is not None:
            for side in pending:
                if len(self._voices) >= self.MAX_CLICK_VOICES:
                    break
                # pan = -1 -> (1, 0); pan = +1 -> (0, 1). Same law, endpoints.
                self._voices.append([0,
                                     0.0 if side == "R" else click_vol,
                                     click_vol if side == "R" else 0.0])
            if self._voices:
                keep = []
                clen = click.size
                for voice in self._voices:
                    pos, cl, cr = voice
                    take = min(frames, clen - pos)
                    if take > 0:
                        seg = click[pos:pos + take]
                        stereo[:take, 0] += seg * cl
                        stereo[:take, 1] += seg * cr
                    voice[0] = pos + frames
                    if voice[0] < clen:
                        keep.append(voice)
                self._voices = keep

        # --- master fade so start/stop never clicks ---
        if abs(self._env - env_target) > 1e-4:
            ecurve = self._env_curve(frames)
            env = env_target + (self._env - env_target) * ecurve
            self._env = float(env[-1])
            stereo *= env[:, None]
        elif env_target < 0.5:
            stereo[:] = 0.0

        np.clip(stereo, -1.0, 1.0, out=stereo)
        return stereo.astype(np.float32)

    def _callback(self, outdata, frames, time_info, status) -> None:
        try:
            outdata[:] = self.render(frames)
        except Exception:
            outdata[:] = 0.0
            try:
                with self._lock:
                    if self._cb_error is None:
                        self._cb_error = traceback.format_exc()
            except Exception:
                pass


# ------------- screen luminance -------------
def analyze_path_luminance(band_y: int, band_h: int, x_min: int, x_max: int) -> tuple[float, str]:
    screen = QApplication.primaryScreen()
    if screen is None: return 128.0, "mixed"
    pixmap = screen.grabWindow(0)
    if pixmap.isNull(): return 128.0, "mixed"
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    W = img.width(); H = img.height()
    cy = max(0, min(H - 1, band_y + band_h // 2))
    samples = []
    n = 20
    for i in range(n):
        t = i / (n - 1)
        x = max(0, min(W - 1, int(x_min + (x_max - x_min) * t)))
        c = QColor(img.pixel(x, cy))
        lum = 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()
        samples.append(lum)
    mean = sum(samples) / len(samples)
    spread = max(samples) - min(samples)
    if spread > 100: decision = "mixed"
    elif mean > 150: decision = "light"
    elif mean < 90: decision = "dark"
    else: decision = "mixed"
    return mean, decision


# ------------- settings dialog with Music tab -------------
class SettingsDialog(QDialog):
    def __init__(self, parent, controller: "EmdrController"):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("EMDR Settings")
        self.resize(560, 520)
        self.setStyleSheet(
            "QDialog { background: #1e1e1e; color: #ddd; } "
            "QLabel, QCheckBox { color: #ddd; } "
            "QSpinBox, QComboBox, QListWidget, QPushButton "
            "{ background: #2a2a2a; color: #eee; border: 1px solid #444; padding: 3px; } "
            "QPushButton:hover { background: #3a3a3a; } "
            "QTabWidget::pane { border: 1px solid #444; } "
            "QTabBar::tab { background: #2a2a2a; color: #ccc; padding: 6px 12px; } "
            "QTabBar::tab:selected { background: #8B0000; color: #fff; }"
        )
        self.settings = dict(controller.settings)
        self.beep_paths = controller.beep_paths
        self._test_effect = QSoundEffect(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_main_tab(), "Main")
        tabs.addTab(self._build_music_tab(), "Music")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(bb)

    # --- Main tab (unchanged options) ---
    def _build_main_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.duration = QSlider(Qt.Orientation.Horizontal)
        self.duration.setRange(30, 300)
        self.duration.setValue(_as_int(self.settings.get("duration_sec"), 90, 30, 300))
        self.dur_lbl = QLabel(f"{self.duration.value()} s")
        self.duration.valueChanged.connect(lambda v: self.dur_lbl.setText(f"{v} s"))
        form.addRow("Duration:", self._row(self.duration, self.dur_lbl))

        self.hz = QSlider(Qt.Orientation.Horizontal)
        self.hz.setRange(5, 20)
        self.hz.setValue(_as_int(_as_float(self.settings.get("sweep_hz"), 1.0,
                                           0.5, 2.0) * 10, 10, 5, 20))
        self.hz_lbl = QLabel(f"{self.hz.value()/10:.1f} Hz")
        self.hz.valueChanged.connect(lambda v: self.hz_lbl.setText(f"{v/10:.1f} Hz"))
        form.addRow("Sweep rate:", self._row(self.hz, self.hz_lbl))

        self.sound = QComboBox(); self.sound.addItems(list(SOUND_FREQS.keys()))
        _snd = self.settings.get("edge_sound", "Beep")
        self.sound.setCurrentText(_snd if _snd in SOUND_FREQS else "Beep")
        test_btn = QPushButton("Test"); test_btn.clicked.connect(self._test_sound)
        form.addRow("Edge sound:", self._row(self.sound, test_btn))

        # --- where the bilateral sound comes OUT ---
        self.pan_out = QComboBox()
        self.pan_out.addItems(PAN_OUT_MODES)
        cur_out = self.settings.get("pan_output_mode", PAN_OUT_TONE)
        self.pan_out.setCurrentText(
            cur_out if cur_out in PAN_OUT_MODES else PAN_OUT_TONE)
        form.addRow("Bilateral sound:", self.pan_out)

        self.sc_optin = QCheckBox("Enable System-audio mode")
        self.sc_optin.setChecked(bool(self.settings.get("soundcard_optin", False)))
        if not _SCP_OK:
            self.sc_optin.setEnabled(False)
            self.sc_optin.setChecked(False)
        scp_status = "module OK" if _SCP_OK else "module MISSING"
        form.addRow(f"Advanced ({scp_status}):", self.sc_optin)

        self.sc_warn = QLabel(
            "System-audio mode changes the Windows per-channel volume of your "
            "DEFAULT OUTPUT DEVICE. It swings EVERY app on the machine - your "
            "music, your browser, everything - not just EMDR, and it writes to "
            "a system mixer setting. The recommended mode pans EMDR's own tone "
            "and leaves your speakers alone."
        )
        self.sc_warn.setWordWrap(True)
        self.sc_warn.setStyleSheet("color: #e0a030;")
        form.addRow("", self.sc_warn)

        self.pan_mode = QComboBox(); self.pan_mode.addItems(PAN_MODES)
        self.pan_mode.setCurrentText(self.settings.get("pan_mode", "Sine"))
        form.addRow("EMDR tone waveform:", self.pan_mode)

        self.pan_vol = QSlider(Qt.Orientation.Horizontal)
        self.pan_vol.setRange(0, 100)
        self.pan_vol.setValue(_as_int(self.settings.get("pan_volume_pct"), 30, 0, 100))
        self.pan_vol_lbl = QLabel(f"{self.pan_vol.value()}%")
        self.pan_vol.valueChanged.connect(lambda v: self.pan_vol_lbl.setText(f"{v}%"))
        form.addRow("EMDR tone volume:", self._row(self.pan_vol, self.pan_vol_lbl))

        self.smooth = QSpinBox()
        self.smooth.setRange(1, 200)
        self.smooth.setValue(_as_int(self.settings.get("pan_smooth_ms"),
                                     PAN_SMOOTH_MS_DEFAULT, 1, 200))
        self.smooth.setSuffix(" ms")
        form.addRow("Pan smoothing:", self.smooth)

        tp_main = QPushButton("Test bilateral pan (5 sec)")
        tp_main.clicked.connect(self._test_pan)
        form.addRow("", tp_main)

        self.seed = QSpinBox(); self.seed.setRange(0, 999999)
        self.seed.setValue(_as_int(self.settings.get("seed"), 42, 0, 999999))
        form.addRow("Seed:", self.seed)

        self.orb_size = QSpinBox(); self.orb_size.setRange(12, 40)
        self.orb_size.setValue(_as_int(self.settings.get("orb_size"), 22, 12, 40))
        form.addRow("Orb size (px):", self.orb_size)

        self.amp = QSlider(Qt.Orientation.Horizontal)
        self.amp.setRange(50, 100)
        self.amp.setValue(_as_int(self.settings.get("amplitude_pct"), 95, 50, 100))
        self.amp_lbl = QLabel(f"{self.amp.value()}%")
        self.amp.valueChanged.connect(lambda v: self.amp_lbl.setText(f"{v}%"))
        form.addRow("Amplitude:", self._row(self.amp, self.amp_lbl))

        self.auto = QCheckBox("Auto color")
        self.auto.setChecked(bool(self.settings.get("auto_color", True)))
        form.addRow("", self.auto)
        return w

    # --- Music tab ---
    def _build_music_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        # source dropdown + add buttons
        src_row = QHBoxLayout()
        self.quick_src = QComboBox()
        self.quick_src.addItems(["File...", "Scan folder...", "Last music_daemon track"])
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_source)
        src_row.addWidget(QLabel("Add:")); src_row.addWidget(self.quick_src, 1); src_row.addWidget(add_btn)
        root.addLayout(src_row)

        # playlist — populated lazily in chunks to keep tab-open snappy even
        # with 10k+ tracks. Uniform item sizes + no tooltip-per-item at fill
        # time (tooltip set on demand) — avoids blocking the UI thread.
        import time as _t
        _t0 = _t.perf_counter()
        self.playlist = QListWidget()
        self.playlist.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.playlist.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.playlist.setUniformItemSizes(True)
        self.playlist.itemDoubleClicked.connect(self._on_playlist_dblclick)
        # Chunked async fill
        self._pending_paths = list(self.controller.playlist)
        self._fill_timer = QTimer(self)
        self._fill_timer.setInterval(0)
        self._fill_timer.timeout.connect(self._fill_chunk)
        if self._pending_paths:
            self._fill_timer.start()
        root.addWidget(self.playlist, 1)
        # CRASH FIX 2026-09-01 (Iddo: "היא קורסת כשאני לוחץ SETTINGS").
        # PyInstaller builds this with console=False, and in a WINDOWED build
        # sys.stderr is None -- so this line raised AttributeError the instant
        # the Settings dialog built its Music tab, killing the whole process
        # with no traceback anywhere (no console to print one to). log() writes
        # to the file the app already keeps. Never stderr in this app again.
        log(f"Music tab built with {len(self._pending_paths)} pending "
            f"tracks in {_t.perf_counter()-_t0:.3f}s (async fill)")

        # list buttons
        lst_row = QHBoxLayout()
        rm_btn = QPushButton("Remove"); rm_btn.clicked.connect(self._remove_selected)
        clr_btn = QPushButton("Clear"); clr_btn.clicked.connect(self._clear_playlist)
        lst_row.addWidget(rm_btn); lst_row.addWidget(clr_btn); lst_row.addStretch(1)
        root.addLayout(lst_row)

        # transport
        tr = QHBoxLayout()
        for label, slot in [("Prev", self.controller.music_prev),
                            ("Play", self._on_play_selected),
                            ("Pause", self.controller.music_toggle_pause),
                            ("Stop", self.controller.music_stop),
                            ("Next", self.controller.music_next)]:
            b = QPushButton(label); b.clicked.connect(slot); tr.addWidget(b)
        self.shuffle_cb = QCheckBox("Shuffle")
        self.shuffle_cb.setChecked(bool(self.settings.get("shuffle", False)))
        self.shuffle_cb.stateChanged.connect(
            lambda v: self.controller.set_shuffle(bool(v)))
        tr.addWidget(self.shuffle_cb)
        root.addLayout(tr)

        # volume
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("Volume:"))
        self.mvol = QSlider(Qt.Orientation.Horizontal)
        self.mvol.setRange(0, 100)
        self.mvol.setValue(_as_int(self.settings.get("music_volume_pct"), 70, 0, 100))
        self.mvol_lbl = QLabel(f"{self.mvol.value()}%")
        def _vol_ch(v):
            self.mvol_lbl.setText(f"{v}%")
            self.controller.music.set_volume_pct(v)
        self.mvol.valueChanged.connect(_vol_ch)
        vrow.addWidget(self.mvol, 1); vrow.addWidget(self.mvol_lbl)
        root.addLayout(vrow)

        # test pan button
        tp = QPushButton("Test Pan (5 sec L<->R demo)")
        tp.clicked.connect(self._test_pan)
        root.addWidget(tp)

        root.addWidget(QLabel(f"Music engine: {self.controller.music.status_text()}"))
        return w

    # --- helpers ---
    @staticmethod
    def _row(*widgets):
        lay = QHBoxLayout()
        for wd in widgets: lay.addWidget(wd)
        box = QWidget(); box.setLayout(lay); return box

    def _add_item(self, path: str):
        if not path: return
        it = QListWidgetItem(Path(path).name)
        it.setData(Qt.ItemDataRole.UserRole, path)
        # Tooltip omitted at fill time — set lazily on demand to avoid
        # 10k-item UI stalls. Full path still accessible via UserRole.
        self.playlist.addItem(it)

    def _fill_chunk(self):
        # Append up to N items per tick so the UI stays responsive.
        CHUNK = 500
        if not self._pending_paths:
            self._fill_timer.stop()
            return
        batch = self._pending_paths[:CHUNK]
        self._pending_paths = self._pending_paths[CHUNK:]
        for p in batch:
            self._add_item(p)
        if not self._pending_paths:
            self._fill_timer.stop()

    def _playlist_paths(self) -> list[str]:
        # Include items already in the widget PLUS any still-pending async-fill
        # items so that accepting the dialog before fill completes does not
        # truncate a 10k playlist.
        filled = [self.playlist.item(i).data(Qt.ItemDataRole.UserRole)
                  for i in range(self.playlist.count())]
        return filled + list(getattr(self, "_pending_paths", []))

    def _stop_fill(self):
        """Freeze the chunked async fill and fold what is left into the widget.

        BUG this fixes: Clear and Remove only touched the QListWidget, while
        _fill_timer kept appending from _pending_paths AND _playlist_paths()
        returned ``filled + _pending_paths``. Cleared or removed tracks came
        straight back and were saved to playlist.json on OK.
        """
        try:
            self._fill_timer.stop()
        except Exception:
            pass
        pending = list(getattr(self, "_pending_paths", []))
        self._pending_paths = []
        for p in pending:
            self._add_item(p)

    def _clear_playlist(self):
        self._stop_fill()
        self.playlist.clear()

    def _remove_selected(self):
        self._stop_fill()
        for it in self.playlist.selectedItems():
            self.playlist.takeItem(self.playlist.row(it))

    def _on_add_source(self):
        src = self.quick_src.currentText()
        if src == "File...":
            files, _ = QFileDialog.getOpenFileNames(
                self, "Pick audio files", str(Path.home()),
                "Audio (*.mp3 *.flac *.wav *.m4a *.ogg *.opus *.aac)")
            for f in files: self._add_item(f)
        elif src == "Scan folder...":
            folder = QFileDialog.getExistingDirectory(self, "Pick folder", str(Path.home()))
            if folder:
                added = 0
                for root, _, files in os.walk(folder):
                    for f in sorted(files):
                        if Path(f).suffix.lower() in AUDIO_EXTS:
                            self._add_item(str(Path(root) / f)); added += 1
                log(f"scan added {added} tracks from {folder}")
        elif src == "Last music_daemon track":
            q = music_daemon_last_query()
            if q and Path(q).exists():
                self._add_item(q)
            else:
                log(f"music_daemon last query not a local file: {q!r}")

    def _on_playlist_dblclick(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        idx = self.playlist.row(item)
        self.controller.playlist = self._playlist_paths()
        self.controller.playlist_index = idx
        self.controller.music_play_path(path)

    def _on_play_selected(self):
        row = self.playlist.currentRow()
        self.controller.playlist = self._playlist_paths()
        if row < 0 and self.playlist.count() > 0:
            row = 0
        if row >= 0:
            self.controller.playlist_index = row
            self.controller.music_play_path(self._playlist_paths()[row])

    def _test_sound(self):
        name = self.sound.currentText()
        p = self.beep_paths.get(name)
        if p:
            self._test_effect.setSource(QUrl.fromLocalFile(str(p)))
            self._test_effect.setVolume(0.55)
            self._test_effect.play()

    def _test_pan(self):
        self.controller.playlist = self._playlist_paths()
        self.controller.test_pan()

    def accept(self):
        self.controller.playlist = self._playlist_paths()
        save_playlist(self.controller.playlist)
        super().accept()

    def result_settings(self) -> dict:
        return {
            "duration_sec": self.duration.value(),
            "sweep_hz": self.hz.value() / 10.0,
            "edge_sound": self.sound.currentText(),
            "seed": self.seed.value(),
            "orb_size": self.orb_size.value(),
            "amplitude_pct": self.amp.value(),
            "auto_color": self.auto.isChecked(),
            "pan_mode": self.pan_mode.currentText(),
            "pan_volume_pct": self.pan_vol.value(),
            "music_volume_pct": self.mvol.value(),
            "shuffle": self.shuffle_cb.isChecked(),
            "pan_output_mode": self.pan_out.currentText(),
            "soundcard_optin": self.sc_optin.isChecked(),
            "pan_smooth_ms": self.smooth.value(),
        }


# ------------- distress button -------------
class DistressButton(QWidget):
    def __init__(self, controller: "EmdrController") -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.controller = controller
        self._drag_offset: QPointF | None = None
        self._press_pos: QPointF | None = None
        self._moved = False
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - BUTTON_SIZE - 24, screen.bottom() - BUTTON_SIZE - 80)

    def paintEvent(self, _ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(3, 3, -3, -3)
        grad = QRadialGradient(QPointF(r.center()), r.width() / 2)
        grad.setColorAt(0.0, QColor(180, 20, 20)); grad.setColorAt(1.0, QColor(90, 0, 0))
        p.setBrush(QBrush(grad)); p.setPen(QPen(QColor(0, 0, 0), 2.5))
        p.drawEllipse(r)
        p.setPen(QPen(QColor(139, 0, 0, 90), 1)); p.drawEllipse(r.adjusted(-2, -2, 2, 2))
        p.setPen(QPen(QColor(255, 240, 240), 2))
        font = p.font(); font.setBold(True); font.setPointSize(9); p.setFont(font)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "SOS")

    def mousePressEvent(self, ev):
        if ev.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._drag_offset = ev.globalPosition() - QPointF(self.pos())
            self._press_pos = ev.globalPosition(); self._moved = False

    def mouseMoveEvent(self, ev):
        if self._drag_offset is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            new = ev.globalPosition() - self._drag_offset
            self.move(int(new.x()), int(new.y()))
            if (ev.globalPosition() - self._press_pos).manhattanLength() > 5:
                self._moved = True

    def mouseReleaseEvent(self, ev):
        if self._drag_offset is None: return
        moved = self._moved; self._drag_offset = None; self._moved = False
        if moved: return
        gp = ev.globalPosition().toPoint()
        if ev.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.controller.show_menu(gp)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.controller.start_sequence()


# ------------- EMDR sweep STRIP -------------
class EmdrSequence(QWidget):
    def __init__(self, controller: "EmdrController") -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowTransparentForInput
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.controller = controller
        self._beep = QSoundEffect(self); self._beep.setVolume(0.55)
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick)
        self._frame_ms = int(1000 / FPS)
        self._elapsed_ms = 0; self._duration_ms = 90_000; self._period_ms = 1000
        self._x_min = 0; self._x_max = 0; self._orb_x = 0.0
        self._orb_radius = 22; self._last_side = None
        self._orb_color = QColor(255, 255, 255)
        self._ring_color = QColor(0, 0, 0)
        self._amp_jitter = 0.0
        self._rng = random.Random()
        self._pan_consumers: list = []
        self._click_mode = "qt"

    def start(self, settings: dict, beep_path: Path, pan_consumers: list,
              click_mode: str = "qt") -> None:
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(0, STRIP_Y, screen.width(), STRIP_H)
        # Every read below is coerced. A settings.json holding a string or a
        # zero here used to kill the process on Start (int(1000 / 0)).
        amp_pct = _as_int(settings.get("amplitude_pct"), 95, 50, 100) / 100.0
        full = screen.width() - 2 * EDGE_MARGIN
        used = int(full * amp_pct)
        center = screen.width() // 2
        self._x_min = center - used // 2; self._x_max = center + used // 2
        self._band_cy = STRIP_H // 2
        self._orb_radius = min(_as_int(settings.get("orb_size"), 22, 12, 40),
                               STRIP_H // 2 - 4)
        self._duration_ms = _as_int(settings.get("duration_sec"), 90, 30, 300) * 1000
        hz = _as_float(settings.get("sweep_hz"), 1.0, 0.5, 2.0)
        self._period_ms = max(1, int(1000 / hz))
        self._click_mode = click_mode if click_mode in ("engine", "qt", "none") else "qt"
        self._rng.seed(_as_int(settings.get("seed"), 42, 0, 999999))
        self._amp_jitter = self._rng.uniform(-0.02, 0.02)

        if settings.get("auto_color", True):
            mean_lum, decision = analyze_path_luminance(STRIP_Y, STRIP_H, self._x_min, self._x_max)
            if decision == "light":
                self._orb_color = QColor(0, 0, 0); self._ring_color = QColor(255, 255, 255)
            elif decision == "dark":
                self._orb_color = QColor(255, 213, 128); self._ring_color = None
            else:
                if mean_lum > 128:
                    self._orb_color = QColor(0, 0, 0); self._ring_color = QColor(255, 255, 255)
                else:
                    self._orb_color = QColor(255, 213, 128); self._ring_color = None
        else:
            self._orb_color = QColor(255, 213, 128); self._ring_color = QColor(0, 0, 0)

        self._beep.setSource(QUrl.fromLocalFile(str(beep_path)))
        self._pan_consumers = pan_consumers
        self._elapsed_ms = 0; self._last_side = None
        self._orb_x = float(self._x_min)
        self.show(); self._timer.start(self._frame_ms)

    def stop(self) -> None:
        self._timer.stop(); self.hide()

    def _tick(self) -> None:
        self._elapsed_ms += self._frame_ms
        if self._elapsed_ms >= self._duration_ms:
            self.stop(); self.controller.on_sequence_finished(); return
        t = self._elapsed_ms / 1000.0
        mid = (self._x_min + self._x_max) / 2.0
        base_amp = (self._x_max - self._x_min) / 2.0
        amp = base_amp * (1.0 + self._amp_jitter)
        phase = 2 * math.pi * t * 1000.0 / self._period_ms
        swing = math.sin(phase)
        self._orb_x = mid + amp * swing

        if base_amp > 0:
            pan = (self._orb_x - mid) / base_amp
            for pc in self._pan_consumers:
                try: pc.set_pan(pan)
                except Exception: pass

        # THE EDGE, FROM THE PHASE - NOT FROM A PIXEL BAND (fixed 2026-09-01).
        # The old test asked whether the orb had entered a 6 px band at _x_min /
        # _x_max. But the orb swings by amp = base_amp * (1 + _amp_jitter), and
        # _amp_jitter is rng.uniform(-0.02, +0.02) drawn from the user's seed. On
        # every NEGATIVE draw the orb never reaches those extremes at all, the band
        # is never entered, _last_side stays None, and the session runs to the end
        # with NO beep and NO bilateral cue whatsoever. Measured: seeds 1, 3 and 7
        # never fire; roughly a third of all seeds are silent. In a therapy tool
        # the alternating cue IS the treatment, so a third of sessions were doing
        # nothing at all - and this is the true face of "the panning is not good".
        #
        # sin(phase) reaches exactly -1 and +1 no matter what the jitter, the window
        # size or the DPI are, so the phase test cannot be defeated by any of them.
        # 0.985 is the browser's own threshold in ALMA-EMDR.html, kept identical on
        # purpose: every client must put the buzz in the same place.
        EDGE_SWING = 0.985
        if swing <= -EDGE_SWING:
            if self._last_side != "L":
                self._last_side = "L"; self._edge("L")
        elif swing >= EDGE_SWING:
            if self._last_side != "R":
                self._last_side = "R"; self._edge("R")
        elif abs(swing) < 0.3:
            self._last_side = None
        self.update()

    def _edge(self, side: str) -> None:
        """Fire the edge cue for the side the orb just reached.

        "engine": the click rides EMDR's own stereo stream and is panned HARD
        to that ear - the alternating cue is the point of the instrument, and
        it was previously a mono QSoundEffect stuck dead centre.
        "qt":     legacy centred QSoundEffect (system-audio mode, or no
                  sounddevice).
        "none":   Off means off - no sound at all.
        """
        if self._click_mode == "engine":
            try:
                self.controller.bilateral.trigger_click(side)
            except Exception as e:
                log(f"edge click failed: {e!r}")
        elif self._click_mode == "qt":
            if self._beep.isLoaded():
                self._beep.play()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self._orb_x; cy = self._band_cy; R = self._orb_radius
        glow = QRadialGradient(QPointF(cx, cy), R * 2.2)
        c = self._orb_color
        glow.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 230))
        glow.setColorAt(0.35, QColor(c.red(), c.green(), c.blue(), 110))
        glow.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setBrush(QBrush(glow)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R * 2.2, R * 2.2)
        core = QRadialGradient(QPointF(cx, cy), R)
        core.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 255))
        core.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 200))
        p.setBrush(QBrush(core))
        if self._ring_color is not None:
            p.setPen(QPen(self._ring_color, 2))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)


# ------------- tray icon -------------
def _build_tray_icon() -> QIcon:
    pm = QPixmap(32, 32); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(139, 0, 0))); p.setPen(QPen(QColor(0, 0, 0), 2))
    p.drawEllipse(2, 2, 28, 28); p.end()
    return QIcon(pm)


# ------------- controller -------------
class _PanTap:
    """Pan consumer that only records the orb position, for the soundcard
    worker thread to sample. Module level so it is not rebuilt per sweep."""

    def __init__(self, ctrl) -> None:
        self.ctrl = ctrl

    def set_pan(self, p: float) -> None:
        self.ctrl._current_orb_pan = float(p)



class EmdrController:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.settings = load_settings()
        self.beep_paths = ensure_beep_files()
        self.playlist: list[str] = load_playlist()
        self.playlist_index = 0
        self._daemon_was_playing = False
        self._test_pan_timer: QTimer | None = None
        self._current_orb_pan: float = 0.0
        self._soundcard_active: bool = False

        # If a previous run was killed mid-sweep while System-audio mode was
        # active, one channel of his output device may still be sitting at the
        # panned value. soundcard_pan now writes the pre-sweep volumes to disk
        # before it touches anything, so we can put them back on next launch.
        if _SCP_OK:
            try:
                soundcard_pan.set_log_fn(log)
                soundcard_pan.set_residue_path(str(SOUNDCARD_RESIDUE))
                soundcard_pan.recover_residue()
            except Exception as e:
                log(f"soundcard residue recovery failed: {e!r}")

        smooth_ms = _as_int(self.settings.get("pan_smooth_ms"),
                            PAN_SMOOTH_MS_DEFAULT, 1, 200)
        self.music = MusicEngine()
        self.music.set_volume_pct(_as_int(self.settings.get("music_volume_pct"), 70, 0, 100))
        self.music.set_smooth_ms(smooth_ms)
        self.bilateral = BilateralEngine()
        self.bilateral.set_mode(self.settings.get("pan_mode", "Sine"))
        self.bilateral.set_volume_pct(_as_int(self.settings.get("pan_volume_pct"), 30, 0, 100))
        self.bilateral.set_smooth_ms(smooth_ms)
        self.bilateral.set_click_sound(self.settings.get("edge_sound", "Beep"))

        self.button = DistressButton(self)
        self.sequence = EmdrSequence(self)
        self._running = False

        # auto-advance poll
        self._advance_timer = QTimer()
        self._advance_timer.timeout.connect(self._auto_advance)
        self._advance_timer.start(1000)

        self.tray = QSystemTrayIcon(_build_tray_icon())
        self.tray.setToolTip("EMDR Widget")
        tm = QMenu()
        tm.addAction("Show", self.show_button)
        tm.addAction("Start EMDR", self.start_sequence)
        tm.addAction("Stop EMDR", self.stop_sequence)
        tm.addAction("Settings...", self.open_settings)
        tm.addSeparator()
        tm.addAction("Exit", self.exit_app)
        self.tray.setContextMenu(tm)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        log(f"widget v4.1 started PID={QApplication.applicationPid()} "
            f"pg_ok={_PG_OK} sd_ok={_SD_OK} scp_ok={_SCP_OK} "
            f"playlist_len={len(self.playlist)} "
            f"pan_out={self.settings.get('pan_output_mode')!r} "
            f"base_dir={str(BASE_DIR)!r}")

    # tray/menu
    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_button()

    def show_button(self): self.button.show()

    def show_menu(self, global_pos):
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #1a1a1a; color: #eee; border: 1px solid #444; } "
                           "QMenu::item:selected { background: #8B0000; }")
        menu.addAction("Start EMDR", self.start_sequence)
        menu.addAction("Stop EMDR", self.stop_sequence)
        menu.addAction("Settings...", self.open_settings)
        menu.addSeparator()
        menu.addAction("Minimize", self.minimize_to_tray)
        menu.addAction("Close", self.exit_app)
        menu.exec(global_pos)

    def open_settings(self):
        dlg = SettingsDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.result_settings()
            save_settings(self.settings)
            smooth_ms = _as_int(self.settings.get("pan_smooth_ms"),
                                PAN_SMOOTH_MS_DEFAULT, 1, 200)
            self.bilateral.set_mode(self.settings.get("pan_mode", "Sine"))
            self.bilateral.set_volume_pct(
                _as_int(self.settings.get("pan_volume_pct"), 30, 0, 100))
            self.bilateral.set_smooth_ms(smooth_ms)
            self.bilateral.set_click_sound(self.settings.get("edge_sound", "Beep"))
            self.music.set_volume_pct(
                _as_int(self.settings.get("music_volume_pct"), 70, 0, 100))
            self.music.set_smooth_ms(smooth_ms)
            log(f"settings saved: {self.settings}")

    def minimize_to_tray(self):
        self.button.hide()
        self.tray.showMessage("EMDR", "Minimized to tray.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def exit_app(self):
        # exit_app used to log NOTHING, so a clean Close and a silent crash
        # looked identical in the log. Now they do not.
        log("exit_app requested")
        try: self.sequence.stop()
        except Exception as e: log(f"sequence.stop on exit: {e!r}")
        self._running = False
        if _SCP_OK:
            try: soundcard_pan.stop_pan()
            except Exception as e: log(f"stop_pan on exit: {e!r}")
        try: self.bilateral.stop()
        except Exception as e: log(f"bilateral.stop on exit: {e!r}")
        try: self.music.stop()
        except Exception: pass
        self.button.hide(); self.tray.hide()
        log("exit_app done")
        self.app.quit()

    # music ops
    def music_play_path(self, path: str):
        if self.music.play(path):
            self.music.set_volume_pct(self.settings.get("music_volume_pct", 70))

    def music_toggle_pause(self):
        if self.music.is_playing(): self.music.pause()
        else: self.music.unpause()

    def music_stop(self): self.music.stop()

    def music_next(self):
        if not self.playlist: return
        if self.settings.get("shuffle"):
            self.playlist_index = random.randrange(len(self.playlist))
        else:
            self.playlist_index = (self.playlist_index + 1) % len(self.playlist)
        self.music_play_path(self.playlist[self.playlist_index])

    def music_prev(self):
        if not self.playlist: return
        self.playlist_index = (self.playlist_index - 1) % len(self.playlist)
        self.music_play_path(self.playlist[self.playlist_index])

    def set_shuffle(self, on: bool):
        self.settings["shuffle"] = on
        save_settings(self.settings)

    def _auto_advance(self):
        # if a track was playing, ended, and we have a playlist, go next
        if (self.playlist and self.music.available()
                and self.music.current_path()  # a track was loaded
                and not self.music.is_playing()
                and self._running_or_test()):
            # only auto-advance during sweep or test pan
            self.music_next()

    def _running_or_test(self) -> bool:
        return self._running or (self._test_pan_timer is not None and self._test_pan_timer.isActive())

    # sweep lifecycle
    def start_sequence(self):
        if self._running:
            return
        self._running = True
        self._soundcard_active = False

        mode = self.settings.get("pan_output_mode", PAN_OUT_TONE)
        if mode not in PAN_OUT_MODES:
            log(f"unknown pan_output_mode {mode!r} -> {PAN_OUT_TONE!r}")
            mode = PAN_OUT_TONE

        # ---- the system-wide endpoint mode is gated, never a default ----
        if mode == PAN_OUT_SYSTEM:
            if not self.settings.get("soundcard_optin", False):
                log("System-audio pan selected but the opt-in box is OFF "
                    "-> using EMDR's own tone")
                mode = PAN_OUT_TONE
            elif not _SCP_OK:
                log("System-audio pan selected but soundcard_pan is missing "
                    "-> using EMDR's own tone")
                mode = PAN_OUT_TONE

        # Pause our own music daemon ONLY when we are about to play a track
        # ourselves and two music sources would collide. The EMDR tone is
        # quiet and coexists -- we do not reach for his audio to make room.
        self._daemon_was_playing = False
        if mode == PAN_OUT_MUSIC:
            dmode = music_daemon_state_mode()
            self._daemon_was_playing = dmode in ("auto", "manual")
            if self._daemon_was_playing:
                music_daemon_call("pause")

        smooth_ms = _as_int(self.settings.get("pan_smooth_ms"),
                            PAN_SMOOTH_MS_DEFAULT, 1, 200)
        self.bilateral.set_smooth_ms(smooth_ms)
        self.music.set_smooth_ms(smooth_ms)

        consumers: list = []
        click_mode = "none"

        if mode == PAN_OUT_SYSTEM:
            consumers.append(_PanTap(self))
            ok = False
            try:
                ok = soundcard_pan.start_pan(
                    lambda: self._current_orb_pan, rate_hz=60.0)
            except Exception as e:
                log(f"soundcard_pan.start_pan raised: {e!r}")
            if ok:
                self._soundcard_active = True
                click_mode = "qt"
                log("sweep audio = SYSTEM ENDPOINT pan (explicit opt-in): "
                    "equal-power law, pre-sweep channel volumes saved to disk "
                    "for crash recovery. This affects EVERY app.")
            else:
                err = soundcard_pan.last_error() if soundcard_pan else "n/a"
                log(f"soundcard_pan unavailable ({err}) -> EMDR's own tone")
                consumers = []
                mode = PAN_OUT_TONE

        if mode == PAN_OUT_MUSIC:
            use_music = False
            if self.music.available() and self.playlist:
                idx = max(0, min(self.playlist_index, len(self.playlist) - 1))
                if self.music.play(self.playlist[idx]):
                    self.music.set_volume_pct(
                        _as_int(self.settings.get("music_volume_pct"), 70, 0, 100))
                    self.music.reset_pan()
                    self.playlist_index = idx
                    use_music = True
            if use_music:
                consumers.append(self.music)
                click_mode = "qt"
                log("sweep audio = MUSIC TRACK (pygame, equal-power balance, "
                    f"{smooth_ms} ms smoothing)")
            else:
                log("music engine unavailable or playlist empty "
                    "-> EMDR's own tone")
                mode = PAN_OUT_TONE

        if mode == PAN_OUT_TONE:
            self.bilateral.set_mode(self.settings.get("pan_mode", "Sine"))
            self.bilateral.set_volume_pct(
                _as_int(self.settings.get("pan_volume_pct"), 30, 0, 100))
            self.bilateral.set_click_sound(self.settings.get("edge_sound", "Beep"))
            if self.bilateral.start():
                consumers.append(self.bilateral)
                click_mode = "engine"
                log("sweep audio = EMDR TONE: own stereo stream, equal-power "
                    f"pan (cos/sin), {smooth_ms} ms per-sample smoothing, full "
                    "travel, edge click panned to the ear. No system mixer "
                    "setting is touched.")
            else:
                click_mode = "qt"
                log("BilateralEngine could not start -> visual sweep with the "
                    "legacy centred Qt beep only")
        elif mode == PAN_OUT_OFF:
            click_mode = "none"
            log("sweep audio = OFF (visual only). Off now really means off - "
                "the edge beep used to keep playing.")

        beep = self.beep_paths.get(self.settings.get("edge_sound", "Beep"),
                                   self.beep_paths["Beep"])
        self.sequence.start(self.settings, beep, consumers, click_mode)

    def stop_sequence(self):
        """Abort a running sweep.

        There was NO way to stop one before: the only exits were waiting out
        the full duration or killing the app -- and killing it during
        System-audio mode is exactly what can leave a channel volume stuck.
        """
        if not self._running:
            return
        try:
            self.sequence.stop()
        except Exception as e:
            log(f"sequence.stop error: {e!r}")
        log("sequence stopped by user")
        self.on_sequence_finished()

    def on_sequence_finished(self):
        if not self._running:
            return
        self._running = False
        if self._soundcard_active and _SCP_OK:
            try:
                soundcard_pan.stop_pan()
            except Exception as e:
                log(f"soundcard_pan.stop_pan error: {e!r}")
            self._soundcard_active = False
        try:
            self.bilateral.stop()
        except Exception as e:
            log(f"bilateral.stop error: {e!r}")
        try:
            self.music.stop()
        except Exception:
            pass
        self.music.reset_pan()
        if self._daemon_was_playing:
            music_daemon_call("resume")
            self._daemon_was_playing = False
        log("sequence finished")

    # test pan (5s)
    def test_pan(self):
        """Audition the pan for 5 seconds.

        Two fixes here. (1) It used to return silently when the playlist was
        empty -- which is every fresh install -- so the button did nothing and
        said nothing. It now auditions EMDR's own tone, which is the default
        path. (2) It only ever tested the pygame route, so the mode he
        actually got on Start could never be heard. Test deliberately never
        engages the System-audio endpoint mode: auditioning that means writing
        to his output device.
        """
        if self._running:
            log("test_pan ignored: a sweep is already running")
            return
        if self._test_pan_timer is not None and self._test_pan_timer.isActive():
            return

        mode = self.settings.get("pan_output_mode", PAN_OUT_TONE)
        smooth_ms = _as_int(self.settings.get("pan_smooth_ms"),
                            PAN_SMOOTH_MS_DEFAULT, 1, 200)
        self.bilateral.set_smooth_ms(smooth_ms)
        self.music.set_smooth_ms(smooth_ms)

        consumers: list = []
        used_music = False
        if mode == PAN_OUT_MUSIC and self.music.available() and self.playlist:
            idx = max(0, min(self.playlist_index, len(self.playlist) - 1))
            if self.music.play(self.playlist[idx]):
                self.music.set_volume_pct(
                    _as_int(self.settings.get("music_volume_pct"), 70, 0, 100))
                self.music.reset_pan()
                consumers.append(self.music)
                used_music = True

        use_engine = False
        if not consumers:
            self.bilateral.set_mode(self.settings.get("pan_mode", "Sine"))
            self.bilateral.set_volume_pct(
                _as_int(self.settings.get("pan_volume_pct"), 30, 0, 100))
            self.bilateral.set_click_sound(self.settings.get("edge_sound", "Beep"))
            if self.bilateral.start():
                consumers.append(self.bilateral)
                use_engine = True

        if not consumers:
            log("test_pan: no audio engine available (sounddevice missing and "
                "no playable track)")
            return
        if mode == PAN_OUT_SYSTEM:
            log("test_pan: auditioning EMDR's own tone. Test never engages "
                "System-audio mode - that writes to your output device.")
        log(f"test_pan started ({'music' if used_music else 'EMDR tone'}, "
            f"equal-power, {smooth_ms} ms smoothing)")

        self._tp_start_ms = 0
        self._tp_last_side = None
        self._test_pan_timer = QTimer()
        self._test_pan_timer.setInterval(int(1000 / FPS))
        hz = _as_float(self.settings.get("sweep_hz"), 1.0, 0.5, 2.0)
        period_ms = max(1, int(1000 / hz))

        def _finish():
            try:
                self._test_pan_timer.stop()
            except Exception:
                pass
            try:
                self.music.stop()
            except Exception:
                pass
            self.music.reset_pan()
            if use_engine:
                try:
                    self.bilateral.stop()
                except Exception as e:
                    log(f"test_pan bilateral.stop: {e!r}")
            log("test_pan done")

        def _step():
            try:
                self._tp_start_ms += self._test_pan_timer.interval()
                if self._tp_start_ms >= 5000:
                    _finish()
                    return
                t = self._tp_start_ms / 1000.0
                pan = math.sin(2 * math.pi * t * 1000.0 / period_ms)
                for pc in consumers:
                    pc.set_pan(pan)
                if use_engine:
                    # give him the real edge cue too, not just the drone
                    if pan <= -0.98 and self._tp_last_side != "L":
                        self._tp_last_side = "L"
                        self.bilateral.trigger_click("L")
                    elif pan >= 0.98 and self._tp_last_side != "R":
                        self._tp_last_side = "R"
                        self.bilateral.trigger_click("R")
                    elif abs(pan) < 0.3:
                        self._tp_last_side = None
            except Exception as e:
                log(f"test_pan step error: {e!r}")
                _finish()

        self._test_pan_timer.timeout.connect(_step)
        self._test_pan_timer.start()


def _selftest(ctrl: "EmdrController") -> int:
    """Headless acceptance check for a FROZEN build:  EMDR_Widget.exe --selftest

    Opens the Settings dialog exactly the way the user does, and reports
    whether it survived. This is the path that used to kill the process, and
    it can ONLY be proved on the real windowed binary: launched from a
    terminal, sys.stderr is a real stream and the bug does not reproduce at
    all. Run it detached (Start-Process) with QT_QPA_PLATFORM=offscreen.

    Opens no audio device and plays nothing.
    """
    log(f"SELFTEST begin: frozen={getattr(sys, 'frozen', False)} "
        f"stderr_is_None={sys.stderr is None} "
        f"stdout_is_None={sys.stdout is None} "
        f"qt_platform={os.environ.get('QT_QPA_PLATFORM', '(default)')!r}")
    if sys.stderr is not None:
        log("SELFTEST NOTE: sys.stderr is a REAL stream in this run, so the "
            "original crash condition is not reproduced here.")
    try:
        dlg = SettingsDialog(None, ctrl)
        vals = dlg.result_settings()
        dlg.deleteLater()
    except Exception:
        log("SELFTEST FAIL:\n" + traceback.format_exc())
        return 3
    log(f"SELFTEST OK: Settings opened and returned {len(vals)} settings; "
        f"pan_output_mode={vals.get('pan_output_mode')!r} "
        f"soundcard_optin={vals.get('soundcard_optin')!r}")
    return 0


def main() -> int:
    app = QApplication(sys.argv)
    # Iddo Unified Design System v1.0.0
    try:
        import sys as _sys
        _sys.path.insert(0, r"D:\NEWCLAUDE\DESIGN_SYSTEM")
        from qt_theme import apply_theme  # type: ignore
        apply_theme(app, mode="dark")  # EMDR is a floating tray widget — dark suits overlay
    except Exception as _e:
        log(f"theme load skipped: {_e}")
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log("WARNING: system tray not available")
    ctrl = EmdrController(app)
    if "--selftest" in sys.argv:
        rc = _selftest(ctrl)
        try:
            ctrl.tray.hide()
        except Exception:
            pass
        return rc
    ctrl.show_button()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
