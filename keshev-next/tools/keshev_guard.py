r"""keshev_guard -- ONE supervisor for Iddo's microphone, and it restarts exactly
the link that died.

🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
output, not a proxy (`health: ok` != working).

WHY THERE IS ONLY ONE OF THESE
------------------------------
Before tonight the mic had FOUR half-supervisors -- the window's 20 s engine
restart, main.py's dead-man switch, its deaf-watchdog, and the delivery watchdog
-- and **nobody owned the boot**. On 2026-09-10 22:11 the engine died, the PC
rebooted at 02:54, and KESHEV 6 stayed down until an agent noticed at 03:13: the
`KESHEV` scheduled task was disabled AND pointed at the old tree. Each of the
four supervisors fixes a different link and none of them asks the only question
that matters -- *is his speech reaching his chat?*

So: one guard, one log, one probe (tools\mic_probe.py -- imported, never
re-implemented, so the guard and the human read the SAME measurement), and one
action per dead link.

WHAT IT MAY DO, AND WHAT IT MAY NEVER DO
----------------------------------------
may:  start the window (RUN-KESHEV6.cmd) when no engine exists anywhere
      rewrite state\decoder.json so a live decoder door becomes primary
      start the PC's :8738 when BOTH eran1 doors are dead, stop it when they return
      start the delivery watchdog when it is gone
      run the standing acceptance test (tools\mic_accept.py) every 6 h

never: start a second engine. Every start is preceded by a command-line scan of
       BOTH trees (keshev-next and mic-rebuild). 2026-09-02 17:40, both mics
       typed into his chat for 43 minutes; 2026-08-09, every word twice for
       hours. The ONE-MIC LAW is not negotiable.
never: touch a SIGNED pause, or start anything while one exists. If Iddo
       pressed pause, the microphone is off because he says so. The guard logs
       one INFO line and does nothing else -- no restart, no alarm, no RAMCHAT.
never: open an audio device, or choose one. It reads; the engine's own fence
       (main.py device_allowed) is the only thing that opens a microphone.
never: run elevated. RunLevel=LeastPrivilege in the task, BELOW_NORMAL priority,
       verified by reading the class back (the 2026-09-07 silent-no-op bug).
never: alarm on repeat. RAMCHAT hears a link only when it CHANGES colour.

Run:
    python tools\keshev_guard.py                     # the loop (what the task runs)
    python tools\keshev_guard.py --once              # one cycle, then exit
    python tools\keshev_guard.py --dry-run           # say what it WOULD do
    python tools\keshev_guard.py --state-dir D:\tmp\decoy --dry-run --once
    python tools\keshev_guard.py --selftest          # decoys only, nothing live
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mic_probe  # noqa: E402  the one measurement, shared with the human

LOG_DIR = os.path.join(ROOT, "logs")
LOG = os.path.join(LOG_DIR, "guard.log")
GUARD_STATE = os.path.join(LOG_DIR, "guard-state.json")
LAUNCHER = os.path.join(ROOT, "RUN-KESHEV6.cmd")
RUN_HIDDEN = r"D:\CLAUDE\run_hidden.vbs"
WATCHDOG = r"D:\CLAUDE\tools\watchdogs\keshev_delivery_watchdog.py"
RAMLINK = r"D:\CLAUDE\RAMCHAT\ramlink.py"
ACCEPT = os.path.join(HERE, "mic_accept.py")
PC_DECODER_CMD = r"D:\CLAUDE\keshev-6\RUN-KESHEV6-SERVER.cmd"
PYTHONW = r"C:\Program Files\Python312\pythonw.exe"
PYTHON = r"C:\Program Files\Python312\python.exe"

CYCLE_S = 30.0
ENGINE_RESTART_COOLDOWN_S = 300.0     # never a restart storm
ENGINE_RESTARTS_PER_HOUR = 3
WATCHDOG_RESTART_COOLDOWN_S = 600.0
PC_DECODER_COOLDOWN_S = 1800.0
ACCEPT_EVERY_S = 6 * 3600.0
ACCEPT_IDLE_MIN_S = 300.0             # he must be away from the keyboard
HEARTBEAT_EVERY_S = 600.0             # so silence in the log is not death
_NOWIN = 0x08000000 if os.name == "nt" else 0

# ORDER = PREFERENCE. 2026-09-15 (Iddo 06:26 "תעביר את פענוח המיק לערן2"): eran2:8739
# runs the same KESHEV 6 model as eran1:8739 (sha256-identical) and is first now,
# because eran1's GPU is carrying vipass/targ/comfyui and gpt-oss-120b. Without
# eran2 in this list, fix_doors() would flip decoder.json back to eran1 within
# one 30 s cycle. Rollback: tools\keshev_guard.py.bak-sttmove-20260915.
DOOR_CANDIDATES = [
    ("eran2:8739", "http://<lan-ip>:8739/v1/transcribe"),
    ("eran1:8739", "http://<lan-ip>:8739/v1/transcribe"),
    ("eran1:8737", "http://<lan-ip>:8737/v1/transcribe"),
    ("pc:8738", "http://127.0.0.1:8738/v1/transcribe"),
]
PC_DOOR = "http://127.0.0.1:8738/v1/transcribe"


# ------------------------------------------------------------------ priority
def below_normal():
    """Drop to BELOW_NORMAL and VERIFY it took.

    The argtypes are not decoration: without restype/argtypes the (HANDLE)-1
    pseudo-handle is truncated on 64-bit, SetPriorityClass fails SILENTLY, and
    the process stays at Normal -- which is what happened on 2026-09-07, and
    again in mic_probe while it was being written. Nothing on this machine may
    ever outrank his microphone.
    """
    if os.name != "nt":
        return None
    try:
        BELOW = 0x00004000
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.GetCurrentProcess.argtypes = []
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.SetPriorityClass.restype = wintypes.BOOL
        k32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        k32.GetPriorityClass.restype = ctypes.c_uint32
        h = k32.GetCurrentProcess()
        k32.SetPriorityClass(h, BELOW)
        return k32.GetPriorityClass(h) == BELOW      # read back, never assumed
    except Exception:
        return None


def idle_seconds():
    """Seconds since Iddo last touched the keyboard or mouse. -1 when unknown."""
    if os.name != "nt":
        return -1
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        u32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        u32.GetLastInputInfo.restype = wintypes.BOOL
        k32.GetTickCount.restype = wintypes.DWORD
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not u32.GetLastInputInfo(ctypes.byref(info)):
            return -1
        return max(0.0, (k32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception:
        return -1


# ----------------------------------------------------------------------- log
def log(msg):
    line = "%s  %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with io.open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


# A DRY RUN AND A SELFTEST MUST BE SILENT.
# Measured the hard way at 07:31 on the night this was written: the selftest ran
# its decoy cases -- a fabricated dead pid, a fabricated orphan pause -- and
# posted all three to RAMCHAT as if Iddo's microphone had just failed. A test
# that cries wolf in the council is the same disease as the 15-minute alarm on
# his own pause that this whole build exists to end.
RAMCHAT_ENABLED = True


def post_ramchat(text):
    """The council hears a link only when it CHANGES colour. 9 alarms in three
    days on his own pause is how a real alarm gets ignored."""
    if not RAMCHAT_ENABLED:
        log("(RAMCHAT suppressed -- dry run / selftest) " + text[:120])
        return
    try:
        subprocess.run([PYTHON, RAMLINK, "post", "keshev-guard", text],
                       capture_output=True, timeout=45, creationflags=_NOWIN,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except Exception as exc:
        log("RAMCHAT post failed (%s) -- the council being down must never "
            "silence the guard: %s" % (type(exc).__name__, text[:80]))


def load_state():
    try:
        with io.open(GUARD_STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(st):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        tmp = GUARD_STATE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, GUARD_STATE)
    except OSError:
        pass


# --------------------------------------------------------------- ONE-MIC LAW
def live_engines():
    """Every python process on this machine that is running a KESHEV engine.

    By COMMAND LINE, not by a pid file: on 2026-09-02 the pid file said one mic
    and two were typing, because mic-rebuild's rival check looked for the literal
    substring "keshev-next" and gui6 had launched with a relative path. Both
    trees, absolute and relative, are matched here.
    """
    if os.name != "nt":
        return []
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
          "Where-Object { $_.CommandLine -match 'main\\.py|mic_engine|alma_mic|voice_input' } | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, timeout=40, creationflags=_NOWIN)
    except Exception as exc:
        # A scan we could not run is NOT "no engines". Refuse to start anything.
        raise RuntimeError("one-mic scan failed: %s: %s" % (type(exc).__name__, exc))
    found = []
    for line in (out.stdout or "").splitlines():
        pid, _, cmd = line.partition("\t")
        pid = pid.strip()
        if not pid.isdigit():
            continue
        low = cmd.lower()
        if ("keshev-next" in low and "main.py" in low) or "mic-rebuild" in low \
                or "alma-mic" in low or "voice-input" in low:
            found.append((int(pid), cmd.strip()))
    return found


# ---------------------------------------------------------------- the doors
def door_state(url, timeout=3.0):
    """'READY' / 'LOADING' / 'HTTPnnn' / 'UNREACHABLE' -- the server's own word."""
    return mic_probe._health(url)[0]


def read_doors():
    try:
        with io.open(os.path.join(mic_probe.STATE, "decoder.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_doors(doors, why):
    path = os.path.join(mic_probe.STATE, "decoder.json")
    doors = dict(doors)
    doors["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    doors["by"] = "tools/keshev_guard.py"
    doors["why"] = why
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doors, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def choose_doors(states):
    """Order the doors by what ANSWERED, keeping the PC last on purpose.

    states: {url: 'READY'|...}. Returns (primary, fallback, last_resort) or None
    when nothing answered -- 'nothing answered' is a RED to report, not an order
    to invent.
    """
    ready = [u for _n, u in DOOR_CANDIDATES if states.get(u) == "READY"]
    if not ready:
        return None
    # The PC's :8738 is a rescue, never a preference: same weights as eran1:8739
    # but on the GPU that sits beside the live microphone (2026-08-25, two CUDA
    # Whispers on one 8 GB card = every decode timed out).
    ordered = [u for u in ready if u != PC_DOOR] + [u for u in ready if u == PC_DOOR]
    primary = ordered[0]
    fallback = ordered[1] if len(ordered) > 1 else ""
    return primary, fallback, PC_DOOR


# ------------------------------------------------------------------ actions
def _spawn_hidden(args, what):
    subprocess.Popen(args, cwd=ROOT, creationflags=_NOWIN,
                     env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    log("STARTED %s: %s" % (what, " ".join(args)))


class Guard:
    def __init__(self, dry_run=False, allow_pc_decoder=True, accept_test=True):
        self.dry = dry_run
        self.allow_pc_decoder = allow_pc_decoder
        self.accept_test = accept_test
        self.state = load_state()
        self.state.setdefault("links", {})
        self.state.setdefault("engine_starts", [])
        self.state.setdefault("last_watchdog_start", 0)
        self.state.setdefault("last_pc_decoder", 0)
        self.state.setdefault("last_accept", 0)
        # NOT setdefault: every new guard process writes one line within its
        # first cycle. A supervisor that says nothing for ten minutes after it
        # starts is indistinguishable from a supervisor that died at start --
        # and "a disabled watchdog looks exactly like a passing one" is the
        # 2026-09-05 lesson this whole night is built on.
        self.state["last_heartbeat"] = 0

    # -- announce a link only when it CHANGES ---------------------------
    def link_changed(self, name, colour, detail=""):
        prev = self.state["links"].get(name)
        if prev == colour:
            return False
        self.state["links"][name] = colour
        log("%s %s -> %s %s" % ("LINK", name, colour, detail))
        if prev is not None:          # the first reading is not a change
            if colour == "RED":
                post_ramchat("KESHEV %s went RED: %s" % (name, detail or "no detail"))
            else:
                post_ramchat("KESHEV %s is GREEN again: %s" % (name, detail or ""))
        return True

    # -- repairs ---------------------------------------------------------
    def restart_engine(self, why):
        now = time.time()
        starts = [t for t in self.state["engine_starts"] if now - t < 3600]
        self.state["engine_starts"] = starts
        if starts and now - starts[-1] < ENGINE_RESTART_COOLDOWN_S:
            log("engine dead (%s) but the last start was %.0fs ago -- waiting, "
                "a restart storm is its own failure" % (why, now - starts[-1]))
            return False
        if len(starts) >= ENGINE_RESTARTS_PER_HOUR:
            log("engine dead (%s) and already started %d times this hour -- "
                "STOPPING. Something is wrong that a restart does not fix."
                % (why, len(starts)))
            post_ramchat("KESHEV engine will not stay up: %d starts in an hour. "
                         "The guard has stopped restarting it; this needs a human."
                         % len(starts))
            return False
        try:
            engines = live_engines()
        except RuntimeError as exc:
            log("REFUSING to start: %s. A scan that did not run is not proof "
                "that no mic is alive (ONE-MIC LAW)." % exc)
            return False
        if engines:
            log("NOT starting: %d engine(s) already alive -- %s"
                % (len(engines), "; ".join("pid %d %s" % (p, c[:70]) for p, c in engines)))
            return False
        if self.dry:
            log("would restart engine (%s) via %s" % (why, LAUNCHER))
            return True
        _spawn_hidden(["wscript.exe", RUN_HIDDEN, LAUNCHER], "KESHEV 6 window")
        starts.append(now)
        self.state["engine_starts"] = starts
        post_ramchat("KESHEV engine was down (%s) -- the guard started "
                     "RUN-KESHEV6.cmd. ONE engine, checked by command line first." % why)
        return True

    def restart_watchdog(self, why):
        now = time.time()
        if now - self.state["last_watchdog_start"] < WATCHDOG_RESTART_COOLDOWN_S:
            return False
        if self.dry:
            log("would start the delivery watchdog (%s)" % why)
            return True
        _spawn_hidden([PYTHONW, WATCHDOG], "delivery watchdog")
        self.state["last_watchdog_start"] = now
        return True

    def start_pc_decoder(self, why):
        """The 2026-09-11 03:28 hole: eran1 rebooted and BOTH doors live on eran1."""
        now = time.time()
        if not self.allow_pc_decoder:
            log("both eran1 doors are dead (%s) and the PC decoder is disabled "
                "by flag -- nothing to fall back to" % why)
            return False
        if now - self.state["last_pc_decoder"] < PC_DECODER_COOLDOWN_S:
            return False
        if self.dry:
            log("would start the PC decoder :8738 (%s) via %s" % (why, PC_DECODER_CMD))
            return True
        _spawn_hidden(["wscript.exe", RUN_HIDDEN, PC_DECODER_CMD], "PC decoder :8738")
        self.state["last_pc_decoder"] = now
        post_ramchat("KESHEV: both eran1 STT doors are dead (%s). Started the PC's "
                     ":8738 as the rescue decoder -- ABOVENORMAL, and it goes away "
                     "when eran1 answers again." % why)
        return True

    def stop_pc_decoder(self):
        """eran1 is back. The PC GPU belongs to his renders, not to a spare decoder."""
        if self.dry:
            log("would stop the PC decoder :8738 (eran1 answers again)")
            return True
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -match 'keshev6_server' } | "
              "ForEach-Object { $_.ProcessId }")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                 capture_output=True, text=True, timeout=40, creationflags=_NOWIN)
            pids = [int(x) for x in (out.stdout or "").split() if x.strip().isdigit()]
        except Exception:
            return False
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=30, creationflags=_NOWIN)
                log("stopped the PC decoder pid %d (eran1 answers again -- VRAM)" % pid)
            except Exception:
                pass
        return bool(pids)

    def maybe_accept_test(self, r):
        """The standing REAL-OUTPUT test: a known WAV, the real decoder, the real
        typer, a decoy window we own. Only when he is not here, and never while
        he has paused -- the test types, and typing into his window is his job."""
        if not self.accept_test:
            return
        now = time.time()
        if now - self.state["last_accept"] < ACCEPT_EVERY_S:
            return
        pause = r["links"]["pause"]
        if pause.get("paused"):
            return
        idle = idle_seconds()
        if idle < ACCEPT_IDLE_MIN_S:
            return
        if self.dry:
            log("would run the acceptance test (idle %.0fs)" % idle)
            self.state["last_accept"] = now
            return
        self.state["last_accept"] = now
        try:
            p = subprocess.run([PYTHON, "-X", "utf8", ACCEPT, "--quiet"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=300, creationflags=_NOWIN,
                               cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            head = (p.stdout or p.stderr or "").strip().splitlines()
            head = head[-1] if head else "(no output)"
        except Exception as exc:
            p, head = None, "the test itself broke: %s: %s" % (type(exc).__name__, exc)
        ok = bool(p) and p.returncode == 0
        log("ACCEPTANCE %s  %s" % ("PASS" if ok else "FAIL", head[:200]))
        if self.link_changed("acceptance", "GREEN" if ok else "RED", head[:160]):
            pass

    # -- one cycle -------------------------------------------------------
    def cycle(self):
        r = mic_probe.probe()
        L = r["links"]
        pause = L["pause"]

        # 1. HIS PAUSE IS THE END OF THE CONVERSATION -------------------
        if pause.get("paused") and pause.get("signed"):
            who = pause.get("who", "?")
            self.link_changed("pause", "GREEN", "signed by %s" % who[:40])
            now = time.time()
            if now - self.state.get("last_heartbeat", 0) > HEARTBEAT_EVERY_S:
                self.state["last_heartbeat"] = now
                log("INFO paused by %s for %.0f min -- signed, so the guard does "
                    "nothing: no restart, no alarm. %s"
                    % (who[:40], pause.get("age_min", 0), mic_probe.one_line(r)))
            save_state(self.state)
            return r
        if pause.get("paused"):
            # An ORPHAN pause is the 2026-09-03 shape. The delivery watchdog owns
            # that repair (it writes a receipt beside the file, never on it); the
            # guard reports it and keeps its hands off, so there is exactly one
            # hand on the pause file.
            self.link_changed("pause", "RED", "ORPHAN pause, %.0f min, no author "
                                              "-- the delivery watchdog repairs this"
                              % pause.get("age_min", 0))
            save_state(self.state)
            return r
        self.link_changed("pause", "GREEN", "not paused")

        # 2. THE ENGINE --------------------------------------------------
        eng = L["engine"]
        if not eng.get("ok"):
            why = ("mic pid %s %s, gui pid %s %s, heartbeat %s min"
                   % (eng.get("mic_pid"), "alive" if eng.get("mic_alive") else "DEAD",
                      eng.get("gui_pid"), "alive" if eng.get("gui_alive") else "DEAD",
                      eng.get("heartbeat_age_min")))
            # HE CLOSED THE WINDOW. gui6.on_close() removes state\gui6.pid and
            # state\mic.pid on its way out; a crash, a kill and a reboot all
            # LEAVE them behind holding a dead pid. So a missing pid file is not
            # a failure, it is an instruction -- the window owns the mic (his law
            # of 2026-08-24) and closing it is how he turns the microphone off.
            # A supervisor that reopens it is a supervisor he has to fight.
            if not eng.get("gui_pid_file_present"):
                self.link_changed("engine", "GREEN",
                                  "closed by Iddo (no gui6.pid) -- not a fault")
                save_state(self.state)
                return r
            self.link_changed("engine", "RED", why)
            self.restart_engine(why)
        else:
            self.link_changed("engine", "GREEN", "pid %s, heartbeat %s min"
                              % (eng.get("mic_pid"), eng.get("heartbeat_age_min")))

        # 3. THE AUDIO ---------------------------------------------------
        au = L["audio"]
        if eng.get("ok") and not au.get("ok"):
            self.link_changed("audio", "RED", "%s blocks/min on %s (936 = a live BRIO, "
                                              "<100 = starved; check the USB controller "
                                              "and the input level)"
                              % (au.get("blocks_per_min"), au.get("device") or "?"))
        elif au.get("ok"):
            self.link_changed("audio", "GREEN", "%s blocks/min%s"
                              % (au.get("blocks_per_min"),
                                 " CLIPPING" if au.get("clipping") else ""))

        # 4. THE DECODER DOORS -------------------------------------------
        self.fix_doors(L["decoder"])

        # 5. THE DELIVERY WATCHDOG ---------------------------------------
        wd = L["watchdog"]
        if not wd.get("alive"):
            self.link_changed("watchdog", "RED", "the delivery judge is not running")
            self.restart_watchdog("not running")
        else:
            self.link_changed("watchdog", "GREEN", "pid %s verdict %s"
                              % (wd.get("pid"), wd.get("last_verdict") or "-"))

        # 6. THE STANDING REAL-OUTPUT TEST -------------------------------
        self.maybe_accept_test(r)

        now = time.time()
        if now - self.state.get("last_heartbeat", 0) > HEARTBEAT_EVERY_S:
            self.state["last_heartbeat"] = now
            log("HEARTBEAT %s" % mic_probe.one_line(r))
        save_state(self.state)
        return r

    def fix_doors(self, dec):
        states = {}
        for _name, url in DOOR_CANDIDATES:
            states[url] = door_state(url)
        cur = read_doors()
        cur_primary = cur.get("primary") or dec.get("primary_url") or ""
        chosen = choose_doors(states)
        if chosen is None:
            self.link_changed("decoder", "RED",
                              "NO decoder answers: " + ", ".join(
                                  "%s=%s" % (n, states[u]) for n, u in DOOR_CANDIDATES))
            if self.allow_pc_decoder and states.get(PC_DOOR) != "READY":
                self.start_pc_decoder("every door silent")
            return
        primary, fallback, last = chosen
        eran1_dead = all(states.get(u) != "READY" for _n, u in DOOR_CANDIDATES if u != PC_DOOR)
        if eran1_dead and states.get(PC_DOOR) != "READY":
            self.start_pc_decoder("both eran1 doors are dead")
        if (not eran1_dead) and states.get(PC_DOOR) == "READY":
            # eran1 is back and the rescue is still burning VRAM beside the mic
            self.stop_pc_decoder()
        if primary != cur_primary:
            why = ("%s answered %s; the door in use was %s (%s)"
                   % (primary, states.get(primary), cur_primary or "-",
                      states.get(cur_primary, "unknown")))
            if self.dry:
                log("would flip decoder.json primary -> %s (%s)" % (primary, why))
            else:
                write_doors({"primary": primary, "fallback": fallback,
                             "last_resort": last}, why)
                log("FLIPPED decoder.json primary -> %s (%s)" % (primary, why))
                post_ramchat("KESHEV decoder door changed to %s -- %s" % (primary, why))
        self.link_changed("decoder", "GREEN" if states.get(primary) == "READY" else "RED",
                          "primary %s = %s" % (primary, states.get(primary)))


# ----------------------------------------------------------------- selftest
def selftest():
    """Decoys only. No live process is started, stopped or probed for repair."""
    import tempfile
    ok = True
    d = tempfile.mkdtemp(prefix="keshev-guard-decoy-")
    state = os.path.join(d, "state")
    os.makedirs(state)
    with io.open(os.path.join(state, "mic.pid"), "w") as fh:
        fh.write("999999")        # a pid that cannot be alive
    with io.open(os.path.join(state, "gui6.pid"), "w") as fh:
        fh.write("999998")
    with io.open(os.path.join(d, "trial.log"), "w", encoding="utf-8") as fh:
        fh.write("07:00:00 [mic] heartbeat: 936 blocks, peak RMS 333\n")
    mic_probe.configure(root=d)

    lines = []
    global log, RAMCHAT_ENABLED
    real_log, real_ramchat = log, RAMCHAT_ENABLED
    log = lines.append
    RAMCHAT_ENABLED = False          # a decoy must never reach the council
    try:
        # (a) THE ONE-MIC LAW, against the REAL machine. There is very likely a
        # live engine on this PC right now; the guard must REFUSE to start
        # another one even though its decoy pid file says the mic is dead. This
        # is the 2026-09-02 "both mics typed for 43 minutes" case, and it is
        # proved here against the real process table, not a stub.
        g = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
        g.state["links"] = {"engine": "GREEN", "pause": "GREEN"}
        g.cycle()
        refused = [l for l in lines if "NOT starting" in l]
        would = [l for l in lines if "would restart engine" in l]
        engines_now = live_engines()
        if engines_now:
            print("dead pid + a LIVE engine -> %s" % (refused[0][:120] if refused else "STARTED ANYWAY -- FAIL"))
            ok &= bool(refused) and not would
        else:
            print("dead pid, no engine alive -> %s" % (would[0][:120] if would else "SAID NOTHING"))
            ok &= bool(would)
        ok &= (g.state["links"].get("engine") == "RED")

        # (a2) THE WINDOW HE CLOSED HIMSELF. gui6 removes its pid file on the way
        # out; nothing else does. The guard must read that as "off", not "dead".
        lines.clear()
        os.remove(os.path.join(state, "gui6.pid"))
        g1a2 = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
        g1a2.state["links"] = {"engine": "GREEN", "pause": "GREEN"}
        g1a2.cycle()
        acted = [l for l in lines if "would restart" in l or "NOT starting" in l]
        print("window closed by Iddo   -> engine=%s acted=%r"
              % (g1a2.state["links"].get("engine"), acted))
        ok &= (g1a2.state["links"].get("engine") == "GREEN") and not acted
        with io.open(os.path.join(state, "gui6.pid"), "w") as fh:
            fh.write("999998")

        # (b) the same decision with the machine emptied: it MUST act.
        lines.clear()
        real_scan = globals()["live_engines"]
        globals()["live_engines"] = lambda: []
        try:
            g1b = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
            g1b.state["links"] = {"engine": "GREEN", "pause": "GREEN"}
            g1b.cycle()
            would = [l for l in lines if "would restart engine" in l]
            print("dead pid, no rival     -> %s" % (would[0][:120] if would else "SAID NOTHING -- FAIL"))
            ok &= bool(would)
        finally:
            globals()["live_engines"] = real_scan

        # (c) a scan that could not RUN is not proof that no mic is alive
        lines.clear()
        def _broken_scan():
            raise RuntimeError("one-mic scan failed: decoy")
        globals()["live_engines"] = _broken_scan
        try:
            g1c = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
            g1c.state["links"] = {"engine": "GREEN", "pause": "GREEN"}
            g1c.cycle()
            refused = [l for l in lines if "REFUSING to start" in l]
            print("scan itself broken     -> %s" % (refused[0][:120] if refused else "STARTED ANYWAY -- FAIL"))
            ok &= bool(refused)
        finally:
            globals()["live_engines"] = real_scan

        lines.clear()

        # a SIGNED pause stops everything, including the restart above
        lines.clear()
        with io.open(os.path.join(state, "PAUSED"), "w", encoding="utf-8") as fh:
            json.dump({"who": "iddo (pause button)", "why": "he pressed pause"}, fh)
        g2 = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
        g2.state["links"] = {"engine": "GREEN", "pause": "GREEN"}
        g2.state["last_heartbeat"] = 0
        g2.cycle()
        acted = [l for l in lines if "would restart" in l or "STARTED" in l]
        info = [l for l in lines if "INFO paused by" in l]
        print("signed pause         -> acted=%r info=%s" % (acted, bool(info)))
        ok &= (not acted) and bool(info)

        # an ORPHAN pause is reported, never repaired here
        lines.clear()
        with io.open(os.path.join(state, "PAUSED"), "w", encoding="utf-8") as fh:
            fh.write("2026-09-03T22:55:00")
        g3 = Guard(dry_run=True, allow_pc_decoder=False, accept_test=False)
        g3.state["links"] = {"pause": "GREEN"}
        g3.cycle()
        print("orphan pause         -> pause link = %s" % g3.state["links"].get("pause"))
        ok &= (g3.state["links"].get("pause") == "RED")

        # the door chooser, on fabricated /health answers
        P, F, PCD = DOOR_CANDIDATES[0][1], DOOR_CANDIDATES[1][1], PC_DOOR
        cases = [
            ({P: "READY", F: "READY", PCD: "UNREACHABLE"}, P, "both eran1 doors up"),
            ({P: "UNREACHABLE", F: "READY", PCD: "UNREACHABLE"}, F, "8739 down"),
            ({P: "UNREACHABLE", F: "UNREACHABLE", PCD: "READY"}, PCD, "eran1 gone, PC up"),
            ({P: "READY", F: "UNREACHABLE", PCD: "READY"}, P, "PC up but eran1 answers"),
        ]
        for states, want, name in cases:
            got = choose_doors(states)
            good = got is not None and got[0] == want
            print("doors %-24s -> primary %-38s %s"
                  % (name, (got[0] if got else "None").split("//")[-1], "OK" if good else "FAIL"))
            ok &= good
        got = choose_doors({P: "UNREACHABLE", F: "UNREACHABLE", PCD: "UNREACHABLE"})
        print("doors %-24s -> %s %s" % ("nothing answers", got,
                                        "OK" if got is None else "FAIL"))
        ok &= (got is None)

        # priority, read back rather than assumed
        prio = below_normal()
        print("BELOW_NORMAL verified -> %s" % prio)
        ok &= (prio is True or os.name != "nt")
    finally:
        log = real_log
        RAMCHAT_ENABLED = real_ramchat
        mic_probe.configure(root=ROOT)
    print("\nGUARD SELFTEST: %s" % ("PASS" if ok else "BROKEN"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--dry-run", action="store_true", help="say what it WOULD do")
    ap.add_argument("--selftest", action="store_true", help="decoys only")
    ap.add_argument("--state-dir", default=None,
                    help="probe a DECOY tree instead of the live microphone")
    ap.add_argument("--interval", type=float, default=CYCLE_S)
    ap.add_argument("--no-pc-decoder", action="store_true",
                    help="never start the PC's :8738, whatever eran1 does")
    ap.add_argument("--no-accept-test", action="store_true")
    a = ap.parse_args(argv)

    prio = below_normal()
    if a.dry_run or a.selftest or a.state_dir:
        # Nothing that is pretending, or looking at a decoy, may speak to the
        # council as though it were the live microphone.
        globals()["RAMCHAT_ENABLED"] = False
    if a.selftest:
        return selftest()
    if a.state_dir:
        mic_probe.configure(state=a.state_dir)
        log("probing a DECOY state dir: %s" % a.state_dir)

    g = Guard(dry_run=a.dry_run, allow_pc_decoder=not a.no_pc_decoder,
              accept_test=not a.no_accept_test)
    log("guard up (pid %d, BELOW_NORMAL=%s, dry_run=%s, every %.0fs)"
        % (os.getpid(), prio, a.dry_run, a.interval))
    if a.once:
        r = g.cycle()
        print(mic_probe.one_line(r))
        return 0 if r["verdict"] == "GREEN" else 1
    while True:
        try:
            g.cycle()
        except Exception as exc:
            log("GUARD ITSELF BROKE: %s: %s" % (type(exc).__name__, exc))
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
