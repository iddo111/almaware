# לזכרה של עלמה ז״ל
"""QUORUM · workers — the Eran Federation worker coordination core.

One click in a browser tab = one WORKER donating that machine's compute.
This module is the server side of that federation:

  * register    — a worker announces itself + capabilities (webgpu, models
                  it can run in-browser like Gemma, free-form tags).
  * heartbeat   — liveness; a worker is LIVE if seen in the last WORKER_TTL s.
  * lease       — long-poll pull of the next matching job (Condition-based,
                  no busy loop). A leased job that is not finished within its
                  lease_timeout is re-queued — a closed laptop never strands
                  a job.
  * result      — the worker returns the finished job's output.
  * jobs        — anyone (rooms, the UI, training drivers) enqueues work:
                  kind "generate" powers worker-donated chat models; any other
                  kind (e.g. "train_step") flows through untouched so training
                  coordinators can ride the same queue.

Auth: register returns a per-worker token; lease/result/heartbeat require it.
The HTTP layer above already gates callers to loopback + Tailscale CGNAT.

Durability: finished jobs append to state\\jobs_done.jsonl (audit trail);
queue itself is in-memory — a server restart drops pending jobs, which is the
honest choice for interactive work (the UI re-submits).

failure-is-a-value everywhere. 100% stdlib.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid

import stateio

WORKER_TTL = 90.0            # seconds since last contact to count as live
DEFAULT_LEASE_TIMEOUT = 300.0
MAX_JOBS = 1000
_DONE_LOG = os.path.join(stateio.STATE_DIR, "jobs_done.jsonl")

_lock = threading.RLock()
_cond = threading.Condition(_lock)     # signalled when a job becomes leasable
_workers: dict[str, dict] = {}         # worker_id -> record
_jobs: dict[str, dict] = {}            # job_id -> record
_job_events: dict[str, threading.Event] = {}   # job_id -> done event


def _now() -> float:
    return time.time()


def _worker_live(w: dict) -> bool:
    return (_now() - w.get("last_seen", 0)) < WORKER_TTL


def _public_worker(w: dict) -> dict:
    return {
        "worker_id": w["worker_id"],
        "name": w["name"],
        "capabilities": w["capabilities"],
        "live": _worker_live(w),
        "last_seen": round(_now() - w.get("last_seen", 0), 1),
        "jobs_done": w.get("jobs_done", 0),
        "registered_at": w.get("registered_at", 0),
    }


# ── worker lifecycle ─────────────────────────────────────────────────────────

def register(name: str, capabilities: dict | None) -> dict:
    caps = capabilities if isinstance(capabilities, dict) else {}
    models = caps.get("models")
    caps["models"] = [m for m in models if isinstance(m, (str, dict))] if isinstance(models, list) else []
    caps["tags"] = [str(t)[:64] for t in caps.get("tags", []) if t][:16] \
        if isinstance(caps.get("tags"), list) else []
    worker_id = "w-" + uuid.uuid4().hex[:12]
    token = secrets.token_urlsafe(24)
    with _lock:
        _workers[worker_id] = {
            "worker_id": worker_id,
            "name": str(name or "worker")[:80],
            "token": token,
            "capabilities": caps,
            "registered_at": _now(),
            "last_seen": _now(),
            "jobs_done": 0,
        }
    return {"ok": True, "worker_id": worker_id, "token": token,
            "heartbeat_every": int(WORKER_TTL // 3)}


def _auth(worker_id: str, token: str) -> dict | None:
    w = _workers.get(worker_id or "")
    if w is None or not token or w["token"] != token:
        return None
    return w


def heartbeat(worker_id: str, token: str) -> dict:
    with _lock:
        w = _auth(worker_id, token)
        if w is None:
            return {"ok": False, "error": "unknown worker or bad token"}
        w["last_seen"] = _now()
        pending = sum(1 for j in _jobs.values()
                      if j["status"] == "queued" and _matches(w, j))
    return {"ok": True, "pending_for_you": pending}


def update_caps(worker_id: str, token: str, model=None,
                ready: bool = False) -> dict:
    """PWA-worker heartbeats carry {model, model_ready}: the browser joins
    BEFORE its in-tab model finishes downloading, then flips readiness here.
    Sets capabilities["models"] to [model] iff ready, else [] — which is what
    donated_models()/_matches() read. Wakes lease waiters: a queued job may
    have just become matchable."""
    mid = str(model or "").strip()
    with _cond:
        w = _auth(worker_id, token)
        if w is None:
            return {"ok": False, "error": "unknown worker or bad token"}
        models = [mid] if (mid and ready) else []
        if w["capabilities"].get("models") != models:
            w["capabilities"]["models"] = models
            _cond.notify_all()
    return {"ok": True}


def list_workers() -> list[dict]:
    with _lock:
        return [_public_worker(w) for w in _workers.values()]


def donated_models() -> list[dict]:
    """Models offered by LIVE workers, as registry entries: id worker:<model>."""
    seen: dict[str, dict] = {}
    with _lock:
        for w in _workers.values():
            if not _worker_live(w):
                continue
            for m in w["capabilities"].get("models", []):
                mid = m if isinstance(m, str) else str(m.get("id", ""))
                if not mid:
                    continue
                label = mid if isinstance(m, str) else str(m.get("label") or mid)
                key = "worker:" + mid
                if key in seen:
                    seen[key]["count"] += 1
                    seen[key]["detail"] = f"{seen[key]['count']} workers"
                else:
                    seen[key] = {"id": key, "label": f"{label} (worker)",
                                 "detail": f"via {w['name']}", "count": 1}
    return [{"id": v["id"], "label": v["label"], "detail": v["detail"]}
            for v in seen.values()]


# ── job queue ────────────────────────────────────────────────────────────────

def _matches(w: dict, job: dict) -> bool:
    req = job.get("requires") or {}
    model = req.get("model")
    if model:
        offered = []
        for m in w["capabilities"].get("models", []):
            offered.append(m if isinstance(m, str) else str(m.get("id", "")))
        if model not in offered:
            return False
    for tag in req.get("tags", []):
        if tag not in w["capabilities"].get("tags", []):
            return False
    return True


def submit_job(kind: str, payload, requires: dict | None = None,
               lease_timeout: float = DEFAULT_LEASE_TIMEOUT) -> dict:
    if not kind or not isinstance(kind, str):
        return {"ok": False, "error": "kind is required"}
    req = requires if isinstance(requires, dict) else {}
    req.setdefault("tags", [])
    job_id = "j-" + uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "kind": kind[:64],
        "payload": payload,
        "requires": req,
        "status": "queued",          # queued | leased | done | failed
        "created_at": _now(),
        "leased_by": "",
        "leased_at": 0.0,
        "lease_timeout": max(10.0, float(lease_timeout or DEFAULT_LEASE_TIMEOUT)),
        "result": None,
        "error": "",
        "finished_at": 0.0,
    }
    with _cond:
        if len(_jobs) >= MAX_JOBS:
            # drop oldest finished jobs to stay bounded
            finished = sorted((j for j in _jobs.values()
                               if j["status"] in ("done", "failed")),
                              key=lambda j: j["finished_at"])
            for j in finished[: max(1, len(_jobs) - MAX_JOBS + 1)]:
                _jobs.pop(j["job_id"], None)
                _job_events.pop(j["job_id"], None)
            if len(_jobs) >= MAX_JOBS:
                return {"ok": False, "error": "job queue full"}
        _jobs[job_id] = job
        _job_events[job_id] = threading.Event()
        _cond.notify_all()
    return {"ok": True, "job_id": job_id}


def _requeue_expired_locked():
    now = _now()
    for j in _jobs.values():
        if j["status"] == "leased" and now - j["leased_at"] > j["lease_timeout"]:
            j["status"] = "queued"
            j["leased_by"] = ""
            j["leased_at"] = 0.0


def lease(worker_id: str, token: str, wait: float = 20.0) -> dict:
    """Long-poll: block up to `wait` seconds for a matching job."""
    deadline = time.monotonic() + max(0.0, min(float(wait or 0), 55.0))
    with _cond:
        w = _auth(worker_id, token)
        if w is None:
            return {"ok": False, "error": "unknown worker or bad token"}
        while True:
            w["last_seen"] = _now()
            _requeue_expired_locked()
            for j in _jobs.values():
                if j["status"] == "queued" and _matches(w, j):
                    j["status"] = "leased"
                    j["leased_by"] = worker_id
                    j["leased_at"] = _now()
                    return {"ok": True, "job": {
                        "job_id": j["job_id"], "kind": j["kind"],
                        "payload": j["payload"], "requires": j["requires"],
                        "lease_timeout": j["lease_timeout"],
                    }}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"ok": True, "job": None}
            _cond.wait(timeout=min(remaining, 5.0))


def finish_job(job_id: str, worker_id: str, token: str,
               ok: bool, result, error: str = "") -> dict:
    with _cond:
        w = _auth(worker_id, token)
        if w is None:
            return {"ok": False, "error": "unknown worker or bad token"}
        j = _jobs.get(job_id or "")
        if j is None:
            return {"ok": False, "error": "unknown job"}
        if j["status"] != "leased" or j["leased_by"] != worker_id:
            return {"ok": False, "error": "job is not leased by this worker"}
        j["status"] = "done" if ok else "failed"
        j["result"] = result
        j["error"] = str(error or "")[:400]
        j["finished_at"] = _now()
        w["jobs_done"] = w.get("jobs_done", 0) + 1
        w["last_seen"] = _now()
        ev = _job_events.get(job_id)
        if ev:
            ev.set()
        record = {"job_id": job_id, "kind": j["kind"], "ok": ok,
                  "worker": w["name"], "worker_id": worker_id,
                  "elapsed": round(j["finished_at"] - j["created_at"], 2),
                  "finished_at": j["finished_at"]}
    try:  # audit trail — outside the lock
        stateio.ensure_dir(stateio.STATE_DIR)
        with open(_DONE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"ok": True}


def job_status(job_id: str) -> dict:
    with _lock:
        j = _jobs.get(job_id or "")
        if j is None:
            return {"ok": False, "error": "unknown job"}
        return {"ok": True, "job": {
            "job_id": j["job_id"], "kind": j["kind"], "status": j["status"],
            "leased_by": j["leased_by"], "result": j["result"],
            "error": j["error"], "created_at": j["created_at"],
            "finished_at": j["finished_at"],
        }}


def wait_job(job_id: str, timeout: float) -> dict:
    ev = _job_events.get(job_id)
    if ev is not None:
        ev.wait(timeout=max(0.0, timeout))
    return job_status(job_id)


def stats() -> dict:
    with _lock:
        live = sum(1 for w in _workers.values() if _worker_live(w))
        by_status: dict[str, int] = {}
        for j in _jobs.values():
            by_status[j["status"]] = by_status.get(j["status"], 0) + 1
        return {"workers_total": len(_workers), "workers_live": live,
                "jobs": by_status, "donated_models": len(donated_models())}


# ── worker-donated chat routing (called by registry.chat) ────────────────────

def chat_via_worker(model_id: str, messages: list[dict],
                    timeout: float, t0: float) -> dict:
    """model_id is 'worker:<model>'. Enqueue a generate job requiring that
    model and wait for a live worker to answer."""
    bare = model_id.split(":", 1)[1] if ":" in model_id else model_id
    with _lock:
        have = any(_worker_live(w) and _matches(
            w, {"requires": {"model": bare, "tags": []}})
            for w in _workers.values())
    if not have:
        return {"ok": False, "text": "", "model": model_id, "error": "backend",
                "note": f"no live worker offers {bare!r}",
                "elapsed": round(time.monotonic() - t0, 2)}
    sub = submit_job("generate", {"model": bare, "messages": messages},
                     requires={"model": bare}, lease_timeout=timeout)
    if not sub.get("ok"):
        return {"ok": False, "text": "", "model": model_id, "error": "backend",
                "note": sub.get("error", "submit failed"),
                "elapsed": round(time.monotonic() - t0, 2)}
    status = wait_job(sub["job_id"], timeout)
    j = status.get("job") or {}
    if j.get("status") == "done":
        result = j.get("result")
        text = ""
        if isinstance(result, dict):
            text = str(result.get("text", ""))
        elif isinstance(result, str):
            text = result
        text = text.strip()
        if text:
            return {"ok": True, "text": text, "model": model_id,
                    "error": "none", "note": "",
                    "elapsed": round(time.monotonic() - t0, 2)}
        return {"ok": False, "text": "", "model": model_id, "error": "empty",
                "note": "worker returned empty text",
                "elapsed": round(time.monotonic() - t0, 2)}
    if j.get("status") == "failed":
        return {"ok": False, "text": "", "model": model_id, "error": "backend",
                "note": j.get("error") or "worker failed the job",
                "elapsed": round(time.monotonic() - t0, 2)}
    return {"ok": False, "text": "", "model": model_id, "error": "timeout",
            "note": f"no worker finished within {timeout}s "
                    f"(job {sub['job_id']} status {j.get('status')})",
            "elapsed": round(time.monotonic() - t0, 2)}
