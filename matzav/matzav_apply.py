# -*- coding: utf-8 -*-
r"""
matzav_apply.py — the ONLY module in MATZAV that executes anything.

GATE 3 of the sacred guard: _execute() re-checks is_sacred() against the frozen
table on EVERY call and raises before touching ssh. Deliberately redundant with
Gate 1 (registry load) and Gate 2 (plan): Gate 1 protects against a bad registry
file, Gate 3 protects against a bug that builds a unit object in memory.

THERE IS NO FORCE PARAMETER. Not here, not in the API, not in the UI.

Atomicity across five machines does not exist. It is bought with four devices:
  (a) a restore record, fsynced, BEFORE the first action
  (b) the plan is a state machine ON DISK (state/inflight.json), not in memory
  (c) rollback is best-effort and AUDITED, never silent
  (d) idempotence — systemctl start on an active unit is a no-op, so CONTINUE
      after a crash is safe, and the plan is RECOMPUTED from a fresh
      observation, never replayed from the stale one.
"""
import io
import json
import os
import re
import subprocess
import time

import matzav_probe as P
from matzav_sacred import SacredViolation, is_sacred

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state")
INFLIGHT = os.path.join(STATE, "inflight.json")
HISTORY = os.path.join(STATE, "history.jsonl")
LOCK = os.path.join(STATE, "matzav.lock")

UNIT_RE = re.compile(r"^[A-Za-z0-9@._:-]+$")
ACT_TIMEOUT = 25


# --------------------------------------------------------------------------
def _fsync_write(path, obj):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_inflight():
    try:
        with io.open(INFLIGHT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                        # noqa: BLE001
        return None


def clear_inflight():
    if os.path.exists(INFLIGHT):
        os.replace(INFLIGHT, INFLIGHT + ".last")


def append_history(rec):
    os.makedirs(STATE, exist_ok=True)
    with io.open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


# --------------------------------------------------------------------------
def _ssh_cmd(box_ssh, shell, timeout=ACT_TIMEOUT):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           box_ssh, "bash -s"]
    try:
        r = subprocess.run(cmd, input=shell.encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        return (r.returncode, r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"))
    except subprocess.TimeoutExpired:
        # A TIMEOUT IS NOT "THE ACTION FAILED". It may well have succeeded.
        return (-1, "", "TIMEOUT")
    except Exception as e:                                   # noqa: BLE001
        return (-2, "", "%s: %s" % (type(e).__name__, e))


def _execute(unit, action, boxes):
    """The single choke point. Structured verbs only — never a free-form command
    from JSON. A JSON file containing shell strings, reachable from a web page,
    is a remote-code-execution surface."""
    box, name = unit["box"], unit["unit"]

    # ---- GATE 3 ----------------------------------------------------------
    if action == "stop" and (is_sacred(box, name) or unit.get("sacred")):
        raise SacredViolation("%s/%s is SACRED. There is no force flag."
                              % (box, name))
    if box == "pc":
        raise SacredViolation("the PC hosts no modes (PC_HOSTS_NO_MODES).")
    if not UNIT_RE.match(name):
        raise SacredViolation("unit name %r fails validation." % name)

    verb = unit.get(action) or {}
    ssh = boxes[box]["ssh"]

    if "systemd" in verb:
        sub = verb["systemd"]
        assert sub in ("start", "stop")
        sh = ("export XDG_RUNTIME_DIR=/run/user/$(id -u)\n"
              "systemctl --user %s %s\n" % (sub, name))
    elif "systemd-system" in verb:
        sub = verb["systemd-system"]
        assert sub in ("start", "stop")
        sh = "sudo -n systemctl %s %s\n" % (sub, name)
    elif "ollama" in verb:
        ka = "30m" if verb["ollama"] == "load" else "0"
        sh = ("curl -s --max-time 240 http://127.0.0.1:11434/api/generate "
              "-d '{\"model\":\"%s\",\"prompt\":\"\",\"keep_alive\":\"%s\"}' "
              ">/dev/null; echo done\n" % (name, ka))
    else:
        raise SacredViolation("no executable verb for %s/%s %s"
                              % (box, name, action))
    return _ssh_cmd(ssh, sh)


def verify(units, boxes, uid, want_up, deadline_s):
    """Verify by PROBE. Never by exit code, never by systemctl is-active alone."""
    one = {uid: units[uid]}
    delays, t0 = [0.5, 1, 2, 4, 8, 8, 8, 8, 8, 8], time.time()
    last = None
    for d in delays:
        time.sleep(d)
        st = P.observe(one, boxes, only_boxes=[units[uid]["box"]])
        last = st["units"].get(uid) or {}
        real = last.get("real")
        if want_up and real == "up":
            return True, last
        if (not want_up) and real == "down":
            return True, last
        if time.time() - t0 > deadline_s:
            break
    return False, last


# --------------------------------------------------------------------------
def apply_plan(plan_obj, units, boxes, actor="iddo via matzav"):
    """Executes a plan. Yields progress dicts. Assumes the caller holds the
    single global lock (matzav.py enforces one plan or HTTP 409)."""
    pid = "p%d" % int(time.time())
    steps = []
    for s in plan_obj["steps"]:
        steps.append(dict(s, status="pending", started=None, ended=None,
                          dur_s=None, err=None))
    inflight = {"plan_id": pid, "mode": plan_obj["mode"], "actor": actor,
                "started": time.time(), "steps": steps, "restore": [],
                "status": "running", "outcome": None}
    _fsync_write(INFLIGHT, inflight)
    yield {"event": "start", "plan_id": pid, "steps": len(steps)}

    done_ok = True
    for i, s in enumerate(steps):
        u = units[s["unit"]]
        s["status"] = "running"
        s["started"] = time.time()
        # ---- (a) restore record BEFORE the action, fsynced -----------------
        inflight["restore"].insert(0, {
            "unit": s["unit"], "box": s["box"],
            "inverse": "start" if s["act"] == "stop" else "stop",
            "pre_real": (plan_obj.get("pre_state") or {}).get(s["unit"]),
        })
        _fsync_write(INFLIGHT, inflight)
        yield {"event": "step", "i": i, "act": s["act"], "unit": s["unit"],
               "status": "running"}

        try:
            rc, out, err = _execute(u, s["act"], boxes)
        except SacredViolation as e:
            s["status"], s["err"] = "failed", "SACRED: %s" % e
            done_ok = False
            break
        deadline = (u["cost"].get("load_s_cold") or 30) * 2 + 30
        ok, last = verify(units, boxes, s["unit"],
                          want_up=(s["act"] == "start"), deadline_s=deadline)
        s["ended"] = time.time()
        s["dur_s"] = round(s["ended"] - s["started"], 1)
        if ok:
            s["status"] = "done"
            s["measured"] = last.get("detail")
        else:
            s["status"] = "failed"
            s["err"] = ("rc=%s %s | probe still says %s"
                        % (rc, (err or out or "").strip()[:120],
                           (last or {}).get("real")))
            done_ok = False
        _fsync_write(INFLIGHT, inflight)
        yield {"event": "step", "i": i, "act": s["act"], "unit": s["unit"],
               "status": s["status"], "dur_s": s["dur_s"], "err": s["err"]}
        if not done_ok:
            break

    outcome, rolled = ("APPLIED", [])
    if not done_ok:
        yield {"event": "rollback_start"}
        outcome, rolled = _rollback(inflight, units, boxes)
        yield {"event": "rollback_done", "outcome": outcome, "rolled": rolled}

    inflight["status"] = "finished"
    inflight["outcome"] = outcome
    inflight["ended"] = time.time()
    _fsync_write(INFLIGHT, inflight)
    append_history({
        "plan_id": pid, "ts": time.time(),
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": plan_obj["mode"], "actor": actor, "outcome": outcome,
        "steps": [{"act": x["act"], "unit": x["unit"], "status": x["status"],
                   "dur_s": x["dur_s"], "err": x["err"],
                   "measured": x.get("measured")} for x in steps],
        "budget_before": plan_obj.get("budget"),
        "rolled_back": rolled,
    })
    clear_inflight()
    yield {"event": "end", "outcome": outcome, "plan_id": pid}


def _rollback(inflight, units, boxes):
    """Best-effort and audited, never silent. Three reported outcomes."""
    rolled, failed = [], []
    for r in inflight["restore"]:
        # only undo steps that actually completed
        st = next((s for s in inflight["steps"] if s["unit"] == r["unit"]), None)
        if not st or st["status"] != "done":
            continue
        u = units[r["unit"]]
        bs = r["box"]
        if (inflight.get("unreachable") or {}).get(bs):
            failed.append(r["unit"])
            continue
        try:
            _execute(u, r["inverse"], boxes)
        except SacredViolation:
            failed.append(r["unit"])
            continue
        ok, _ = verify(units, boxes, r["unit"],
                       want_up=(r["inverse"] == "start"), deadline_s=90)
        (rolled if ok else failed).append(r["unit"])
    if failed and rolled:
        return "PARTIAL", rolled
    if failed:
        return "FAILED", rolled
    return "ROLLED_BACK", rolled


def history(n=60):
    out = []
    try:
        with io.open(HISTORY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:                        # noqa: BLE001
                        pass
    except Exception:                                        # noqa: BLE001
        return []
    return out[-n:][::-1]
