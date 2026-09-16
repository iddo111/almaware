"""
supervisor.py - keeps ERAN's trainer running FOREVER.  (hardened 2026-07-04)

Failure modes this version fixes (all actually happened):
  * PID-reuse deadlock: old lock held pid 20184; that pid was reused by
    RuntimeBroker.exe, so every new supervisor said "already running" and
    exited -> training silently dead for 11h. Lock now stores PID + process
    creation time; identity must match BOTH, else the lock is stale.
  * Trainer HANG (not exit): the old loop only detected exit codes. Now a
    stall watchdog polls the trainer's progress (eran.log mtime); if no
    progress for STALL_TIMEOUT while the process is alive, the trainer is
    tree-killed and relaunched from the latest checkpoint.
  * Supervisor's own death: writes supervisor_heartbeat.json every poll so an
    external scheduled task / dashboard can detect a dead supervisor; the
    single-instance lock makes "relaunch every N minutes" a safe no-op.

  * single-instance guard (lockfile with PID+creation-time)
  * launches train.py with `-s` (ignore shadowing user-site CPU torch -> cu121 torch)
  * auto-restarts the trainer on exit OR stall (with backoff), forever
  * windowless-friendly: run via pythonw.exe for the Startup shortcut / schtask

Run (foreground):    python  -s supervisor.py
Run (windowless):    pythonw -s supervisor.py     (Startup .lnk + scheduled task)

Test overrides (env vars, used by the self-test only - never set in production):
  ERAN_SUP_TRAIN, ERAN_SUP_PROGRESS, ERAN_SUP_STALL_TIMEOUT_S,
  ERAN_SUP_STARTUP_GRACE_S, ERAN_SUP_POLL_S, ERAN_SUP_LOCK, ERAN_SUP_LOG
"""

import os
import sys
import json
import time
import ctypes
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.environ.get("ERAN_SUP_LOCK") or os.path.join(HERE, "supervisor.lock")
SUP_LOG = os.environ.get("ERAN_SUP_LOG") or os.path.join(HERE, "supervisor.log")
TRAIN = os.environ.get("ERAN_SUP_TRAIN") or os.path.join(HERE, "train.py")
CONFIG = os.path.join(HERE, "config.json")
HEARTBEAT = os.path.join(HERE, "supervisor_heartbeat.json")
PYTHON = sys.executable  # whatever launched us (we re-add -s for the child)

# Watchdog tuning. Trainer normally logs ~every second; corpus reloads and
# checkpoint saves take seconds. 15 minutes of total silence = hung.
STALL_TIMEOUT_S = float(os.environ.get("ERAN_SUP_STALL_TIMEOUT_S", 900))
STARTUP_GRACE_S = float(os.environ.get("ERAN_SUP_STARTUP_GRACE_S", 900))
POLL_S = float(os.environ.get("ERAN_SUP_POLL_S", 15))
SUP_LOG_MAX_BYTES = 5 * 1024 * 1024


def slog(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # rotate once when large (keep .1) so the log can never eat the disk
        try:
            if os.path.exists(SUP_LOG) and os.path.getsize(SUP_LOG) > SUP_LOG_MAX_BYTES:
                old = SUP_LOG + ".1"
                if os.path.exists(old):
                    os.remove(old)
                os.replace(SUP_LOG, old)
        except Exception:
            pass
        with open(SUP_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------- process id
class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _open_process(pid):
    return ctypes.windll.kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))


def proc_creation_time(pid):
    """Windows FILETIME (100ns ticks) the process started, or None if gone."""
    try:
        h = _open_process(pid)
        if not h:
            return None
        try:
            c, e, k, u = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
            ok = ctypes.windll.kernel32.GetProcessTimes(
                h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
            if not ok:
                return None
            return (c.dwHighDateTime << 32) | c.dwLowDateTime
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return None


def proc_exe_name(pid):
    """Basename of the process executable, lowercase, or None."""
    try:
        h = _open_process(pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_uint32(1024)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size))
            if not ok:
                return None
            return os.path.basename(buf.value).lower()
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return None


# ---------------------------------------------------------------------- lock
def _lock_is_live(raw):
    """True only if the lock provably belongs to a LIVE supervisor process."""
    raw = (raw or "").strip()
    if not raw:
        return False
    try:
        info = json.loads(raw)
        pid = int(info["pid"])
        created = int(info["created"])
    except Exception:
        # legacy format: bare pid. Identity can't be fully verified; accept it
        # as live ONLY if that pid is a python process (RuntimeBroker etc. can
        # NOT hold our lock -- this exact bug killed training on 2026-07-04).
        try:
            pid = int(raw)
        except Exception:
            return False
        exe = proc_exe_name(pid)
        return exe in ("python.exe", "pythonw.exe")
    now_created = proc_creation_time(pid)
    return now_created is not None and now_created == created


def acquire_lock():
    if os.path.exists(LOCK):
        try:
            with open(LOCK, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            raw = ""
        if _lock_is_live(raw):
            slog(f"Another supervisor is alive ({raw.strip()!r}). Exiting.")
            return False
        slog(f"Stale lock found ({raw.strip()!r}); taking over.")
    me = {"pid": os.getpid(), "created": proc_creation_time(os.getpid()),
          "started": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(LOCK, "w", encoding="utf-8") as f:
        json.dump(me, f)
    return True


def release_lock():
    try:
        if os.path.exists(LOCK):
            with open(LOCK, "r", encoding="utf-8") as f:
                info = json.loads(f.read() or "{}")
            if int(info.get("pid", -1)) == os.getpid():
                os.remove(LOCK)
    except Exception:
        pass


# ------------------------------------------------------------------ watchdog
def progress_path():
    """File whose mtime proves the trainer is making progress."""
    p = os.environ.get("ERAN_SUP_PROGRESS")
    if p:
        return p
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("log_path") or os.path.join(HERE, "eran.log")
    except Exception:
        return os.path.join(HERE, "eran.log")


def progress_age(path, since):
    """Seconds since last progress (log mtime), floored at trainer launch."""
    try:
        m = os.path.getmtime(path)
    except Exception:
        m = 0.0
    return time.time() - max(m, since)


def write_heartbeat(obj):
    try:
        tmp = HEARTBEAT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, HEARTBEAT)
    except Exception:
        pass


def kill_tree(proc):
    """taskkill the trainer's whole tree; fall back to proc.kill()."""
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, timeout=30)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        pass


# ---------------------------------------------------------------------- main
def run_trainer_once():
    """Launch the trainer, babysit it (exit + stall watchdog). Returns (rc, ran_s)."""
    child_py = PYTHON
    if child_py.lower().endswith("pythonw.exe"):
        cand = child_py[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            child_py = cand
    prog = progress_path()
    slog(f"Launching trainer: {child_py} -s {TRAIN} (watchdog: {prog}, "
         f"stall>{STALL_TIMEOUT_S:.0f}s, grace {STARTUP_GRACE_S:.0f}s)")
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [child_py, "-s", TRAIN],
            cwd=HERE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        slog(f"Trainer launch failed: {e}")
        return -1, time.time() - t0

    while True:
        rc = proc.poll()
        age = progress_age(prog, t0)
        write_heartbeat({
            "supervisor_pid": os.getpid(),
            "trainer_pid": proc.pid,
            "trainer_alive": rc is None,
            "progress_age_s": round(age, 1),
            "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        if rc is not None:
            return rc, time.time() - t0
        in_grace = (time.time() - t0) < STARTUP_GRACE_S
        if (not in_grace) and age > STALL_TIMEOUT_S:
            slog(f"STALL detected: trainer pid {proc.pid} alive but no progress "
                 f"on {prog} for {age:.0f}s (> {STALL_TIMEOUT_S:.0f}s). Killing tree.")
            kill_tree(proc)
            return "stall-killed", time.time() - t0
        time.sleep(POLL_S)


def main():
    if not acquire_lock():
        sys.exit(0)
    slog(f"Supervisor start (pid {os.getpid()}). python={PYTHON}")
    backoff = 3
    try:
        while True:
            rc, ran = run_trainer_once()
            slog(f"Trainer exited rc={rc} after {ran:.0f}s. Restarting...")
            # if it died fast, back off; if it ran a while, reset backoff
            if ran > 60:
                backoff = 3
            else:
                backoff = min(backoff * 2, 120)
            time.sleep(backoff)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
