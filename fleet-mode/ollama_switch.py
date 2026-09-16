#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OLLAMA MODEL SWITCH - the verb FLEET MODE deliberately left out.

Iddo, 2026-09-07 18:05: "סיים את הדשבורד שדיברנו עליו כך שאני מחליף בקלות"
(finish the dashboard we talked about, so I can switch easily)

fleet_mode.py / modes.json already say, in modes.json's own comment block:
    "OLLAMA IS NOT LISTED HERE ON PURPOSE ... this program only ever runs
     systemctl --user ... no mode needs an opinion about it."
That was correct for systemd MODES (training/code/film) - ollama.service is
system-scope and always on. But it left a real gap: nothing lets Iddo see or
change WHICH MODEL is resident in a box's unified RAM, and each DGX Spark has
only ~121 GB of it shared between everything running there. This module is
that missing verb, added beside fleet_mode.py, not instead of it.

HARD RULE, enforced in two places on purpose (same pattern as
fleet_mode.assert_actionable):
    eran1 is ERAN himself. This module may DISPLAY eran1's ollama state (an
    honest read changes nothing) but NEVER issues `ollama stop` / `ollama run`
    there. assert_switchable() is called at PLAN time and again at EXECUTE
    time, so a hand-built call still cannot reach eran1.

Every remote action is:  ssh <host> ollama <verb> <validated-token> ...
Model names are checked against a strict pattern AND against that host's own
`ollama list` before anything is stopped or run - there is no path that pulls
an arbitrary string as a model.

Read functions never write anything and are safe to call as often as the
dashboard likes; `ollama_ps`/`ollama_list`/`mem_info` are plain SSH+parse.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import fleet_mode as fm  # reuses _ssh (argv list, shell=False, BatchMode ssh)

HOSTS: tuple[str, ...] = ("eran1", "eran2", "eran3", "eran4")

# eran1 is ERAN. Read-only forever. Nothing below may add it to this tuple.
SWITCHABLE_HOSTS: tuple[str, ...] = ("eran2", "eran3", "eran4")

OLLAMA_PORT = 11434

# A model name is a strict token - the same discipline fleet_mode.py applies
# to unit names. Ollama tags look like "qwen3.5:122b" or
# "MichelRosselli/GLM-4.5-Air:Q3_K_M" - letters, digits, . : _ - / are enough.
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Extra headroom demanded ON TOP of the model's own on-disk size before a
# switch is allowed. ollama's runtime footprint is not identical to the gguf
# size on disk (KV cache, context buffers), and other processes on the box
# keep moving while the switch is in flight. Refuse close calls, don't gamble.
SAFETY_MARGIN_GB = 4.0

STATE_DIR = Path(__file__).resolve().parent / "state"
SWITCH_LOG = STATE_DIR / "ollama_switch.jsonl"


class SwitchRefused(Exception):
    """Raised when a switch (or even naming eran1 as a target) is refused."""


def assert_switchable(host: str) -> None:
    """The point-of-execution gate. Called at plan time AND at apply time.

    Mirrors fleet_mode.assert_actionable(): re-derived from nothing but the
    host string, so a caller that hand-builds a plan dict still cannot use
    this to touch eran1.
    """
    h = (host or "").strip()
    if not _HOST_RE.match(h):
        raise SwitchRefused(f"REFUSED: bad host token {host!r}")
    if h == "eran1":
        raise SwitchRefused(
            "REFUSED: eran1 is ERAN himself - a living organism, not a model "
            "slot. This dashboard will show eran1's ollama state but will "
            "never load or stop a model there. No flag overrides this."
        )
    if h not in SWITCHABLE_HOSTS:
        raise SwitchRefused(f"REFUSED: {h!r} is not a switchable host "
                            f"(only {SWITCHABLE_HOSTS})")


def _valid_model(name: str) -> bool:
    return bool(_MODEL_RE.match((name or "").strip()))


# --------------------------------------------------------------------------
# Parsing ollama's own table output - no JSON-over-ssh quoting to get wrong.
# --------------------------------------------------------------------------

def _split_cols(line: str) -> list[str]:
    return [c for c in re.split(r"\s{2,}", line.rstrip()) if c != ""]


def _size_to_gb(size_str: str) -> float | None:
    """'53 GB' / '7.6 GB' / '128 MB' -> float GB. None if unparsable."""
    m = re.match(r"^([\d.]+)\s*([KMGT]?B)$", (size_str or "").strip(), re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    mult = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}.get(unit)
    if mult is None:
        return None
    return (val * mult) / (1024**3)


def ollama_list(host: str, timeout: int = 25) -> dict[str, Any]:
    """`ollama list` on HOST -> {ok, error, models:[{name,id,size_str,size_gb,modified}]}."""
    rc, out, err = fm._ssh(host, ["ollama", "list"], timeout=timeout)
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400], "models": []}
    lines = [ln for ln in out.splitlines() if ln.strip()]
    models: list[dict[str, Any]] = []
    for ln in lines[1:]:  # skip header "NAME ID SIZE MODIFIED"
        cols = _split_cols(ln)
        if len(cols) < 3:
            continue
        name, mid, size_str = cols[0], cols[1], cols[2]
        modified = cols[3] if len(cols) > 3 else ""
        models.append({
            "name": name, "id": mid, "size_str": size_str,
            "size_gb": _size_to_gb(size_str), "modified": modified,
        })
    return {"ok": True, "error": None, "models": models}


def ollama_ps(host: str, timeout: int = 20) -> dict[str, Any]:
    """`ollama ps` on HOST -> {ok, error, loaded:[{name,id,size_gb,processor,context,until}]}."""
    rc, out, err = fm._ssh(host, ["ollama", "ps"], timeout=timeout)
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400], "loaded": []}
    lines = [ln for ln in out.splitlines() if ln.strip()]
    loaded: list[dict[str, Any]] = []
    for ln in lines[1:]:  # skip header "NAME ID SIZE PROCESSOR CONTEXT UNTIL"
        cols = _split_cols(ln)
        if len(cols) < 3:
            continue
        name, mid, size_str = cols[0], cols[1], cols[2]
        processor = cols[3] if len(cols) > 3 else ""
        context = cols[4] if len(cols) > 4 else ""
        until = cols[5] if len(cols) > 5 else (cols[4] if len(cols) == 5 else "")
        loaded.append({
            "name": name, "id": mid, "size_str": size_str,
            "size_gb": _size_to_gb(size_str), "processor": processor,
            "context": context, "until": until,
        })
    return {"ok": True, "error": None, "loaded": loaded}


def mem_info(host: str, timeout: int = 15) -> dict[str, Any]:
    """`free -b` on HOST -> GB total/used/free/available. Bytes parsed, not trusted eyeballed."""
    rc, out, err = fm._ssh(host, ["free", "-b"], timeout=timeout)
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400]}
    for ln in out.splitlines():
        if ln.strip().lower().startswith("mem:"):
            parts = ln.split()
            # Mem: total used free shared buff/cache available
            if len(parts) >= 7:
                total, used, free_, shared, buffcache, avail = (int(x) for x in parts[1:7])
                g = 1024.0 ** 3
                return {
                    "ok": True, "error": None,
                    "total_gb": round(total / g, 1),
                    "used_gb": round(used / g, 1),
                    "free_gb": round(free_ / g, 1),
                    "available_gb": round(avail / g, 1),
                }
    return {"ok": False, "error": "could not parse `free -b` output"}


def disk_info(host: str, path: str = "/", timeout: int = 15) -> dict[str, Any]:
    rc, out, err = fm._ssh(host, ["df", "-B1", path], timeout=timeout)
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400]}
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) >= 2:
        cols = lines[-1].split()
        if len(cols) >= 4:
            try:
                total_b, used_b, avail_b = int(cols[1]), int(cols[2]), int(cols[3])
                g = 1024.0 ** 3
                return {"ok": True, "error": None,
                        "total_gb": round(total_b / g, 1),
                        "used_gb": round(used_b / g, 1),
                        "free_gb": round(avail_b / g, 1)}
            except ValueError:
                pass
    return {"ok": False, "error": "could not parse `df` output"}


def door_status(host: str, ports: tuple[int, ...], timeout: int = 8) -> dict[int, bool]:
    """Loopback curl on HOST for each port - True only on a real HTTP response.

    One ssh round-trip per port, on purpose: ssh does not shell-quote the argv
    it joins for the remote command, so a single combined `sh -c "...; ...; "`
    call silently mangles anything with `{}`/`;`/quotes in it (measured
    2026-09-07 - curl's own `-w '%{http_code}'` came back as the mangled
    literal '%http_code', a false DOWN for a door that was actually up). A
    bare `curl -s -o /dev/null <url>` has no characters ssh's word-splitting
    can break, and curl's own exit code (0 = got a response, 7 = could not
    connect) is exactly the signal needed - no output parsing required.
    """
    result: dict[int, bool] = {}
    for p in ports:
        rc, _out, _err = fm._ssh(
            host, ["curl", "-s", "-o", "/dev/null", "-m", "3", f"http://127.0.0.1:{p}/"],
            timeout=timeout,
        )
        result[p] = (rc == 0)
    return result


# eran4's coder doors are `tailscale serve` TLS listeners (8447-8450) owned by
# tailscaled itself, proxying to plain-HTTP backends bound to loopback only
# (measured 2026-09-07 by claude-cli-eran4coder, see
# D:\CLAUDE\_deliverables\fleet-20260907\eran4-coder-colibri.md). A loopback
# curl on 8447-8450 gets connection-refused (tailscaled doesn't bind loopback
# there) and would falsely read as "down" - so this dashboard checks the real
# backend ports instead and labels them by the public door they serve.
ERAN4_DOOR_BACKENDS: dict[int, int] = {8447: 8096, 8448: 8097, 8449: 8098, 8450: 11435}


def eran4_doors() -> dict[int, bool]:
    backend_ok = door_status("eran4", tuple(ERAN4_DOOR_BACKENDS.values()))
    return {pub: backend_ok.get(backend, False)
            for pub, backend in ERAN4_DOOR_BACKENDS.items()}


def build_box(host: str) -> dict[str, Any]:
    """Everything the dashboard shows for one box. Read-only, honest about failure."""
    mem = mem_info(host)
    if not mem.get("ok"):
        return {"host": host, "reachable": False, "error": mem.get("error"),
                "switchable": host in SWITCHABLE_HOSTS}
    disk = disk_info(host)
    lst = ollama_list(host)
    ps = ollama_ps(host)
    box = {
        "host": host,
        "reachable": True,
        "switchable": host in SWITCHABLE_HOSTS,
        "mem": mem,
        "disk": disk if disk.get("ok") else None,
        "catalog_ok": lst.get("ok"),
        "catalog_error": lst.get("error"),
        "catalog": lst.get("models", []),
        "loaded_ok": ps.get("ok"),
        "loaded_error": ps.get("error"),
        "loaded": ps.get("loaded", []),
    }
    if host == "eran4":
        try:
            box["doors"] = eran4_doors()
        except Exception as exc:  # noqa: BLE001 - a door check must never blank the box
            box["doors_error"] = f"{type(exc).__name__}: {exc}"
    return box


def fleet_status(hosts: tuple[str, ...] = HOSTS) -> dict[str, dict[str, Any]]:
    """One box's worth of ssh calls does not block another's - each box is
    independent I/O, and sequentially this was measured at ~20s for 4 boxes
    (2026-09-07), which is a real wait on a page Iddo re-opens often.
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(hosts) or 1) as ex:
        results = list(ex.map(build_box, hosts))
    return dict(zip(hosts, results))


# --------------------------------------------------------------------------
# Plan / apply - same two-step, confirm-then-act shape as fleet_mode.py
# --------------------------------------------------------------------------

def plan_switch(host: str, model: str) -> dict[str, Any]:
    """Compute the arithmetic and either allow or refuse. Never guesses - if a
    read fails, the plan says so and refuses; it does not assume the RAM is free.
    """
    result: dict[str, Any] = {"host": host, "model": model, "fits": False,
                              "will_stop": [], "reasons": []}
    try:
        assert_switchable(host)
    except SwitchRefused as exc:
        result["reasons"].append(str(exc))
        return result

    if not _valid_model(model):
        result["reasons"].append(f"REFUSED: {model!r} is not a valid ollama tag token")
        return result

    lst = ollama_list(host)
    if not lst.get("ok"):
        result["reasons"].append(f"REFUSED: could not read {host}'s model catalog - "
                                 f"{lst.get('error')}")
        return result
    catalog = {m["name"]: m for m in lst["models"]}
    if model not in catalog:
        result["reasons"].append(
            f"REFUSED: {model!r} is not in {host}'s own `ollama list` - "
            "this dashboard only switches to a model that already exists on "
            "that box, it never pulls one."
        )
        return result
    target = catalog[model]
    target_gb = target.get("size_gb")
    if target_gb is None:
        result["reasons"].append(f"REFUSED: could not parse the size of {model!r} "
                                 f"({target.get('size_str')!r})")
        return result

    mem = mem_info(host)
    if not mem.get("ok"):
        result["reasons"].append(f"REFUSED: could not read {host}'s free RAM - "
                                 f"{mem.get('error')}")
        return result

    ps = ollama_ps(host)
    if not ps.get("ok"):
        result["reasons"].append(f"REFUSED: could not read {host}'s currently-loaded "
                                 f"models - {ps.get('error')}")
        return result
    loaded = ps["loaded"]

    already = [m for m in loaded if m["name"] == model]
    if already and len(loaded) == 1:
        result["reasons"].append(f"{model!r} is already the only model loaded on {host} - "
                                 "nothing to switch.")
        result["already_loaded"] = True
        return result

    freed_gb = sum((m.get("size_gb") or 0.0) for m in loaded)
    available_gb = mem["available_gb"]
    projected_gb = available_gb + freed_gb
    needed_gb = target_gb + SAFETY_MARGIN_GB
    fits = projected_gb >= needed_gb

    result.update({
        "will_stop": [m["name"] for m in loaded],
        "target_size_gb": round(target_gb, 1),
        "available_gb": available_gb,
        "freed_by_stopping_gb": round(freed_gb, 1),
        "projected_available_gb": round(projected_gb, 1),
        "safety_margin_gb": SAFETY_MARGIN_GB,
        "needed_gb": round(needed_gb, 1),
        "fits": fits,
        "arithmetic": (
            f"{host}: available now {available_gb:.1f} GB + freed by stopping "
            f"{', '.join(m['name'] for m in loaded) or '(nothing loaded)'} "
            f"({freed_gb:.1f} GB) = {projected_gb:.1f} GB projected. "
            f"{model} needs {target_gb:.1f} GB + {SAFETY_MARGIN_GB:.0f} GB safety "
            f"margin = {needed_gb:.1f} GB. "
            + ("FITS." if fits else "DOES NOT FIT - refused.")
        ),
    })
    if not fits:
        result["reasons"].append("REFUSED: does not fit in projected free RAM - see arithmetic.")
    return result


def log_switch(record: dict[str, Any]) -> None:
    record = dict(record)
    record.setdefault("ts", time.time())
    record.setdefault("ts_iso", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with SWITCH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(__import__("json").dumps(record, ensure_ascii=False) + "\n")


def apply_switch(host: str, model: str, actor: str,
                 prompt: str = "Reply with one short sentence confirming you are alive, "
                                "in English then Hebrew.") -> dict[str, Any]:
    """Re-derives the plan from scratch (never trusts a stale plan dict), then:
      1. `ollama ps`  -> BEFORE state, real evidence
      2. `ollama stop <name>` for every currently loaded model on host
      3. `ollama run <model> "<prompt>"` -> a REAL generation, not a health check
      4. `ollama ps`  -> AFTER state, real evidence
    Every step is gated by assert_switchable() again - this function does not
    trust that whoever called it already checked.
    """
    assert_switchable(host)  # raises SwitchRefused - not caught here on purpose
    plan = plan_switch(host, model)
    if not plan.get("fits"):
        log_switch({"actor": actor, "host": host, "model": model, "result": "REFUSED",
                    "reasons": plan.get("reasons"), "plan": plan})
        raise SwitchRefused("REFUSED at apply time: " + "; ".join(plan.get("reasons") or
                            ["does not fit"]))

    before = ollama_ps(host)
    started = time.time()

    stopped: list[dict[str, Any]] = []
    for name in plan["will_stop"]:
        rc, out, err = fm._ssh(host, ["ollama", "stop", name], timeout=30)
        stopped.append({"name": name, "rc": rc, "ok": rc == 0,
                        "stderr": (err or out or "").strip()[:300]})

    rc, out, err = fm._ssh(host, ["ollama", "run", model, prompt], timeout=180)
    ran_ok = (rc == 0)
    generation = (out or "").strip()

    # Give ollama a moment to settle its own /api/ps accounting before re-reading.
    time.sleep(1.5)
    after = ollama_ps(host)

    elapsed = round(time.time() - started, 1)
    after_names = {m["name"] for m in after.get("loaded", [])} if after.get("ok") else set()
    verified = ran_ok and (model in after_names)

    out_rec = {
        "host": host, "model": model, "actor": actor,
        "result": "OK" if verified else "FAIL",
        "elapsed_s": elapsed,
        "stopped": stopped,
        "run_rc": rc, "run_ok": ran_ok,
        "run_stderr": (err or "").strip()[:400] if not ran_ok else "",
        "generation": generation[:800],
        "before_ps": before,
        "after_ps": after,
        "verified_loaded": verified,
        "plan": plan,
    }
    log_switch(out_rec)
    return out_rec
