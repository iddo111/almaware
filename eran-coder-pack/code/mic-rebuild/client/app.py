"""KESHEV entry point — K14/K15 core: THE ASSEMBLY (PHASE2-DESIGN.md
sections 2, 4.1, 4.5, 7; scars 1/16/25/28/34/44/56; criteria 6/7/22/23).

Every other module in client/ was built and tested in isolation. This file is
the one that makes them a PROGRAM:

    config -> telemetry -> mutex -> devices -> capture -> resample ->
    segmenter -> spool -> worker_mgr -> router(guard_fn, type_fn) -> typer

Startup order is LAW (design 7), and it lives in `main()`:

  0a  mutexguard.acquire_or_exit  — the FIRST statement. A duplicate launch
      exits 11 in well under a second, which is only true while nothing heavy
      has been imported yet. That is why every device-bearing / numpy-bearing
      import in this file is LAZY, inside the function that needs it.
  0b  alma-mic coexistence refusal, exit 3 (criterion 23 / scar 56). Both
      probes are INJECTED and neither touches an audio device: a scheduled
      task named ALMA-MIC*/START-MIC* in state Running, or a live process
      whose command line matches alma-mic|voice-input|heb-mic. KESHEV never
      races Iddo's working dictation for a microphone.
  0c  ConfigStore.load_or_halt — corrupt/missing config is a MessageBox and
      exit 2. There is no defaults path anywhere (scar 40).

Then `build_app(cfg, ...)` assembles, and ONLY assembles: it opens no audio
device, spawns no subprocess and starts no thread. Everything with a side
effect lives behind `KeshevApp.start()`. That split is what makes the whole
pipeline testable against synthetic PCM with zero hardware.

Two structural rules this file exists to keep:

  ONE SEGMENTER FOR PROCESS LIFE.  A device re-resolve (scar 25 silent-open,
  unplug, replug) rebuilds the CapturePipeline but REUSES the Segmenter. A
  second Segmenter would reset its `_seq` to 0, regenerate ids already in the
  router's typed_lru, and the router would DUP_DISCARD real speech.

  ONE HEARTBEAT SOURCE.  The Router already pulses HEARTBEAT every 60s from
  its idle tick. This file must never call telemetry.start_heartbeat.

Seams added here that the assembly contract did not name (all default to the
real thing, all exist so a test can drive the whole pipeline headless):
`enumerate_fn`, `native_format_fn`, `check_format_fn`, `open_stream_fn`,
`set_priority_fn`, `focus_api`, `input_api`, `clipboard`, `vad`, `worker`,
`telemetry`, `session_id`, `rss_fn`, `sleep_fn`.
"""
from __future__ import annotations

import csv
import fnmatch
import io
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from client import mutexguard
from client.configstore import ConfigStore
from client.telemetry import Telemetry

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "config" / "client.json"
STATE_DIR = REPO / "state"

# ---------------------------------------------------------------- constants

EXIT_OK = 0
EXIT_CONFIG_HALT = 2          # configstore.halt() owns this one (scar 40)
EXIT_ALMAMIC_ALIVE = 3        # criterion 23 / scar 56
EXIT_UNWIRED = 4              # a mandatory seam is missing — refuse, never guess

# Focus policy is CODE UNDER GIT, not config: the 12-key schema has no focus
# key and configstore.set() refuses a 13th. FocusGuard's constructor default
# is allowlist-mode with ZERO targets, which parks 100% of dictation — the
# exact silent-loss class this rebuild exists to kill. Ship default is
# type-anywhere (matching client/selftest.py:151). Cost, recorded honestly:
# with anywhere=True a browser address bar is a legal target (scar 34 warned
# about that); title-less windows and KESHEV's own window stay hard-blocked.
FOCUS_ANYWHERE_DEFAULT = True

BLOCK_MS = 30                 # capture frame size handed downstream (K7)
SUPERVISOR_TICK_S = 1.0       # device-supervisor wake cadence
TRAY_TICK_S = 1.0             # tray re-observation cadence (K15)

# Threads without which the client can never hear again. Their death stops the
# process (see _spawn); the tray's death does not — the picture is allowed to
# fail, the audio path is not.
CRITICAL_THREADS: frozenset[str] = frozenset({"keshev-pump",
                                              "keshev-device-supervisor"})
REOPEN_BACKOFF_S = (0.0, 1.0, 2.0, 5.0, 15.0)
JOIN_TIMEOUT_S = 5.0
ROUTER_STOP_TIMEOUT_S = 10.0

STATE_ASSEMBLED = "ASSEMBLED"
STATE_IDLE_NO_MIC = "IDLE_NO_MIC"
STATE_CAPTURING = "CAPTURING"
STATE_STOPPED = "STOPPED"

# alma-mic liveness patterns — the SAME truth as tools/mic-switch.ps1:69-72.
ALMA_TASK_PATTERNS: tuple[str, ...] = ("ALMA-MIC*", "START-MIC*")
# The concrete task names behind each pattern. schtasks cannot glob, and
# enumerating every task on the machine is what broke the client (see
# default_list_tasks). Add a name here if a new rival mic task is ever made.
_TASK_NAME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "ALMA-MIC": ("ALMA-MIC", "ALMA-MIC-Admin", "ALMA-MIC-Elevated",
                 "ALMA-MIC-BrioLevelLog"),
    "START-MIC": ("START-MIC",),
}
ALMA_PROC_RE = re.compile(r"alma-mic|voice-input|heb-mic|keshev-next",
                          re.IGNORECASE)
# keshev-next added 2026-08-25: KESHEV 5000 became the live mic that night and
# this app became the rollback. Both ran at once for ~17 minutes — two typers
# on one microphone. The one-mic law is enforced here, not in memory.
# Tools that only ever MENTION a path — they can never be holding a microphone.
# Matched against the whole command line; see almamic_alive() for the incident.
_SEARCHER_NAMES = frozenset((
    "grep", "findstr", "rg", "ripgrep", "ag", "ack", "sed", "awk",
    "bash", "sh", "zsh", "powershell", "pwsh", "cmd", "conhost", "wsl",
    "code", "notepad", "explorer", "git", "tail", "head", "cat",
    "less", "more", "type", "select-string", "python-searcher",
))


def _is_searcher(cmdline: str) -> bool:
    """True when the command's EXECUTABLE is a search/shell tool rather than a
    program that could hold a microphone. Reads the exe name only — never the
    arguments, which is the whole point: the arguments are where the path
    'alma-mic' appears."""
    text = (cmdline or "").strip()
    if not text:
        return False
    if text.startswith('"'):
        exe = text[1:text.find('"', 1)] if text.find('"', 1) > 0 else text
    else:
        exe = text.split(" ", 1)[0]
    base = exe.replace("/", "\\").rsplit("\\", 1)[-1].lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return base in _SEARCHER_NAMES


_SESSION_RE = re.compile(r"^[0-9a-f]{8}$")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AssemblyError(RuntimeError):
    """A mandatory seam is missing or wrong. Loud at build time — KESHEV
    refuses to run half-wired rather than losing speech quietly."""


def _stderr_line(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


# ------------------------------------------------------------- session id

def new_session_id() -> str:
    """EXACTLY 8 lowercase hex. client/segmenter.py builds every segment id as
    f"{session_id}-{seq:06d}" and common/protocol.valid_request_id refuses
    anything else — a wrong session id turns every DGX decode into
    err=bad_request, silently."""
    return uuid.uuid4().hex[:8]


# ------------------------------------------------- alma-mic coexistence (0b)

def almamic_alive(list_procs_fn: Callable[[], Iterable[str]],
                  list_tasks_fn: Callable[[], Iterable[Sequence[str]]],
                  ) -> tuple[bool, str]:
    """(alive, why). Both probes are injected; NEITHER enumerates or opens an
    audio device — liveness is read from the task scheduler and the process
    table only (Sacred Audio: KESHEV never touches a mic to find out whether
    someone else is using one).

    Probe failures propagate. "I could not tell" must never collapse into
    "dead" — that is how two processes end up fighting over the BRIO.
    """
    for row in list_tasks_fn():
        name, state = str(row[0]), str(row[1])
        if state.strip().casefold() != "running":
            continue
        base = name.lstrip("\\").strip().upper()
        for pattern in ALMA_TASK_PATTERNS:
            if fnmatch.fnmatch(base, pattern.upper()):
                return True, f"scheduled task {name.strip()!r} is Running"
    for cmdline in list_procs_fn():
        text = str(cmdline or "")
        # A SEARCHER IS NOT A MICROPHONE. 2026-08-15 00:05: KESHEV refused to
        # start for hours because a stuck
        #     grep.exe -ril scar /d/CLAUDE/alma-mic /d/CLAUDE/voice-input
        # left over from a code search sat in the process table, and its
        # COMMAND LINE contains the pattern. Iddo had no mic and the reason was
        # a grep. His own scar register warns of exactly this
        # (reference_double_mic_fix: "don't match processes by a word that's in
        # your own command" — the same trap caught the pinokio diagnosis).
        # A rival dictation client is a PYTHON program; grep, findstr, bash,
        # powershell and editors merely MENTION the path. Skipping them cannot
        # hide a real rival, because a real rival has to be running python to
        # hold the mic at all.
        if _is_searcher(text):
            continue
        hit = ALMA_PROC_RE.search(text)
        if hit is not None:
            return True, f"a live process matches {hit.group(0)!r}"
    return False, "no ALMA-MIC/START-MIC task Running and no alma-mic process"


def default_list_tasks() -> list[tuple[str, str]]:
    """(TaskName, Status) rows from schtasks — no PowerShell, no window.

    SCAR 2026-08-21: this used to enumerate EVERY task on the machine
    (`schtasks /query /fo csv /nh`). On a box with hundreds of tasks that
    call takes over a minute, blew the 60 s timeout, and the exception
    killed the client at startup — so the guard that exists to protect the
    microphone was the thing that silenced it. Iddo spent a whole day
    dictating into a client that could not start.

    The guard only ever cared about two name patterns, so ask for those by
    name: bounded work, seconds not minutes. A missing task exits 1 with
    "ERROR: The system cannot find the file specified" — that is a healthy
    answer meaning "no such rival", not a failure.
    """
    rows: list[tuple[str, str]] = []
    for pattern in ALMA_TASK_PATTERNS:
        stem = pattern.rstrip("*")
        for name in _TASK_NAME_CANDIDATES.get(stem, (stem,)):
            try:
                proc = subprocess.run(
                    ["schtasks", "/query", "/tn", name, "/fo", "csv", "/nh"],
                    capture_output=True, text=True, timeout=20,
                    creationflags=_NO_WINDOW)
            except subprocess.TimeoutExpired:
                # "I could not tell" must never collapse into "dead" — but it
                # must not kill the mic either. Report the name as Running so
                # the caller's own refusal path decides, loudly.
                rows.append((name, "Running"))
                continue
            for row in csv.reader(io.StringIO(proc.stdout)):
                if len(row) >= 3 and row[0].strip():
                    rows.append((row[0], row[2]))
    return rows


def default_list_procs() -> list[str]:
    """Command lines of every live process (Win32_Process)."""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"],
        capture_output=True, text=True, timeout=120, creationflags=_NO_WINDOW)
    return [line for line in proc.stdout.splitlines() if line.strip()]


# --------------------------------------------------------------- the seams

def resolve_guard_fn(router_module=None) -> Callable[[dict], Any]:
    """The K13 guard seam, taken from client/router.py.

    The adapter MUST live on the router's side: tests/test_textguard.py's
    import-discipline test lets client/router.py import the guard and no other
    client module (scar 28 — exactly one copy, running LAST, the router its
    only caller). So this file never builds the adapter; it asks the router
    for it. Two shapes are accepted, in order:

      1. a module-level `textguard_guard` (the assembly contract's name);
      2. whatever `Router.__init__` declares as its own `guard_fn` DEFAULT —
         the router's signature IS the contract, so the wiring can name the
         import anything and this still finds it.

    There is deliberately NO fallback to router.default_guard: that is the K12
    pass-through placeholder, and running on it means typing every Whisper
    silence-hallucination ("תודה רבה", "subscribe") straight into whatever
    window has focus.
    """
    import inspect

    if router_module is None:
        from client import router as router_module  # lazy (see module docstring)
    placeholder = getattr(router_module, "default_guard", None)

    fn = getattr(router_module, "textguard_guard", None)
    if fn is None or fn is placeholder:
        try:
            fn = inspect.signature(
                router_module.Router.__init__).parameters["guard_fn"].default
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise AssemblyError(
                f"client/router.py declares no readable guard_fn seam: {exc}"
            ) from exc
        if fn is inspect.Parameter.empty:
            fn = None

    if fn is None or fn is placeholder or not callable(fn):
        raise AssemblyError(
            "no textguard adapter wired: client/router.py must import the K13 "
            "guard (client/textguard.py exposes `guard(res) -> str | None` and "
            "`from_result(res) -> Verdict`) and make it the Router's guard_fn "
            "default, or expose it as `textguard_guard`. Refusing to run on "
            "router.default_guard, the K12 pass-through placeholder, which "
            "types hallucinations into live focus.")
    return fn


def build_spawn_fn(cfg: dict, *, repo: Path | str = REPO,
                   python: str | None = None,
                   popen: Callable[..., Any] | None = None,
                   ) -> Callable[[int], Any]:
    """The worker spawn seam. worker_mgr.default_spawn_fn passes ONLY --gen;
    without --server-url and --token-file the worker's DGX engine is never
    built and EVERY dgx decode answers {'ok': False, 'err': 'dgx_unconfigured'}
    for the life of the process."""
    launcher = popen if popen is not None else subprocess.Popen
    exe = python or sys.executable
    server_url = str(cfg["server_url"])
    token_file = str(cfg["auth_token_file"])
    cwd = str(repo)

    def spawn_fn(gen: int):
        from client.keshev_worker import LADDER  # lazy
        argv = [exe, "-u", "-m", "client.keshev_worker",
                "--gen", str(gen), "--model", LADDER[0],
                "--server-url", server_url, "--token-file", token_file]
        return launcher(argv, cwd=cwd, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    return spawn_fn


# ------------------------------------------------------- device seams (live)

def default_enumerate_devices() -> list:
    """PortAudio rows -> client.devices.DeviceInfo. sounddevice is imported
    HERE, never at module level: it is not installed on this PC, and the whole
    assembly must still import, build and test headlessly."""
    import sounddevice as sd
    from client.devices import DeviceInfo

    hostapis = sd.query_hostapis()
    out = []
    for index, row in enumerate(sd.query_devices()):
        try:
            api = str(hostapis[int(row.get("hostapi", 0))].get("name", ""))
        except (IndexError, KeyError, TypeError, ValueError):
            api = ""
        out.append(DeviceInfo(
            index=index,
            name=str(row.get("name", "")),
            hostapi=api,
            max_input_channels=int(row.get("max_input_channels", 0) or 0),
            max_output_channels=int(row.get("max_output_channels", 0) or 0),
        ))
    return out


def default_native_format(device) -> tuple[int, int]:
    import sounddevice as sd
    row = sd.query_devices(device.index)
    return (int(row.get("default_samplerate") or 48000),
            max(1, int(row.get("max_input_channels") or 1)))


def default_check_format(device, rate: int, channels: int) -> None:
    import sounddevice as sd
    sd.check_input_settings(device=device.index, samplerate=rate,
                            channels=channels)


def default_open_stream(device, rate: int, channels: int, pipeline):
    """Open ONE capture stream. A PortAudio 'Unanticipated host error' is the
    scar-23 transient: translated so devices.open_with_retry applies its
    3x/0.4s retry before moving down the same-physical-mic chain."""
    import sounddevice as sd
    from client.devices import TransientDeviceError

    def _callback(indata, frame_count, time_info, status):
        pipeline.on_audio(indata, status)

    try:
        return sd.InputStream(device=device.index, samplerate=rate,
                              channels=channels, dtype="float32",
                              blocksize=int(rate * BLOCK_MS / 1000),
                              callback=_callback)
    except Exception as exc:
        if "unanticipated host error" in str(exc).casefold():
            raise TransientDeviceError(str(exc)) from exc
        raise


# ------------------------------------------------------------------ the app

class KeshevApp:
    """The assembled client. Constructed by build_app(); nothing here starts
    until start() is called."""

    def __init__(self, *, cfg: dict, state_dir: Path, session_id: str,
                 telemetry, spool, recovered, segmenter, worker, focus_guard,
                 typer, enumerate_fn, native_format_fn, check_format_fn,
                 open_stream_fn, set_priority_fn, sleep_fn) -> None:
        self.cfg = cfg
        self.state_dir = state_dir
        self.session_id = session_id
        self.telemetry = telemetry
        self.spool = spool
        self.recovered = recovered
        self.segmenter = segmenter
        self.worker = worker
        self.focus_guard = focus_guard
        self.typer = typer
        self.router = None                      # attached by build_app
        self.tray = None                        # attached by build_app (K15)
        self.hotkeys = None                     # attached by build_app

        self._enumerate_fn = enumerate_fn
        self._native_format_fn = native_format_fn
        self._check_format_fn = check_format_fn
        self._open_stream_fn = open_stream_fn
        self._set_priority_fn = set_priority_fn
        self._sleep = sleep_fn

        self.capture = None                     # rebuilt on every re-resolve
        self.stream = None
        self.device = None
        self.selection = None
        self.state = STATE_ASSEMBLED

        self.stop = threading.Event()           # owned by pump + supervisor
        self._reresolve = threading.Event()
        # PAUSE (Iddo, 2026-08-15: "Keshev should have proper play pause
        # button"). Deliberately a TYPING pause, not a capture pause: the mic
        # stays open, segments keep spooling, decodes keep happening — only
        # the last step, putting text into his window, is withheld. Closing
        # the device instead would re-enter the whole open/silent-reopen
        # hazard every time he taps a button, and this repo has spent two days
        # paying for device churn. Paused speech is parked, never dropped.
        self.paused = threading.Event()
        self._dropped_retired = 0               # counters of RETIRED pipelines
        self._overflow_retired = 0
        self.threads: list[threading.Thread] = []
        self._started = False
        self._shut = False

    # ------------------------------------------------------------ counters

    def drop_frames(self) -> int:
        """Cumulative dropped capture frames across ALL pipelines. The router
        heartbeat reads this; CapturePipeline.frames_dropped resets whenever
        the pipeline is rebuilt, so the retired totals are carried here."""
        cap = self.capture
        return self._dropped_retired + (cap.frames_dropped if cap else 0)

    def overflow_count(self) -> int:
        cap = self.capture
        return self._overflow_retired + (cap.overflow_count if cap else 0)

    def reresolve_pending(self) -> bool:
        return self._reresolve.is_set()

    # ---------------------------------------------------------------- pause

    def pause(self) -> None:
        """Stop TYPING. The mic stays open and everything keeps being heard."""
        if not self.paused.is_set():
            self.paused.set()
            self.telemetry.event("STATE", state="PAUSED")

    def resume(self) -> None:
        if self.paused.is_set():
            self.paused.clear()
            self.telemetry.event("STATE", state="RESUMED")

    def is_paused(self) -> bool:
        return self.paused.is_set()

    def input_level(self) -> float | None:
        """Most recent capture RMS, or None when nothing is being captured.

        None and 0.0 are different answers and the window draws them
        differently: None is "no stream", 0.0 is "a stream delivering
        silence" — which is exactly the scar-25 failure that cost 127
        silent-reopens on 2026-08-15."""
        cap = self.capture
        watch = getattr(cap, "silence_watch", None) if cap is not None else None
        return getattr(watch, "last_level", None)

    # -------------------------------------------------------------- events

    def capture_events(self, evt: str, **fields) -> None:
        """Runs on the PortAudio CALLBACK THREAD. Journal, raise a flag, and
        nothing else — re-resolving here would deadlock PortAudio. The device
        supervisor thread does the actual work."""
        self.telemetry.event(evt, **fields)
        if evt == "DEVICE_SILENT_REOPEN":
            self._reresolve.set()

    def _set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        self.telemetry.event("STATE", state=state)

    # -------------------------------------------------------------- device

    def resolve_device(self):
        """K6 device law. The pinned mic wins UN-PROBED: an RMS probe would
        have to open devices, and this method opens nothing."""
        from client.devices import select_device

        sel = select_device(
            list(self._enumerate_fn()),
            pinned=(self.cfg.get("mic_name") or None),
            extra_avoid=tuple(self.cfg.get("extra_avoid") or ()),
            rms_probe=None,
        )
        self.selection = sel
        return sel

    def open_capture_now(self) -> bool:
        """Resolve + open. False means IDLE_NO_MIC (or an open failure) —
        capture stays DOWN. There is never a fallback device (scar 21)."""
        from client.devices import Selection

        sel = self.resolve_device()
        if sel.state != Selection.SELECTED or sel.device is None:
            self._go_idle_no_mic(sel)
            return False
        return self._open(sel)

    def _open(self, sel) -> bool:
        from client.capture import CapturePipeline, FormatNegotiationError, negotiate_format
        from client.devices import DeviceOpenError, open_with_retry

        dev = sel.device
        native_rate, native_channels = self._native_format_fn(dev)
        try:
            cap_rate, cap_channels = negotiate_format(
                lambda rate, ch: self._check_format_fn(dev, rate, ch),
                native_rate=int(native_rate),
                native_channels=int(native_channels))
        except FormatNegotiationError as exc:
            self.telemetry.event("STATE", level="ERROR",
                                 state="FORMAT_NEGOTIATION_FAIL",
                                 err=str(exc)[:120])
            self._go_idle_no_mic(sel)
            return False

        cap = CapturePipeline(cap_rate, cap_channels, block_ms=BLOCK_MS,
                              set_priority_fn=self._set_priority_fn,
                              on_event=self.capture_events)
        def open_and_start(d):
            """OPEN **AND** START under one try, so the fallback chain covers
            both (2026-08-15).

            The bug this closes: `handle.start()` used to live below, OUTSIDE
            open_with_retry. The chain exists exactly so a device that will not
            work is skipped for the next one — but it only ever guarded the
            OPEN. A device that opened and then failed to START raised straight
            out of _open(), past DeviceOpenError, into the supervisor, which
            journalled RERESOLVE_ERROR and went IDLE_NO_MIC — with the rest of
            the chain never tried.

            Measured that day: 440 RERESOLVE_ERROR, every one of them
            'PortAudioError: Error STARTING stream ... WdmSyncIoctl', in a loop
            that ate ~40 minutes of Iddo's dictation and needed the watchdog to
            restart the process every ten minutes. Meanwhile a plain probe
            proved WASAPI (idx 20) and DirectSound (idx 9) both opened AND
            started the very same BRIO on demand — the two devices the chain
            was supposed to try.

            A half-open handle is closed here rather than leaked: PortAudio
            keeps the endpoint claimed until the handle dies, which is how
            KESHEV ended up losing a race against its own previous stream."""
            h = self._open_stream_fn(d, cap_rate, cap_channels, cap)
            try:
                h.start()
            except Exception:
                for action in ("stop", "close"):
                    fn = getattr(h, action, None)
                    if fn is None:
                        continue
                    try:
                        fn()
                    except Exception as close_exc:      # never silent (gate G1)
                        self.telemetry.event(
                            "DEVICE_CLOSE", level="ERROR",
                            err=f"cleanup after failed start: "
                                f"{type(close_exc).__name__}")
                raise
            return h

        try:
            handle, device = open_with_retry(
                open_and_start, sel.chain, sleep_fn=self._sleep)
        except DeviceOpenError as exc:
            self.telemetry.event("DEVICE_OPEN_FAIL", level="ERROR",
                                 err=str(exc)[:160])
            self._go_idle_no_mic(sel)
            return False

        self.capture = cap
        self.stream = handle
        self.device = device
        self.telemetry.event("DEVICE_OPEN", dev=device.name[:60],
                             hostapi=device.hostapi[:40], rate=cap_rate,
                             ch=cap_channels, pin=int(sel.pin_honored))
        self._set_state(STATE_CAPTURING)
        return True

    def reresolve_now(self) -> bool:
        """Close the current stream and resolve again (scar 25 silent-open,
        device loss, replug). The SEGMENTER IS NOT REBUILT."""
        self._reresolve.clear()
        self._close_stream("reresolve")
        return self.open_capture_now()

    def _close_stream(self, why: str) -> None:
        stream, self.stream = self.stream, None
        cap, self.capture = self.capture, None
        device, self.device = self.device, None
        if cap is not None:
            self._dropped_retired += cap.frames_dropped
            self._overflow_retired += cap.overflow_count
        if stream is None:
            return
        for action in ("stop", "close"):
            fn = getattr(stream, action, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — a stuck close is data
                self.telemetry.event("STATE", level="ERROR",
                                     state="DEVICE_CLOSE_ERROR", op=action,
                                     err=f"{type(exc).__name__}: {str(exc)[:80]}")
        self.telemetry.event("DEVICE_CLOSE", why=why,
                             dev=(device.name[:60] if device is not None else "?"))

    def _go_idle_no_mic(self, sel) -> None:
        self._set_state(STATE_IDLE_NO_MIC)
        self.telemetry.event("DEVICE_IDLE_NO_MIC",
                             refused=len(sel.refused) if sel is not None else 0)
        if sel is not None and sel.announcement:
            _stderr_line(sel.announcement)

    # -------------------------------------------------------------- threads

    def start(self) -> None:
        """Warm the worker, then start every thread in contract order."""
        if self._started:
            raise RuntimeError("app already started")
        self._started = True
        self.stop.clear()
        self.worker.start()                     # blocking warm
        self.focus_guard.start_watcher()        # 0.25s watcher (scar 34)
        self.open_capture_now()
        self._spawn("keshev-pump", self._pump)
        self._spawn("keshev-device-supervisor", self._supervise)
        self.router.start()
        if self.tray is not None:
            self._spawn("keshev-tray", self._tray_loop)
        if self.hotkeys is not None:
            # Owns its own thread (RegisterHotKey binds to the pumping
            # thread, so _spawn's guard cannot host it); registration
            # failures are journalled by the listener itself.
            self.hotkeys.start()

    def _spawn(self, name: str, target) -> None:
        """Every KESHEV thread runs under this guard.

        THE 2026-08-14 17:22 OUTAGE. The stream went silent, the supervisor
        called reresolve_now() -> _close_stream() -> open_capture_now(), and
        something in there raised. The exception escaped _supervise(), the bare
        daemon thread ceased, and NOTHING recorded it: no journal line, no state
        change, no reopen. The device had already been closed one line earlier,
        so KESHEV sat DEAF for four hours while every heartbeat still said
        READY. Iddo was at the printer. The tray had it right — one
        TRAY_IDLE_NO_MIC and a flashing red lamp, unwatched — but nothing ever
        tried to recover, because the thread that recovers was dead.

        A thread of this program may not die quietly. Any escape is journalled
        at ERROR with its type — and then the two kinds part company:

          CRITICAL (pump, device supervisor) — without these the client can
            never hear again, so the app is asked to STOP. A loud death that
            the desktop shortcut or Task Scheduler can restart beats a process
            that lingers reporting READY at a man who is talking to nobody.
          non-critical (tray) — cosmetic. It dies, it is journalled, and
            DICTATION KEEPS RUNNING. Killing the mic because the picture broke
            would be the same inversion as scar 12."""
        def guarded() -> None:
            try:
                target()
            except BaseException as exc:  # noqa: BLE001 — a dying thread is DATA
                self.telemetry.event(
                    "STATE", level="ERROR", state="THREAD_DIED", thread=name,
                    critical=int(name in CRITICAL_THREADS),
                    err=f"{type(exc).__name__}: {str(exc)[:120]}")
                _stderr_line(f"KESHEV: thread {name} died: "
                             f"{type(exc).__name__}: {exc}")
                if name in CRITICAL_THREADS:
                    self.stop.set()

        th = threading.Thread(target=guarded, name=name, daemon=True)
        th.start()
        self.threads.append(th)

    def _pump(self) -> None:
        """Capture frames -> segmenter. The ONLY consumer of capture.read."""
        while not self.stop.is_set():
            cap = self.capture
            if cap is None:
                self.stop.wait(0.1)
                continue
            frame = cap.read(timeout=0.1)
            if frame is not None:
                self.segmenter.feed(frame)

    def _tray_loop(self) -> None:
        """Re-observe once a second and push the reading to the backend. The
        tray holds no truth of its own, so a tray thread that dies leaves the
        icon stale — which is why the death is journalled rather than dropped:
        a frozen icon is exactly the lie K15 exists to prevent."""
        while not self.stop.is_set():
            try:
                self.tray.tick()
            except Exception as exc:  # noqa: BLE001 — a blind tray must SAY so
                self.telemetry.event("STATE", level="ERROR",
                                     state="TRAY_TICK_ERROR",
                                     err=f"{type(exc).__name__}: {str(exc)[:80]}")
            self.stop.wait(TRAY_TICK_S)

    def _supervise(self) -> None:
        """The device supervisor: acts on the re-resolve flag, and keeps
        looking for a mic while we are IDLE_NO_MIC. New policy — nothing in
        the repo owned 'the stream went silent -> reopen' before this."""
        misses = 0
        while not self.stop.is_set():
            triggered = self._reresolve.wait(SUPERVISOR_TICK_S)
            if self.stop.is_set():
                break
            if not triggered and self.state != STATE_IDLE_NO_MIC:
                continue
            # A FAILED REOPEN IS NORMAL AND SURVIVABLE — the device may be
            # unplugged, held by something else, or mid-enumeration. On
            # 2026-08-14 an exception from this call escaped the thread and
            # killed the only code that can ever reopen a microphone, one line
            # after the stream had been closed: four silent deaf hours. The
            # supervisor now treats a throwing reopen exactly like a failing
            # one — journal it, back off, TRY AGAIN — because a supervisor that
            # can die is not a supervisor.
            try:
                reopened = self.reresolve_now()
            except Exception as exc:  # noqa: BLE001 — the reopen path is hostile
                self.telemetry.event("STATE", level="ERROR",
                                     state="RERESOLVE_ERROR",
                                     err=f"{type(exc).__name__}: {str(exc)[:100]}")
                self._set_state(STATE_IDLE_NO_MIC)
                reopened = False
            if reopened:
                misses = 0
                continue
            delay = REOPEN_BACKOFF_S[min(misses, len(REOPEN_BACKOFF_S) - 1)]
            misses += 1
            self.stop.wait(delay)

    # ------------------------------------------------------------- shutdown

    def shutdown(self) -> None:
        """Exact reverse of start(), NO drain-on-exit. Records still queued
        keep their files and no terminal outcome; the next launch finds them
        through spool.orphans() and they land in recovered.txt (design 4.4's
        accepted crash window). A clean Quit mid-sentence therefore sends that
        sentence to recovered.txt, not to the screen — by design."""
        if self._shut:
            return
        self._shut = True
        self.stop.set()
        self._reresolve.set()                   # wake the supervisor to exit
        if self.hotkeys is not None:
            self.hotkeys.stop()
        self._close_stream("shutdown")
        for th in self.threads:
            th.join(timeout=JOIN_TIMEOUT_S)
        self.threads = []
        self.segmenter.flush()                  # the open segment is preserved
        if self.tray is not None:
            self.tray.backend.stop()
        if self._started:
            if self.router is not None:
                self.router.stop(timeout=ROUTER_STOP_TIMEOUT_S)
            self.worker.stop()
            self.focus_guard.stop_watcher()
        self._set_state(STATE_STOPPED)
        self.telemetry.session_end(q=self.spool.qsize(),
                                   segs=self.segmenter.segments_enqueued,
                                   drop_frames=self.drop_frames())
        self.telemetry.close()


# ------------------------------------------------------------------ builder

def build_app(cfg: dict, *,
              state_dir: Path | str | None = None,
              session_id: str | None = None,
              telemetry=None,
              guard_fn: Callable[[dict], Any] | None = None,
              type_fn: Callable[[str], bool] | None = None,
              worker=None,
              spawn_fn=None,
              vram_free_fn=None,
              rss_fn=None,
              focus_api=None,
              input_api=None,
              clipboard=None,
              typer_idle_api=None,
              presence=None,
              arm=None,
              hotkey_api_factory=None,
              vad=None,
              enumerate_fn=None,
              native_format_fn=None,
              check_format_fn=None,
              open_stream_fn=None,
              set_priority_fn=None,
              sleep_fn=time.sleep) -> KeshevApp:
    """Assemble the client. Opens NO device, spawns NO subprocess, starts NO
    thread — call KeshevApp.start() for that."""
    from client.focus import FocusGuard, Win32FocusApi
    from client.presence import PresenceGate
    from client.router import Router
    from client.segmenter import Segmenter
    from client.spool import RecoveredTranscript, Spool
    from client.tray import FrameRecency, Tray, make_backend, snapshot_from_app
    from client.typer import Typer

    # Mandatory seams FIRST — refuse before any file, handle or directory is
    # created, so a half-wired build leaves nothing behind.
    if guard_fn is None:
        guard_fn = resolve_guard_fn()
    session_id = session_id or new_session_id()
    if not _SESSION_RE.match(session_id):
        raise AssemblyError(
            f"session id {session_id!r} is not 8 lowercase hex — every "
            f"segment id would fail common.protocol.valid_request_id and the "
            f"DGX would answer bad_request for the life of the process")

    state_dir = Path(state_dir) if state_dir is not None else STATE_DIR
    gate_rms = float(cfg["gate_rms"]["value"])

    tel = telemetry if telemetry is not None else Telemetry(state_dir, session_id)
    tel.session_begin(pid=os.getpid(), gate=gate_rms,
                      stale_sec=int(cfg["stale_sec"]),
                      anywhere=int(FOCUS_ANYWHERE_DEFAULT))

    spool = Spool(state_dir / "spool", on_event=tel.event)
    recovered = RecoveredTranscript(state_dir / "recovered.txt")
    # ONE segmenter for process life — it must survive every device change.
    segmenter = Segmenter(spool, gate_rms, session_id, vad=vad,
                          on_event=tel.event)

    if worker is None:
        from client.keshev_worker import read_free_vram_mb
        from client.worker_mgr import WorkerManager
        worker = WorkerManager(
            tel, spawn_fn if spawn_fn is not None else build_spawn_fn(cfg),
            vram_free_fn=vram_free_fn or read_free_vram_mb)

    guard = FocusGuard(api=focus_api if focus_api is not None else Win32FocusApi(),
                       own_pid=os.getpid(), emit=tel.event)
    guard.set_policy(anywhere=FOCUS_ANYWHERE_DEFAULT)
    # Hold-while-typing gate (the "מיHello.ק" collision, 2026-08-17): the
    # typer reads the SAME OS last-input boundary the presence gate reads.
    # The real clock is wired HERE, not defaulted inside Typer — a Typer
    # that self-built it would make every unit test depend on whether a
    # human touched the keyboard while the suite ran (the presence gate's
    # own documented scar). Injectable like focus_api/input_api/clipboard;
    # tests pass a quiet fake, and test_app asserts this wiring is not None.
    if typer_idle_api is None:
        from client.presence import Win32IdleApi
        typer_idle_api = Win32IdleApi()
    typer = Typer(guard, input_api=input_api, clip=clipboard,
                  state_dir=state_dir, emit=tel.event,
                  clipboard_restore=bool(cfg["clipboard_restore"]),
                  idle_api=typer_idle_api)

    if rss_fn is None:
        from client import keshev_worker as _kw
        rss_fn = _kw._rss_mb          # ONE copy of the RSS probe, not a second

    app = KeshevApp(
        cfg=cfg, state_dir=state_dir, session_id=session_id, telemetry=tel,
        spool=spool, recovered=recovered, segmenter=segmenter, worker=worker,
        focus_guard=guard, typer=typer,
        enumerate_fn=enumerate_fn or default_enumerate_devices,
        native_format_fn=native_format_fn or default_native_format,
        check_format_fn=check_format_fn or default_check_format,
        open_stream_fn=open_stream_fn or default_open_stream,
        set_priority_fn=set_priority_fn, sleep_fn=sleep_fn)

    # K19 presence gate (scar 58, 2026-08-15 09:46). focus.py answers WHERE
    # typing may land; this answers WHETHER IT MAY HAPPEN — the question no
    # other guard in the client asks, and the reason the room was typed into
    # his chat as him. Built here and consulted on every utterance below.
    # Injectable like every other boundary here (focus_api, input_api,
    # clipboard...). It has to be: the real gate reads the OS last-input
    # clock, so an un-injectable presence gate makes the whole test suite
    # depend on whether a human happened to touch the keyboard in the last
    # two minutes. test_type_fn_carries_auto_enter_from_config caught exactly
    # that — a green suite that goes red when it runs long enough.
    app.presence = presence if presence is not None else PresenceGate(emit=tel.event)

    # The arm switch (KESHEV B's surviving verdict, 2026-08-17): a DELIBERATE
    # consent gate layered over — never instead of — the presence gate.
    # presence.ARMED_MODE is False in the shipped tree, which makes this
    # switch transparent; flipping it on is a commit (design section 5).
    from client.presence import ArmSwitch
    app.arm = arm if arm is not None else ArmSwitch(emit=tel.event)

    if type_fn is None:
        auto_enter = bool(cfg["auto_enter"])

        def type_fn(text: str) -> bool:
            # Typer.park() already writes every refusal to state\parked.txt
            # and the router journals PARKED — do not park twice. The
            # presence refusal is OURS though, so it parks here: scar 35
            # (divert, never drop) applies to this gate exactly as to focus.
            if app.paused.is_set():
                typer.park(text, "paused")     # divert, never drop
                return False
            armed = app.arm.decide()
            if not armed.may_type:             # armed mode on, switch off
                typer.park(text, armed.reason)
                return False
            decision = app.presence.decide()
            if not decision.may_type:
                typer.park(text, decision.reason)
                return False
            return bool(typer.type(
                text, enter=auto_enter and decision.may_enter).ok)

    # The corpus: his own voice, captured ONLY from utterances that were
    # accepted into his window (client/corpus.py explains why that is the
    # right gate while the voice gate is unbuilt). OFF unless config says so.
    from client.corpus import CorpusWriter
    app.corpus = CorpusWriter(state_dir / "corpus",
                              enabled=bool(cfg.get("corpus_capture")))

    def on_typed(rec, text, res) -> None:
        if not app.corpus.enabled:
            return
        app.corpus.add(rec_id=rec.id, sid=session_id, pcm=rec.read_pcm(),
                       text=text, engine=str(res.get("engine", "?")),
                       source="typed")

    app.router = Router(spool, worker, tel, recovered=recovered,
                        type_fn=type_fn, guard_fn=guard_fn,
                        on_typed=on_typed,
                        stale_sec=float(cfg["stale_sec"]),
                        lang_hint=str(cfg.get("lang_hint", "he")), rss_fn=rss_fn,
                        drop_frames_fn=app.drop_frames)

    # K15 tray. Built here, ticked by KeshevApp._tray_loop. make_backend()
    # falls back to headless today (the Shell_NotifyIcon drawing code is
    # UNBUILT) and JOURNALS the fallback, so "there is no icon on the screen"
    # is a fact in the ledger rather than a surprise. Only quit is wired to a
    # real action; pause/recalibrate/restart-worker say "not wired yet" out
    # loud rather than doing nothing quietly.
    backend, _real = make_backend(emit=tel.event)
    recency = FrameRecency()
    app.tray = Tray(
        backend,
        snapshot_fn=lambda: snapshot_from_app(app, recency=recency,
                                              paused=app.paused.is_set()),
        emit=tel.event, state_dir=state_dir,
        # getattr, not worker.restart_graceful: an injected worker double need
        # not grow a method to be assembled, and a worker that cannot restart
        # makes the menu item say "not wired yet" instead of raising at build.
        on_restart_worker=getattr(worker, "restart_graceful", None),
        # Pause is REAL now, so the menu stops saying "not wired yet" — the
        # tray only claims an action it can actually perform.
        on_pause=app.pause,
        on_resume=app.resume,
        on_quit=app.stop.set)

    # Global hotkeys (2026-08-17). hotkey_pause sat in config since K1 with
    # nothing behind it — parse_hotkey's own docstring names that failure
    # mode and then no production code ever called RegisterHotKey. Bound for
    # real now, plus the push-to-arm chord when armed mode is on. A bad spec
    # or a chord another app owns is journalled at ERROR and shown by the
    # listener's `failed` list — never silent, never fatal to dictation.
    from client.hotkeys import HotkeyListener, Win32HotkeyApi
    from client.tray import HotkeyError, parse_hotkey
    app.hotkeys = HotkeyListener(
        emit=tel.event,
        api_factory=(hotkey_api_factory if hotkey_api_factory is not None
                     else Win32HotkeyApi))

    def _toggle_pause() -> None:
        if app.is_paused():
            app.resume()
        else:
            app.pause()

    try:
        app.hotkeys.add(parse_hotkey(cfg["hotkey_pause"]), _toggle_pause)
    except HotkeyError as exc:
        tel.event("STATE", level="ERROR", state="HOTKEY_BAD_SPEC",
                  err=str(exc)[:120])
    if app.arm.enabled:
        from client.presence import ARM_HOTKEY
        try:
            app.hotkeys.add(parse_hotkey(ARM_HOTKEY), app.arm.toggle)
        except HotkeyError as exc:  # a code-constant typo must scream (G1)
            tel.event("STATE", level="ERROR", state="HOTKEY_BAD_SPEC",
                      err=str(exc)[:120])
    return app


# -------------------------------------------------------------------- main

def _surface_existing_instance() -> None:
    """Duplicate-launch feedback (2026-08-25). Under pythonw a duplicate's
    exit 11 is invisible; during the ~70 s engine warm-up there is no window
    either, so a second double-click looked exactly like "KESHEV won't load".
    Bring the live instance's window to the front if it exists; otherwise say
    out loud that it is still loading. UI-only — the caller still exits 11."""
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = user32.FindWindowW(None, "KESHEV קשב")
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE — un-minimize if needed
        user32.SetForegroundWindow(hwnd)
    else:
        user32.MessageBoxW(
            None,
            "KESHEV is already starting — the window will appear "
            "in about a minute.\n"
            "קשב כבר נטען — החלון יופיע בעוד כדקה.",
            "KESHEV קשב",
            0x00040040)  # MB_ICONINFORMATION | MB_TOPMOST


def main(argv=None) -> int:
    _mutex = mutexguard.acquire_or_exit(name=mutexguard.MUTEX_NAME,
                                        log=_stderr_line,
                                        on_duplicate=_surface_existing_instance)
    # `_mutex` is anchored for process life inside mutexguard._HELD; the OS
    # releases it on death. Production NEVER releases it (scar 1).
    alive, why = almamic_alive(list_procs_fn=default_list_procs,
                               list_tasks_fn=default_list_tasks)
    if alive:
        _stderr_line(
            f"KESHEV refuses to start: alma-mic is alive ({why}). "
            f"Two dictation clients never share a microphone — run "
            f"tools/mic-switch.ps1 new to hand the mic over first "
            f"(criterion 23, scar 56). exit {EXIT_ALMAMIC_ALIVE}")
        return EXIT_ALMAMIC_ALIVE

    cfg = ConfigStore(CONFIG_PATH).load_or_halt()

    try:
        app = build_app(cfg)
    except AssemblyError as exc:
        _stderr_line(f"KESHEV refuses to start: {exc} (exit {EXIT_UNWIRED})")
        return EXIT_UNWIRED

    app.start()
    try:
        _run_ui(app)
    except KeyboardInterrupt:
        _stderr_line("KESHEV: interrupt — shutting down")
    finally:
        app.shutdown()
    return EXIT_OK


def _run_ui(app: KeshevApp) -> None:
    """Own the main thread with the window if there is a display to draw on,
    and fall back to the headless wait otherwise. KESHEV keeps dictating either
    way: every capture/decode/type thread runs underneath this call, so a
    window that cannot open costs the picture, never the mic (scar 12's rule —
    the visible layer must never be able to take the audio path down)."""
    from client.window import KeshevWindow

    try:
        win = KeshevWindow(app.tray, on_quit=app.stop.set,
                           level_fn=app.input_level)
    except Exception as exc:  # noqa: BLE001 — no display is survivable, silence is not
        app.telemetry.event("STATE", level="ERROR", state="WINDOW_UNAVAILABLE",
                            err=f"{type(exc).__name__}: {str(exc)[:100]}")
        _stderr_line(f"KESHEV: no window ({type(exc).__name__}: {exc}) — "
                     f"dictation continues headless")
        while not app.stop.wait(1.0):
            continue
        return
    app.telemetry.event("STATE", state="WINDOW_OPEN")
    win.run()


if __name__ == "__main__":
    sys.exit(main())
