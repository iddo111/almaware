#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRAIN <-> ONBOARD CODER -- the one-click flip Iddo asked for, 2026-09-07 22:40:

    "תבנה ותריץ את הדשבורד שבלחיצה אחת אני מעביר מסט אימון לסט אונבורד קודר"
    (build and run the dashboard where one click moves a box from a TRAINING
     setup to an ONBOARD-CODER setup)

eran3 is the training box: coder-train.service (CODER continued-pretrain, the
run Iddo declared PERMANENT on 2026-09-05 23:58 -- "every training run never
stops"). Measured 2026-09-07 22:45: step 175/1600, loss 1.4625, 81.17 GB of
reserved unified memory (status.json's own number -- systemd's cgroup
MemoryCurrent does NOT see CUDA-unified allocation on a GB10: it read 759 MB
for the same process at the same instant). eran3 has ~121 GB total. The
onboard coder (qwen3-coder-next, ~51 GB, measured on eran4 2026-09-07) cannot
share the box with that: 81 + 51 > 121. plan_to_coder() below computes the
real arithmetic every time, never assumes it.

THIS IS A SEPARATE, HEAVIER GATE than fleet_mode.py's PERMANENT_TRAINING list.
fleet_mode.py refuses to EVER stop coder-train.service -- no override, because
that program runs mode switches unattended and Iddo's rule for it is
absolute. This module is the one place that rule is allowed to bend, because
Iddo explicitly asked for a control he can click himself to make that trade.
So here, and only here, coder-train.service CAN be stopped -- but behind:

  (a) a plan step that states in plain language it is stopping a run Iddo
      called permanent, with the LIVE step/loss/checkpoint numbers read fresh
      every time, never cached across the confirm dialog,
  (b) a second, textual confirmation -- the exact phrase in CONFIRM_PHRASE,
      typed by a human into the dialog, not just a second button click --
      checked server-side in apply_to_coder(), never trusted from the client,
  (c) the same re-derive-and-reverify discipline as fleet_mode.execute_plan
      and ollama_switch.apply_switch: nothing here trusts a stale plan dict,
      a cached token's contents, or an rc==0. Every apply re-reads the world
      before AND after.

eran1 is hard-blocked the same way as everywhere else in this program:
assert_host() refuses it by name before any I/O, and TRAIN_HOST is the only
host this module is willing to name at all -- there is no host parameter path
that reaches eran1 through this module, hand-built call or not.

THIS MODULE NEVER PULLS A MODEL. plan_to_coder() only ever offers to load a
model that is already present in the target host's own `ollama list` (same
rule ollama_switch.py already applies) -- a 50+ GB network transfer is not a
side effect any one click should trigger silently. If the onboard coder is
not present on eran3 yet, the plan says so plainly and refuses; provisioning
it (rsync from eran4, or a future `ollama pull` if it is ever published) is a
separate, disclosed action, not something this control does for you.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import fleet_mode as fm  # reuses _ssh (argv list, shell=False, BatchMode ssh)
import ollama_switch as ox  # reuses ollama_list/ollama_ps/mem_info/disk_info

# --------------------------------------------------------------------------
# The only host/unit this control knows how to flip. Adding a second training
# box later means adding one entry here -- nothing else in the module assumes
# there is exactly one.
# --------------------------------------------------------------------------
TRAIN_HOST = "eran3"
TRAIN_UNIT = "coder-train.service"
STATUS_JSON = "coder-train/status.json"
WATCHDOG_JSON = "coder-train/watchdog-status.json"
CKPT_DIR = "coder-train/ckpt2"

# VERIFIED 2026-09-07 by reading the live unit file (`systemctl --user cat
# coder-train.service` on eran3): ExecStart carries `--resume auto`, baked
# into the unit itself. A plain `systemctl --user start coder-train.service`
# after a stop resumes from the newest COMPLETE checkpoint automatically --
# there is no separate flag a human has to remember to pass.
RESUME_CMD = f'ssh {TRAIN_HOST} "systemctl --user start {TRAIN_UNIT}"'

# The onboard coder is one blob under three tags on eran4 (measured
# 2026-09-07: id 77c650d3ef73, 51 GB, `ollama list` on eran4). This module
# looks for any of these already present in a host's OWN catalog -- see the
# module docstring: it never pulls one.
ONBOARD_CODER_CANDIDATES: tuple[str, ...] = (
    "qwen3-coder-next-eran4:latest",
    "qwen-coder-dgx4:latest",
    "qwen3-coder-next:q4_K_M",
)

# Typed, not just clicked. Checked server-side in apply_to_coder().
CONFIRM_PHRASE = "STOP TRAINING"

STATE_DIR = Path(__file__).resolve().parent / "state"
LOG_FILE = STATE_DIR / "train_vs_coder.jsonl"


class TrainCoderRefused(Exception):
    """Raised when a flip is refused - by host, by fit, or by a missing/wrong confirm phrase."""


def assert_host(host: str) -> None:
    """Point-of-execution gate, same shape as fm.assert_actionable / ox.assert_switchable.

    Re-derived from nothing but the host string, so a caller that hand-builds
    a call still cannot reach eran1 through this module.
    """
    h = (host or "").strip()
    if h == "eran1":
        raise TrainCoderRefused(
            "REFUSED: eran1 is ERAN himself - never a training/coder slot in this "
            "dashboard. No flag overrides this."
        )
    if h != TRAIN_HOST:
        raise TrainCoderRefused(
            f"REFUSED: {h!r} is not a training host this control knows about "
            f"(only {TRAIN_HOST!r})"
        )


# --------------------------------------------------------------------------
# Reading the world - all read-only, all honest about failure
# --------------------------------------------------------------------------

def _cat(host: str, path: str, timeout: int = 15) -> str | None:
    rc, out, _err = fm._ssh(host, ["cat", path], timeout=timeout)
    return out if rc == 0 else None


def _json_or_none(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _fmt_age(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown age"
    s = float(seconds)
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.1f}m"
    return f"{s / 3600:.1f}h"


def training_unit_state(host: str = TRAIN_HOST, timeout: int = 30) -> dict[str, Any]:
    """`systemctl --user show coder-train.service` - authoritative ActiveState.

    Same probe fleet_mode.py insists on (user scope, not system scope: system
    scope answers 'not-found' for a unit that is running perfectly).
    """
    rc, out, err = fm._ssh(
        host,
        ["systemctl", "--user", "show", TRAIN_UNIT, "--no-pager",
         "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
         "-p", "ExecMainStartTimestamp", "-p", "NRestarts"],
        timeout=timeout,
    )
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400]}
    d: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            d[k] = v
    return {
        "ok": True, "error": None,
        "active_state": d.get("ActiveState"), "sub_state": d.get("SubState"),
        "main_pid": d.get("MainPID"), "since": d.get("ExecMainStartTimestamp"),
        "n_restarts": d.get("NRestarts"),
    }


def training_progress(host: str = TRAIN_HOST) -> dict[str, Any]:
    """status.json + watchdog-status.json + newest checkpoint dir name.

    All three are read independently and each says so if it is missing --
    a stopped training run means status.json stops updating, which is
    expected and reported, not hidden.
    """
    status = _json_or_none(_cat(host, STATUS_JSON))
    watchdog = _json_or_none(_cat(host, WATCHDOG_JSON))
    rc, out, _err = fm._ssh(host, ["ls", "-1", CKPT_DIR], timeout=15)
    ckpts = sorted(ln.strip() for ln in out.splitlines() if ln.strip()) if rc == 0 else []
    newest = ckpts[-1] if ckpts else None
    return {
        "status_ok": status is not None, "status": status,
        "watchdog_ok": watchdog is not None, "watchdog": watchdog,
        "checkpoints": ckpts, "newest_checkpoint": newest,
        "newest_checkpoint_age_s": (watchdog or {}).get("newest_ckpt_age_seconds"),
    }


def read_state(host: str = TRAIN_HOST) -> dict[str, Any]:
    """Everything the dashboard shows for the flip card. Read-only, always honest."""
    try:
        assert_host(host)
    except TrainCoderRefused as exc:
        return {"host": host, "reachable": False, "error": str(exc)}

    tstate = training_unit_state(host)
    if not tstate.get("ok"):
        return {"host": host, "reachable": False, "error": tstate.get("error")}

    prog = training_progress(host)
    ps = ox.ollama_ps(host)
    mem = ox.mem_info(host)
    disk = ox.disk_info(host)
    lst = ox.ollama_list(host)

    training_active = tstate.get("active_state") == "active"
    loaded_names = {m["name"] for m in ps.get("loaded", [])} if ps.get("ok") else set()
    coder_loaded = [n for n in loaded_names if n in ONBOARD_CODER_CANDIDATES]

    if training_active and not coder_loaded:
        mode = "TRAINING"
    elif coder_loaded and not training_active:
        mode = "ONBOARD CODER"
    elif training_active and coder_loaded:
        mode = "BOTH (unexpected - should not fit)"
    else:
        mode = "NEITHER"

    st = (prog.get("status") or {})
    return {
        "host": host, "reachable": True, "error": None, "mode": mode,
        "training_active": training_active,
        "training_state": tstate,
        "training_step": st.get("step"), "training_max_steps": st.get("max_steps"),
        "training_loss": st.get("loss"), "training_reserved_gb": st.get("reserved_gb"),
        "training_tokens_per_sec": st.get("tokens_per_sec"), "training_eta_h": st.get("eta_h"),
        "training_status_timestamp": st.get("timestamp"),
        "watchdog_verdict": (prog.get("watchdog") or {}).get("verdict_line"),
        "newest_checkpoint": prog.get("newest_checkpoint"),
        "newest_checkpoint_age_s": prog.get("newest_checkpoint_age_s"),
        "newest_checkpoint_age": _fmt_age(prog.get("newest_checkpoint_age_s")),
        "resume_command": RESUME_CMD,
        "ollama_loaded": ps.get("loaded", []) if ps.get("ok") else [],
        "coder_loaded": coder_loaded,
        "mem": mem if mem.get("ok") else None,
        "disk": disk if disk.get("ok") else None,
        "catalog": lst.get("models", []) if lst.get("ok") else [],
        "onboard_coder_present": [c for c in ONBOARD_CODER_CANDIDATES
                                  if any(m["name"] == c for m in lst.get("models", []))],
    }


# --------------------------------------------------------------------------
# Picking the model - never invented, never pulled
# --------------------------------------------------------------------------

def _best_model_candidate(host: str, requested: str | None) -> tuple[str | None, dict[str, Any]]:
    lst = ox.ollama_list(host)
    if not lst.get("ok"):
        return None, {"catalog_ok": False, "catalog_error": lst.get("error"), "catalog": []}
    catalog = {m["name"]: m for m in lst["models"]}
    if requested:
        picked = requested if requested in catalog else None
        return picked, {"catalog_ok": True, "catalog": lst["models"],
                        "requested_present": requested in catalog}
    for c in ONBOARD_CODER_CANDIDATES:
        if c in catalog:
            return c, {"catalog_ok": True, "catalog": lst["models"]}
    return None, {"catalog_ok": True, "catalog": lst["models"]}


# --------------------------------------------------------------------------
# Plan: TRAINING -> ONBOARD CODER (the dangerous direction)
# --------------------------------------------------------------------------

def plan_to_coder(model: str | None = None, host: str = TRAIN_HOST) -> dict[str, Any]:
    """Compute exactly what a flip-to-coder would do. Never guesses, never pulls.

    Always fills in the training numbers (step, loss, checkpoint, resume
    command) even when the plan ends up refused for an unrelated reason (the
    model not being present) - Iddo asked to SEE the arithmetic and the risk,
    not just a yes/no.
    """
    result: dict[str, Any] = {
        "host": host, "direction": "to_coder", "model": model, "fits": False,
        "will_stop_training": False, "will_stop_ollama": [], "reasons": [],
        "requires_confirm_phrase": CONFIRM_PHRASE,
    }
    try:
        assert_host(host)
    except TrainCoderRefused as exc:
        result["reasons"].append(str(exc))
        return result

    tstate = training_unit_state(host)
    if not tstate.get("ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s training-unit state - "
                                 f"{tstate.get('error')}")
        return result
    training_active = tstate.get("active_state") == "active"
    result["training_state"] = tstate

    prog = training_progress(host)
    st = prog.get("status") or {}
    result["training_step"] = st.get("step")
    result["training_max_steps"] = st.get("max_steps")
    result["training_loss"] = st.get("loss")
    result["training_reserved_gb"] = st.get("reserved_gb")
    result["training_eta_h"] = st.get("eta_h")
    result["newest_checkpoint"] = prog.get("newest_checkpoint")
    result["newest_checkpoint_age_s"] = prog.get("newest_checkpoint_age_s")
    result["resume_command"] = RESUME_CMD

    result["warning"] = (
        f"Iddo declared coder-train.service PERMANENT, 2026-09-05 23:58: "
        f"'every training run never stops.' This flip stops it anyway - that is "
        f"the one thing this control exists to let YOU do, on YOUR click. "
        f"Currently step {st.get('step')}/{st.get('max_steps')}, loss {st.get('loss')}, "
        f"{st.get('tokens_per_sec')} tok/s, ETA {st.get('eta_h')}h. Newest checkpoint: "
        f"{prog.get('newest_checkpoint')} ({_fmt_age(prog.get('newest_checkpoint_age_s'))} old). "
        f"Resume any time, from that checkpoint automatically, with: {RESUME_CMD}"
    ) if training_active else (
        "coder-train.service is already NOT active - nothing to stop on the training side."
    )

    picked, cat_info = _best_model_candidate(host, model)
    result["catalog_info"] = cat_info
    if not cat_info.get("catalog_ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s ollama catalog - "
                                 f"{cat_info.get('catalog_error')}")
        return result
    if picked is None:
        wanted = model or " or ".join(ONBOARD_CODER_CANDIDATES)
        result["reasons"].append(
            f"REFUSED: {wanted!r} is not present in {host}'s own `ollama list`. "
            "This control never auto-pulls a 50+ GB model over the network as a "
            "side effect of one click - provision it on the box first (rsync the "
            "blob from eran4, or `ollama pull` if it is ever published as a shared "
            "tag), then this flip can proceed."
        )
        result["will_stop_training"] = training_active  # honest about the OTHER half of the plan
        return result
    result["model"] = picked

    ps = ox.ollama_ps(host)
    if not ps.get("ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s currently-loaded models - "
                                 f"{ps.get('error')}")
        return result
    loaded = ps["loaded"]

    mem = ox.mem_info(host)
    if not mem.get("ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s free RAM - {mem.get('error')}")
        return result

    target = next((m for m in cat_info["catalog"] if m["name"] == picked), None)
    target_gb = target.get("size_gb") if target else None
    if target_gb is None:
        result["reasons"].append(f"REFUSED: could not parse the size of {picked!r}")
        return result

    freed_ollama_gb = sum((m.get("size_gb") or 0.0) for m in loaded)
    # The training process's OWN reported reserved unified memory is the
    # authoritative number on a GB10 - see the module docstring: systemd's
    # cgroup MemoryCurrent does not see CUDA-unified allocation at all.
    freed_training_gb = (st.get("reserved_gb") or 0.0) if training_active else 0.0
    available_gb = mem["available_gb"]
    projected_gb = available_gb + freed_ollama_gb + freed_training_gb
    needed_gb = target_gb + ox.SAFETY_MARGIN_GB
    fits = projected_gb >= needed_gb

    parts = [f"available now {available_gb:.1f} GB"]
    if training_active:
        parts.append(f"freed by stopping {TRAIN_UNIT} ({freed_training_gb:.1f} GB)")
    if loaded:
        parts.append(f"freed by stopping {', '.join(m['name'] for m in loaded)} "
                     f"({freed_ollama_gb:.1f} GB)")

    result.update({
        "will_stop_training": training_active,
        "will_stop_ollama": [m["name"] for m in loaded],
        "target_size_gb": round(target_gb, 1),
        "available_gb": available_gb,
        "freed_by_stopping_training_gb": round(freed_training_gb, 1),
        "freed_by_stopping_ollama_gb": round(freed_ollama_gb, 1),
        "projected_available_gb": round(projected_gb, 1),
        "safety_margin_gb": ox.SAFETY_MARGIN_GB,
        "needed_gb": round(needed_gb, 1),
        "fits": fits,
        "arithmetic": (
            f"{host}: " + " + ".join(parts) +
            f" = {projected_gb:.1f} GB projected. {picked} needs {target_gb:.1f} GB + "
            f"{ox.SAFETY_MARGIN_GB:.0f} GB safety margin = {needed_gb:.1f} GB. "
            + ("FITS." if fits else "DOES NOT FIT - refused.")
        ),
    })
    if not fits:
        result["reasons"].append("REFUSED: does not fit in projected free RAM - see arithmetic.")
    return result


# --------------------------------------------------------------------------
# Plan: ONBOARD CODER -> TRAINING (the safe / reverse direction)
# --------------------------------------------------------------------------

def plan_to_training(host: str = TRAIN_HOST) -> dict[str, Any]:
    result: dict[str, Any] = {
        "host": host, "direction": "to_training", "reasons": [],
        "will_stop_ollama": [], "will_start_training": False, "fits": False,
    }
    try:
        assert_host(host)
    except TrainCoderRefused as exc:
        result["reasons"].append(str(exc))
        return result

    tstate = training_unit_state(host)
    if not tstate.get("ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s training-unit state - "
                                 f"{tstate.get('error')}")
        return result
    training_active = tstate.get("active_state") == "active"
    result["training_state"] = tstate

    ps = ox.ollama_ps(host)
    if not ps.get("ok"):
        result["reasons"].append(f"REFUSED: cannot read {host}'s currently-loaded models - "
                                 f"{ps.get('error')}")
        return result
    loaded = ps["loaded"]

    prog = training_progress(host)
    result["training_progress"] = prog
    result["resume_command"] = RESUME_CMD

    if training_active:
        result["reasons"].append("coder-train.service is already active - nothing to start.")
        result["fits"] = True
        return result

    result.update({
        "will_stop_ollama": [m["name"] for m in loaded],
        "will_start_training": True,
        "fits": True,
        "newest_checkpoint": prog.get("newest_checkpoint"),
        "arithmetic": (
            f"{host}: will stop " +
            (', '.join(m['name'] for m in loaded) if loaded else "(nothing loaded)") +
            f", then `systemctl --user start {TRAIN_UNIT}`. The unit's own ExecStart "
            f"carries --resume auto (verified in the live unit file), so it resumes "
            f"from the newest COMPLETE checkpoint ({prog.get('newest_checkpoint')}) "
            f"automatically - no extra flag to remember."
        ),
    })
    return result


# --------------------------------------------------------------------------
# Logging - append-only, records FAIL and REFUSED, not only OK
# --------------------------------------------------------------------------

def log_flip(record: dict[str, Any]) -> None:
    record = dict(record)
    record.setdefault("ts", time.time())
    record.setdefault("ts_iso", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# Apply: TRAINING -> ONBOARD CODER
# --------------------------------------------------------------------------

def apply_to_coder(actor: str, model: str | None = None, host: str = TRAIN_HOST,
                   confirm_text: str = "",
                   prompt: str = "Reply with one short sentence confirming you are alive, "
                                  "in English then Hebrew.") -> dict[str, Any]:
    """Re-derives the plan from scratch (never trusts a stale plan dict), then:
      1. verify the typed confirm phrase matches CONFIRM_PHRASE exactly
      2. `systemctl --user show` + status.json  -> BEFORE state, real evidence
      3. `systemctl --user stop coder-train.service` (up to 60 min - the unit's
         own TimeoutStopSec for a graceful 50 GB checkpoint write)
      4. `ollama stop` every model already loaded on host
      5. `ollama run <model> "<prompt>"` -> a REAL generation, not a health check
      6. re-read training-unit state AND `ollama ps`  -> AFTER state, real evidence
    Gated by assert_host() again - this function does not trust the caller.
    """
    assert_host(host)
    if (confirm_text or "").strip() != CONFIRM_PHRASE:
        raise TrainCoderRefused(
            f"REFUSED: type the exact phrase {CONFIRM_PHRASE!r} to confirm - this "
            "stops a training run Iddo declared permanent. A click alone is not enough."
        )

    plan = plan_to_coder(model=model, host=host)
    if not plan.get("fits"):
        log_flip({"actor": actor, "direction": "to_coder", "host": host, "model": model,
                  "result": "REFUSED", "reasons": plan.get("reasons"), "plan": plan})
        raise TrainCoderRefused("REFUSED at apply time: " +
                                "; ".join(plan.get("reasons") or ["does not fit"]))

    picked = plan["model"]
    before_train = training_unit_state(host)
    before_prog = training_progress(host)
    before_ps = ox.ollama_ps(host)
    started = time.time()

    stop_result = None
    if plan.get("will_stop_training"):
        rc, out, err = fm._ssh(host, ["systemctl", "--user", "stop", TRAIN_UNIT], timeout=3900)
        stop_result = {"rc": rc, "ok": rc == 0, "stderr": (err or out or "").strip()[:400]}

    stopped_ollama = []
    for name in plan.get("will_stop_ollama", []):
        rc, out, err = fm._ssh(host, ["ollama", "stop", name], timeout=30)
        stopped_ollama.append({"name": name, "rc": rc, "ok": rc == 0,
                               "stderr": (err or out or "").strip()[:300]})

    rc, out, err = fm._ssh(host, ["ollama", "run", picked, prompt], timeout=180)
    ran_ok = (rc == 0)
    generation = (out or "").strip()

    time.sleep(1.5)
    after_train = training_unit_state(host)
    after_ps = ox.ollama_ps(host)

    elapsed = round(time.time() - started, 1)
    after_names = {m["name"] for m in after_ps.get("loaded", [])} if after_ps.get("ok") else set()
    training_really_stopped = (
        (after_train.get("active_state") != "active") if plan.get("will_stop_training") else True
    )
    verified = ran_ok and (picked in after_names) and training_really_stopped

    rec = {
        "actor": actor, "direction": "to_coder", "host": host, "model": picked,
        "result": "OK" if verified else "FAIL", "elapsed_s": elapsed,
        "stop_training_result": stop_result, "stopped_ollama": stopped_ollama,
        "run_rc": rc, "run_ok": ran_ok,
        "run_stderr": (err or "").strip()[:400] if not ran_ok else "",
        "generation": generation[:800],
        "before_training_state": before_train, "after_training_state": after_train,
        "before_progress": before_prog,
        "before_ps": before_ps, "after_ps": after_ps,
        "verified_loaded": picked in after_names,
        "verified_training_stopped": training_really_stopped,
        "verified": verified,
        "plan": plan,
    }
    log_flip(rec)
    return rec


# --------------------------------------------------------------------------
# Apply: ONBOARD CODER -> TRAINING (the safe / reverse direction)
# --------------------------------------------------------------------------

def apply_to_training(actor: str, host: str = TRAIN_HOST) -> dict[str, Any]:
    assert_host(host)
    plan = plan_to_training(host=host)
    if not plan.get("will_start_training"):
        log_flip({"actor": actor, "direction": "to_training", "host": host,
                  "result": "NOOP", "reasons": plan.get("reasons"), "plan": plan})
        return {"result": "NOOP", "reasons": plan.get("reasons"), "plan": plan}

    before_train = training_unit_state(host)
    before_ps = ox.ollama_ps(host)
    started = time.time()

    stopped_ollama = []
    for name in plan.get("will_stop_ollama", []):
        rc, out, err = fm._ssh(host, ["ollama", "stop", name], timeout=30)
        stopped_ollama.append({"name": name, "rc": rc, "ok": rc == 0,
                               "stderr": (err or out or "").strip()[:300]})

    rc, out, err = fm._ssh(host, ["systemctl", "--user", "start", TRAIN_UNIT], timeout=60)
    start_ok = (rc == 0)

    time.sleep(3.0)
    after_train = training_unit_state(host)
    verified = start_ok and (after_train.get("active_state") == "active")

    rec = {
        "actor": actor, "direction": "to_training", "host": host,
        "result": "OK" if verified else "FAIL",
        "elapsed_s": round(time.time() - started, 1),
        "stopped_ollama": stopped_ollama, "start_rc": rc,
        "start_stderr": (err or out or "").strip()[:400],
        "before_training_state": before_train, "after_training_state": after_train,
        "before_ps": before_ps, "verified_active": verified, "plan": plan,
    }
    log_flip(rec)
    return rec


# --------------------------------------------------------------------------
# CLI - works with no Claude, no API key, no MCP (same shape as fleet_mode.py)
# --------------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    import argparse
    import sys as _sys
    ap = argparse.ArgumentParser(prog="train_vs_coder",
                                 description="Flip eran3 between TRAINING and ONBOARD CODER.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("plan-to-coder"); p.add_argument("--model", default=None)
    sub.add_parser("plan-to-training")
    p = sub.add_parser("apply-to-coder")
    p.add_argument("--model", default=None)
    p.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("apply-to-training"); p.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(read_state(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "plan-to-coder":
        print(json.dumps(plan_to_coder(model=args.model), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "plan-to-training":
        print(json.dumps(plan_to_training(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "apply-to-coder":
        if not args.yes:
            print(json.dumps(plan_to_coder(model=args.model), ensure_ascii=False, indent=2))
            print("\n-- dry run. add --yes AND --confirm 'STOP TRAINING' to execute. --")
            return 0
        try:
            out = apply_to_coder("cli", model=args.model, confirm_text=args.confirm)
        except TrainCoderRefused as exc:
            print(f"REFUSED: {exc}", file=_sys.stderr)
            return 3
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("result") == "OK" else 1
    if args.cmd == "apply-to-training":
        if not args.yes:
            print(json.dumps(plan_to_training(), ensure_ascii=False, indent=2))
            print("\n-- dry run. add --yes to execute. --")
            return 0
        try:
            out = apply_to_training("cli")
        except TrainCoderRefused as exc:
            print(f"REFUSED: {exc}", file=_sys.stderr)
            return 3
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("result") in ("OK", "NOOP") else 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
