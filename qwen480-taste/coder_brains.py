# -*- coding: utf-8 -*-
"""coder_brains.py — the ONE place ALMAWARE Coder's brains are defined.

Iddo, 2026-09-15 02:47: "fix the ALMIDO harness so it has ALL the models —
built-in QUORUM and chat online — me with all the models together with you
(Claude) and Muse and everyone." This file is the single source of truth for
what a "brain" (a door-based model the harness can talk to) is — the model id,
the door URL, the Hebrew identity facts, the cost, and whether it is loaded on
demand. coder_desktop.py, coder_identity.py, coder_quorum.py and coder_room.py
all read this file instead of keeping their own private copy (FIVE LAWS #1,
2026-09-14: "one source of truth beats a fresher private copy, always").

Claude and Muse are NOT brains here. They are addressed separately by
coder_room.py (ask_claude / ask_muse) because Claude is paid (MONEY LAW: only
answers when Iddo explicitly selects it, marked with the money emoji in the
UI) and Muse is routed through the RAMCHAT queue, not an HTTP door.

ADDRESSES: fleet_inventory.json DOES track these doors, port included
(eran4_ollama, eran2_gptoss, eran1_router), so each brain's door base
(scheme://host:port) is read from fleet_inventory.door(<name>) and only the
OpenAI path /v1/chat/completions is appended here. Each door is resolved ONCE
into a module constant below (the eran1 router is one constant shared by the
three NVIDIA brains). The literal base is kept only as the fallback for when
fleet_inventory is missing or does not know the door (fix 2026-09-15, review
finding: the first cut copied the ports privately).

PC-LOCAL LAW: the small ollama brain on Iddo's own PC is PC_LOCAL_BRAIN, and it
joins BRAINS when PC_LOCAL_ALLOWED is True. Iddo amended "NO LOCAL MODELS ON THE
PC" on 2026-09-15 02:54-02:55 (D:/CLAUDE/CLAUDE.md "MODELS ON THE PC"): models
on the PC are allowed on demand, never choking it, and he asked for "a nice
onboard coder". So the constant is True. Turn it off only on his word.

Keep this file boring and side-effect-free at import time: no network calls,
no writes, and every fleet_inventory lookup is wrapped so a stale or missing
inventory file never raises — it just falls back to the literal.

No Maverick anywhere (retired 2026-09-15, Iddo: "לא צריך אותו").

BRAIN SWITCH (Iddo 2026-09-15 10:07-10:08: "only one model runs at a time and I
choose - easily", approved "כן"): eran4 holds EITHER gpt-oss-120b OR the coder.
ensure_brain_mode() at the bottom of this file is the ONE client of eran4's
/mode API, shared by the desktop app and the tailnet twin; BrainModeGate is the
desktop's PyQt-free "may this message go out yet" logic. Network only when
called, never at import.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

APP_DIR = os.path.dirname(os.path.abspath(__file__))
_D_CLAUDE = os.path.dirname(APP_DIR)  # D:\CLAUDE\qwen480-taste -> D:\CLAUDE

_fi = None            # lazy-loaded fleet_inventory module, or False if unavailable
_fi_tried = False


def _fleet_inventory():
    """Lazy, cached, never-raising import of D:/CLAUDE/fleet_inventory.py."""
    global _fi, _fi_tried
    if _fi_tried:
        return _fi or None
    _fi_tried = True
    try:
        if _D_CLAUDE not in sys.path:
            sys.path.insert(0, _D_CLAUDE)
        import fleet_inventory as fi  # noqa: PLC0415 (deliberately lazy)
        fi.load()  # make sure the file actually parses before we trust it
        _fi = fi
    except Exception:
        _fi = False
    return _fi or None


CHAT_PATH = "/v1/chat/completions"


def _door_base(door_name: str, fallback: str) -> str:
    """scheme://host:port of fleet_inventory's named door (its path, e.g.
    /v1/models or /api/tags, is dropped), or the literal `fallback` base when
    the inventory is missing, stale, or does not know the door. Never raises.
    """
    fi = _fleet_inventory()
    if fi is not None:
        try:
            from urllib.parse import urlsplit  # noqa: PLC0415
            url = fi.door(door_name)
            parts = urlsplit(url or "")
            if parts.scheme in ("http", "https") and parts.netloc:
                return "%s://%s" % (parts.scheme, parts.netloc)
        except Exception:
            pass
    return fallback


# Each door is resolved exactly once (fleet_inventory door name -> base URL).
_CODER_DGX4 = _door_base("eran4_ollama", "https://<tailnet-host>:8450")
_GPTOSS_ERAN2 = _door_base("eran2_gptoss", "http://<tailnet-ip>:8000")
_ROUTER_ERAN1 = _door_base("eran1_router", "http://<tailnet-ip>:8010")

# Iddo RULED, 2026-09-15 02:54-02:55: "חוק אין מודלים על הפיסי תשנה - יש מודלים
# אבל לא לחנוק" and "מדי פעם בא לי קודר נחמד אונבורד" (CLAUDE.md "MODELS ON THE
# PC"). The swarm's first cut read the older 09-12 ban; this is his later word.
PC_LOCAL_ALLOWED = True


# ---------------------------------------------------------------------------
# BRAINS — the fleet-served + on-demand-local models.
#
# Fields: id, profile, model, label, human_name, where_he, door, max_tokens,
# cost ('free'|'paid'), on_demand (bool — loaded on request, not resident).
#
# max_tokens are today's values from coder_desktop.py:125-158 (2026-09-15,
# post-Maverick-removal); door bases come from fleet_inventory's named doors
# (see _door_base above).
# ---------------------------------------------------------------------------
BRAINS: list[dict] = [
    {
        "id": "qwen-coder-dgx4",
        "profile": "",
        "model": "qwen-coder-dgx4:latest",
        "label": "Qwen3-Coder-Next · eran4",
        "human_name": "Qwen3-Coder-Next",
        "where_he": (
            "79.7B בקוונטיזציית Q4_K_M, טעון קבוע על eran4, "
            "אחת מארבע קופסאות ה-DGX Spark של עידו"
        ),
        "door": _CODER_DGX4 + CHAT_PATH,
        "max_tokens": 8000,
        "cost": "free",
        "on_demand": False,
    },
    {
        "id": "gpt-oss-120b",
        "profile": "chat",
        "model": "gpt-oss-120b",
        "label": "GPT-OSS 120B · eran2",
        "human_name": "GPT-OSS 120B",
        "where_he": "MXFP4, טעון קבוע על eran2",
        "door": _GPTOSS_ERAN2 + CHAT_PATH,
        "max_tokens": 4000,
        "cost": "free",
        "on_demand": False,
    },
    {
        "id": "kimi-k3",
        "profile": "nvidia",
        "model": "moonshotai/kimi-k3",
        "label": "Kimi K3 2.8T (NVIDIA cloud, free) · giant",
        "human_name": "Kimi K3",
        "where_he": (
            "2.8 טריליון פרמטרים סך הכול ו-104 מיליארד פעילים, "
            "מוגש בחינם דרך NVIDIA NIM"
        ),
        "door": _ROUTER_ERAN1 + CHAT_PATH,
        "max_tokens": 1500,
        "cost": "free",
        "on_demand": False,
    },
    {
        "id": "nemotron-3-super",
        "profile": "nemotron",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "label": "Nemotron-3-Super 120B (NVIDIA cloud, free)",
        "human_name": "Nemotron-3-Super",
        "where_he": (
            "120 מיליארד פרמטרים, 12 מיליארד פעילים (MoE), "
            "מוגש בחינם דרך NVIDIA NIM"
        ),
        "door": _ROUTER_ERAN1 + CHAT_PATH,
        "max_tokens": 1500,
        "cost": "free",
        "on_demand": False,
    },
    {
        "id": "glm-5.3-flash",
        "profile": "glm",
        "model": "z-ai/glm-5.3-flash",
        "label": "GLM-5.3-Flash (NVIDIA cloud, free)",
        "human_name": "GLM-5.3-Flash",
        "where_he": "מוגש בחינם דרך NVIDIA NIM",
        "door": _ROUTER_ERAN1 + CHAT_PATH,
        "max_tokens": 1000,
        "cost": "free",
        "on_demand": False,
    },
]

# The small local brain on Iddo's PC. It joins BRAINS while PC_LOCAL_ALLOWED is
# True (Iddo amended the PC-models law 2026-09-15 02:54 -- see the module
# docstring). Loopback only, so there is no address to drift.
PC_LOCAL_BRAIN: dict = {
    "id": "pc-local",
    "profile": "pc",
    "model": "qwen2.5-coder:7b",
    "label": "Qwen2.5-Coder 7B · המחשב של עידו (מקומי, קטן)",
    "human_name": "Qwen2.5-Coder 7B",
    "where_he": (
        "מודל קטן, רץ מקומית על המחשב של עידו דרך ollama; "
        "עולה רק לפי דרישה (on-demand), לא טעון כברירת מחדל"
    ),
    "door": "http://127.0.0.1:11434" + CHAT_PATH,
    "max_tokens": 2000,
    "cost": "free",
    "on_demand": True,
}
if PC_LOCAL_ALLOWED:
    BRAINS.append(dict(PC_LOCAL_BRAIN))


def all_brains() -> list[dict]:
    """A fresh copy of every known brain (callers may not mutate the shared list)."""
    return [dict(b) for b in BRAINS]


def by_model(model: str) -> dict | None:
    """The brain record whose 'model' field matches, or None."""
    for b in BRAINS:
        if b.get("model") == model:
            return dict(b)
    return None


def by_id(brain_id: str) -> dict | None:
    """The brain record whose 'id' field matches, or None."""
    for b in BRAINS:
        if b.get("id") == brain_id:
            return dict(b)
    return None


def model_label(model: str) -> str:
    """Display label for a model id, or the raw id itself if unknown."""
    b = by_model(model)
    if b:
        return b["label"]
    return model or "model"


def brain_facts(model: str) -> tuple[str, str]:
    """(human_name, where_he) for a model id — the pair coder_identity.py's
    identity_line() puts in front of the brain every turn. Unknown models fall
    back to the raw id as the name and a generic "served from the door below",
    matching the fallback identity_line() has always used.
    """
    b = by_model(model)
    if b:
        return (b["human_name"], b["where_he"])
    return (model, "מוגש מהדלת שלמטה")


# ---------------------------------------------------------------------------
# BRAIN SWITCH -- eran4 runs ONE model at a time, Iddo picks it in the Brain menu.
#
# The contract (built on eran4 in parallel by the eran4 builder, 2026-09-15):
#   GET  <door>/mode        -> 200 {"mode": "chat"|"coder", "state": "ready"|"switching"|"error",
#                                   "detail": str, "since": ISO8601, "target": "chat"|"coder"|null}
#   POST <door>/mode/coder  -> 202 {"state":"switching","target":...} a switch started
#   POST <door>/mode/chat   -> 200 <GET body> already in that mode and ready
#                              409 {"state":"switching","target":...} a different switch runs
#   A full switch finishes within 240 s or ends in state=error with eran4 back in CHAT.
#   A chat request for the coder while mode != coder gets a fast 503 "coder asleep ...".
#
# The door is the eran4 coder door that BRAINS already uses (_CODER_DGX4, read from
# fleet_inventory) -- no second copy of the address. Tailnet-only, no token.
# ---------------------------------------------------------------------------

SWITCH_DOOR_BASE = _CODER_DGX4
MODE_SWITCH_TIMEOUT_S = 240.0     # the contract's own limit for a full switch
MODE_POLL_GRACE_S = 15.0          # listen a little past 240 s to hear eran4's own error verdict
MODE_POLL_S = 3.0
MODE_HTTP_TIMEOUT_S = 6.0         # same budget as coder_engine.door_status
MODE_MAX_GET_FAILURES = 3         # consecutive failed polls before "unreachable"
READY_TTL_S = 300.0               # a confirmed-ready coder is re-checked after this long idle

TEXT_LOADING = "טוען את הקודר על eran4... (~דקה) · Loading the coder on eran4... (~1 min)"
TEXT_READY = "הקודר מוכן על eran4 ✓ · the coder is ready on eran4"
TEXT_NO_SWITCH = ("אין עדיין מתג /mode ב-eran4 — שולח לקודר ישירות · "
                  "eran4 has no /mode switch yet — sending to the coder directly")
TEXT_RELEASING = ("משחרר את הקודר ב-eran4 ברקע (חוזר לצ'אט) · "
                  "releasing the coder on eran4 in the background (back to chat)")
TEXT_ALREADY_CHAT = "eran4 כבר במצב צ'אט · eran4 is already in chat mode"
TEXT_SUPERSEDED = "בחירת מוח חדשה יותר החליפה את הטעינה · a newer brain choice replaced this load"
TEXT_STOPPED = "ההמתנה לקודר נעצרה · the wait for the coder was stopped"
TEXT_BAD_BRAIN = "למוח הזה אין דלת תקינה · this brain has no valid door"


def _t_loading(elapsed: float | None = None) -> str:
    if elapsed is not None and elapsed >= 1:
        return "%s · %ds" % (TEXT_LOADING, int(elapsed))
    return TEXT_LOADING


def _t_busy(other) -> str:
    other = other or "?"
    return ("eran4 באמצע החלפה אחרת (אל %s) — מחכה שתיגמר · "
            "eran4 is in the middle of another switch (to %s) — waiting for it to end"
            % (other, other))


def _t_error(detail: str, mode) -> str:
    detail = detail or "?"
    mode = mode or "?"
    return ("ההחלפה לקודר נכשלה: %s — eran4 במצב %s · "
            "the switch to the coder failed: %s — eran4 is in %s mode" % (detail, mode, detail, mode))


def _t_timeout(secs: float) -> str:
    return ("הקודר לא עלה תוך %g שניות — eran4 אמור לחזור לצ'אט לבד · "
            "the coder did not come up within %g s — eran4 should fall back to chat by itself"
            % (secs, secs))


def _t_unreachable(why: str) -> str:
    why = why or "?"
    return ("הדלת של eran4 לא עונה (%s) — אי אפשר להעיר את הקודר עכשיו · "
            "eran4's door does not answer (%s) — cannot wake the coder right now" % (why, why))


def door_base(url) -> str:
    """scheme://host:port of a door URL (host lower-cased), or '' for garbage. Never raises."""
    try:
        p = urlsplit(str(url or ""))
        if p.scheme in ("http", "https") and p.netloc:
            return "%s://%s" % (p.scheme, p.netloc.lower())
    except Exception:
        pass
    return ""


def is_switch_door(door, switch_base=None) -> bool:
    """True when `door` is served through eran4's switchable door. `switch_base`
    defaults to SWITCH_DOOR_BASE, read at call time (never frozen at import)."""
    base = door_base(door)
    sw = door_base(SWITCH_DOOR_BASE if switch_base is None else switch_base)
    return bool(base) and base == sw


def _mode_request(method: str, url: str, timeout: float):
    """-> (http_code, json_dict_or_None, note). http_code 0 = transport failure and
    note is the error; for any other code note is the start of a non-JSON body.
    Never raises."""
    try:
        req = urllib.request.Request(
            url, data=(b"{}" if method == "POST" else None), method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = int(getattr(r, "status", 200) or 200)
            raw = r.read(65536)
    except urllib.error.HTTPError as e:
        code = int(e.code or 0)
        try:
            raw = e.read(65536)
        except Exception:
            raw = b""
        try:
            e.close()
        except Exception:
            pass
    except Exception as e:
        return 0, None, "%s: %s" % (type(e).__name__, e)
    text = (raw or b"").decode("utf-8", "replace")
    try:
        body = json.loads(text) if text.strip() else None
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return code, None, text.strip()[:160]
    return code, body, ""


def get_mode(base: str, timeout: float = MODE_HTTP_TIMEOUT_S):
    return _mode_request("GET", door_base(base) + "/mode", timeout)


def post_mode(base: str, target: str, timeout: float = MODE_HTTP_TIMEOUT_S):
    return _mode_request("POST", door_base(base) + "/mode/" + target, timeout)


# "The last choice wins": every ensure_brain_mode() call takes a new intent number;
# a wake still polling, or a release about to POST, gives up once a newer choice exists.
_intent_lock = threading.Lock()
_intent_seq = 0


def _new_intent() -> int:
    global _intent_seq
    with _intent_lock:
        _intent_seq += 1
        return _intent_seq


def _superseded(seq: int) -> bool:
    return seq != _intent_seq


def _result(ok, state, text, brain, target, mode=None, detail="") -> dict:
    b = brain if isinstance(brain, dict) else {}
    return {"ok": bool(ok), "state": state, "mode": mode, "target": target,
            "detail": detail or "", "text": text, "model": b.get("model")}


def _call_quietly(fn, *args) -> bool:
    if fn is None:
        return False
    try:
        return bool(fn(*args))
    except Exception:
        return False


def _nap(seconds: float, *aborts) -> None:
    """Sleep up to `seconds`, waking early (50 ms granularity) if any abort() is true."""
    t_end = time.monotonic() + max(0.0, seconds)
    while True:
        left = t_end - time.monotonic()
        if left <= 0 or any(a() for a in aborts):
            return
        time.sleep(min(0.05, left))


def _http_why(code: int, note: str) -> str:
    if code == 0:
        return note or "no connection"
    return "HTTP %d%s" % (code, (": " + note) if note else "")


def _wake(b, base, seq, on_status, wait, timeout, grace, poll_s, should_stop) -> dict:
    target = "coder"
    t0 = time.monotonic()
    deadline = t0 + max(0.0, float(timeout)) + max(0.0, float(grace))

    def say(text):
        _call_quietly(on_status, text)

    def stopped():
        return _call_quietly(should_stop)

    def ask():
        """POST /mode/coder -> (kind, why, body); kind in ready|switching|busy|no-switch|unreachable."""
        code, body, note = post_mode(base, target)
        if code in (404, 405, 501):
            return "no-switch", "", body
        if code == 0 or code >= 500 or code in (400, 401, 403):
            return "unreachable", _http_why(code, note), body
        if code == 409:
            return "busy", "", body
        if code == 200 and body and body.get("mode") == target and body.get("state") == "ready":
            return "ready", "", body
        if code in (200, 202):
            return "switching", "", body
        return "unreachable", _http_why(code, note), body

    def settle(kind, why, body):
        if kind == "unreachable":
            return _result(False, "unreachable", _t_unreachable(why), b, target)
        if kind == "no-switch":
            return _result(True, "no-switch", TEXT_NO_SWITCH, b, target)
        if kind == "ready":
            return _result(True, "ready", TEXT_READY, b, target, mode=target)
        return None

    kind, why, body = ask()
    done = settle(kind, why, body)
    if done is not None:
        return done
    last_ask = kind
    text = _t_busy((body or {}).get("target")) if kind == "busy" else _t_loading()
    say(text)
    if not wait:
        return _result(False, "switching", text, b, target, mode=(body or {}).get("mode"))

    failures = 0
    while True:
        if stopped():
            return _result(False, "stopped", TEXT_STOPPED, b, target)
        if _superseded(seq):
            return _result(False, "superseded", TEXT_SUPERSEDED, b, target)
        now = time.monotonic()
        if now >= deadline:
            return _result(False, "timeout", _t_timeout(timeout), b, target)
        _nap(min(float(poll_s), deadline - now), stopped, lambda: _superseded(seq))
        if stopped() or _superseded(seq):
            continue
        code, st, note = get_mode(base)
        if code != 200 or st is None:
            failures += 1
            if failures >= MODE_MAX_GET_FAILURES:
                return _result(False, "unreachable", _t_unreachable(_http_why(code, note)), b, target)
            continue
        failures = 0
        mode, state = st.get("mode"), st.get("state")
        if state == "switching":
            if st.get("target") in (None, target):
                say(_t_loading(time.monotonic() - t0))
            else:
                say(_t_busy(st.get("target")))
            continue
        if state == "ready" and mode == target:
            return _result(True, "ready", TEXT_READY, b, target, mode=mode)
        if last_ask == "busy":
            # the OTHER switch we were refused for (409) has ended -- ask again, once per refusal
            kind, why, body = ask()
            done = settle(kind, why, body)
            if done is not None:
                return done
            last_ask = kind
            say(_t_busy((body or {}).get("target")) if kind == "busy"
                else _t_loading(time.monotonic() - t0))
            continue
        detail = st.get("detail") or ("the switch ended in %s mode" % (mode or "?"))
        return _result(False, "error", _t_error(detail, mode), b, target, mode=mode, detail=detail)


def _release(b, base, seq, timeout, grace, poll_s, should_stop) -> dict:
    """Best effort: if eran4 holds the coder, ask it back to chat. The brain Iddo
    picked is not on eran4's coder door, so every outcome here is ok=True."""
    target = "chat"
    deadline = time.monotonic() + max(0.0, float(timeout)) + max(0.0, float(grace))

    def stopped():
        return _call_quietly(should_stop)

    while True:
        if stopped():
            return _result(True, "stopped", TEXT_STOPPED, b, target)
        if _superseded(seq):
            return _result(True, "superseded", TEXT_SUPERSEDED, b, target)
        code, st, note = get_mode(base)
        if code in (404, 405, 501):
            return _result(True, "no-switch", TEXT_NO_SWITCH, b, target)
        if code != 200 or st is None:
            return _result(True, "unreachable", _t_unreachable(_http_why(code, note)), b, target)
        mode, state = st.get("mode"), st.get("state")
        if state != "switching" and mode != "coder":
            return _result(True, "idle", TEXT_ALREADY_CHAT, b, target, mode=mode)
        if state != "switching":
            if _superseded(seq):
                return _result(True, "superseded", TEXT_SUPERSEDED, b, target)
            pcode, _pbody, pnote = post_mode(base, target)
            if pcode in (200, 202):
                return _result(True, "released", TEXT_RELEASING, b, target, mode=mode)
            if pcode != 409:
                return _result(True, "unreachable", _t_unreachable(_http_why(pcode, pnote)), b, target)
        now = time.monotonic()
        if now >= deadline:
            return _result(True, "timeout", _t_timeout(timeout), b, target)
        _nap(min(float(poll_s), deadline - now), stopped, lambda: _superseded(seq))


def _release_quietly(*args) -> None:
    try:
        _release(*args)
    except Exception:
        pass


def ensure_brain_mode(brain, on_status=None, wait=True, background=True, switch_base=None,
                      timeout=MODE_SWITCH_TIMEOUT_S, grace=MODE_POLL_GRACE_S,
                      poll_s=MODE_POLL_S, should_stop=None) -> dict:
    """Make eran4 hold the model this brain needs. Never raises.

    Coder brain (its door IS eran4's switch door): POST /mode/coder, then -- when
    `wait` -- poll GET /mode until ready, reporting progress through on_status(text)
    ("טוען את הקודר על eran4... / Loading the coder on eran4..."). wait=False starts
    the switch and returns at once (the twin's phone page). Blocking: call it from a
    worker thread, never a UI thread.

    Any other brain: if eran4 holds the coder, POST /mode/chat. With `background`
    (the default) that runs on a daemon thread and this returns immediately.

    Returns {"ok", "state", "mode", "target", "detail", "text", "model"}. ok=True
    means a message to this brain may go out now. States: ready, switching, error,
    timeout, unreachable, no-switch (the door has no /mode: send directly), stopped,
    superseded (a newer choice replaced this one), releasing / released / idle
    (other brains)."""
    b = brain if isinstance(brain, dict) else {}
    try:
        base = door_base(SWITCH_DOOR_BASE if switch_base is None else switch_base)
        door = b.get("door")
        if not base or not door_base(door):
            return _result(False, "error", TEXT_BAD_BRAIN, b, None)
        seq = _new_intent()
        if is_switch_door(door, base):
            return _wake(b, base, seq, on_status, wait, timeout, grace, poll_s, should_stop)
        args = (b, base, seq, timeout, grace, poll_s, should_stop)
        if background:
            threading.Thread(target=_release_quietly, args=args, daemon=True,
                             name="brain-switch-release").start()
            return _result(True, "releasing", TEXT_RELEASING, b, "chat")
        return _release(*args)
    except Exception as e:
        return _result(False, "error", _t_error("%s: %s" % (type(e).__name__, e), None), b, None)


class BrainModeGate:
    """The desktop window's switch logic with no Qt in it (testable headless).

    on_select(brain)            -> "wake" (start a worker running ensure_brain_mode) |
                                   "release" (call ensure_brain_mode; it backgrounds itself)
    on_send(door, model, resend)-> "send" | "hold" (queue it, wake) | "hold-resend"
    on_result(door, model, r)   -> "dispatch" (send what is queued) | "retry" | "keep"
    on_turn_done / on_turn_failed keep the "ready" belief honest between checks.
    """

    def __init__(self, switch_base=None, ttl_s=READY_TTL_S, clock=time.monotonic):
        self._switch_base = switch_base
        self.ttl_s = float(ttl_s)
        self.clock = clock
        self._ready_model = None
        self._ready_at = None

    @property
    def switch_base(self) -> str:
        return door_base(SWITCH_DOOR_BASE if self._switch_base is None else self._switch_base)

    def needs_switch(self, door) -> bool:
        return is_switch_door(door, self.switch_base)

    def is_ready(self, model) -> bool:
        return (self._ready_model is not None and self._ready_model == model
                and self._ready_at is not None
                and (self.clock() - self._ready_at) < self.ttl_s)

    def mark_ready(self, model) -> None:
        self._ready_model, self._ready_at = model, self.clock()

    def invalidate(self) -> None:
        self._ready_model, self._ready_at = None, None

    def on_select(self, brain) -> str:
        if self.needs_switch((brain or {}).get("door")):
            self.invalidate()            # picking the coder always re-checks the real box
            return "wake"
        return "release"

    def on_send(self, door, model, resend=False) -> str:
        if not self.needs_switch(door) or self.is_ready(model):
            return "send"
        return "hold-resend" if resend else "hold"

    def on_result(self, door, model, result) -> str:
        r = result if isinstance(result, dict) else {}
        if not self.needs_switch(door):
            return "dispatch"            # he moved to a brain that needs no switch
        if r.get("ok") and r.get("model") == model:
            self.mark_ready(model)
            return "dispatch"
        if self.is_ready(model):
            return "dispatch"
        if r.get("state") == "superseded" or r.get("model") != model:
            return "retry"
        return "keep"

    def on_turn_done(self, door, model) -> None:
        if self.needs_switch(door):
            self.mark_ready(model)       # a real answer is the best proof it is up

    def on_turn_failed(self, door, model, message) -> bool:
        """True -> the coder was put to sleep under us: re-check (wake) it."""
        if not self.needs_switch(door):
            return False
        m = str(message or "").lower()
        if "asleep" in m or "http 503" in m or "error 503" in m:
            self.invalidate()
            return True
        return False
