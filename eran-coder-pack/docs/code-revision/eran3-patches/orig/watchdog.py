#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coder-train watchdog -- one run = one check pass.

Watches the Qwen3.5-4B-Base full-weight continued-pretraining run in
~/coder-train/ on eran3. Detects: dead process, HUNG process (status.json
stale while process alive -- the failure that matters most), non-finite or
stalled loss, GPU idle-but-alive, low disk, checkpoint freshness.

Fixes what it safely can:
  - restarts a dead or hung run with --resume auto (gated behind ~/coder-train/ENABLED)
  - deletes the OLDEST checkpoints when disk is tight (never the newest 2)

Refuses to fix, and escalates instead:
  - crash-loops (more than MAX_RESTARTS_PER_HOUR restarts/hour) -> writes
    WATCHDOG-ESCALATED and stops touching the process until a human clears it
  - bad loss (NaN/Inf, stalled, increasing) -- reported only, never "fixed"
    by a restart, since a restart cannot repair a hyperparameter problem
  - disk still low after cleanup with only 2 checkpoints left

See WATCHDOG.md for the full contract. Never touches voice-ant-farm.service
or chef.service -- this script only ever manages the coder-train process
(directly, or via a "coder-train.service" user unit if one exists).

PYTHONIOENCODING=utf-8 is set by the systemd unit; this file is pure ASCII
regardless, but status.json / logs may carry Hebrew from elsewhere on the box.
"""

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE = Path.home() / "coder-train"
STATUS = BASE / "status.json"
CKPT_DIR = BASE / "ckpt"
ENABLED_FILE = BASE / "ENABLED"
PIDFILE = BASE / "train.pid"
STDOUT_LOG = BASE / "train.stdout.log"
WATCHDOG_LOG = BASE / "watchdog.log"
WATCHDOG_STATE = BASE / "watchdog-state.json"
WATCHDOG_STATUS = BASE / "watchdog-status.json"
LOSS_HISTORY = BASE / "watchdog-loss-history.jsonl"
ESCALATION_FLAG = BASE / "WATCHDOG-ESCALATED"

TRAIN_UNIT = "coder-train.service"  # used ONLY if such a user unit already exists

# --------------------------------------------------------------------------
# Thresholds -- tune here, not scattered through the logic below
# --------------------------------------------------------------------------
# THE CAP MUST BE LONGER THAN ONE STEP. This is the bug under all the others.
#
# Measured 2026-09-06 05:20: this run is micro_batch 1 x grad_accum 128 x
# seq_len 4096 = 524,288 tokens per step, at 522.6 tok/s. **One step takes
# 1003 s = 16.7 minutes.** log_every=1, so status.json is legitimately written
# only once every 16.7 minutes -- against a 15-minute cap.
#
# So a perfectly healthy run crossed "stale" on almost every step, and the
# watchdog killed it as `reason=hung` five times tonight. Four earlier fixes
# (checkpointing exemption, resume re-basing, tri-state liveness, the full
# status classifier) each closed a real hole and NONE of them touched this,
# because I never asked the simplest question: how long is one step?
#
# Do not hand-tune this number. Derive it from the run's own reported rate, so
# it cannot go stale again when the batch size or the hardware changes.
STALE_FLOOR_SECONDS = 60 * 60      # never less patient than an hour
STALE_STEP_MULTIPLE = 3.0          # three steps of silence before we call it hung
STALE_SECONDS = STALE_FLOOR_SECONDS  # replaced per-pass by stale_cap_for()


def stale_cap_for(status_data):
    """Patience for a 'running' run, in seconds: max(1 hour, 3 x one step).

    tokens_per_sec and the batch shape both come from status.json, written by
    the training itself -- so this tracks the real run rather than an assumption
    baked in months earlier.
    """
    try:
        tps = float((status_data or {}).get("tokens_per_sec") or 0)
        seen = float((status_data or {}).get("tokens_seen") or 0)
        step = float((status_data or {}).get("step") or 0)
        if tps > 0 and step > 0 and seen > 0:
            tok_per_step = seen / step
            return max(STALE_FLOOR_SECONDS, STALE_STEP_MULTIPLE * tok_per_step / tps)
    except Exception:
        pass
    return STALE_FLOOR_SECONDS
BUSY_STATES   = frozenset({"starting", "checkpointing", "resuming"})
EXITED_STATES = frozenset({"stopped", "finished"})
CRASH_STATES  = frozenset({"crash_nonfinite_loss", "crash_nonfinite_grad",
                           "crash_oom"})
BUSY_STALE_SECONDS = 45 * 60   # loading or writing 50 GB legitimately takes
                               # ~19 min here; only silence far past that is a hang
NO_STATUS_GRACE_SECONDS = 20 * 60  # allow this long after process start before
                                    # requiring status.json to exist at all
LOSS_TREND_WINDOW_SECONDS = 2 * 3600   # ~2h window to judge loss trend
LOSS_STALL_REL_EPS = 1e-3          # relative improvement required over the window
GPU_IDLE_THRESHOLD = 5             # percent; below this counts as "idle"
MIN_DISK_FREE_GB = 50.0            # never let / fall below this
KEEP_CKPTS = 2                     # never delete down to fewer than this many
CKPT_STALE_WARN_SECONDS = 6 * 3600 # informational only -- interval is unknown
MAX_RESTARTS_PER_HOUR = 4          # crash-loop cap -> escalate instead of retry
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 30 * 60
STABLE_RESET_SECONDS = 30 * 60     # this long healthy since last restart => reset backoff

LAUNCH_CMD = ["python3", "train.py", "--resume", "auto"]

MAX_LOSS_HISTORY_LINES = 2000


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def log(msg, level="INFO"):
    line = f"[{now_iso()}] {level:8s} {msg}"
    print(line)
    try:
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def json_safe_number(x):
    """Python's json module happily writes bare NaN/Infinity tokens (its own
    allow_nan default) -- valid for another Python reader, but not strict
    JSON, and this file is read by "any other agent" per the spec. Keep the
    watchdog-status.json output strictly parseable everywhere by swapping a
    non-finite float for its string name."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "NaN" if math.isnan(x) else ("Infinity" if x > 0 else "-Infinity")
    return x


def save_json(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def append_jsonl(path, obj, max_lines=MAX_LOSS_HISTORY_LINES):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        # trim occasionally so this never grows unbounded over a multi-day run
        if os.path.getsize(path) > 2_000_000:
            lines = Path(path).read_text(encoding="utf-8").splitlines()[-max_lines:]
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        log(f"loss-history append failed: {e}", "WARN")


def run_cmd(args, timeout=15):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)


# --------------------------------------------------------------------------
# Process discovery -- pidfile first, then a /proc scan (pgrep-equivalent)
# scoped to cmdline containing "train.py" AND cwd == BASE, so we never
# mistake someone else's train.py (qwen-fleet-train/, whisper-iddo/,
# vaada-miko/ all have one) for ours.
# --------------------------------------------------------------------------
def is_pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def read_cmdline(pid):
    """Human-readable joined command line, for logging only -- NOT for
    identity matching (a shell invocation that merely mentions "train.py"
    as a string, e.g. `bash -c "...train.py..."`, would falsely match a
    naive substring check on this)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\x00", b" ").decode(errors="replace")
    except Exception:
        return ""


def read_argv(pid):
    """argv as a list of real tokens (empty trailing token from the
    NUL-terminated /proc format dropped)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        parts = raw.split(b"\x00")
        return [p.decode(errors="replace") for p in parts if p != b""]
    except Exception:
        return []


def is_train_process(pid):
    """True identity check: argv[0] must look like a python interpreter AND
    some argv token must be exactly train.py (or end in /train.py) -- a
    whole-token match, not a substring of the joined command line. This is
    what keeps us from mistaking a shell wrapper, an editor, or a `grep
    train.py` sitting in this directory for the real trainer."""
    argv = read_argv(pid)
    if not argv:
        return False
    exe = os.path.basename(argv[0])
    looks_python = "python" in exe
    has_train_token = any(a == "train.py" or a.endswith("/train.py") for a in argv)
    return looks_python and has_train_token


def read_cwd(pid):
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except Exception:
        return None


def read_proc_start_age_seconds(pid):
    """Best-effort process age via /proc/<pid> ctime (not exact, good enough
    for a grace-period check)."""
    try:
        return time.time() - os.stat(f"/proc/{pid}").st_ctime
    except Exception:
        return None


def find_train_pid():
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
            if is_pid_alive(pid) and is_train_process(pid):
                return pid
        except Exception:
            pass
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if not is_train_process(pid):
                continue
            if read_cwd(pid) == str(BASE):
                return pid
    except Exception:
        pass
    return None


def systemd_unit_exists(name):
    rc, out, _ = run_cmd(["systemctl", "--user", "list-unit-files", name, "--no-legend"])
    return rc == 0 and name in out


def systemd_is_active(name):
    """TRI-STATE: True / False / None.

    None means "I could not ask" -- systemctl timed out, errored, or printed
    nothing. It does NOT mean "not active".

    2026-09-06 02:18: the previous version returned `out.strip() == "active"`,
    so a systemctl call that timed out on a loaded box produced out="" and the
    watchdog concluded the training was DEAD. It restarted a process that was
    training normally at step 22. That is the second run this watchdog killed
    tonight, and the first fix (checkpointing/resume staleness) did not touch
    this path at all, because the kill came in as reason=dead, not hung.

    "I could not ask" scored as "the answer is no" is the same bug shape that
    made a sibling agent's judge report a live model as answering 0/209: its
    HTTP client scored every 400 as an empty transcript.
    """
    rc, out, _ = run_cmd(["systemctl", "--user", "is-active", name])
    out = (out or "").strip()
    if not out:
        return None                      # could not ask -- NOT evidence of death
    if out == "active":
        return True
    if out in ("inactive", "failed", "deactivating", "activating"):
        return False
    return None                          # unrecognised answer: refuse to judge


def determine_liveness():
    """Returns (alive, pid, via_systemd).

    systemd is the preferred witness, but it is not the only one, and it is
    allowed to be unavailable. When it cannot answer, fall back to the /proc
    scan, which reads the filesystem directly and is scoped to a cmdline
    containing train.py AND cwd == BASE. Only when NEITHER witness can speak do
    we report dead -- and even then the caller must treat that as weak.
    """
    pid = find_train_pid()
    if systemd_unit_exists(TRAIN_UNIT):
        state = systemd_is_active(TRAIN_UNIT)
        if state is None:
            # Could not ask systemd. The process scan is the surviving witness.
            log("systemctl could not answer is-active; falling back to the "
                "/proc scan (pid=%s)" % pid, "WARN")
            return pid is not None, pid, True
        return state, pid, True
    return pid is not None, pid, False


# --------------------------------------------------------------------------
# GPU / disk
# --------------------------------------------------------------------------
def get_gpu_util():
    rc, out, _ = run_cmd(
        ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
    )
    if rc != 0:
        return None
    vals = []
    for line in out.strip().splitlines():
        line = line.strip()
        if line.isdigit():
            vals.append(int(line))
    return vals or None


def get_disk_free_gb(path="/"):
    du = shutil.disk_usage(path)
    return du.free / (1024 ** 3)


# --------------------------------------------------------------------------
# Checkpoints
# --------------------------------------------------------------------------
def live_ckpt_dir():
    """The directory the RUNNING job actually writes to.

    CKPT_DIR was hardcoded to BASE/"ckpt". The live run writes to BASE/"ckpt2",
    so every checkpoint reading this watchdog produced described a DEAD directory
    from an abandoned run: on 2026-09-06 it reported "newest checkpoint is 11.2h
    old" eleven minutes after a checkpoint was written. Nothing was deleted only
    because the stale dir held fewer entries than KEEP_CKPTS -- i.e. the guard
    that saved us was luck, not design.

    Each checkpoint records its own ckpt_dir in train_state.json, written by the
    training itself, so ask the run rather than assume. Falls back to CKPT_DIR.
    """
    best, best_mtime = None, -1.0
    try:
        for child in BASE.iterdir():
            if not child.is_dir() or not child.name.startswith("ckpt"):
                continue
            for step in child.iterdir():
                ts = step / "train_state.json"
                if not ts.is_file():
                    continue
                m = ts.stat().st_mtime
                if m > best_mtime:
                    try:
                        recorded = json.loads(ts.read_text(encoding="utf-8"))                             .get("args", {}).get("ckpt_dir")
                    except Exception:
                        recorded = None
                    best_mtime = m
                    best = Path(recorded) if recorded else child
    except Exception:
        pass
    if best is not None and best.exists():
        return best
    return CKPT_DIR


def list_ckpts():
    d = live_ckpt_dir()
    if not d.exists():
        return []
    return sorted(d.iterdir(), key=lambda p: p.stat().st_mtime)


def newest_ckpt_age_seconds():
    entries = list_ckpts()
    if not entries:
        return None
    return time.time() - entries[-1].stat().st_mtime


def cleanup_checkpoints_if_needed():
    """Always allowed, regardless of ENABLED -- protecting shared disk on the
    box is not the same authority question as starting/stopping training."""
    actions = []
    try:
        free_gb = get_disk_free_gb()
    except Exception as e:
        log(f"disk check failed: {e}", "ERROR")
        return actions, None

    if free_gb >= MIN_DISK_FREE_GB:
        return actions, free_gb

    entries = list_ckpts()
    while free_gb < MIN_DISK_FREE_GB and len(entries) > KEEP_CKPTS:
        victim = entries.pop(0)  # oldest first, newest N always survive
        try:
            if victim.is_dir():
                shutil.rmtree(victim)
            else:
                victim.unlink()
            free_gb = get_disk_free_gb()
            msg = f"disk tight ({MIN_DISK_FREE_GB:.0f}GB floor) -- deleted oldest checkpoint {victim.name}; free now {free_gb:.1f}GB"
            actions.append(msg)
            log(msg, "WARN")
        except Exception as e:
            log(f"failed to delete checkpoint {victim}: {e}", "ERROR")
            break

    if free_gb < MIN_DISK_FREE_GB and len(list_ckpts()) <= KEEP_CKPTS:
        log(
            f"disk still low ({free_gb:.1f}GB free) but only {len(list_ckpts())} "
            f"checkpoint(s) remain -- refusing to delete the newest {KEEP_CKPTS}",
            "CRITICAL",
        )
    return actions, free_gb


# --------------------------------------------------------------------------
# status.json / loss trend
# --------------------------------------------------------------------------
def read_status():
    try:
        raw = STATUS.read_text(encoding="utf-8")
        data = json.loads(raw)
        mtime = STATUS.stat().st_mtime
        return data, mtime
    except FileNotFoundError:
        return None, None
    except Exception as e:
        log(f"status.json unreadable: {e}", "ERROR")
        return None, None


def compute_loss_trend():
    try:
        lines = Path(LOSS_HISTORY).read_text(encoding="utf-8").splitlines()
    except Exception:
        return "insufficient_data", "no loss history yet"

    now = time.time()
    window = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if now - obj.get("ts", 0) <= LOSS_TREND_WINDOW_SECONDS:
            window.append(obj)

    distinct_steps = {o.get("step") for o in window if o.get("step") is not None}
    if len(distinct_steps) < 3:
        return "insufficient_data", f"only {len(distinct_steps)} distinct step(s) in window"

    window.sort(key=lambda o: o["ts"])
    earliest, latest = window[0], window[-1]
    e_loss, l_loss = earliest.get("loss"), latest.get("loss")
    if e_loss is None or l_loss is None:
        return "insufficient_data", "loss missing in window"

    threshold = max(abs(e_loss) * LOSS_STALL_REL_EPS, 1e-4)
    if l_loss <= e_loss - threshold:
        return "decreasing", f"{e_loss:.4f} -> {l_loss:.4f} over {(latest['ts']-earliest['ts'])/60:.0f}min"
    if l_loss >= e_loss + threshold:
        return "increasing", f"{e_loss:.4f} -> {l_loss:.4f} over {(latest['ts']-earliest['ts'])/60:.0f}min"
    return "stalled", f"{e_loss:.4f} -> {l_loss:.4f} (flat) over {(latest['ts']-earliest['ts'])/60:.0f}min"


# --------------------------------------------------------------------------
# Start / stop / restart
# --------------------------------------------------------------------------
def start_via_systemd():
    rc, out, err = run_cmd(["systemctl", "--user", "start", TRAIN_UNIT])
    return rc == 0, (out + err).strip()


def restart_via_systemd():
    rc, out, err = run_cmd(["systemctl", "--user", "restart", TRAIN_UNIT])
    return rc == 0, (out + err).strip()


def start_direct():
    BASE.mkdir(parents=True, exist_ok=True)
    train_py = BASE / "train.py"
    if not train_py.exists():
        return False, f"{train_py} does not exist -- nothing to start"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        with open(STDOUT_LOG, "a", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                LAUNCH_CMD,
                cwd=str(BASE),
                stdout=logf,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
        PIDFILE.write_text(str(proc.pid))
        return True, f"started pid {proc.pid} ({' '.join(LAUNCH_CMD)})"
    except Exception as e:
        return False, f"start failed: {e}"


def stop_direct(pid):
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception as e:
        log(f"SIGTERM to {pid} failed: {e}", "WARN")
        return
    for _ in range(10):
        time.sleep(1)
        if not is_pid_alive(pid):
            return
    try:
        os.kill(pid, signal.SIGKILL)
        log(f"pid {pid} did not exit on SIGTERM, sent SIGKILL", "WARN")
    except ProcessLookupError:
        pass


def do_restart(hung, pid, via_systemd):
    """Returns (ok, detail)."""
    if via_systemd:
        detail_prefix = ""
        if hung:
            detail_prefix = "hung (via systemd unit) -- "
        ok, detail = restart_via_systemd()
        return ok, detail_prefix + (detail or f"systemctl --user restart {TRAIN_UNIT}")
    else:
        if hung and pid:
            log(f"stopping hung pid {pid} before relaunch", "WARN")
            stop_direct(pid)
        return start_direct()


# --------------------------------------------------------------------------
# Backoff / crash-loop
# --------------------------------------------------------------------------
def restart_allowed(state):
    now = time.time()
    hist = [t for t in state.get("restart_history", []) if now - t < 3600]
    state["restart_history"] = hist
    if len(hist) >= MAX_RESTARTS_PER_HOUR:
        return False, f"crash-loop cap reached ({len(hist)} restarts in the last hour, cap={MAX_RESTARTS_PER_HOUR})"
    consecutive = state.get("consecutive_restarts", 0)
    backoff = min(BACKOFF_BASE_SECONDS * (2 ** consecutive), BACKOFF_CAP_SECONDS)
    last_ts = state.get("last_restart_ts", 0)
    remaining = backoff - (now - last_ts)
    if remaining > 0:
        return False, f"backoff active, {int(remaining)}s remaining before restart #{consecutive + 1} is allowed"
    return True, None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    BASE.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    state = load_json(WATCHDOG_STATE, {})
    problems = []
    actions = []

    # 1. disk cleanup -- always allowed, protects the shared host regardless
    #    of whether training is authorized to run.
    cleanup_actions, disk_free_gb = cleanup_checkpoints_if_needed()
    actions += cleanup_actions
    if disk_free_gb is not None and disk_free_gb < MIN_DISK_FREE_GB:
        problems.append(f"disk free {disk_free_gb:.1f}GB is below the {MIN_DISK_FREE_GB:.0f}GB floor even after cleanup")

    # 2. liveness
    alive, pid, via_systemd = determine_liveness()

    # 3. status.json
    status_data, status_mtime = read_status()
    status_age = (time.time() - status_mtime) if status_mtime else None
    enabled = ENABLED_FILE.exists()

    hung = False
    if alive:
        # A RESUME IS NOT A HANG EITHER. Loading this run's 50 GB optimizer state
        # takes minutes, during which status.json still holds the PREVIOUS
        # process's last line -- which is both stale and says "stopped". Measuring
        # staleness from that timestamp would make every legitimate restart look
        # hung and start a kill loop. Staleness is only meaningful since THIS
        # process started, so re-base the age on process start when the status
        # predates it.
        _proc_age = read_proc_start_age_seconds(pid) if pid else None
        if status_age is not None and _proc_age is not None and _proc_age < status_age:
            status_age = _proc_age
        # ---------------------------------------------------------------
        # STALENESS IS ONLY MEANINGFUL IN A STATE THAT PROMISES A HEARTBEAT.
        #
        # This watchdog killed a healthy run THREE times on 2026-09-06 -- 01:18
        # ("hung", mid 50 GB checkpoint), 02:18 ("dead", systemctl timed out on a
        # loaded box), 02:44 ("hung", status.json 904s > 900s while the run was
        # 19 minutes into LOADING that same 50 GB back). The first two fixes were
        # narrow: they exempted "checkpointing", then fixed liveness. Neither
        # asked the general question, so "starting" walked straight through.
        #
        # The trainer's full vocabulary, read out of train.py rather than guessed:
        #   starting / running / checkpointing / stopped / finished
        #   crash_nonfinite_loss / crash_nonfinite_grad / crash_oom
        #
        # So classify all of it. Act only where the state itself means trouble;
        # in a BUSY state the absence of a heartbeat is expected, not evidence.
        # ---------------------------------------------------------------
        reported = (status_data or {}).get("status")

        if reported in CRASH_STATES:
            hung = True
            problems.append(
                "training reports %s -- a real crash, restart is the right answer"
                % reported)

        elif reported in BUSY_STATES:
            # Loading or writing 50 GB. No heartbeat is due. Only a silence far
            # longer than either operation has ever taken counts as a hang.
            if status_age is not None and status_age > BUSY_STALE_SECONDS:
                hung = True
                problems.append(
                    "status.json is stale (%.0fs > %ds) while the process still "
                    "reports '%s' -- past any checkpoint or resume we have seen, "
                    "so this looks HUNG" % (status_age, BUSY_STALE_SECONDS, reported))
            else:
                problems.append(
                    "'%s' for %.0fs -- NOT restarting; a busy state is not a hang"
                    % (reported, status_age if status_age is not None else -1))

        elif reported in EXITED_STATES:
            # It ended on purpose. systemd owns what happens next, not us.
            problems.append(
                "training reports '%s' -- an intentional exit; leaving it to systemd"
                % reported)

        elif reported == "running":
            _cap = stale_cap_for(status_data)
            if status_mtime is not None and status_age > _cap:
                hung = True
                problems.append(
                    "status.json is stale (%.0fs > %.0fs, which is 3 full steps at "
                    "the run's own reported rate) while the process is alive -- "
                    "looks HUNG" % (status_age, _cap))

        elif reported is not None:
            # A state this watchdog has never heard of. Refusing to act is always
            # recoverable; acting on a misreading is not.
            problems.append(
                "unrecognised training status %r -- refusing to judge it" % reported)
        elif status_mtime is None:
            age = read_proc_start_age_seconds(pid) if pid else None
            if age is not None and age > NO_STATUS_GRACE_SECONDS:
                hung = True
                problems.append(f"process has been alive {age:.0f}s with no status.json ever written (> {NO_STATUS_GRACE_SECONDS}s grace) -- looks HUNG")

    # 4. loss checks
    loss_finite = True
    loss_trend = "insufficient_data"
    if status_data is not None:
        loss = status_data.get("loss")
        if isinstance(loss, (int, float)):
            if math.isnan(loss) or math.isinf(loss):
                loss_finite = False
                problems.append("loss is NaN/Inf")
            else:
                append_jsonl(LOSS_HISTORY, {"ts": time.time(), "step": status_data.get("step"), "loss": loss})
        loss_trend, trend_detail = compute_loss_trend()
        if loss_trend == "stalled":
            problems.append(f"loss not improving over the trend window ({trend_detail}) -- reported only, a restart cannot fix this")
        elif loss_trend == "increasing":
            problems.append(f"loss increasing over the trend window ({trend_detail}) -- reported only, a restart cannot fix this")

    # 5. GPU (informational -- a single idle reading is not, on its own, proof of a hang)
    gpu_util = get_gpu_util()
    if alive and not hung and gpu_util is not None and max(gpu_util) < GPU_IDLE_THRESHOLD:
        problems.append(f"GPU utilization {gpu_util} looks idle while the process reports alive+fresh (informational, transient checkpoints/eval can look like this)")

    # 6. checkpoint freshness (informational -- true interval is unknown to us)
    ckpt_age = newest_ckpt_age_seconds()
    if enabled and ckpt_age is not None and ckpt_age > CKPT_STALE_WARN_SECONDS:
        problems.append(f"newest checkpoint is {ckpt_age / 3600:.1f}h old (informational, interval unknown)")

    # 7. dead-or-hung -> fix, gated by ENABLED + backoff + crash-loop cap
    needs_restart = (not alive) or hung

    # The escalation GATE is the flag file's existence, full stop -- that is
    # what the escalation message tells a human to delete, so deleting it
    # must be a COMPLETE undo. If we also kept a separate persistent
    # "escalated" bit that outlived the file, a human clearing the flag
    # would still get immediately re-escalated by the same stale
    # restart_history (since the crash-loop cap looks at the last hour) --
    # confusing and, worse, indistinguishable from "the delete didn't work".
    # So: state["escalated"] exists ONLY to notice that a human just cleared
    # the file, and that noticing resets the crash-loop counters so the very
    # next check gets a genuine fresh attempt instead of re-tripping the cap.
    escalated = ESCALATION_FLAG.exists()
    if state.get("escalated") and not escalated:
        log("WATCHDOG-ESCALATED was cleared by a human -- resetting crash-loop counters for a fresh attempt", "INFO")
        state["restart_history"] = []
        state["consecutive_restarts"] = 0
    state["escalated"] = escalated

    if needs_restart:
        why = "dead" if not alive else "hung"
        if not enabled:
            problems.append(f"training process is {why}, but ~/coder-train/ENABLED does not exist -- refusing to auto-start (Iddo's call)")
        elif escalated:
            problems.append("WATCHDOG-ESCALATED is present -- refusing further auto-restart until a human clears it")
        else:
            ok_backoff, reason = restart_allowed(state)
            if not ok_backoff:
                if "crash-loop cap" in reason:
                    save_json(ESCALATION_FLAG, {"ts": now_iso(), "reason": reason})
                    state["escalated"] = True
                    escalated = True
                    problems.append(f"CRASH-LOOP: {reason} -- escalating, wrote WATCHDOG-ESCALATED")
                    log(f"CRASH-LOOP escalation: {reason}", "CRITICAL")
                else:
                    problems.append(f"restart deferred: {reason}")
            else:
                log(f"attempting restart (reason={why}, via_systemd={via_systemd})", "WARN")
                problems.append(f"training process was {why} -- restart attempted this pass")
                ok, detail = do_restart(hung, pid, via_systemd)
                actions.append(detail)
                state.setdefault("restart_history", []).append(time.time())
                state["last_restart_ts"] = time.time()
                state["consecutive_restarts"] = state.get("consecutive_restarts", 0) + 1
                if ok:
                    log(f"restart OK: {detail}", "WARN")
                    # Re-confirm liveness so the verdict reflects reality AFTER
                    # the fix, not the pre-fix snapshot -- a successful auto
                    # recovery should not still read as an unresolved BROKEN.
                    for _ in range(5):
                        time.sleep(1)
                        alive, pid, via_systemd = determine_liveness()
                        if alive:
                            break
                    if alive:
                        hung = False
                        needs_restart = False
                        actions.append("post-restart check: process confirmed alive")
                    else:
                        problems.append("post-restart check: process still not visible in /proc after 5s")
                else:
                    problems.append(f"restart attempt FAILED: {detail}")
                    log(f"restart FAILED: {detail}", "ERROR")
    else:
        # healthy (or never-started) -- let the backoff counter heal after a
        # stable stretch, so one old crash doesn't keep slowing down restarts
        # forever. This never touches WATCHDOG-ESCALATED itself (that stays a
        # deliberate human gate, see WATCHDOG.md) -- only the reset above,
        # triggered by the file's disappearance, does that.
        if enabled and (time.time() - state.get("last_restart_ts", 0)) > STABLE_RESET_SECONDS:
            if state.get("consecutive_restarts", 0):
                log("stable for 30+ min since last restart -- resetting backoff counter", "INFO")
            state["consecutive_restarts"] = 0

    # 8. verdict
    never_started = (not enabled) and (not alive) and (status_data is None) and (pid is None)
    if never_started:
        verdict = "UNKNOWN"
        reason = "training not started yet (no ENABLED sentinel, no status.json, no process) -- expected before Iddo authorizes the run"
    elif escalated:
        verdict = "BROKEN"
        reason = "crash-loop escalated -- a human must inspect and delete ~/coder-train/WATCHDOG-ESCALATED to resume auto-restart"
    elif not loss_finite:
        verdict = "BROKEN"
        reason = "loss is NaN/Inf"
    elif needs_restart:
        verdict = "BROKEN"
        reason = "; ".join(problems) if problems else f"process {'dead' if not alive else 'hung'}"
    elif disk_free_gb is not None and disk_free_gb < MIN_DISK_FREE_GB:
        verdict = "BROKEN"
        reason = f"disk still low after cleanup: {disk_free_gb:.1f}GB free"
    elif problems:
        verdict = "VERIFIED"
        reason = "alive and fresh; informational warnings only: " + " | ".join(problems)
    else:
        verdict = "VERIFIED"
        reason = "training alive, status fresh, loss finite, GPU busy, disk and checkpoints OK"

    verdict_line = f"{verdict}: {reason}"

    out = {
        "timestamp": now_iso(),
        "verdict": verdict,
        "verdict_line": verdict_line,
        "enabled": enabled,
        "process_alive": alive,
        "pid": pid,
        "via_systemd_unit": via_systemd,
        "hung": hung,
        "status_age_seconds": status_age,
        "step": status_data.get("step") if status_data else None,
        "tokens_seen": status_data.get("tokens_seen") if status_data else None,
        "loss": json_safe_number(status_data.get("loss")) if status_data else None,
        "loss_finite": loss_finite,
        "loss_trend": loss_trend,
        "tokens_per_sec": json_safe_number(status_data.get("tokens_per_sec")) if status_data else None,
        "peak_gb": json_safe_number(status_data.get("peak_gb")) if status_data else None,
        "gpu_util_percent": gpu_util,
        "disk_free_gb": disk_free_gb,
        "newest_ckpt_age_seconds": ckpt_age,
        "restarts_last_hour": len(state.get("restart_history", [])),
        "consecutive_restarts": state.get("consecutive_restarts", 0),
        "escalated": escalated,
        "actions_taken": actions,
        "problems": problems,
    }
    save_json(WATCHDOG_STATUS, out)
    save_json(WATCHDOG_STATE, state)
    log(verdict_line)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if verdict != "BROKEN" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Never let an uncaught exception look like a crash with no explanation.
        import traceback
        tb = traceback.format_exc()
        try:
            log(f"WATCHDOG CRASHED: {e}\n{tb}", "CRITICAL")
            BASE.mkdir(parents=True, exist_ok=True)
            save_json(WATCHDOG_STATUS, {
                "timestamp": now_iso(),
                "verdict": "UNKNOWN",
                "verdict_line": f"UNKNOWN: watchdog itself crashed: {e}",
                "error": str(e),
                "traceback": tb,
            })
        except Exception:
            print(f"WATCHDOG CRASHED (and could not even write status): {e}\n{tb}", file=sys.stderr)
        sys.exit(2)
