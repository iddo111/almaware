"""KESHEV 6 -- the floating window that owns Iddo's microphone.

Iddo, 2026-09-04 06:37:
  "אני רוצה שתהפוך את ה-GUI של קשב - אייקון זעיר שמרחף, ווידג'ט קטנצ'יק
   שמרחף. ואם אני רוצה אני יכול להגדיל אותו לחלון, לעשות לו מינימייז, ולסגור."

So: a tiny always-on-top badge by default, one click to the full window and
back, minimize, close. Started from app/gui.py and CHANGED -- every line of the
lifecycle below was written after a real failure and is carried over intact:

  * the window OWNS the mic (his law 2026-08-24): it spawns app/main.py with
    KESHEV_OWNER_PID=<its own pid>, records state/mic.pid, and kills the engine
    tree when it closes.
  * state/gui.heartbeat every 8 s from THIS Tk loop -- main.py's dead-man
    switch stops the microphone 60 s after it goes stale.
  * one-mic check before every start; absolute "keshev-next\\app\\main.py" on
    the command line so the rival-mic guards can see us (2026-09-02: both mics
    typed into his chat for 43 minutes).
  * the trial.log PermissionError branch (2026-08-25 "i cant load keshev").
  * the engine supervisor, the crash log, ABOVE_NORMAL/HIGH priorities.

WHAT IS NEW, and why (Broken Windows Law -- the window must not be able to
look fine while nothing arrives):

  1. It says which decoder is really running, read out of the ENGINE PROCESS's
     own environment block, not echoed from our config. On 2026-09-04 the
     config said eran1 and the engine was on :8738. A label that can lie is
     worse than no label.
  2. Health is a measured canary (/health on the server the engine is using),
     never a hardcoded ok.
  3. `decode=ok` is no longer called "typed". Measured on the live log: 9,701
     of 15,733 decode=ok segments were thrown away by textguard AFTER being
     decoded and routed. The old window counted every one of them as typed.
  4. The old segment regex matched none of the recent lines at all (main.py
     added `lp=`), so "הוקלדו" read 0 forever and the Hebrew arrived as
     backslash escapes. app/logread6.py fixes that and is tested against the
     real trial.log.
  5. Every not-listening state is loud: PAUSED, DEAF, "waiting for the
     decoder", a dead engine, a stale log, a decoder that stopped answering,
     and any use of the fallback server.
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime

import tkinter as tk
from tkinter import ttk

KESHEV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(KESHEV_ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import engine_probe            # noqa: E402  read-only look at the live engine
import logread6                # noqa: E402  the trial.log reader that actually matches

STATE_DIR = os.path.join(KESHEV_ROOT, "state")
PAUSE_FILE = os.path.join(STATE_DIR, "PAUSED")
MIC_PID_FILE = os.path.join(STATE_DIR, "mic.pid")
MIC_CHOICE_FILE = os.path.join(STATE_DIR, "mic-choice.json")
TRIAL_LOG = os.path.join(KESHEV_ROOT, "trial.log")
HEARTBEAT_FILE = os.path.join(STATE_DIR, "gui.heartbeat")
HEARTBEAT_MS = 8000

# KESHEV 6's own files -- never the engine's.
VIEW_FILE = os.path.join(STATE_DIR, "gui6-view.json")
GUI6_PID_FILE = os.path.join(STATE_DIR, "gui6.pid")
SHOW_FILE = os.path.join(STATE_DIR, "gui6.show")
CRASH_LOG = os.path.join(STATE_DIR, "gui6-crash.log")
GUI6_LOG = os.path.join(STATE_DIR, "gui6.log")

# ── bright palette (he likes bright) ─────────────────────────────────────────
BG = "#FFFFFF"
PANEL = "#F7F9FC"
LINE = "#E3E8EF"
INK = "#111827"
MUTED = "#6B7280"
BLUE = "#1E88E5"
GREEN = "#0E9F51"
AMBER = "#E08600"
RED = "#D62828"
CHIP = "#EEF4FD"

PILL_W, PILL_H = 258, 70
FULL_W, FULL_H = 480, 762

# ── stdout/stderr under pythonw.exe ──────────────────────────────────────────
# The window runs windowless so Iddo has no black console on his desktop. Under
# pythonw sys.stderr is None, and one library write to it would take the window
# down. Point both at our own log instead -- diagnostics kept, crash removed.
def _bootstrap_streams():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        if os.path.exists(GUI6_LOG) and os.path.getsize(GUI6_LOG) > 2_000_000:
            try:
                os.replace(GUI6_LOG, GUI6_LOG + ".1")
            except OSError:
                pass
        if sys.stdout is None or sys.stderr is None:
            fh = open(GUI6_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
            if sys.stdout is None:
                sys.stdout = fh
            if sys.stderr is None:
                sys.stderr = fh
    except Exception:
        pass


_bootstrap_streams()

# ── --selftest-render ────────────────────────────────────────────────────────
# Renders the real window, exercises pill/full/minimize/restore, writes a JSON
# report and exits. It NEVER starts an engine, NEVER opens an audio device,
# NEVER writes gui.heartbeat, mic.pid or PAUSED, and keeps its own files out of
# state/ so it cannot collide with a live KESHEV. Used to prove the window
# without going anywhere near Iddo's microphone.
DRY = [False]


def _enter_dry(scratch):
    global VIEW_FILE, GUI6_PID_FILE, SHOW_FILE, CRASH_LOG
    global MIC_PID_FILE, PAUSE_FILE, HEARTBEAT_FILE
    DRY[0] = True
    os.makedirs(scratch, exist_ok=True)
    VIEW_FILE = os.path.join(scratch, "gui6-view.json")
    GUI6_PID_FILE = os.path.join(scratch, "gui6.pid")
    SHOW_FILE = os.path.join(scratch, "gui6.show")
    CRASH_LOG = os.path.join(scratch, "gui6-crash.log")
    # read the SCRATCH copies of the mic's files, never the live ones: a test
    # can then stand up a fake engine and exercise the decoder panel without
    # going near state/mic.pid, state/PAUSED or state/gui.heartbeat.
    MIC_PID_FILE = os.path.join(scratch, "mic.pid")
    PAUSE_FILE = os.path.join(scratch, "PAUSED")
    HEARTBEAT_FILE = os.path.join(scratch, "gui.heartbeat")


def log(msg):
    try:
        print(f"[gui6 {datetime.now().strftime('%H:%M:%S')}] {msg}",
              file=sys.stderr, flush=True)
    except Exception:
        pass


# The ENGINE is always started with console python, never pythonw: main.py
# writes its whole timeline to stderr and that stream must be real.
def _engine_python():
    exe = sys.executable or "python.exe"
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            return cand
    return exe


ENGINE_PY = _engine_python()

# 2026-09-03: the heartbeat is written by this Tk loop. Under a saturated CPU the
# loop did not run for 32 s and the engine's dead-man switch fired on a LIVE
# window. Lift the window above the crowd (never REALTIME; never above the engine).
if os.name == "nt":
    try:
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        _k32 = ctypes.windll.kernel32
        # restype/argtypes matter: without them the pseudo-handle (-1) is truncated
        # on 64-bit and the call fails silently (measured 2026-09-03: prio=Normal).
        _k32.GetCurrentProcess.restype = ctypes.c_void_p
        _k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        _k32.SetPriorityClass(_k32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


# ── the mic lifecycle, carried over from gui.py unchanged in substance ───────
_mic_proc = None
_viewer_mode = [False]          # another window owns the mic: touch nothing


def touch_heartbeat():
    if DRY[0]:
        return True
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        # 2026-09-05: the plain open("w") failed 161 times in one day with
        # [Errno 22] Invalid argument -- the engine's dead-man reads this same
        # file on its own cycle, and on Windows a reader holding it makes the
        # truncating open fail outright. Harmless at 1/min (beats are every 8 s
        # and the dead-man waits 60 s) but it is a real collision, and it writes
        # a scary line into the log every time. Write beside it and rename:
        # os.replace is atomic on Windows, so a reader either sees the old file
        # or the new one and never blocks the writer.
        tmp = HEARTBEAT_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(os.getpid()))
        os.replace(tmp, HEARTBEAT_FILE)
        return True
    except OSError as exc:
        # a missed beat is survivable: the engine only stops after 60 s -- but say
        # so, because on 2026-09-03 08:29 the beats stopped after the second one
        # and the engine shut itself down with nobody the wiser.
        log(f"heartbeat write failed: {exc}")
        return False


def beat_forever(root):
    # Schedule the NEXT beat before writing this one, so nothing that happens in
    # the write can ever end the chain (2026-09-03 08:29: chain died at beat 2).
    try:
        root.after(HEARTBEAT_MS, lambda: beat_forever(root))
    except Exception as exc:
        log(f"heartbeat reschedule failed: {exc!r}")
        return
    if not _viewer_mode[0]:
        touch_heartbeat()


def clear_heartbeat():
    if DRY[0]:
        return
    try:
        os.remove(HEARTBEAT_FILE)
    except OSError:
        pass


def _pid_alive(pid, want_python=False):
    """tasklist, not os.kill: on Windows os.kill(pid, 0) TERMINATES the process."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if str(pid) not in out.stdout:
            return False
        if want_python and "python" not in out.stdout.lower():
            return False            # the pid was recycled by something else
        return True
    except Exception:
        return False


def list_input_devices():
    """Ask the ENGINE which mics the Sacred-Audio fence allows. Never enumerate
    audio devices in this process, and never on the Tk thread."""
    try:
        out = subprocess.run(
            [ENGINE_PY, "-X", "utf8", os.path.join(KESHEV_ROOT, "app", "main.py"),
             "--list-devices"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as exc:
        log(f"list_input_devices failed: {type(exc).__name__}: {exc}")
        return []


def read_mic_choice():
    try:
        with open(MIC_CHOICE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"mode": "default"}


def write_mic_choice(choice):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = MIC_CHOICE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(choice, fh, ensure_ascii=False)
    os.replace(tmp, MIC_CHOICE_FILE)


def start_mic():
    """Start app/main.py as a child, unless a live mic is already in mic.pid."""
    global _mic_proc
    if _viewer_mode[0] or DRY[0]:
        return
    try:
        if os.path.exists(MIC_PID_FILE):
            old = int(open(MIC_PID_FILE).read().strip() or "0")
            if old and _pid_alive(old, want_python=True):
                return  # a mic is already running; never start a second (ONE-MIC LAW)
    except Exception:
        pass
    os.makedirs(STATE_DIR, exist_ok=True)
    touch_heartbeat()      # exists before the engine arms its dead-man switch
    try:
        logf = open(TRIAL_LOG, "a", encoding="utf-8", errors="ignore")
    except PermissionError:
        # trial.log is locked by an engine started OUTSIDE the window. Starting a
        # second engine is forbidden, and dying here is worse: on 2026-08-25 this
        # exact line crashed the window before it opened ("i cant load keshev").
        # Stay a viewer of the running engine instead.
        log("trial.log is locked -- staying a viewer, not starting an engine")
        return
    logf.write(f"\n=== gui6 start mic {datetime.now().isoformat()} ===\n")
    logf.flush()
    # Absolute path on purpose: rival-mic guards (mic-rebuild's ALMA_PROC_RE)
    # recognize this engine by "keshev-next" in its command line. A relative
    # "app\main.py" is invisible to them (2026-08-25, the two-typers night).
    _mic_proc = subprocess.Popen(
        [ENGINE_PY, "-X", "utf8", os.path.join(KESHEV_ROOT, "app", "main.py")],
        cwd=KESHEV_ROOT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8",
                 KESHEV_OWNER_PID=str(os.getpid())),
        stdout=logf, stderr=subprocess.STDOUT,
        # HIGH is the 2026-09-03 19:50 starvation fix: at NORMAL the engine lost
        # 256 audio blocks in 8 minutes behind two render jobs and the dead-man
        # switch fired three times on a live window.
        creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                       | subprocess.HIGH_PRIORITY_CLASS) if os.name == "nt" else 0,
    )
    try:
        with open(MIC_PID_FILE, "w") as f:
            f.write(str(_mic_proc.pid))
    except Exception:
        pass
    log(f"engine started pid={_mic_proc.pid} owner={os.getpid()}")


def stop_mic():
    """Kill the mic child tree. Called on close -- no window, no mic."""
    global _mic_proc
    if _viewer_mode[0] or DRY[0]:
        return          # not ours to kill
    pids = []
    if _mic_proc is not None:
        pids.append(_mic_proc.pid)
    try:
        if os.path.exists(MIC_PID_FILE):
            p = int(open(MIC_PID_FILE).read().strip() or "0")
            if p:
                pids.append(p)
    except Exception:
        pass
    for pid in set(pids):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    try:
        if os.path.exists(MIC_PID_FILE):
            os.remove(MIC_PID_FILE)
    except Exception:
        pass
    clear_heartbeat()
    _mic_proc = None
    log("engine stopped")


# ── remembered view (mode + where he parked it) ──────────────────────────────

def read_view():
    try:
        with open(VIEW_FILE, encoding="utf-8") as fh:
            v = json.load(fh)
        if isinstance(v, dict):
            return v
    except Exception:
        pass
    return {}


def write_view(view):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = VIEW_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(view, fh, ensure_ascii=False)
        os.replace(tmp, VIEW_FILE)
    except Exception:
        pass


def virtual_screen():
    """The whole desktop, all monitors -- so a position saved on his second
    screen is not 'corrected' onto the first one."""
    try:
        gsm = ctypes.windll.user32.GetSystemMetrics
        x, y, w, h = gsm(76), gsm(77), gsm(78), gsm(79)
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return None


# ── the engine's truth, gathered off the Tk thread ───────────────────────────
# Network calls and ReadProcessMemory NEVER run on the Tk thread: a stalled Tk
# loop stops the heartbeat and the engine kills the microphone 60 s later.

TRUTH = {
    "engine_pid": 0,
    "stt_url": "",
    "fallback_url": "",
    "env_read_ok": False,
    "health": None,          # dict from engine_probe.probe_health
    "health_at": 0.0,
    "fb_health": None,
    "checked": False,
}
TRUTH_LOCK = threading.Lock()
_probe_stop = threading.Event()


def probe_loop():
    last_env_pid = -1
    last_health = 0.0
    last_fb = 0.0
    while not _probe_stop.is_set():
        try:
            pid = 0
            try:
                if os.path.exists(MIC_PID_FILE):
                    pid = int(open(MIC_PID_FILE).read().strip() or "0")
            except Exception:
                pid = 0

            if pid != last_env_pid:
                last_env_pid = pid
                env = engine_probe.read_engine_env(pid) if pid else None
                with TRUTH_LOCK:
                    TRUTH["engine_pid"] = pid
                    TRUTH["env_read_ok"] = env is not None
                    TRUTH["stt_url"] = (env or {}).get("KESHEV_STT_URL", "") if env else ""
                    TRUTH["fallback_url"] = (env or {}).get("KESHEV_STT_FALLBACK_URL", "") if env else ""
                    TRUTH["health"] = None
                    TRUTH["checked"] = True
                last_health = 0.0

            now = time.time()
            with TRUTH_LOCK:
                url = TRUTH["stt_url"]
                fb = TRUTH["fallback_url"]
            if url and now - last_health >= 8.0:
                last_health = now
                h = engine_probe.probe_health(url)
                with TRUTH_LOCK:
                    TRUTH["health"] = h
                    TRUTH["health_at"] = now
                    TRUTH["checked"] = True
            if fb and now - last_fb >= 45.0:
                last_fb = now
                hf = engine_probe.probe_health(fb)
                with TRUTH_LOCK:
                    TRUTH["fb_health"] = hf
            if not url and pid == 0:
                with TRUTH_LOCK:
                    TRUTH["checked"] = True
        except Exception as exc:
            log(f"probe loop: {type(exc).__name__}: {exc}")
        _probe_stop.wait(2.0)


def _run_selftest(root, outdir, set_mode, do_minimize, show_self, mode,
                  pending_pill, compute_state, S, TRUTH, TRUTH_LOCK):
    """Drive the window through every mode it has and record what really happened.

    This is the only way to prove the overrideredirect/minimize dance short of
    Iddo clicking it: a badge that cannot be un-minimized is the failure this
    whole job had to avoid.
    """
    steps = []
    shots = []

    def snap(label):
        try:
            root.update_idletasks()
            steps.append({
                "step": label,
                "mode": mode[0],
                "wm_state": root.state(),
                "overrideredirect": bool(root.overrideredirect()),
                "geometry": root.winfo_geometry(),
                "w": root.winfo_width(), "h": root.winfo_height(),
                "x": root.winfo_x(), "y": root.winfo_y(),
                "viewable": bool(root.winfo_viewable()),
                "topmost": bool(root.attributes("-topmost")),
            })
        except Exception as exc:
            steps.append({"step": label, "error": f"{type(exc).__name__}: {exc}"})

    def shoot(name):
        # a desktop BitBlt of the window's rectangle, so the badge can be looked
        # at rather than imagined. Never PrintWindow: see tools/capture6.py.
        try:
            tools = os.path.join(KESHEV_ROOT, "tools")
            if tools not in sys.path:
                sys.path.insert(0, tools)
            import capture6
            try:
                root.lift()
                root.update()          # a real paint, not just idle tasks
            except Exception:
                pass
            path = os.path.join(outdir, name + ".png")
            if capture6.grab_window(root.winfo_id(), path):
                shots.append(path)
        except Exception as exc:
            steps.append({"step": "shoot:" + name, "error": repr(exc)})

    def inventory(label):
        """What is actually on screen, by widget -- deterministic, unlike a
        screenshot that can catch the window mid-paint."""
        rows = []

        def walk(w, depth=0):
            try:
                cls = w.winfo_class()
                item = {"cls": cls, "depth": depth,
                        "w": w.winfo_width(), "h": w.winfo_height(),
                        "mapped": bool(w.winfo_ismapped())}
                try:
                    txt = w.cget("text")
                    if txt:
                        item["text"] = str(txt)
                except Exception:
                    pass
                try:
                    item["bg"] = str(w.cget("bg"))
                except Exception:
                    pass
                rows.append(item)
                for c in w.winfo_children():
                    walk(c, depth + 1)
            except Exception:
                pass
        walk(root)
        return {"label": label, "widgets": rows}

    invs = []
    seq = []

    def add(delay, fn):
        seq.append((delay, fn))

    add(900, lambda: snap("1-launch-default"))
    add(350, lambda: (shoot("pill"), invs.append(inventory("pill"))))
    add(300, lambda: (set_mode("full"), snap("2-expanded")))
    add(500, lambda: (shoot("full"), invs.append(inventory("full"))))
    add(400, lambda: (set_mode("pill"), snap("3-collapsed-back")))
    add(400, lambda: (do_minimize(), snap("4-minimized-from-pill")))
    add(900, lambda: snap("5-still-minimized"))
    add(200, lambda: (root.deiconify(), snap("6-restored-by-user")))
    add(900, lambda: snap("7-after-auto-return-to-pill"))
    add(300, lambda: (set_mode("full"), do_minimize(), snap("8-minimized-from-full")))
    add(700, lambda: (root.deiconify(), snap("9-restored-stays-full")))
    add(500, lambda: (show_self(), snap("10-show-self-recovery")))

    def finish():
        key, text, colour, detail, short = compute_state()
        with TRUTH_LOCK:
            truth = dict(TRUTH)
        report = {
            "when": datetime.now().isoformat(),
            "pill_target": [PILL_W, PILL_H],
            "full_target": [FULL_W, FULL_H],
            "steps": steps,
            "screenshots": shots,
            "state_machine": {"key": key, "text": text, "colour": colour, "detail": detail},
            "inventories": invs,
            "counters": {k: S[k] for k in ("typed", "guarded", "empty", "fail",
                                           "blocked", "skip", "ui_errors")},
            "engine_truth": {k: truth[k] for k in ("engine_pid", "stt_url",
                                                   "fallback_url", "env_read_ok")},
            "health": truth["health"],
            "ui_errors": S["ui_errors"],
            "last_ui_error": S["last_ui_error"],
        }
        try:
            with open(os.path.join(outdir, "selftest.json"), "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        root.destroy()

    t = 0
    for delay, fn in seq:
        t += delay
        root.after(t, fn)
    root.after(t + 500, finish)


def main():
    log_file = TRIAL_LOG
    selftest = ""
    hold_s = 0.0
    force_mode = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--selftest-render"):
            selftest = arg.partition("=")[2] or os.path.join(STATE_DIR, "gui6-selftest")
            _enter_dry(selftest)
        elif arg.startswith("--selftest-hold="):
            # render and sit still, so ANOTHER process can photograph the window.
            # Never photograph it from inside: a synchronous PrintWindow into a
            # window from its own Tk callback deadlocks, and that is the loop
            # that keeps Iddo's microphone alive.
            hold_s = float(arg.partition("=")[2] or "6")
        elif arg.startswith("--selftest-dir="):
            selftest = arg.partition("=")[2]
            _enter_dry(selftest)
        elif arg.startswith("--mode="):
            force_mode = arg.partition("=")[2]
        elif not arg.startswith("--"):
            log_file = arg
    if (hold_s or force_mode) and not DRY[0]:
        # --selftest-hold / --mode are test scaffolding. Without this, passing
        # one of them WITHOUT --selftest-dir would run the window for real and
        # open Iddo's microphone. A test flag must never be able to do that.
        selftest = os.path.join(STATE_DIR, "gui6-selftest")
        _enter_dry(selftest)

    # ── ONE WINDOW: hand the running one the focus instead of opening a second.
    # Two windows would write the same gui.heartbeat and both supervisors would
    # race to restart the engine; the dead-man switch cannot tell them apart.
    # It is also the guaranteed way back if he ever loses the badge: run the
    # shortcut again and the live window un-minimizes itself.
    try:
        if os.path.exists(GUI6_PID_FILE):
            other = int(open(GUI6_PID_FILE).read().strip() or "0")
            if other and other != os.getpid() and _pid_alive(other, want_python=True):
                with open(SHOW_FILE, "w") as fh:
                    fh.write(str(time.time()))
                log(f"KESHEV 6 already running (pid {other}) -- asked it to show itself")
                return
    except Exception:
        pass

    # ── VIEWER MODE: is another window already the mic's owner?
    # (the old KESHEV 5 gui.py, for instance). If so we must not beat, must not
    # start an engine and must not kill one on close.
    try:
        hb_pid = int(open(HEARTBEAT_FILE).read().strip() or "0") if os.path.exists(HEARTBEAT_FILE) else 0
        mic_pid = int(open(MIC_PID_FILE).read().strip() or "0") if os.path.exists(MIC_PID_FILE) else 0
        if (hb_pid and hb_pid != os.getpid() and _pid_alive(hb_pid, want_python=True)
                and mic_pid and _pid_alive(mic_pid, want_python=True)):
            _viewer_mode[0] = True
            log(f"VIEWER MODE: window pid {hb_pid} already owns engine {mic_pid}")
    except Exception:
        pass

    try:
        with open(GUI6_PID_FILE, "w") as fh:
            fh.write(str(os.getpid()))
    except Exception:
        pass

    # ── log tail state (start near the tail: history is not this session) ────
    try:
        offset = max(0, os.path.getsize(log_file) - 65536)
    except OSError:
        offset = 0
    partial_line = b""
    catching_up = True

    S = {
        "mic": None,               # device / rates from the engine's own banner
        "drops": 0,
        "typed": 0, "guarded": 0, "empty": 0, "fail": 0, "blocked": 0,
        "skip": 0, "backlog": 0, "confidence": 0,
        "last_typed_text": "", "last_typed_at": 0.0,
        "last_verdict": "", "last_reason": "", "last_seg_at": 0.0,
        "peak_rms": 0,
        "deaf_at": 0.0, "deaf_msg": "",
        "waiting_since": 0.0, "waiting_state": "", "decoder_ready": False,
        "no_mic": False,
        "fallback_n": 0, "fallback_url": "", "fallback_at": 0.0,
        "admin_until": 0.0, "admin_proc": "",
        "ui_errors": 0, "last_ui_error": "", "ui_error_at": 0.0,
    }
    pending_guard = {}
    segments = deque(maxlen=14)
    recent = deque(maxlen=400)     # (t, verdict) for the 5-minute rate

    def parse_line(line):
        line = line.strip()
        if not line:
            return
        # 2026-09-11: the engine now stamps every line with HH:MM:SS
        # (app/logstamp.py). Every pattern below is ^-anchored, so the stamp
        # comes off first. An unstamped line (old log, replayed fixture) is
        # returned unchanged -- nothing that worked yesterday stops working.
        line = logread6.unstamp(line)

        m = logread6.TEXTGUARD_RE.match(line)
        if m:
            pending_guard[int(m.group(1))] = m.group(2)
            if len(pending_guard) > 64:
                pending_guard.clear()
            return

        # 2026-09-06: the typer refused an elevated window -- decoded, routed, NOT
        # typed. Pair it like a textguard drop so the row says נחסם, not הוקלד.
        m = logread6.TYPER_REFUSED_RE.match(line)
        if m:
            pending_guard[int(m.group(1))] = "admin-window: " + m.group(2).split(" | ")[0]
            if len(pending_guard) > 64:
                pending_guard.clear()
            return

        m = logread6.TYPER_BLOCKED_RE.match(line)
        if m:
            if not catching_up:
                S["admin_until"] = time.time() + 20
                S["admin_proc"] = m.group(1)
            return

        m = logread6.DROPS_RE.match(line)
        if m:
            S["drops"] = int(m.group(2))
            return

        m = logread6.MIC_RE.search(line)
        if m:
            device, native, ri, ro, target, block = m.groups()
            S["mic"] = {"device": device, "native": native,
                        "resample": f"{ri}/{ro}", "target": target, "block": block}
            S["no_mic"] = False
            return

        if logread6.NO_MIC_RE.match(line):
            S["no_mic"] = True
            return

        m = logread6.DEAF_RE.match(line)
        if m:
            if not catching_up:
                S["deaf_at"] = time.time()
                S["deaf_msg"] = m.group(1)[:90]
            return

        if logread6.HEARTBEAT_RE.match(line):
            S["deaf_at"] = 0.0          # audio is arriving again
            return

        m = logread6.WAITING_RE.match(line)
        if m:
            S["waiting_state"] = m.group(1)
            S["decoder_ready"] = False
            if not S["waiting_since"]:
                S["waiting_since"] = time.time()
            return

        if logread6.READY_RE.match(line):
            S["waiting_since"] = 0.0
            S["waiting_state"] = ""
            S["decoder_ready"] = True
            return

        m = logread6.FALLBACK_RE.match(line)
        if m:
            if not catching_up:
                S["fallback_n"] += 1
                S["fallback_url"] = m.group(1)
                S["fallback_at"] = time.time()
            return

        if logread6.CONFIDENCE_RE.match(line):
            if not catching_up:
                S["confidence"] += 1
            return

        if logread6.BACKLOG_RE.match(line):
            if not catching_up:
                S["backlog"] += 1
            return

        d = logread6.parse_segment(line, pending_guard)
        if d is None:
            return
        S["peak_rms"] = d["peak_rms"]
        S["last_seg_at"] = time.time()
        if catching_up:
            return
        v = d["verdict"] if d["verdict"] in ("typed", "guarded", "empty", "fail",
                                             "blocked", "skip") else "empty"
        S[v] += 1
        S["last_verdict"] = v
        S["last_reason"] = d.get("reason") or ""
        recent.append((time.time(), v))
        if v == "typed":
            S["last_typed_text"] = d["text"]
            S["last_typed_at"] = time.time()
        if v != "skip":
            segments.appendleft({
                "time": datetime.now().strftime("%H:%M:%S"),
                "text": d["text"], "gate": d["gate"], "lp": d["lp"],
                "peak_rms": d["peak_rms"], "verdict": v,
                "reason": d.get("reason") or "",
            })

    # ── the honest state machine ────────────────────────────────────────────
    # Worst truth wins. Every branch here is a thing that has actually happened
    # to his mic; none of them may be reported as "fine".
    def compute_state():
        now = time.time()
        if _viewer_mode[0]:
            return ("viewer", "צופה בלבד", RED,
                    "חלון אחר (קשב 5) מחזיק את המיקרופון — סגור אותו",
                    "קשב 5 עדיין פתוח")
        if S["ui_errors"] and now - S["ui_error_at"] < 120:
            return ("uierror", "תקלת חלון", RED,
                    f"הלולאה נכשלה {S['ui_errors']}× — {S['last_ui_error'][:60]}",
                    f"הלולאה נכשלה {S['ui_errors']}×")
        if S["no_mic"]:
            return ("nomic", "אין מיקרופון", RED,
                    "כל הכניסות פסולות (אוזניות/בלוטות׳) — המנוע נשאר כבוי",
                    "אין כניסה מותרת")
        with TRUTH_LOCK:
            pid = TRUTH["engine_pid"]
            checked = TRUTH["checked"]
            health = TRUTH["health"]
            url = TRUTH["stt_url"]
        if checked and not pid:
            return ("noengine", "המנוע כבוי", RED,
                    "אין תהליך מנוע — מנסה להפעיל מחדש", "אין תהליך מנוע")
        if S["waiting_since"]:
            waited = int(now - S["waiting_since"])
            return ("waiting", "ממתין למפענח", RED,
                    f"המיקרופון עוד לא נפתח — {S['waiting_state']} ({waited}s)",
                    f"המיקרופון סגור ({waited}s)")
        if os.path.exists(PAUSE_FILE):
            return ("paused", "מושהה", AMBER,
                    "לא מקליד כלום — לחץ 'האזן' כדי לחזור", "לא מקליד")
        if S["deaf_at"] and now - S["deaf_at"] < 120:
            return ("deaf", "לא שומע", RED, S["deaf_msg"] or "לא מגיע שמע",
                    "לא מגיע שמע")
        try:
            log_age = now - os.path.getmtime(log_file)
        except OSError:
            log_age = 1e9
        if log_age > 90:
            return ("stale", "אין סימן חיים", RED,
                    f"המנוע לא כתב כלום {int(log_age)} שניות",
                    f"שותק {int(log_age)}s")
        if url and health is not None:
            if health["state"] != "READY":
                return ("decoder", "מפענח לא זמין", RED,
                        f"{engine_probe.short_tag(url)} → {health['state']}"
                        + (f" ({health['error']})" if health["error"] else ""),
                        f"{engine_probe.short_tag(url)} לא עונה")
            ca = health.get("canary_age_s")
            if ca is not None and ca > 900:
                return ("canary", "מפענח חשוד", AMBER,
                        f"הקנרי של {engine_probe.short_tag(url)} בן {int(ca)}s",
                        f"קנרי בן {int(ca)}s")
        if S["fallback_n"] and now - S["fallback_at"] < 900:
            return ("fallback", "גיבוי!", AMBER,
                    f"נענה ע\"י {engine_probe.short_tag(S['fallback_url'])} ×{S['fallback_n']}",
                    f"מודל גיבוי ×{S['fallback_n']}")
        return ("listening", "מקשיב", GREEN, "", "")

    def pill_second_line(key):
        """What is actually coming through -- or honestly, why nothing is."""
        now = time.time()
        if key in ("uierror", "viewer", "nomic", "noengine", "waiting", "deaf",
                   "stale", "decoder"):
            return "", MUTED
        if key == "paused":
            return "לא מקליד — מושהה", AMBER
        if S["last_typed_at"] and now - S["last_typed_at"] < 150:
            return S["last_typed_text"][:44] or "…", INK
        lv = S["last_verdict"]
        if lv == "guarded":
            return f"נחסם: {S['last_reason'][:26]}", AMBER
        if lv == "fail":
            return "המפענח לא ענה", RED
        if lv == "empty":
            return "פוענח ריק", MUTED
        if lv == "blocked":
            return "שער הבעלים חסם", MUTED
        if lv == "skip":
            return {"too-quiet": "שקט מדי", "vad": "לא זוהה דיבור",
                    "steady-noise": "רעש קבוע"}.get(S["last_reason"], "דילוג"), MUTED
        return "ממתין לדיבור", MUTED

    # ── window ──────────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("קשב 6 — KESHEV 6")
    root.configure(bg=BG)
    try:
        root.minsize(1, 1)
    except Exception:
        pass

    view = read_view()
    mode = ["pill" if view.get("mode", "pill") == "pill" else "full"]
    if force_mode in ("pill", "full"):
        mode[0] = force_mode
    topmost_var = tk.BooleanVar(value=bool(view.get("topmost", True)))
    pending_pill = [False]        # minimized from the pill: come back as a pill
    switching = [False]

    def clamp(x, y, w, h):
        vs = virtual_screen()
        if vs:
            vx, vy, vw, vh = vs
        else:
            vx, vy, vw, vh = 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
        # keep a real grab-handle on screen, whatever monitor was unplugged
        x = max(vx - w + 120, min(int(x), vx + vw - 60))
        y = max(vy, min(int(y), vy + vh - 40))
        return x, y

    vs = virtual_screen()
    def_x = (vs[0] + vs[2] - PILL_W - 24) if vs else (root.winfo_screenwidth() - PILL_W - 24)
    def_y = (vs[1] + 60) if vs else 60
    pill_pos = list(clamp(view.get("pill_x", def_x), view.get("pill_y", def_y), PILL_W, PILL_H))
    full_pos = list(clamp(view.get("full_x", def_x - FULL_W + PILL_W),
                          view.get("full_y", def_y), FULL_W, FULL_H))

    # ══ THE PILL ══════════════════════════════════════════════════════════
    pill = tk.Frame(root, bg=BG, highlightthickness=1, highlightbackground=LINE)

    stripe = tk.Frame(pill, bg=GREEN, width=7)
    stripe.pack(side="right", fill="y")
    stripe.pack_propagate(False)

    btnbar = tk.Frame(pill, bg=BG)
    btnbar.pack(side="left", padx=(5, 0), pady=(4, 0), anchor="n")

    def mini_button(parent, glyph, cmd, tip_color=MUTED):
        # a Label, not a tk.Button: a Button also fires on Space and Return once
        # focused, and that is exactly how the mic got paused twice in 90 minutes
        # (2026-08-28). A Label can only be clicked.
        b = tk.Label(parent, text=glyph, font=("Segoe UI", 10), bg=BG, fg=tip_color,
                     width=2, cursor="hand2")
        b.bind("<Button-1>", lambda _e: cmd())
        b.bind("<Enter>", lambda _e: b.config(bg=CHIP))
        b.bind("<Leave>", lambda _e: b.config(bg=BG))
        b.pack(side="left")
        return b

    pill_body = tk.Frame(pill, bg=BG)
    pill_body.pack(side="right", fill="both", expand=True, padx=(6, 8), pady=5)

    pill_l1 = tk.Frame(pill_body, bg=BG)
    pill_l1.pack(side="top", fill="x")
    tk.Label(pill_l1, text="קשב 6", font=("Arial", 12, "bold"),
             fg=BLUE, bg=BG).pack(side="right")
    pill_state = tk.Label(pill_l1, text="…", font=("Arial", 12, "bold"), fg=MUTED, bg=BG)
    pill_state.pack(side="right", padx=(0, 6))

    pill_l2 = tk.Frame(pill_body, bg=BG)
    pill_l2.pack(side="top", fill="x", pady=(1, 0))
    pill_dec = tk.Label(pill_l2, text="", font=("Arial", 8, "bold"), fg=MUTED, bg=BG)
    pill_dec.pack(side="right")
    pill_text = tk.Label(pill_l2, text="", font=("Arial", 9), fg=MUTED, bg=BG,
                         anchor="e", justify="right")
    pill_text.pack(side="right", fill="x", expand=True, padx=(0, 6))

    pill_bar = tk.Canvas(pill_body, height=5, bg="#EDF1F7", highlightthickness=0)
    pill_bar.pack(side="top", fill="x", pady=(4, 0))

    # ══ THE FULL WINDOW ═══════════════════════════════════════════════════
    full = tk.Frame(root, bg=BG)

    head = tk.Frame(full, bg=BG)
    head.pack(fill="x", padx=12, pady=(10, 2))
    tk.Label(head, text="קשב 6", font=("Arial", 26, "bold"), fg=BLUE, bg=BG).pack(side="right")
    full_state = tk.Label(head, text="…", font=("Arial", 15, "bold"), fg=MUTED, bg=BG)
    full_state.pack(side="right", padx=(0, 10))
    collapse_lbl = tk.Label(head, text="⤡", font=("Segoe UI", 15), fg=BLUE, bg=BG,
                            cursor="hand2")
    collapse_lbl.pack(side="left")

    full_detail = tk.Label(full, text="", font=("Arial", 10), fg=MUTED, bg=BG,
                           anchor="e", justify="right", wraplength=440)
    full_detail.pack(fill="x", padx=12, pady=(0, 6))

    # ── the decoder panel: measured, never echoed ───────────────────────────
    dec_panel = tk.Frame(full, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
    dec_panel.pack(fill="x", padx=12, pady=(0, 8))
    dec_line1 = tk.Label(dec_panel, text="מפענח: …", font=("Arial", 11, "bold"),
                         fg=INK, bg=PANEL, anchor="e", justify="right")
    dec_line1.pack(fill="x", padx=8, pady=(6, 0))
    dec_line2 = tk.Label(dec_panel, text="", font=("Arial", 9), fg=MUTED, bg=PANEL,
                         anchor="e", justify="right", wraplength=430)
    dec_line2.pack(fill="x", padx=8, pady=(1, 6))
    fb_banner = tk.Label(dec_panel, text="", bg=AMBER, fg="#FFFFFF",
                         font=("Arial", 10, "bold"), wraplength=430, justify="center")

    # ── mic chooser (the engine decides what is allowed; we only offer it) ──
    mic_row = tk.Frame(full, bg=BG)
    mic_row.pack(fill="x", padx=12, pady=(0, 0))
    tk.Label(mic_row, text="🎙 מיקרופון:", font=("Arial", 11, "bold"),
             fg=BLUE, bg=BG).pack(side="right", padx=(6, 0))
    mic_devices = []
    mic_combo = ttk.Combobox(mic_row, state="readonly", font=("Arial", 10))
    mic_combo.pack(side="right", fill="x", expand=True)

    mic_note = tk.Label(full, text="", font=("Arial", 9), fg=MUTED, bg=BG,
                        anchor="e", justify="right")
    mic_note.pack(fill="x", padx=12, pady=(2, 0))
    drops_label = tk.Label(full, text="נפילות שמע: 0", font=("Arial", 9), fg=MUTED,
                           bg=BG, anchor="e", justify="right")
    drops_label.pack(fill="x", padx=12)

    pause_wrap = tk.Frame(full, bg=RED)
    pause_button = tk.Button(pause_wrap, text="השהה 🔴", font=("Arial", 17, "bold"),
                             bg=BG, fg=RED, command=lambda: toggle_pause(),
                             takefocus=0, padx=18, pady=12, bd=0, relief="flat",
                             highlightthickness=0, activebackground=CHIP)
    # takefocus=0 (2026-08-28): a focused tk.Button also fires on Space and
    # Return. This one is full-width and near the top, so a stray space silently
    # paused the mic -- twice in 90 minutes, and both times Iddo reported "the
    # mic doesn't work" not knowing he had done it. Only a mouse click pauses.
    pause_wrap.pack(fill="x", padx=12, pady=(6, 8))
    pause_button.pack(fill="x", padx=2, pady=2)

    # Both banners live in `full` and stay packed-in-order children of it, so
    # `before=status_label` can never raise while the pill is showing: collapsing
    # only pack_forget()s `full` itself, never its children (a TclError in here
    # would be raised inside update_status and would kill the poll chain, which
    # also carries the engine supervisor).
    pause_banner = tk.Label(full, text="⏸ מושהה — המיקרופון לא מקליד", bg=AMBER,
                            fg="#FFFFFF", font=("Arial", 13, "bold"))
    admin_banner = tk.Label(full, text="", bg=RED, fg="#FFFFFF",
                            font=("Arial", 11, "bold"), wraplength=430, justify="center")

    status_label = tk.Label(full, text="ממתין ללוג…", font=("Arial", 10), fg=INK,
                            bg=BG, anchor="e", justify="right")
    status_label.pack(fill="x", padx=12, pady=(4, 6))

    status_row = tk.Frame(full, bg=BG)
    status_row.pack(fill="x", padx=12)
    canvas_dot = tk.Canvas(status_row, width=18, height=18, bg=BG, highlightthickness=0)
    canvas_dot.pack(side="left")
    canvas_dot.create_oval(2, 2, 15, 15, fill="#BBBBBB", outline="")

    def toggle_topmost():
        try:
            root.attributes("-topmost", topmost_var.get())
        except Exception:
            pass
        save_view()

    tk.Checkbutton(status_row, text="תמיד עליון", variable=topmost_var,
                   command=toggle_topmost, bg=BG, fg=INK, font=("Arial", 9),
                   selectcolor="#E0E0E0", takefocus=0,
                   activebackground=BG).pack(side="left", padx=(12, 0))
    tk.Label(status_row, text="⤡ כווץ לתג", font=("Arial", 9), fg=BLUE, bg=BG,
             cursor="hand2").pack(side="left", padx=(12, 0))

    # ── what actually reached his chat ──────────────────────────────────────
    tk.Label(full, text="מה עבר בפועל", font=("Arial", 10, "bold"), fg=MUTED, bg=BG,
             anchor="e").pack(fill="x", padx=12, pady=(10, 2))

    middle = tk.Frame(full, bg=BG, highlightthickness=1, highlightbackground=LINE)
    middle.pack(fill="both", expand=True, padx=12)
    canvas_seg = tk.Canvas(middle, bg=BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(middle, orient="vertical", command=canvas_seg.yview)
    segment_container = tk.Frame(canvas_seg, bg=BG)
    segment_container.bind("<Configure>",
                           lambda e: canvas_seg.configure(scrollregion=canvas_seg.bbox("all")))
    seg_window = canvas_seg.create_window((0, 0), window=segment_container, anchor="nw")
    canvas_seg.bind("<Configure>",
                    lambda e: canvas_seg.itemconfigure(seg_window, width=e.width))
    canvas_seg.configure(yscrollcommand=scrollbar.set)
    # bound to the canvas, NOT bind_all: gui.py's application-wide wheel binding
    # fires inside every other window of this interpreter.
    canvas_seg.bind("<MouseWheel>",
                    lambda e: canvas_seg.yview_scroll(int(-1 * (e.delta / 120)), "units"))
    canvas_seg.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    bottom = tk.Frame(full, bg=BG)
    bottom.pack(fill="x", padx=12, pady=(8, 12))
    canvas_meter = tk.Canvas(bottom, height=22, bg="#EDF1F7", highlightthickness=1,
                             highlightbackground=LINE)
    canvas_meter.pack(fill="x")          # never a fixed 440 px again
    totals_label = tk.Label(bottom, text="", font=("Arial", 9), fg=INK, bg=BG,
                            anchor="e", justify="right")
    totals_label.pack(fill="x", pady=(5, 0))

    # ── mode switching: ONE root, forever ───────────────────────────────────
    # The mic's whole lifecycle hangs off this process: its pid is the engine's
    # KESHEV_OWNER_PID and this loop writes gui.heartbeat. Expand/collapse must
    # therefore be geometry on the SAME root -- never a new Tk(), never a new
    # process. A new pid and the dead-man switch kills the mic within 3 s.
    def _apply_frame(frameless):
        try:
            if bool(root.overrideredirect()) == bool(frameless):
                return
        except Exception:
            pass
        root.overrideredirect(bool(frameless))
        # Windows only applies the style change when the window is re-created,
        # and a plain overrideredirect() toggle can leave it invisible.
        try:
            root.withdraw()
            root.update_idletasks()
            root.deiconify()
            root.update_idletasks()
        except Exception:
            pass

    def capture_pos():
        """Remember where he has actually parked it -- only when that is real.

        Measured 2026-09-04: a geometry set immediately after the
        withdraw/deiconify of a frame change does NOT stick on Windows (the
        window lands at 0,0), and winfo_x() reports 0 until it does. Reading a
        position in that window would save 0,0 and park the badge in the corner
        on his next launch, forever.
        """
        if switching[0]:
            return
        try:
            if not root.winfo_viewable() or root.state() != "normal":
                return
            x, y = root.winfo_x(), root.winfo_y()
        except Exception:
            return
        if mode[0] == "pill":
            pill_pos[0], pill_pos[1] = x, y
        else:
            full_pos[0], full_pos[1] = x, y

    def set_mode(new_mode, save=True):
        if switching[0]:
            return
        capture_pos()
        switching[0] = True
        try:
            mode[0] = new_mode
            if new_mode == "pill":
                w, h, pos = PILL_W, PILL_H, pill_pos
            else:
                w, h, pos = FULL_W, FULL_H, full_pos
            x, y = clamp(pos[0], pos[1], w, h)
            pos[0], pos[1] = x, y
            geom = f"{w}x{h}+{x}+{y}"
            # set it BEFORE the frame change, again after, and once more on a
            # timer: only the "before" reliably survives the re-map, and the
            # later two heal anything Windows moved (see capture_pos above).
            try:
                root.geometry(geom)
            except Exception:
                pass
            if new_mode == "pill":
                full.pack_forget()
                _apply_frame(True)
                root.geometry(geom)
                pill.pack(fill="both", expand=True)
            else:
                pill.pack_forget()
                _apply_frame(False)
                root.geometry(geom)
                full.pack(fill="both", expand=True)
            try:
                root.attributes("-topmost", topmost_var.get())
            except Exception:
                pass
            root.after(80, lambda g=geom, m=new_mode:
                       (root.geometry(g) if mode[0] == m and root.state() == "normal" else None))
        finally:
            switching[0] = False
        if save:
            root.after(160, save_view)

    def save_view():
        capture_pos()
        write_view({"mode": mode[0], "pill_x": pill_pos[0], "pill_y": pill_pos[1],
                    "full_x": full_pos[0], "full_y": full_pos[1],
                    "topmost": bool(topmost_var.get())})

    def do_minimize():
        """Minimize that can always be undone.

        A window with overrideredirect(True) has NO taskbar button, so iconify()
        on the badge would put it somewhere Iddo cannot click it back from --
        the exact 'window he cannot get out of' this whole job must avoid. So:
        put the frame back FIRST (Windows then gives it a taskbar button), then
        minimize; when he restores it, poll() notices and returns it to the
        badge. Belt and braces: running the shortcut again also brings it back
        (see SHOW_FILE below), even if this dance ever fails.
        """
        try:
            if mode[0] == "pill":
                pending_pill[0] = True
                pill_pos[0], pill_pos[1] = root.winfo_x(), root.winfo_y()
                set_mode("full", save=False)
            root.iconify()
        except Exception as exc:
            log(f"minimize failed: {exc!r}")

    def show_self():
        """Come back from anywhere -- the guaranteed way home."""
        try:
            if root.state() != "normal":
                root.deiconify()
            if pending_pill[0]:
                pending_pill[0] = False
                set_mode("pill", save=False)
            root.lift()
            root.attributes("-topmost", True)
            if not topmost_var.get():
                root.after(1200, lambda: root.attributes("-topmost", False))
        except Exception as exc:
            log(f"show_self failed: {exc!r}")

    # ── 2026-09-04, Iddo: "בווידגט זה רק און אוף". The badge carries ONE
    # control and nothing else. Everything else moved into the window, which is
    # reached by clicking the badge and left by closing it.
    # A Label, never a tk.Button: a focused Button also fires on Space and
    # Return, and that is exactly how the mic got paused twice in 90 minutes
    # on 2026-08-28 while Iddo reported "the mic doesn't work".
    onoff = tk.Label(btnbar, text="ON", font=("Arial", 12, "bold"),
                     fg="#FFFFFF", bg=GREEN, width=4, height=2, cursor="hand2")
    onoff.pack(side="left", padx=(0, 2), pady=(0, 2))
    onoff.bind("<Button-1>", lambda _e: toggle_pause())

    # The window's own controls. ✕ CLOSES BACK TO THE BADGE and does not quit;
    # ⏻ is the only thing that ends the program, and it is red on purpose.
    mini_button(head, "✕", lambda: set_mode("pill"), BLUE)
    mini_button(head, "–", do_minimize, MUTED)
    mini_button(head, "⏻", lambda: on_close(), RED)
    collapse_lbl.bind("<Button-1>", lambda _e: set_mode("pill"))
    for w in status_row.winfo_children():
        if isinstance(w, tk.Label) and w.cget("text").startswith("⤡"):
            w.bind("<Button-1>", lambda _e: set_mode("pill"))

    # drag the badge anywhere; the buttons are excluded so a click cannot slide it
    drag = [0, 0]
    press_at = [0, 0]
    moved = [False]

    def drag_start(e):
        drag[0] = e.x_root - root.winfo_x()
        drag[1] = e.y_root - root.winfo_y()
        press_at[0], press_at[1] = e.x_root, e.y_root
        moved[0] = False

    def drag_move(e):
        if mode[0] != "pill":
            return
        if abs(e.x_root - press_at[0]) > 4 or abs(e.y_root - press_at[1]) > 4:
            moved[0] = True
        root.geometry(f"+{e.x_root - drag[0]}+{e.y_root - drag[1]}")

    def drag_end(_e):
        if mode[0] != "pill":
            return
        # A press that never moved is a CLICK, and a click on the badge opens
        # the window (2026-09-04). 4 px of slack, because a hand on a mouse is
        # never perfectly still and a badge that only opened on a pixel-perfect
        # click would read as broken.
        if not moved[0]:
            set_mode("full")
            return
        save_view()

    for w in (pill, pill_body, pill_l1, pill_l2, pill_state, pill_text,
              pill_dec, pill_bar, stripe):
        w.bind("<Button-1>", drag_start)
        w.bind("<B1-Motion>", drag_move)
        w.bind("<ButtonRelease-1>", drag_end)
        w.bind("<Double-Button-1>", lambda _e: set_mode("full"))

    # ── pause (the ONLY writer of state/PAUSED in the whole tree) ───────────
    def refresh_pause_ui():
        paused = os.path.exists(PAUSE_FILE)
        if paused:
            pause_button.config(text="האזן 🟢", bg=AMBER, fg="#FFFFFF")
            onoff.config(text="OFF", bg=RED)
            pause_wrap.config(bg=AMBER)
            if not pause_banner.winfo_ismapped():
                pause_banner.pack(fill="x", padx=12, pady=(4, 0), before=status_label)
        else:
            pause_button.config(text="השהה 🔴", bg=BG, fg=RED)
            onoff.config(text="ON", bg=GREEN)
            pause_wrap.config(bg=RED)
            if pause_banner.winfo_ismapped():
                pause_banner.pack_forget()

    def toggle_pause():
        if DRY[0]:
            return
        try:
            if os.path.exists(PAUSE_FILE):
                os.remove(PAUSE_FILE)
                log("PAUSED removed by button")
            else:
                os.makedirs(STATE_DIR, exist_ok=True)
                # 2026-09-06 17:20 -- SIGN THE PAUSE, because an unsigned one gets undone.
                # This button wrote a bare timestamp, byte-for-byte the shape of the
                # 2026-09-03 scar (an agent wrote state\PAUSED and walked away; Iddo had
                # no microphone until morning). tools\watchdogs\keshev_delivery_watchdog.py
                # clears exactly that shape after 15 minutes -- and at 17:20:48 today it
                # cleared IDDO'S OWN pause, 16 minutes after he pressed this button.
                # A watcher may only act on a state it can name. So name it: with who/why
                # present, that watchdog's looks_like_receipt guard leaves a human pause
                # alone however long it lasts.
                with open(PAUSE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "who": "iddo (pause button in KESHEV 6)",
                        "why": "הוא לחץ השהה -- the mic stays off until he presses האזן",
                        "at": datetime.now().isoformat(),
                        "restore": "press האזן in the window, or delete state\\PAUSED",
                        "disables": True,
                    }, f, ensure_ascii=False, indent=2)
                log("PAUSED written by button")
        except Exception as exc:
            log(f"toggle_pause failed: {exc!r}")
        refresh_pause_ui()

    # ── mic chooser wiring ──────────────────────────────────────────────────
    def refresh_mic_list(select_current=True):
        """list_input_devices() is a subprocess with a 30 s timeout. It ran on
        the Tk thread until 2026-09-03 08:45 and froze the heartbeat with it.
        The wait belongs in a worker; only the widget update is Tk's."""
        def work():
            devs = list_input_devices()
            try:
                root.after(0, lambda: _apply_mic_list(devs, select_current))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="mic-list").start()

    def _apply_mic_list(devs, select_current):
        nonlocal mic_devices
        mic_devices = [None] + devs
        pc_name = next((d["name"] for d in devs if d.get("is_pc_default")), None)
        labels = ["ברירת מחדל של המחשב" + (f"  ({pc_name})" if pc_name else "  (אין ברירת מחדל תקינה)")]
        for d in devs:
            labels.append(f"{d['name']}  [{d['hostapi']}]" + (" ⭐" if d.get("is_pc_default") else ""))
        mic_combo["values"] = labels
        if not select_current:
            return
        choice = read_mic_choice()
        idx = 0
        if choice.get("mode") != "default":
            for i, d in enumerate(devs):
                if d["name"] == choice.get("name") and d["hostapi"] == choice.get("hostapi"):
                    idx = i + 1
                    break
        try:
            mic_combo.current(idx)
        except Exception:
            pass

    def on_mic_selected(_event=None):
        if _viewer_mode[0]:
            mic_note.config(text="צופה בלבד — סגור את קשב 5 קודם", fg=RED)
            return
        i = mic_combo.current()
        if i < 0:
            return
        d = mic_devices[i] if i < len(mic_devices) else None
        if d is None:
            write_mic_choice({"mode": "default"})
            mic_note.config(text="עוקב אחרי ברירת המחדל של Windows", fg=MUTED)
        else:
            write_mic_choice({"mode": "pick", "name": d["name"], "hostapi": d["hostapi"]})
            mic_note.config(text=f"נבחר: {d['name']} — מפעיל מחדש…", fg=BLUE)
        stop_mic()
        # gui.py slept 1.0 s right here, on the Tk thread. after() does the same
        # wait without stopping the heartbeat that keeps the engine alive.
        root.after(1000, start_mic)
        root.after(3200, lambda: mic_note.config(text="המיקרופון הופעל מחדש", fg=GREEN))

    mic_combo.bind("<<ComboboxSelected>>", on_mic_selected)
    tk.Button(mic_row, text="⟳", font=("Arial", 11), bg=BG, fg=BLUE, takefocus=0,
              command=lambda: refresh_mic_list()).pack(side="left", padx=(6, 0))

    # ── drawing ─────────────────────────────────────────────────────────────
    VERDICT_BG = {"typed": "#DCF5E3", "guarded": "#FDF0D5", "empty": "#F1F3F6",
                  "fail": "#FBE0E0", "blocked": "#E9ECF1"}
    VERDICT_TAG = {"typed": "הוקלד", "guarded": "נחסם", "empty": "ריק",
                   "fail": "כשל", "blocked": "שער"}
    _seg_sig = [None]

    def update_segment_list():
        # rebuild only when it changed: gui.py rebuilt ~40 widgets every 300 ms
        # and cost ~25% of a core on an idle window (2026-08-28).
        sig = tuple((s["time"], s["text"], s["verdict"], s["reason"]) for s in segments)
        if sig == _seg_sig[0]:
            return
        _seg_sig[0] = sig
        for w in segment_container.winfo_children():
            w.destroy()
        for s in segments:
            bg = VERDICT_BG.get(s["verdict"], "#F1F3F6")
            row = tk.Frame(segment_container, bg=bg)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=s["time"], font=("Arial", 8), bg=bg,
                     fg=MUTED).pack(side="left", padx=(5, 6))
            tk.Label(row, text=VERDICT_TAG.get(s["verdict"], s["verdict"]),
                     font=("Arial", 8, "bold"), bg=bg,
                     fg=(GREEN if s["verdict"] == "typed" else
                         AMBER if s["verdict"] == "guarded" else
                         RED if s["verdict"] == "fail" else MUTED)
                     ).pack(side="left", padx=(0, 6))
            body = s["text"] or "—"
            if s["reason"]:
                body = f"{body}   ({s['reason']})" if s["text"] else f"({s['reason']})"
            heb = logread6.has_hebrew(body)
            tk.Label(row, text=body, font=("Arial", 10), bg=bg, fg=INK,
                     anchor="e" if heb else "w",
                     justify="right" if heb else "left"
                     ).pack(side="right" if heb else "left", fill="x",
                            expand=True, padx=6)

    def draw_bar(canvas, rms, colour):
        try:
            w = max(1, canvas.winfo_width())
            h = max(1, canvas.winfo_height())
            canvas.delete("all")
            frac = min(max(rms, 0) / 12000.0, 1.0)
            if frac > 0:
                canvas.create_rectangle(0, 0, int(w * frac), h, fill=colour, outline="")
        except Exception:
            pass

    def update_status():
        nonlocal offset, partial_line, catching_up

        # tail trial.log by byte offset -- the only channel there is
        try:
            if os.path.exists(log_file):
                with open(log_file, "rb") as f:
                    size = os.path.getsize(log_file)
                    if size < offset:
                        offset = 0
                    f.seek(offset)
                    data = f.read()
                    offset += len(data)
                blob = partial_line + data
                lines = blob.split(b"\n")
                partial_line = lines[-1]
                for raw in lines[:-1]:
                    try:
                        parse_line(raw.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
        except Exception:
            pass
        catching_up = False

        key, text, colour, detail, short = compute_state()
        with TRUTH_LOCK:
            url = TRUTH["stt_url"]
            fburl = TRUTH["fallback_url"]
            health = TRUTH["health"]
            fbh = TRUTH["fb_health"]
            env_ok = TRUTH["env_read_ok"]
            epid = TRUTH["engine_pid"]

        # ── the badge
        stripe.config(bg=colour)
        pill_state.config(text=text, fg=colour)
        line2, line2col = pill_second_line(key)
        if not line2 and short:
            line2, line2col = short, colour
        pill_text.config(text=line2, fg=line2col)
        if url:
            tag = engine_probe.short_tag(url)
            short = "6" if engine_probe.is_keshev6(url) else tag.split()[0]
            ok = bool(health) and health["state"] == "READY"
            pill_dec.config(text=short, fg=GREEN if ok else RED)
        else:
            pill_dec.config(text="?", fg=RED)
        draw_bar(pill_bar, S["peak_rms"], colour if key != "listening" else GREEN)

        # ── the full window
        full_state.config(text=text, fg=colour)
        full_detail.config(text=detail or "", fg=colour if detail else MUTED)

        if not url:
            dec_line1.config(text="מפענח: לא ידוע", fg=RED)
            dec_line2.config(
                text=("לא הצלחתי לקרוא את הסביבה של המנוע — לא אמציא כתובת"
                      if epid and not env_ok else "אין מנוע פעיל"))
        else:
            tag = engine_probe.short_tag(url)
            st = health["state"] if health else "…"
            ok = bool(health) and health["state"] == "READY"
            dec_line1.config(text=f"מפענח: {tag} · {st}",
                             fg=GREEN if ok else (MUTED if health is None else RED))
            bits = []
            if health:
                if health.get("model"):
                    bits.append(health["model"].split("/")[-1])
                if health.get("canary_age_s") is not None:
                    bits.append(f"קנרי {int(health['canary_age_s'])}s")
                if health.get("p50"):
                    bits.append(f"p50 {int(health['p50'])}ms")
                if health.get("error"):
                    bits.append(health["error"])
            bits.append("גיבוי: " + (engine_probe.short_tag(fburl) +
                                     (f" ({fbh['state']})" if fbh else "")
                                     if fburl else "אין"))
            dec_line2.config(text="  ·  ".join(bits))

        if S["fallback_n"]:
            fb_banner.config(
                text=f"⚠ הפענוח נענה ע\"י שרת הגיבוי {engine_probe.short_tag(S['fallback_url'])} "
                     f"×{S['fallback_n']} — המודל שונה")
            if not fb_banner.winfo_ismapped():
                fb_banner.pack(fill="x", padx=8, pady=(0, 6))
        elif fb_banner.winfo_ismapped():
            fb_banner.pack_forget()

        d = S["drops"]
        drops_label.config(
            text=f"נפילות שמע: {d}" + ("" if d < 10 else "  ⚠ המחשב עמוס"),
            fg=MUTED if d < 10 else (AMBER if d < 60 else RED))

        if S["mic"]:
            m = S["mic"]
            status_label.config(text=f"{m['device']}  |  {m['native']}Hz → {m['target']}Hz")
        else:
            status_label.config(text="אין נתוני מיקרופון עדיין")

        try:
            age = time.time() - os.path.getmtime(log_file)
        except OSError:
            age = 1e9
        canvas_dot.delete("all")
        canvas_dot.create_oval(2, 2, 15, 15,
                               fill=(GREEN if age <= 60 else "#BBBBBB"), outline="")

        update_segment_list()
        draw_bar(canvas_meter, S["peak_rms"], GREEN if key == "listening" else colour)
        totals_label.config(
            text=(f"הוקלדו: {S['typed']}  ·  נחסמו: {S['guarded']}  ·  ריק: {S['empty']}"
                  f"  ·  כשל: {S['fail']}  ·  דילוג: {S['skip']}"))

        refresh_pause_ui()

        if time.time() < S["admin_until"]:
            # 2026-09-06: bilingual (Iddo's law) -- and it names the way out.
            admin_banner.config(
                text=(f"🚫 החלון הפעיל ({S['admin_proc']}) רץ כמנהל — ווינדוס חוסם הקלדה אליו. "
                      f"פתח אותו מחדש בלי 'הרץ כמנהל'.\n"
                      f"The focused window ({S['admin_proc']}) runs as Administrator — Windows "
                      f"blocks typing into it. Reopen it WITHOUT 'Run as administrator'."))
            if not admin_banner.winfo_ismapped():
                admin_banner.pack(fill="x", padx=12, pady=(4, 0), before=status_label)
        elif admin_banner.winfo_ismapped():
            admin_banner.pack_forget()

    # ── engine supervisor ───────────────────────────────────────────────────
    closing = [False]
    last_supervise = [0.0]
    last_restart = [0.0]
    last_viewer_check = [0.0]

    def supervise_engine():
        # Tk timers DO stall on Windows. When they do, the engine's dead-man
        # switch stops the mic and nothing restarts it -- a live window over a
        # dead microphone (2026-09-03 08:33). Same start_mic(), same one-mic
        # check, at most once per 20 s.
        now = time.time()
        if closing[0] or _viewer_mode[0] or DRY[0] or now - last_supervise[0] < 5.0:
            return
        last_supervise[0] = now
        try:
            pid = int(open(MIC_PID_FILE).read().strip() or "0") if os.path.exists(MIC_PID_FILE) else 0
        except Exception:
            pid = 0
        if pid and _pid_alive(pid, want_python=True):
            return
        if now - last_restart[0] < 20.0:
            return
        last_restart[0] = now
        log(f"engine dead (mic.pid={pid or '-'}) - restarting")
        try:
            with open(log_file, "a", encoding="utf-8", errors="ignore") as lf:
                lf.write(f"[gui6] engine dead (mic.pid={pid or '-'}) - restarting "
                         f"{datetime.now().isoformat()}\n")
        except OSError:
            pass
        try:
            start_mic()
        except Exception as exc:
            log(f"restart failed: {type(exc).__name__}: {exc}")

    def check_show_request():
        """Running the shortcut again asks the live window to come back."""
        try:
            if os.path.exists(SHOW_FILE):
                os.remove(SHOW_FILE)
                show_self()
        except Exception:
            pass

    def check_restore():
        # polled instead of bound to <Map>: an event handler that re-enters
        # set_mode() during the withdraw/deiconify dance can loop.
        if pending_pill[0] and not switching[0]:
            try:
                if root.state() == "normal":
                    pending_pill[0] = False
                    set_mode("pill")
            except Exception:
                pass

    def check_viewer():
        """If the window that owned the mic has gone, take over rather than
        watching a microphone that nobody is keeping alive.

        The orphaned engine still carries the dead window's KESHEV_OWNER_PID, so
        it stops itself within 3 s; supervise_engine() then starts a fresh one
        owned by us. That is the ONE-MIC LAW being obeyed, not bypassed.
        """
        if not _viewer_mode[0] or closing[0]:
            return
        now = time.time()
        if now - last_viewer_check[0] < 5.0:
            return
        last_viewer_check[0] = now
        try:
            hb = int(open(HEARTBEAT_FILE).read().strip() or "0") if os.path.exists(HEARTBEAT_FILE) else 0
        except Exception:
            hb = 0
        if hb and hb != os.getpid() and _pid_alive(hb, want_python=True):
            return
        _viewer_mode[0] = False
        log("the other window is gone - taking ownership of the mic")
        touch_heartbeat()
        mic_note.config(text="קשב 5 נסגר — קשב 6 לקח בעלות על המיקרופון", fg=GREEN)

    def ui_failed(exc):
        S["ui_errors"] += 1
        S["ui_error_at"] = time.time()
        S["last_ui_error"] = f"{type(exc).__name__}: {exc}"
        if S["ui_errors"] <= 5:
            log("update failed:\n" + traceback.format_exc())
            try:
                with open(CRASH_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n=== {datetime.now().isoformat()} (poll survived) ===\n"
                            + traceback.format_exc())
            except OSError:
                pass

    def poll():
        # Schedule the successor FIRST. gui.py scheduled it last, so any
        # exception in update_status() ended polling for good -- the log tail,
        # the alive dot, the pause banner AND the engine supervisor all stop
        # while the window still looks alive.
        try:
            root.after(300, poll)
        except Exception:
            return
        for fn in (check_show_request, check_restore, check_viewer,
                   update_status, supervise_engine):
            try:
                fn()
            except Exception as exc:
                ui_failed(exc)

    def on_close():
        closing[0] = True         # before stop_mic, or the supervisor resurrects it
        save_view()
        _probe_stop.set()
        stop_mic()                # the window owns the mic (Iddo's law 2026-08-24)
        try:
            if os.path.exists(GUI6_PID_FILE):
                os.remove(GUI6_PID_FILE)
        except OSError:
            pass
        root.after(120, root.destroy)

    # overrideredirect windows never get WM_DELETE_WINDOW, so the badge's ✕
    # calls on_close() directly (above). This covers the framed window.
    root.protocol("WM_DELETE_WINDOW",
                  lambda: set_mode("pill") if mode[0] == "full" else on_close())

    refresh_pause_ui()
    refresh_mic_list()
    set_mode(mode[0], save=False)
    if _viewer_mode[0]:
        mic_note.config(text="צופה בלבד — חלון אחר מחזיק את המיקרופון", fg=RED)
    else:
        # The window must OPEN even if the mic cannot start: a dead window hides
        # every other failure (2026-08-25).
        try:
            start_mic()
        except Exception as exc:
            log(f"start_mic failed: {type(exc).__name__}: {exc}")
    # started in BOTH modes: it writes nothing while we are only a viewer, and is
    # already running the moment check_viewer() promotes us to owner.
    beat_forever(root)

    threading.Thread(target=probe_loop, daemon=True, name="engine-probe").start()

    if hold_s:
        try:
            with open(os.path.join(selftest or STATE_DIR, "hold.hwnd"), "w") as fh:
                fh.write("%d %d" % (os.getpid(), root.winfo_id()))
        except Exception:
            pass

        def _hold_done():
            key, text, colour, detail, short = compute_state()
            with TRUTH_LOCK:
                truth = dict(TRUTH)
            try:
                with open(os.path.join(selftest or STATE_DIR, "hold-report.json"),
                          "w", encoding="utf-8") as fh:
                    json.dump({
                        "state": {"key": key, "text": text, "detail": detail,
                                  "short": short, "colour": colour},
                        "counters": {k: S[k] for k in ("typed", "guarded", "empty",
                                                       "fail", "blocked", "skip",
                                                       "backlog", "confidence",
                                                       "ui_errors")},
                        "last_typed_text": S["last_typed_text"],
                        "fallback_n": S["fallback_n"],
                        "fallback_url": S["fallback_url"],
                        "drops": S["drops"],
                        "mic": S["mic"],
                        "pill_state": pill_state.cget("text"),
                        "pill_text": pill_text.cget("text"),
                        "pill_dec": pill_dec.cget("text"),
                        "dec_line1": dec_line1.cget("text"),
                        "dec_line2": dec_line2.cget("text"),
                        "totals": totals_label.cget("text"),
                        "status": status_label.cget("text"),
                        "drops_label": drops_label.cget("text"),
                        "fb_banner_shown": bool(fb_banner.winfo_ismapped()),
                        "pause_banner_shown": bool(pause_banner.winfo_ismapped()),
                        "admin_banner_shown": bool(admin_banner.winfo_ismapped()),
                        "rows": [w.cget("text") for f in segment_container.winfo_children()
                                 for w in f.winfo_children()],
                        "engine_truth": {k: truth[k] for k in
                                         ("engine_pid", "stt_url", "fallback_url",
                                          "env_read_ok")},
                        "health": truth["health"],
                    }, fh, ensure_ascii=False, indent=2)
            except Exception:
                log("hold report failed:\n" + traceback.format_exc())
            root.destroy()

        root.after(int(hold_s * 1000), _hold_done)
    elif selftest:
        _run_selftest(root, selftest, set_mode, do_minimize, show_self, mode,
                      pending_pill, compute_state, S, TRUTH, TRUTH_LOCK)

    root.after(300, poll)
    try:
        root.mainloop()
    finally:
        _probe_stop.set()
        stop_mic()      # belt and braces: never a live mic without a window
        try:
            if os.path.exists(GUI6_PID_FILE):
                os.remove(GUI6_PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A window that dies silently reads as "KESHEV won't load" (2026-08-25).
        # Leave a trace on disk and on screen, always.
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now().isoformat()} ===\n{traceback.format_exc()}")
        try:
            ctypes.WinDLL("user32").MessageBoxW(
                None,
                "קשב 6 קרס — הפרטים ב-state\\gui6-crash.log\n"
                "KESHEV 6 window crashed - details in state\\gui6-crash.log",
                "קשב 6 · KESHEV 6", 0x00040010)  # MB_ICONERROR | MB_TOPMOST
        finally:
            raise
