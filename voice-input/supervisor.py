"""supervisor.py - ALMAWARE diamond always-on watchdog for the Hebrew PC mic.

Launches voice_input.py as a subprocess and keeps it alive: if the child exits
(clean exit, crash, native segfault in an audio/CUDA lib — anything), it is
relaunched with exponential backoff capped at 30s. A fast, clean run resets the
backoff. Crashes and restarts are logged to history/supervisor.log.

IMPORTANT: importing this module launches NOTHING. Only running it as __main__
starts the supervise loop. This keeps `import supervisor` side-effect free so it
can be unit-tested / introspected without spawning the mic.

The supervisor itself must never crash on a restart failure — every relaunch is
wrapped, and a failed launch is logged and retried (with backoff) rather than
killing the watchdog.

"""
from __future__ import annotations

import datetime
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(HERE, "history")
LOG_PATH = os.path.join(HISTORY_DIR, "supervisor.log")
TARGET = os.path.join(HERE, "voice_input.py")

# Same interpreter that runs the supervisor runs the child, so a venv / specific
# Python is honored. Falls back to the known ALMAWARE Python if sys.executable is
# unavailable (e.g. frozen host).
PYTHON = sys.executable or \
    r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"
# Run the child with the WINDOWLESS interpreter (pythonw) so NO console window
# ever flashes/steals the foreground on (re)launch. The old python.exe child
# popped a console on every restart and was experienced as screen-hijacking
# (2026-06-15, by Iddo's explicit request).
PYTHONW = PYTHON.replace("python.exe", "pythonw.exe")

# backoff policy
BACKOFF_START = 1.0      # first restart waits ~1s
BACKOFF_MAX = 30.0       # capped at 30s as specified
BACKOFF_FACTOR = 2.0
HEALTHY_RUN_SECS = 60.0  # a child that ran this long is "healthy" -> reset backoff

def _log(msg: str) -> None:
    """Append a timestamped line to supervisor.log. Never raises — logging must
    not be able to take down the watchdog."""
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')}  {msg}"
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass

def _spawn() -> subprocess.Popen | None:
    """Launch voice_input.py in VAD mode. Returns the Popen, or None if the
    launch itself failed (caller treats None as a crash and backs off)."""
    try:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUNBUFFERED", "1")
        # NO-FLASH: pythonw + CREATE_NO_WINDOW => the mic runs fully hidden and
        # never pops or steals a console window on launch or restart.
        # CRITICAL (2026-06-15): pythonw has NO console, so the child's
        # stdout/stderr MUST be redirected to a real file — otherwise any code
        # that writes to / reconfigures sys.stdout crashes the child instantly
        # (rc=1 in 0s) and the mic never runs. Redirect to mic-child.log.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logf = open(os.path.join(HISTORY_DIR, "mic-child.log"), "ab")
        return subprocess.Popen(
            [PYTHONW, TARGET, "--vad"],
            cwd=HERE,
            env=env,
            creationflags=creationflags,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        _log(f"SPAWN FAILED: {e!r}")
        return None

def _enforce_single_mic() -> None:
    """ONE-MIC LAW (2026-08-09): keep voice-input the ONLY dictation transcriber.
    Two mics at once = every word typed twice (the alma-mic double-typing bug).
    Idempotently re-disables the alma-mic auto-start task and kills any stray
    alma-mic gui.py. Runs hidden (CREATE_NO_WINDOW — no popup) and NEVER raises,
    so it can't take down the watchdog. See memory feedback_one_mic_law."""
    ps = (
        "try { Disable-ScheduledTask -TaskName 'ALMA-MIC-Elevated' "
        "-ErrorAction SilentlyContinue | Out-Null } catch {}; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -match '^pythonw?\\.exe$' -and $_.CommandLine -match 'gui\\.py' "
        "-and $_.ExecutablePath -match 'Python313' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=20, creationflags=creationflags)
        _log("ONE-MIC LAW enforced (alma-mic task disabled; stray gui.py cleared)")
    except Exception as e:  # noqa: BLE001 — enforcement must never crash the watchdog
        _log(f"single-mic enforce skipped: {e!r}")

def supervise() -> None:
    """Run the watchdog loop forever. Never returns under normal operation; only
    a SIGINT/SIGTERM (Ctrl+C / task stop) tears it down, killing the child first."""
    _log(f"SUPERVISOR START — python={PYTHON} target={TARGET}")
    backoff = BACKOFF_START
    child: subprocess.Popen | None = None
    restart_times = []  # Circuit-breaker: track restart timestamps (last 1 hour)

    def _shutdown(*_a):
        # Best-effort: take the child down with us so we don't orphan the mic.
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except Exception:
                    child.kill()
            except Exception:
                pass
        _log("SUPERVISOR STOP (signal received)")
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except Exception:
        # signal may be unavailable on some hosts/threads — non-fatal
        pass

    while True:
        started = time.monotonic()
        child = _spawn()

        if child is None:
            # Launch itself failed — treat like a crash, back off, retry.
            _log(f"launch failed; retrying in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
            continue

        _log(f"child started (pid={child.pid})")

        # Wait for the child to exit. Wrapped so even a wait()-side surprise
        # cannot kill the watchdog — worst case we loop and re-spawn.
        rc = None
        try:
            rc = child.wait()
        except KeyboardInterrupt:
            _shutdown()
        except Exception as e:
            _log(f"wait() error: {e!r} — assuming child dead")
            try:
                child.kill()
            except Exception:
                pass

        ran = time.monotonic() - started
        _log(f"child exited rc={rc} after {ran:.0f}s")

        # Circuit-breaker: if >10 QUICK deaths in last 3600s, exit instead of
        # looping (crash-loop detection — prevents a restart cascade / mem leak).
        # ONLY quick deaths count. A healthy long run (>=HEALTHY_RUN_SECS) is normal
        # always-on behavior — counting those would trip the breaker on a mic that
        # is working perfectly (e.g. 11 clean >60s sessions over a long day) and
        # permanently kill the very supervisor whose job is to stay up.
        now = time.monotonic()
        if ran < HEALTHY_RUN_SECS:
            restart_times.append(now)
        restart_times = [t for t in restart_times if now - t < 3600]  # Keep last 1 hour
        if len(restart_times) > 10:
            _log(f"CIRCUIT BREAKER: {len(restart_times)} quick deaths in 1h — exiting to prevent cascade")
            os._exit(1)

        # A healthy long run earns a backoff reset; a quick death escalates backoff.
        if ran >= HEALTHY_RUN_SECS:
            backoff = BACKOFF_START
            _log("healthy run -> backoff reset")
        else:
            _log(f"quick exit -> restarting in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
        # loop -> relaunch

if __name__ == "__main__":
    # Singleton guard: if a supervisor is already running, do NOT start a second
    # one. Clicking the desktop icon again while the mic is up must be a no-op,
    # not spawn a duplicate mic / double-typing (2026-06-15, by Iddo's request).
    try:
        import ctypes
        _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "ALMAWARE_HebMic_Supervisor")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            _log("another supervisor already running -> exiting (singleton guard)")
            sys.exit(0)
    except Exception:
        pass
    supervise()
