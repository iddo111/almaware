"""KESHEV tray — K15 (PHASE2-DESIGN.md section 4.5 "Client top-level state
(tray honesty)", the tray.py row of section 2, the K15 row of section 10;
scars 22/49; criterion 18).

This is the part that makes KESHEV HONEST TO LOOK AT. It is the only place
where the machine tells the human what it is actually doing, and the failure
it exists to prevent is exactly one:

    a mic that has silently stopped hearing while showing a calm green icon.

Everything below is shaped by that. Three structural rules, not policies:

  1. THE TRAY CANNOT BE TOLD A STATE.  There is no set_state(). `TrayInputs`
     carries raw OBSERVATIONS only — capture state, how long since the last
     capture callback delivered a frame, the FSM's routing state, the worker
     state, the engine of the last decode that really happened. `resolve_state`
     DERIVES the state from those. No caller can hand the tray a conclusion,
     so no caller can make the tray lie.

  2. DEAFNESS IS UNMISTAKABLE AND KEEPS SHOUTING.  Two deaf-family states —
     IDLE_NO_MIC (nothing is feeding us audio) and DEAF (audio arrives, no
     engine can decode it) — both FLASH (two icon frames that alternate every
     tick, design 4.5 "red flash + balloon"), both sit in the red family, and
     both re-balloon every DEAF_BALLOON_REPEAT_S. A deafness that scrolled out
     of the notification area is a deafness nobody saw.

     A capture callback that went quiet counts as deafness EVEN THOUGH the
     capture state variable still says CAPTURING (FRAME_STALE_S). That is the
     calm-green-icon failure itself, and it is the one case the tray must
     catch on its own rather than wait to be told about.

  3. THE ENGINE SHOWN IS THE ENGINE USED.  Never the configured one; never the
     routing pointer when the last real decode disagrees with it. A pointer
     that has not yet decoded anything (or whose last decode is older than
     ENGINE_PROVEN_S) is labelled *unproven* — the tray says "I believe DGX,
     but nothing has proved it", never "DGX".

  And the corollary of all three: A TRAY THAT CANNOT SEE ITS OWN STATE SAYS SO.
  If the snapshot function raises, the icon goes UNKNOWN and flashes. It never
  keeps showing the last-good green.

SACRED AUDIO (scar 22). Every alert here is VISUAL. Balloons carry NIIF_NOSOUND
in `BALLOON_FLAGS`; `Balloon` has no field with which to request a sound; there
is no beep call site in this file, and K0's G6 gate forbids one repo-wide.

NO WINDOW (design 2 tray.py row, K15 row). This module creates no window class
and contains no foreground-stealing call site. A tray you can focus is a tray
that can eat a sentence of dictation.

BACKEND (the honest state of the world on this PC, 2026-08-13): pystray is NOT
installed and this milestone does not install it. So the GUI backend is a thin
seam — `TrayBackend` has five methods — with two implementations:
`PystrayBackend`, which REFUSES to construct when its dependency is absent
(never a pretend tray), and `HeadlessBackend`, which records everything and is
both the test double and the honest production fallback: the states still
resolve, the ledger still gets them, there is simply no icon on screen and
`make_backend()` journals that fact instead of hiding it.

stdlib only. Pillow is used lazily by `render_icon_png` and nowhere else.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------- the states
# Section 4.5's table plus the two activity states the design's tray row
# implies (LISTENING / DECODING) and UNKNOWN (see rule 3's corollary).

READY = "READY"
LISTENING = "LISTENING"
DECODING = "DECODING"
CAPTURING = "CAPTURING"
DEGRADED = "DEGRADED"
MAINT = "MAINT"
FLAKY = "FLAKY"
DEAF = "DEAF"
IDLE_NO_MIC = "IDLE_NO_MIC"
PAUSED = "PAUSED"
UNKNOWN = "UNKNOWN"

# Precedence, highest first. FAULTS OUTRANK ACTIVITY: a DEGRADED client that
# happens to be decoding shows DEGRADED, because the fault is the thing Iddo
# needs to know and the activity is in the tooltip anyway. The reverse order
# would let a busy client hide a lost DGX for as long as it stayed busy.
LADDER: tuple[str, ...] = (
    PAUSED, IDLE_NO_MIC, DEAF, MAINT, FLAKY, DEGRADED,
    CAPTURING, DECODING, LISTENING, READY,
)
STATES: tuple[str, ...] = LADDER + (UNKNOWN,)

DEAF_FAMILY: frozenset[str] = frozenset({DEAF, IDLE_NO_MIC})
LOUD_STATES: frozenset[str] = DEAF_FAMILY | {UNKNOWN}

# ------------------------------------------------------------- the constants

# A capture callback delivers a frame every BLOCK_MS (30ms). Five seconds of
# nothing is not a hiccup, it is a dead stream. Deliberately far below the
# 120s capture-recency threshold at which design 7 makes the client self-exit
# for Task Scheduler to restart: the HUMAN must see deafness long before the
# machine gives up on itself.
FRAME_STALE_S = 5.0

# How long a real decode keeps proving which engine is live.
ENGINE_PROVEN_S = 120.0

# Deafness re-announces itself at this cadence for as long as it lasts.
DEAF_BALLOON_REPEAT_S = 60.0

# Mirrors client/app.py STATE_CAPTURING without importing it (app imports the
# world; the tray must stay importable in a bare test process).
CAPTURE_STATE_LIVE = "CAPTURING"

# Worker states that can actually decode (client/worker_mgr.py:123).
WORKER_USABLE = frozenset({"READY", "BUSY"})

PRIMARY_DGX = "PRIMARY_DGX"
FALLBACK_LOCAL = "FALLBACK_LOCAL"
PINNED_LOCAL = "PINNED_LOCAL"

ENGINE_NAMES = {"dgx": "DGX (eran1)", "local": "local whisper"}

# Win32 balloon flags (shellapi.h). NIIF_NOSOUND is not optional here.
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003
NIIF_NOSOUND = 0x00000010
BALLOON_FLAGS = NIIF_NOSOUND          # OR'd with the level flag at call time
LEVEL_FLAGS = {"info": NIIF_INFO, "warn": NIIF_WARNING, "error": NIIF_ERROR}

# RegisterHotKey modifiers (winuser.h).
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
_MOD_NAMES = {
    "alt": (MOD_ALT, "Alt"), "ctrl": (MOD_CONTROL, "Ctrl"),
    "control": (MOD_CONTROL, "Ctrl"), "shift": (MOD_SHIFT, "Shift"),
    "win": (MOD_WIN, "Win"),
}


class TrayBackendUnavailable(RuntimeError):
    """The real tray backend cannot be built. Raised, never swallowed: a tray
    that pretends to be on screen is worse than no tray."""


class HotkeyError(ValueError):
    """The configured hotkey string cannot be honored."""


# ----------------------------------------------------------------- the icons


@dataclass(frozen=True)
class Icon:
    key: str
    rgb: tuple[int, int, int]
    glyph: str                        # ASCII — the default PIL font has it


# One entry per state. len(frames) > 1 IS the flash: it is structural, not a
# flag someone can forget to set. Every rgb is distinct, so every frame renders
# to distinct pixels (tests/test_tray.py proves it against real Pillow output).
ICONS: dict[str, tuple[Icon, ...]] = {
    READY:       (Icon("ready.green", (46, 160, 67), "*"),),
    LISTENING:   (Icon("listening.green_loud", (86, 211, 100), "("),),
    DECODING:    (Icon("decoding.blue", (58, 130, 246), "."),),
    CAPTURING:   (Icon("capturing.cyan", (34, 167, 180), "o"),),
    DEGRADED:    (Icon("degraded.yellow", (214, 158, 0), "!"),),
    FLAKY:       (Icon("flaky.orange", (222, 110, 15), "~"),),
    MAINT:       (Icon("maint.olive", (150, 140, 70), "="),),
    PAUSED:      (Icon("paused.grey", (130, 130, 130), "|"),),
    DEAF:        (Icon("deaf.red", (220, 38, 38), "X"),
                  Icon("deaf.dark", (48, 4, 4), "X")),
    # Both deaf states are the SAME alarm red on purpose: they mean the same
    # actionable thing to Iddo — KESHEV is not hearing you — and the glyph,
    # tooltip and balloon carry which one it is. An earlier cut made this one
    # pink to "distinguish" it; on screen it read as decoration, not alarm.
    IDLE_NO_MIC: (Icon("nomic.red", (198, 24, 24), "/"),
                  Icon("nomic.dark", (40, 4, 12), "/")),
    # UNKNOWN is violet, off the yellow/orange warning ramp entirely: "I cannot
    # see myself" is a different KIND of trouble from "the link is degraded",
    # and at 16px an amber-vs-yellow distinction does not survive.
    UNKNOWN:     (Icon("unknown.violet", (150, 70, 230), "?"),
                  Icon("unknown.dark", (40, 10, 70), "?")),
}


def icon_frames(state: str) -> tuple[Icon, ...]:
    """The frames for a state. Two or more frames = it flashes."""
    return ICONS[state]


def render_icon_png(icon: Icon, size: int = 32) -> bytes:
    """Render one frame to PNG bytes (Pillow, imported lazily — it is not in
    the client's declared dependency set, design 1)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ModuleNotFoundError as exc:   # pragma: no cover - PIL is present
        raise TrayBackendUnavailable(f"Pillow not installed: {exc}") from exc

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    d.ellipse((pad, pad, size - pad - 1, size - pad - 1),
              fill=(*icon.rgb, 255))
    font = ImageFont.load_default()
    d.text((size // 2, size // 2), icon.glyph, anchor="mm",
           fill=(255, 255, 255, 255), font=font)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------- observations


@dataclass(frozen=True)
class Counters:
    """The running totals the tray makes visible. Read from the router /
    spool / owner gate; never computed here.

    NOTHING BUILDS ONE OF THESE YET. `TrayInputs.counters` is therefore
    OPTIONAL, and None renders as "not counted" — never as 0. "Owner-rej: 0"
    is a claim that a count was taken and came out empty; if nobody is
    counting, printing 0 reports a healthy number for a measurement that never
    happened, which is the same lie as a green icon over a dead mic."""
    typed: int = 0
    guard_drop: int = 0
    empty: int = 0
    parked: int = 0
    recovered: int = 0
    spilled: int = 0
    owner_rej: int = 0                 # criterion 18 / scar 49 — VISIBLE
    deaf_drop: int = 0


@dataclass(frozen=True)
class TrayInputs:
    """RAW OBSERVATIONS. Note what is NOT here: no `state`, no `client_state`,
    no `icon`. Nothing in this record is a conclusion about how KESHEV is
    doing — that is the tray's job to work out, and the reason it cannot be
    lied to."""
    paused: bool = False
    capture_state: str = ""            # client/app.py STATE_* verbatim
    frame_age_s: float | None = None   # since the last capture callback frame
    fsm_state: str = PRIMARY_DGX       # routing POINTER, not a promise
    fsm_deaf: bool = False
    maint: bool = False
    worker_state: str = "IDLE"         # client/worker_mgr.py state machine
    local_state: str | None = None     # READY | LOCAL_UNAVAILABLE
    decoding: bool = False
    speech_active: bool = False        # segmenter is inside a segment
    last_decode_engine: str | None = None    # the engine that REALLY decoded
    last_decode_age_s: float | None = None
    mic_name: str | None = None        # the device actually open
    queue_depth: int = 0
    degraded_reason: str = ""
    counters: Counters | None = None   # None = nobody is counting (see above)


@dataclass(frozen=True)
class Balloon:
    """An in-eyeline, SILENT notification. There is deliberately no field with
    which to request a sound (scar 22)."""
    title: str
    text: str
    level: str = "info"                # info | warn | error

    def win32_flags(self) -> int:
        return BALLOON_FLAGS | LEVEL_FLAGS.get(self.level, NIIF_INFO)


@dataclass(frozen=True)
class Visual:
    state: str
    icon: Icon
    flash: bool
    tooltip: str
    engine: str
    balloon: Balloon | None = None


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    enabled: bool = True


MENU_KEYS: tuple[str, ...] = (
    "pause", "engine", "mic", "owner_rej", "recovered",
    "open_log", "recalibrate", "restart_worker", "quit",
)
_DISPLAY_ONLY = frozenset({"engine", "mic"})


# ------------------------------------------------------------- the resolver


def _mic_is_delivering(obs: TrayInputs) -> bool:
    if obs.capture_state != CAPTURE_STATE_LIVE:
        return False
    if obs.frame_age_s is None:
        return False
    return obs.frame_age_s <= FRAME_STALE_S


def _no_engine(obs: TrayInputs) -> bool:
    """The FSM's DEAF flag OR the tray's own reading of the same facts. The
    tray does not wait to be told: if we are off the DGX and the worker is
    down, nothing can decode, whatever flag anyone forgot to set."""
    if obs.fsm_deaf:
        return True
    off_dgx = obs.fsm_state != PRIMARY_DGX
    worker_dead = (obs.worker_state == "WORKER_DOWN"
                   or obs.local_state == "LOCAL_UNAVAILABLE")
    return off_dgx and worker_dead


def resolve_state(obs: TrayInputs) -> str:
    """Observations -> one state, by the LADDER. Pure, total, no memory."""
    if obs.paused:
        return PAUSED
    if not _mic_is_delivering(obs):
        return IDLE_NO_MIC
    if _no_engine(obs):
        return DEAF
    if obs.maint:
        return MAINT
    if obs.fsm_state == PINNED_LOCAL:
        return FLAKY
    if obs.fsm_state == FALLBACK_LOCAL:
        return DEGRADED
    if obs.worker_state not in WORKER_USABLE:
        return CAPTURING
    if obs.decoding:
        return DECODING
    if obs.speech_active:
        return LISTENING
    return READY


def _pointer_engine(obs: TrayInputs) -> str:
    return "dgx" if obs.fsm_state == PRIMARY_DGX else "local"


def engine_label(obs: TrayInputs) -> str:
    """The engine ACTUALLY IN USE — never the configured one.

    A decode that really happened inside ENGINE_PROVEN_S is the only thing
    that proves an engine. Without one we show the routing pointer and say
    plainly that it is unproven.
    """
    state = resolve_state(obs)
    if state in DEAF_FAMILY:
        return "none"
    eng = obs.last_decode_engine
    age = obs.last_decode_age_s
    proven = eng in ENGINE_NAMES and age is not None and age <= ENGINE_PROVEN_S
    name = ENGINE_NAMES[eng] if proven else ENGINE_NAMES[_pointer_engine(obs)]
    if state == PAUSED:
        # nothing is flowing, so nothing is "in use" — say so rather than
        # leave a live-looking engine line over a stopped pipeline.
        return f"{name} (idle — paused)"
    if proven:
        return f"{name} (in use)"
    return f"{name} (unproven — no decode yet)"


def _headline(state: str, obs: TrayInputs) -> str:
    if state == PAUSED:
        return "PAUSED by hotkey — nothing is being captured or typed"
    if state == IDLE_NO_MIC:
        if obs.capture_state != CAPTURE_STATE_LIVE:
            return ("NOT HEARING — no allowed microphone is open "
                    "(USB only; Bluetooth is never a mic)")
        if obs.frame_age_s is None:
            return "NOT HEARING — the capture stream has never delivered a frame"
        return (f"NOT HEARING — mic open but silent for "
                f"{obs.frame_age_s:.0f}s")
    if state == DEAF:
        return "NOT TYPING — audio is arriving but NO engine can decode it"
    if state == MAINT:
        return "DEGRADED — fleet maintenance window (01:55-02:20), local only"
    if state == FLAKY:
        return "PINNED to local — the link flapped too often"
    if state == DEGRADED:
        return "DEGRADED — " + (obs.degraded_reason or "DGX lost, running local")
    if state == CAPTURING:
        return ("CAPTURING — spool absorbing while the worker warms "
                f"({obs.worker_state})")
    if state == DECODING:
        return "decoding..."
    if state == LISTENING:
        return "listening — speech in progress"
    if state == UNKNOWN:
        return "KESHEV CANNOT READ ITS OWN STATE"
    return "hearing you"


def _mic_label(obs: TrayInputs) -> str:
    if _mic_is_delivering(obs) and obs.mic_name:
        return f"● {obs.mic_name}"
    return f"○ none{f' ({obs.mic_name} not delivering)' if obs.mic_name else ''}"


UNCOUNTED = "not counted"


def _counter_line(obs: TrayInputs) -> str:
    c = obs.counters
    if c is None:
        return f"q {obs.queue_depth} · outcomes {UNCOUNTED} (no source wired)"
    return (f"q {obs.queue_depth} · typed {c.typed} · guard {c.guard_drop} · "
            f"parked {c.parked} · recovered {c.recovered} · "
            f"owner-rej {c.owner_rej}")


def tooltip(state: str, obs: TrayInputs, engine: str) -> str:
    return (f"KESHEV — {state}\n"
            f"{_headline(state, obs)}\n"
            f"Engine: {engine}\n"
            f"Mic: {_mic_label(obs)}\n"
            f"{_counter_line(obs)}")


def _level(state: str) -> str:
    if state in LOUD_STATES:
        return "error"
    if state in (DEGRADED, FLAKY, MAINT):
        return "warn"
    return "info"


def balloon_for(state: str, obs: TrayInputs, engine: str) -> Balloon:
    """Every state entry gets a balloon: a state change nobody was told about
    is a state change that did not happen, as far as the human is concerned."""
    if state in DEAF_FAMILY:
        title = "KESHEV IS NOT HEARING YOU"
    elif state == UNKNOWN:
        title = "KESHEV IS BLIND TO ITSELF"
    else:
        title = f"KESHEV: {state}"
    text = _headline(state, obs)
    if state not in DEAF_FAMILY and state != UNKNOWN:
        text += f"\nEngine: {engine}"
    return Balloon(title=title, text=text, level=_level(state))


# ---------------------------------------------------------------- the hotkey


@dataclass(frozen=True)
class Hotkey:
    mods: int
    vk: int
    label: str


def parse_hotkey(spec: str) -> Hotkey:
    """'ctrl+alt+m' -> RegisterHotKey arguments. Refuses anything it cannot
    honor — a hotkey that silently did not bind is a pause key that does
    nothing when Iddo needs it."""
    parts = [p.strip().lower() for p in str(spec).split("+")]
    if len(parts) < 2 or any(not p for p in parts):
        raise HotkeyError(
            f"hotkey {spec!r}: need at least one modifier and one key, "
            f"e.g. 'ctrl+alt+m'")
    *mod_names, key = parts
    mods = 0
    labels = []
    for name in mod_names:
        if name not in _MOD_NAMES:
            raise HotkeyError(f"hotkey {spec!r}: unknown modifier {name!r}")
        bit, pretty = _MOD_NAMES[name]
        mods |= bit
        labels.append(pretty)
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise HotkeyError(f"hotkey {spec!r}: unsupported key {key!r}")
    return Hotkey(mods=mods, vk=vk, label="+".join(labels + [key.upper()]))


# ------------------------------------------------------- the recency deriver


class FrameRecency:
    """Seconds since the capture callback last delivered a frame.

    client/capture.py:198 hands this job here BY NAME: "A stream that stops
    delivering callbacks entirely is the wedge case, watched elsewhere (design
    sec 7, capture-callback recency)."

    CapturePipeline keeps no timestamp — it keeps `callbacks`, a counter that
    only ever goes up (client/capture.py:288). So recency is derived by
    watching that counter across ticks, and capture.py does not have to change
    to make the tray honest. A counter that stopped moving IS a stream that
    stopped delivering.

    One subtlety with teeth: `app.reresolve_now()` builds a NEW CapturePipeline
    (scar 25 silent-open, unplug, replug) whose counter restarts at zero. A
    counter going DOWN is a device re-open, not a dead mic — the clock restarts
    from the reset, and if the new pipeline then delivers nothing, the age grows
    from there and DEAF fires on its own merits.
    """

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._mono = monotonic
        self._count: int | None = None
        self._changed_at = 0.0
        self._ever_heard = False

    def observe(self, callbacks: int | None) -> float | None:
        """Age in seconds, or None for "nothing is even trying to hear" — no
        pipeline at all, or one that has not yet delivered its first frame.
        None is NOT zero, and resolve_state() treats it as deafness."""
        now = self._mono()
        if callbacks is None:                    # no pipeline: capture is down
            self._count = None
            self._changed_at = now
            self._ever_heard = False
            return None
        first = self._count is None
        if first or callbacks != self._count:
            self._count = callbacks
            self._changed_at = now
            if callbacks > 0:
                self._ever_heard = True
            if first and not self._ever_heard:
                return None                      # opened, never delivered
            return 0.0                           # a real frame, or a re-open
        return now - self._changed_at            # the counter is FROZEN


# --------------------------------------------------------------- the backend


class TrayBackend:
    """The whole GUI surface, five methods wide. Everything above this line is
    pure data, which is why every state is unit-testable with no GUI at all."""

    def set_icon(self, icon: Icon, tooltip_text: str) -> None:
        raise NotImplementedError

    def notify(self, balloon: Balloon) -> None:
        raise NotImplementedError

    def set_menu(self, items: Iterable[MenuItem]) -> None:
        raise NotImplementedError

    def run(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class HeadlessBackend(TrayBackend):
    """Records instead of drawing. The test double, and the honest production
    fallback when no GUI backend can be built."""

    def __init__(self) -> None:
        self.icons: list[tuple[str, str]] = []
        self.balloons: list[Balloon] = []
        self.menus: list[tuple[MenuItem, ...]] = []
        self.running = False

    def set_icon(self, icon: Icon, tooltip_text: str) -> None:
        self.icons.append((icon.key, tooltip_text))

    def notify(self, balloon: Balloon) -> None:
        self.balloons.append(balloon)

    def set_menu(self, items: Iterable[MenuItem]) -> None:
        self.menus.append(tuple(items))

    def run(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class PystrayBackend(TrayBackend):
    """The real on-screen icon — A DECLARED SEAM, NOT AN IMPLEMENTATION.

    It refuses to construct for either of two distinct reasons, and says which:

      * pystray is not installed on this PC (true today, 2026-08-13) and K15
        does not install it;
      * even where the dependency exists, the Shell_NotifyIcon/pystray drawing
        code is UNBUILT.

    The second refusal is the important one. A backend that constructed happily
    and then quietly drew nothing would make `make_backend()` report is_real=True
    over an empty notification area — a tray claiming to be on screen when it is
    not, which is the same class of lie as a green icon over a dead mic. So it
    fails at construction, `make_backend()` falls back to headless, and the
    ledger says so. Deleting this refusal is the last step of building the real
    backend, not a step someone can skip.
    """

    def __init__(self, *, import_fn: Callable[[str], Any] | None = None) -> None:
        imp = import_fn or self._import
        try:
            imp("pystray")
            imp("PIL.Image")
        except ImportError as exc:
            raise TrayBackendUnavailable(
                f"pystray/Pillow backend unavailable: {exc}. KESHEV runs with "
                f"no icon on screen rather than show a fake one.") from exc
        raise TrayBackendUnavailable(
            "pystray/Pillow are importable, but the Shell_NotifyIcon drawing "
            "code is UNBUILT (K15 left_undone). Refusing to hand back a "
            "backend that would report itself real and draw nothing.")

    @staticmethod
    def _import(name: str) -> Any:
        import importlib
        return importlib.import_module(name)


def make_backend(*, import_fn: Callable[[str], Any] | None = None,
                 emit: Callable[..., None] | None = None,
                 ) -> tuple[TrayBackend, bool]:
    """(backend, is_real). Falls back to headless and JOURNALS the fallback —
    "there is no icon on your screen" is itself a fact Iddo must be able to
    find in the ledger."""
    say = emit or (lambda evt, **kw: None)
    try:
        backend: TrayBackend = PystrayBackend(import_fn=import_fn)
    except TrayBackendUnavailable as exc:
        say("STATE", state="TRAY_BACKEND_HEADLESS", err=str(exc)[:120])
        return HeadlessBackend(), False
    say("STATE", state="TRAY_BACKEND_PYSTRAY")
    return backend, True


# ------------------------------------------------------------------ the tray


class Tray:
    """Holds no truth of its own: every render pulls a fresh observation."""

    def __init__(self, backend: TrayBackend, *,
                 snapshot_fn: Callable[[], TrayInputs],
                 emit: Callable[..., None] | None = None,
                 state_dir: Path | str | None = None,
                 open_fn: Callable[[Path], Any] | None = None,
                 on_pause: Callable[[], Any] | None = None,
                 on_resume: Callable[[], Any] | None = None,
                 on_recalibrate: Callable[[], Any] | None = None,
                 on_restart_worker: Callable[[], Any] | None = None,
                 on_quit: Callable[[], Any] | None = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.backend = backend
        self._snapshot_fn = snapshot_fn
        self._emit = emit or (lambda evt, **kw: None)
        self.state_dir = Path(state_dir) if state_dir is not None else Path("state")
        self._open_fn = open_fn or _default_open
        self._actions = {
            "pause": None,                       # handled by toggle_pause
            "recalibrate": on_recalibrate,
            "restart_worker": on_restart_worker,
            "quit": on_quit,
        }
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._mono = monotonic

        self._last: Visual | None = None
        self._obs: TrayInputs | None = None
        self._phase = 0
        self._balloon_at = 0.0

    # ------------------------------------------------------------- rendering

    def update(self) -> Visual:
        """Pull one observation, derive the truth, push it to the backend."""
        try:
            obs = self._snapshot_fn()
        except Exception as exc:  # noqa: BLE001 — a blind tray must SAY so
            return self._render(UNKNOWN, TrayInputs(), blind=exc)
        self._obs = obs
        return self._render(resolve_state(obs), obs)

    def tick(self) -> Visual:
        """update() plus one flash step. The tray thread calls this."""
        self._phase += 1
        return self.update()

    def _render(self, state: str, obs: TrayInputs, *,
                blind: BaseException | None = None) -> Visual:
        frames = icon_frames(state)
        icon = frames[self._phase % len(frames)]
        engine = "none" if blind is not None else engine_label(obs)
        tip = tooltip(state, obs, engine)
        if blind is not None:
            tip += f"\nsnapshot failed: {type(blind).__name__}: {str(blind)[:80]}"

        changed = self._last is None or self._last.state != state
        now = self._mono()
        repeat = (state in LOUD_STATES
                  and now - self._balloon_at >= DEAF_BALLOON_REPEAT_S)
        bal = balloon_for(state, obs, engine) if (changed or repeat) else None

        vis = Visual(state=state, icon=icon, flash=len(frames) > 1,
                     tooltip=tip, engine=engine, balloon=bal)
        if changed:
            self._emit("STATE", state=f"TRAY_{state}", eng=engine)
        self.backend.set_icon(icon, tip)
        if bal is not None:
            self._balloon_at = now
            self.backend.notify(bal)
        self._last = vis
        self.backend.set_menu(self._menu_for(obs, state))
        return vis

    # ----------------------------------------------------------------- menu

    def menu(self) -> list[MenuItem]:
        if self._last is None:
            self.update()
        obs = self._obs if self._obs is not None else TrayInputs()
        state = self._last.state if self._last is not None else UNKNOWN
        return list(self._menu_for(obs, state))

    def _menu_for(self, obs: TrayInputs, state: str) -> tuple[MenuItem, ...]:
        c = obs.counters
        labels = {
            "pause": "Resume" if state == PAUSED else "Pause",
            "engine": f"Engine: {engine_label(obs)}",
            "mic": f"Mic: {_mic_label(obs)}",
            "owner_rej": (f"Owner-rej: {c.owner_rej}" if c is not None
                          else f"Owner-rej: {UNCOUNTED}"),
            "recovered": (f"Recovered: {c.recovered}" if c is not None
                          else f"Recovered: {UNCOUNTED}"),
            "open_log": "Open log",
            "recalibrate": "Recalibrate",
            "restart_worker": "Restart worker",
            "quit": "Quit",
        }
        return tuple(MenuItem(key=k, label=labels[k],
                              enabled=k not in _DISPLAY_ONLY)
                     for k in MENU_KEYS)

    # --------------------------------------------------------------- actions

    def invoke(self, key: str) -> None:
        """Run a menu action. An action with nothing behind it SAYS SO — a
        menu item that quietly does nothing is the same lie as a green icon
        over a dead mic."""
        if key not in MENU_KEYS:
            raise KeyError(f"no such menu item: {key!r}")
        if key == "pause":
            self.toggle_pause()
            return
        if key in _DISPLAY_ONLY:
            self._say(f"KESHEV: {key}", self._last.tooltip if self._last
                      else "no reading yet", "info")
            return
        if key == "owner_rej":
            self._open_path(self.state_dir / "owner_rej.log",
                            "no owner-gate rejections recorded yet")
            return
        if key == "recovered":
            self._open_path(self.state_dir / "recovered.txt",
                            "nothing has been recovered yet")
            return
        if key == "open_log":
            logs = sorted((self.state_dir / "logs").glob("mic-*.log"))
            if logs:
                self._open_fn(logs[-1])
            else:
                self._say("KESHEV", f"no log file under {self.state_dir/'logs'}",
                          "warn")
            return
        fn = self._actions.get(key)
        if fn is None:
            self._say("KESHEV", f"'{key}' is not wired yet — nothing happened",
                      "warn")
            return
        fn()

    def toggle_pause(self) -> bool:
        """The hotkey action. Returns the pause state it ASKED FOR; the next
        update() reports what actually happened, from observation."""
        obs = self._obs
        if obs is None:
            self.update()
            obs = self._obs if self._obs is not None else TrayInputs()
        want = not obs.paused
        fn = self._on_pause if want else self._on_resume
        if fn is None:
            self._say("KESHEV", "pause is not wired yet — nothing happened",
                      "warn")
            return obs.paused
        fn()
        return want

    # -------------------------------------------------------------- internals

    def _open_path(self, path: Path, empty_msg: str) -> None:
        if path.is_file():
            self._open_fn(path)
        else:
            self._say("KESHEV", empty_msg, "info")

    def _say(self, title: str, text: str, level: str) -> None:
        self.backend.notify(Balloon(title=title, text=text, level=level))


def snapshot_from_app(app: Any, *, recency: FrameRecency,
                      paused: bool = False,
                      counters: Counters | None = None) -> TrayInputs:
    """Read one honest observation off a live KeshevApp.

    This is the whole wiring contract, and it is deliberately the ONLY place
    that knows the app's attribute names — proven against a REAL assembled app
    in tests/test_tray.py rather than against a mock, per the law in
    tests/test_wiring_discipline.py ("a test that supplies the dependency it
    is meant to verify cannot fail when the dependency is missing").

    Two fields have no producer in the client yet, and this function refuses to
    invent either of them:

      last_decode_engine/at — client/router.py records no such thing; its
          heartbeat reports fsm.engine(), the routing POINTER. Read here via
          getattr, so the day the router starts recording the engine that
          actually served a decode, the tray reports it with no change to this
          file. Until then every label says "unproven", which is true.
      counters — nothing aggregates TYPED / GUARD_DROP / OWNER_REJ totals yet
          (ownergate.py is K17b and does not exist). Passed in or left None,
          and None renders as "not counted", never as 0.
    """
    cap = getattr(app, "capture", None)
    router = getattr(app, "router", None)
    fsm = getattr(router, "fsm", None)
    worker = getattr(app, "worker", None)
    device = getattr(app, "device", None)
    spool = getattr(app, "spool", None)
    worker_state = str(getattr(worker, "state", "") or "")
    return TrayInputs(
        paused=paused,
        capture_state=str(getattr(app, "state", "") or ""),
        frame_age_s=recency.observe(getattr(cap, "callbacks", None)
                                    if cap is not None else None),
        fsm_state=str(getattr(fsm, "state", PRIMARY_DGX) or PRIMARY_DGX),
        fsm_deaf=bool(getattr(fsm, "deaf", False)),
        maint=bool(getattr(fsm, "maint", False)),
        worker_state=worker_state,
        local_state=getattr(worker, "local_state", None),
        decoding=(worker_state == "BUSY"),
        # client/segmenter.py exposes no public "am I mid-utterance" flag; a
        # read-only accessor there would be tidier than reaching for _in_seg,
        # but segmenter.py is not this milestone's to edit.
        speech_active=bool(getattr(getattr(app, "segmenter", None),
                                   "_in_seg", False)),
        last_decode_engine=getattr(router, "last_decode_engine", None),
        last_decode_age_s=_age_of(getattr(router, "last_decode_at", None)),
        mic_name=(getattr(device, "name", None) if device is not None else None),
        queue_depth=int(spool.qsize()) if spool is not None else 0,
        counters=counters,
    )


def _age_of(mono_ts: Any) -> float | None:
    if not isinstance(mono_ts, (int, float)):
        return None
    return max(0.0, time.monotonic() - float(mono_ts))


def _default_open(path: Path) -> None:
    """Hand the file to the shell. os.startfile opens it in the user's editor
    without this process ever taking the foreground."""
    starter = getattr(os, "startfile", None)
    if starter is None:                          # pragma: no cover - non-Windows
        raise TrayBackendUnavailable("os.startfile is Windows-only")
    starter(str(path))
